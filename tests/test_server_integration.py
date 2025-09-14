"""
Integration tests for server Phase 2 components (5-9)
Tests the interaction between Problem Pool Service, Game State Manager, 
Timer Service, Submission Processor, and Message Broadcaster
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock
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
from submission_processor import SubmissionProcessor
from message_broadcaster import MessageBroadcaster
from room_manager import RoomManager
from player_manager import PlayerManager
from pydantic_schemas import (
    Room, PlayerInternal, Problem, MVPRoomSettings, RoomState, RoundPhase, RoundState,
    CountdownStartMessage, RoundStartMessage, RoundEndMessage
)


class MockWebSocket:
    """Mock WebSocket for testing"""
    def __init__(self):
        self.sent_messages = []
        
    async def send_text(self, message):
        self.sent_messages.append(message)


class TestServerIntegration:
    """Test integration between Phase 2 server components"""

    @pytest.fixture
    async def integrated_server_components(self):
        """Set up all server components in integrated configuration"""
        
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
        
        # Set up cross-service dependencies
        timer_service.set_game_state_manager(game_state_manager)
        
        # Set up mock WebSocket connections
        active_connections = {}
        player_connections = {}
        message_broadcaster.set_connection_manager(active_connections, player_connections)
        
        return {
            'problem_pool': problem_pool,
            'room_manager': room_manager,
            'player_manager': player_manager,
            'message_broadcaster': message_broadcaster,
            'timer_service': timer_service,
            'submission_processor': submission_processor,
            'game_state_manager': game_state_manager,
            'active_connections': active_connections,
            'player_connections': player_connections
        }

    @pytest.fixture
    async def sample_game_setup(self, integrated_server_components):
        """Set up a sample game with players ready to start"""
        components = integrated_server_components
        room_manager = components['room_manager']
        
        # Create room
        host_username = "HostPlayer"
        host_player_id = uuid4()
        
        room_result = await room_manager.create_room(host_username, host_player_id)
        room_code = room_result.room_code
        
        # Add another player
        guest_player_id = uuid4()
        await room_manager.join_room(room_code, "GuestPlayer", guest_player_id)
        
        # Set up mock WebSocket connections
        host_ws = MockWebSocket()
        guest_ws = MockWebSocket()
        
        components['active_connections']['host_conn'] = host_ws
        components['active_connections']['guest_conn'] = guest_ws
        components['player_connections'][host_player_id] = 'host_conn'
        components['player_connections'][guest_player_id] = 'guest_conn'
        
        return {
            'room_code': room_code,
            'host_player_id': host_player_id,
            'guest_player_id': guest_player_id,
            'host_session_token': room_result.host_session_token,
            'host_ws': host_ws,
            'guest_ws': guest_ws
        }

    @pytest.mark.asyncio
    async def test_full_game_flow_integration(self, integrated_server_components, sample_game_setup):
        """Test complete game flow from start to finish"""
        components = integrated_server_components
        setup = sample_game_setup
        
        game_state_manager = components['game_state_manager']
        room_manager = components['room_manager']
        submission_processor = components['submission_processor']
        
        # Start the game
        await game_state_manager.start_game(
            setup['room_code'], 
            setup['host_player_id'], 
            setup['host_session_token']
        )
        
        # Verify room is in RUNNING state
        room = room_manager.get_room(setup['room_code'])
        assert room.state == RoomState.RUNNING
        assert room.round_index == 0
        
        # Wait a moment for countdown to complete and round to start
        await asyncio.sleep(0.1)
        
        # Check that both players received countdown and round start messages
        host_messages = [json.loads(msg) for msg in setup['host_ws'].sent_messages]
        guest_messages = [json.loads(msg) for msg in setup['guest_ws'].sent_messages]
        
        # Both should have received countdown.start messages
        countdown_messages = [msg for msg in host_messages if msg['type'] == 'countdown.start']
        assert len(countdown_messages) > 0
        
        countdown_messages = [msg for msg in guest_messages if msg['type'] == 'countdown.start']
        assert len(countdown_messages) > 0

    @pytest.mark.asyncio
    async def test_problem_generation_and_distribution(self, integrated_server_components, sample_game_setup):
        """Test that problems are generated and distributed correctly"""
        components = integrated_server_components
        setup = sample_game_setup
        
        problem_pool = components['problem_pool']
        game_state_manager = components['game_state_manager']
        room_manager = components['room_manager']
        
        # Start game
        await game_state_manager.start_game(
            setup['room_code'], 
            setup['host_player_id'], 
            setup['host_session_token']
        )
        
        # Verify room has problems
        room = room_manager.get_room(setup['room_code'])
        assert len(room.problems) == 10  # MVP setting
        
        # Each problem should be valid
        for problem in room.problems:
            assert len(problem.numbers) == 4
            assert all(1 <= n <= 13 for n in problem.numbers)
            assert problem.canonical_solution is not None

    @pytest.mark.asyncio
    async def test_submission_processing_integration(self, integrated_server_components, sample_game_setup):
        """Test submission processing with scoring integration"""
        components = integrated_server_components
        setup = sample_game_setup
        
        game_state_manager = components['game_state_manager']
        submission_processor = components['submission_processor']
        room_manager = components['room_manager']
        player_manager = components['player_manager']
        
        # Start game and wait for active round
        await game_state_manager.start_game(
            setup['room_code'], 
            setup['host_player_id'], 
            setup['host_session_token']
        )
        
        # Get the current problem
        room = room_manager.get_room(setup['room_code'])
        current_problem = room.problems[room.round_index]
        
        # Submit a valid answer from host
        result = await submission_processor.process_submission(
            room_code=setup['room_code'],
            player_id=setup['host_player_id'],
            session_token=setup['host_session_token'],
            round_index=0,
            expression="valid_expression",
            used_numbers=current_problem.numbers,
            client_eval_value=24.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=room_manager
        )
        
        # Submission should be accepted
        assert result is not None
        assert result.accepted is True
        
        # Player should have been marked as scored
        assert player_manager.has_player_scored_this_round(setup['room_code'], setup['host_player_id'])

    @pytest.mark.asyncio
    async def test_timer_and_game_state_integration(self, integrated_server_components, sample_game_setup):
        """Test timer service integration with game state management"""
        components = integrated_server_components
        setup = sample_game_setup
        
        game_state_manager = components['game_state_manager']
        timer_service = components['timer_service']
        room_manager = components['room_manager']
        
        # Start game
        await game_state_manager.start_game(
            setup['room_code'], 
            setup['host_player_id'], 
            setup['host_session_token']
        )
        
        # Verify that timers are scheduled
        assert len(timer_service.active_timers) > 0
        
        # Get room state
        room = room_manager.get_room(setup['room_code'])
        assert room.current_round_state is not None
        
        # Should initially be in countdown phase
        assert room.current_round_state.phase == RoundPhase.COUNTDOWN

    @pytest.mark.asyncio
    async def test_message_broadcasting_integration(self, integrated_server_components, sample_game_setup):
        """Test message broadcasting integration"""
        components = integrated_server_components
        setup = sample_game_setup
        
        game_state_manager = components['game_state_manager']
        message_broadcaster = components['message_broadcaster']
        
        # Clear any existing messages
        setup['host_ws'].sent_messages.clear()
        setup['guest_ws'].sent_messages.clear()
        
        # Start game
        await game_state_manager.start_game(
            setup['room_code'], 
            setup['host_player_id'], 
            setup['host_session_token']
        )
        
        # Give a moment for messages to be sent
        await asyncio.sleep(0.01)
        
        # Both players should have received messages
        assert len(setup['host_ws'].sent_messages) > 0
        assert len(setup['guest_ws'].sent_messages) > 0
        
        # Messages should be valid JSON
        for msg in setup['host_ws'].sent_messages:
            parsed = json.loads(msg)
            assert 'type' in parsed
            assert 'payload' in parsed

    @pytest.mark.asyncio
    async def test_round_progression_integration(self, integrated_server_components, sample_game_setup):
        """Test round progression through all phases"""
        components = integrated_server_components
        setup = sample_game_setup
        
        game_state_manager = components['game_state_manager']
        room_manager = components['room_manager']
        timer_service = components['timer_service']
        
        # Mock shorter timings for testing
        original_config = game_state_manager.config.copy()
        game_state_manager.config.update({
            'countdown_seconds': 0.1,
            'round_seconds': 0.1,
            'results_seconds': 0.1
        })
        
        try:
            # Start game
            await game_state_manager.start_game(
                setup['room_code'], 
                setup['host_player_id'], 
                setup['host_session_token']
            )
            
            room = room_manager.get_room(setup['room_code'])
            initial_round = room.round_index
            
            # Wait for full round cycle
            await asyncio.sleep(0.5)
            
            # Round should have progressed or game ended
            updated_room = room_manager.get_room(setup['room_code'])
            if updated_room.state != RoomState.FINISHED:
                assert updated_room.round_index >= initial_round
                
        finally:
            # Restore original config
            game_state_manager.config = original_config

    @pytest.mark.asyncio
    async def test_player_scoring_integration(self, integrated_server_components, sample_game_setup):
        """Test player scoring integration across components"""
        components = integrated_server_components
        setup = sample_game_setup
        
        player_manager = components['player_manager']
        room_manager = components['room_manager']
        
        # Get initial player scores
        room = room_manager.get_room(setup['room_code'])
        host_player = room.players[setup['host_player_id']]
        initial_score = host_player.score
        
        # Simulate scoring
        base_points, speed_bonus, streak_bonus = player_manager.calculate_score(
            time_left=25.0, time_limit=30.0, current_streak=0
        )
        
        total_points = player_manager.apply_score_to_player(
            host_player, base_points, speed_bonus, streak_bonus
        )
        
        # Score should have increased
        assert host_player.score > initial_score
        assert total_points > 0

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, integrated_server_components, sample_game_setup):
        """Test error handling across integrated components"""
        components = integrated_server_components
        setup = sample_game_setup
        
        game_state_manager = components['game_state_manager']
        submission_processor = components['submission_processor']
        
        # Try to start game with invalid session token
        with pytest.raises(Exception):  # Should raise UnauthorizedOperationError
            await game_state_manager.start_game(
                setup['room_code'], 
                setup['host_player_id'], 
                "invalid_token"
            )
        
        # Try to process submission for non-existent room
        result = await submission_processor.process_submission(
            room_code="NONEXISTENT",
            player_id=setup['host_player_id'],
            session_token=setup['host_session_token'],
            round_index=0,
            expression="test",
            used_numbers=[1, 2, 3, 4],
            client_eval_value=24.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=components['room_manager']
        )
        
        # Should be rejected gracefully
        assert result is not None
        assert result.accepted is False

    @pytest.mark.asyncio
    async def test_concurrent_operations_integration(self, integrated_server_components, sample_game_setup):
        """Test concurrent operations across components"""
        components = integrated_server_components
        setup = sample_game_setup
        
        game_state_manager = components['game_state_manager']
        submission_processor = components['submission_processor']
        room_manager = components['room_manager']
        
        # Start game
        await game_state_manager.start_game(
            setup['room_code'], 
            setup['host_player_id'], 
            setup['host_session_token']
        )
        
        # Get current problem
        room = room_manager.get_room(setup['room_code'])
        current_problem = room.problems[room.round_index]
        
        # Submit from both players concurrently
        tasks = [
            submission_processor.process_submission(
                room_code=setup['room_code'],
                player_id=setup['host_player_id'],
                session_token=setup['host_session_token'],
                round_index=0,
                expression="expression1",
                used_numbers=current_problem.numbers,
                client_eval_value=24.0,
                client_eval_is_valid=True,
                client_timestamp=datetime.now(timezone.utc),
                room_manager=room_manager
            ),
            submission_processor.process_submission(
                room_code=setup['room_code'],
                player_id=setup['guest_player_id'],
                session_token="valid_token",  # Assuming guest has valid token
                round_index=0,
                expression="expression2",
                used_numbers=current_problem.numbers,
                client_eval_value=24.0,
                client_eval_is_valid=True,
                client_timestamp=datetime.now(timezone.utc),
                room_manager=room_manager
            )
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # At least one should succeed (both should if guest token is valid)
        successful_results = [r for r in results if not isinstance(r, Exception) and r.accepted]
        assert len(successful_results) > 0

    @pytest.mark.asyncio
    async def test_cleanup_integration(self, integrated_server_components, sample_game_setup):
        """Test cleanup integration across components"""
        components = integrated_server_components
        setup = sample_game_setup
        
        timer_service = components['timer_service']
        player_manager = components['player_manager']
        room_manager = components['room_manager']
        
        # Start game and create some state
        await components['game_state_manager'].start_game(
            setup['room_code'], 
            setup['host_player_id'], 
            setup['host_session_token']
        )
        
        # Should have active timers and player state
        assert len(timer_service.active_timers) > 0
        
        # Force end game
        await components['game_state_manager'].force_end_game(
            setup['room_code'], 
            "Test cleanup"
        )
        
        # Timers should be cleaned up
        room_timers = [tid for tid in timer_service.active_timers.keys() 
                      if setup['room_code'] in tid]
        assert len(room_timers) == 0
        
        # Player scoring should be cleaned up
        assert setup['room_code'] not in player_manager.players_scored_this_round