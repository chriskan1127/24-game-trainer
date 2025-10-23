"""
Test that round.end messages include leaderboard data
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
server_dir = os.path.join(project_root, 'server')
lib_dir = os.path.join(project_root, 'lib')
plans_dir = os.path.join(project_root, 'plans')

for path in [server_dir, lib_dir, plans_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from problem_pool_service import ProblemPoolService
from game_state_manager import GameStateManager
from timer_service import TimerService
from message_broadcaster import MessageBroadcaster
from room_manager import RoomManager
from player_manager import PlayerManager
from submission_processor import SubmissionProcessor
from pydantic_schemas import (
    RoomState, RoundPhase, RoundEndPayload
)


class MockWebSocket:
    """Mock WebSocket for testing"""
    def __init__(self):
        self.sent_messages = []

    async def send_text(self, message):
        self.sent_messages.append(message)


class TestRoundEndLeaderboard:
    """Test that leaderboard is included in round.end messages"""

    @pytest.fixture
    async def setup_game_with_players(self):
        """Set up a game with players who have scored"""
        # Initialize services
        problem_pool = ProblemPoolService()
        await problem_pool.initialize()

        room_manager = RoomManager(problem_pool)
        player_manager = PlayerManager()
        message_broadcaster = MessageBroadcaster()
        timer_service = TimerService()
        submission_processor = SubmissionProcessor(player_manager)

        game_state_manager = GameStateManager(
            room_manager, player_manager, message_broadcaster, timer_service
        )

        timer_service.set_game_state_manager(game_state_manager)

        # Set up mock WebSocket connections
        active_connections = {}
        player_connections = {}
        message_broadcaster.set_connection_manager(active_connections, player_connections)

        # Create room
        host_player_id = uuid4()
        room_result = await room_manager.create_room("Player1", host_player_id)
        room_code = room_result.room_code

        # Add second player
        guest_player_id = uuid4()
        await room_manager.join_room(room_code, "Player2", guest_player_id)

        # Set up mock WebSockets
        host_ws = MockWebSocket()
        guest_ws = MockWebSocket()

        active_connections['host_conn'] = host_ws
        active_connections['guest_conn'] = guest_ws
        player_connections[host_player_id] = 'host_conn'
        player_connections[guest_player_id] = 'guest_conn'

        return {
            'room_code': room_code,
            'host_player_id': host_player_id,
            'guest_player_id': guest_player_id,
            'host_session_token': room_result.host_session_token,
            'host_ws': host_ws,
            'guest_ws': guest_ws,
            'game_state_manager': game_state_manager,
            'room_manager': room_manager,
            'player_manager': player_manager,
            'submission_processor': submission_processor
        }

    @pytest.mark.asyncio
    async def test_round_end_includes_leaderboard(self, setup_game_with_players):
        """Test that round.end message includes leaderboard field"""
        setup = setup_game_with_players

        # Start game
        await setup['game_state_manager'].start_game(
            setup['room_code'],
            setup['host_player_id'],
            setup['host_session_token']
        )

        # Give players some scores
        room = setup['room_manager'].get_room(setup['room_code'])
        host_player = room.players[setup['host_player_id']]
        guest_player = room.players[setup['guest_player_id']]

        # Host scores 15 points
        setup['player_manager'].apply_score_to_player(host_player, 10, 5, 0)

        # Guest scores 10 points
        setup['player_manager'].apply_score_to_player(guest_player, 10, 0, 0)

        # Mark host as having scored this round
        setup['player_manager'].mark_player_scored(setup['room_code'], setup['host_player_id'])

        # Clear messages
        setup['host_ws'].sent_messages.clear()
        setup['guest_ws'].sent_messages.clear()

        # End the round
        await setup['game_state_manager'].end_round(setup['room_code'])

        # Wait for messages to be sent
        await asyncio.sleep(0.1)

        # Find round.end message in host's messages
        round_end_msg = None
        for msg_str in setup['host_ws'].sent_messages:
            msg = json.loads(msg_str)
            if msg['type'] == 'round.end':
                round_end_msg = msg
                break

        # Verify message exists
        assert round_end_msg is not None, "No round.end message found"

        # Verify leaderboard field exists
        payload = round_end_msg['payload']
        assert 'leaderboard' in payload, "Leaderboard field missing from round.end payload"

        # Verify leaderboard is not empty
        leaderboard = payload['leaderboard']
        assert len(leaderboard) > 0, "Leaderboard is empty"

        # Verify leaderboard has correct structure
        assert isinstance(leaderboard, list), "Leaderboard should be a list"
        for entry in leaderboard:
            assert 'player_id' in entry, "Leaderboard entry missing player_id"
            assert 'username' in entry, "Leaderboard entry missing username"
            assert 'score' in entry, "Leaderboard entry missing score"

        # Verify leaderboard is sorted by score (descending)
        scores = [entry['score'] for entry in leaderboard]
        assert scores == sorted(scores, reverse=True), "Leaderboard not sorted by score descending"

        # Verify host has highest score
        assert leaderboard[0]['score'] == 15, f"Host should have 15 points, got {leaderboard[0]['score']}"
        assert leaderboard[1]['score'] == 10, f"Guest should have 10 points, got {leaderboard[1]['score']}"

    @pytest.mark.asyncio
    async def test_round_end_leaderboard_starts_round_1(self, setup_game_with_players):
        """Test that leaderboard populates starting at end of Round 1, even with no scores"""
        setup = setup_game_with_players

        # Start game
        await setup['game_state_manager'].start_game(
            setup['room_code'],
            setup['host_player_id'],
            setup['host_session_token']
        )

        # Don't score any points for either player
        # Clear messages
        setup['host_ws'].sent_messages.clear()
        setup['guest_ws'].sent_messages.clear()

        # End the round (Round 1)
        await setup['game_state_manager'].end_round(setup['room_code'])

        # Wait for messages to be sent
        await asyncio.sleep(0.1)

        # Find round.end message
        round_end_msg = None
        for msg_str in setup['host_ws'].sent_messages:
            msg = json.loads(msg_str)
            if msg['type'] == 'round.end':
                round_end_msg = msg
                break

        # Verify message exists
        assert round_end_msg is not None, "No round.end message found"

        # Verify leaderboard exists even with no scores
        payload = round_end_msg['payload']
        assert 'leaderboard' in payload, "Leaderboard field missing from round.end payload"

        leaderboard = payload['leaderboard']
        assert len(leaderboard) == 2, f"Leaderboard should have 2 players, got {len(leaderboard)}"

        # Verify all players have 0 score
        for entry in leaderboard:
            assert entry['score'] == 0, f"Player should have 0 score, got {entry['score']}"

    @pytest.mark.asyncio
    async def test_round_end_payload_schema(self, setup_game_with_players):
        """Test that RoundEndPayload schema includes leaderboard field"""
        setup = setup_game_with_players

        # Start game
        await setup['game_state_manager'].start_game(
            setup['room_code'],
            setup['host_player_id'],
            setup['host_session_token']
        )

        # Clear messages
        setup['host_ws'].sent_messages.clear()

        # End the round
        await setup['game_state_manager'].end_round(setup['room_code'])

        # Wait for messages
        await asyncio.sleep(0.1)

        # Get the round.end message
        round_end_msg = None
        for msg_str in setup['host_ws'].sent_messages:
            msg = json.loads(msg_str)
            if msg['type'] == 'round.end':
                round_end_msg = msg
                break

        assert round_end_msg is not None, "No round.end message found"

        # Validate against RoundEndPayload schema
        payload_dict = round_end_msg['payload']

        # This will raise ValidationError if schema doesn't match
        validated_payload = RoundEndPayload(**payload_dict)

        # Verify leaderboard field is accessible
        assert hasattr(validated_payload, 'leaderboard'), "RoundEndPayload schema missing leaderboard field"
        assert isinstance(validated_payload.leaderboard, list), "Leaderboard should be a list"
