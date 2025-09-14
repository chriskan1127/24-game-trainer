"""
Comprehensive tests for Game State Manager component

Tests cover:
- Game start validation and authorization
- Round phase transitions (COUNTDOWN → ACTIVE → RESULTS)
- Timer management and scheduling
- Game completion and cleanup
- Error handling and recovery
- State machine validation
- Integration with other managers
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch

# Add project paths for imports
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from multiplayer_core.managers.game_state_manager import (
    GameStateManager, GameStateError, InvalidGameStateError,
    InsufficientPlayersError, UnauthorizedOperationError,
    RoundTransitionError, GamePhaseState
)
from pydantic_schemas import (
    Room, PlayerInternal, RoomState, RoundPhase, RoundState,
    Problem, MVPRoomSettings
)


class MockRoomManager:
    """Mock room manager for testing"""
    
    def __init__(self):
        self.rooms = {}
        self.session_tokens = {}
    
    def get_room(self, room_code):
        return self.rooms.get(room_code)
    
    def validate_session_token(self, room_code, player_id, session_token):
        return session_token in self.session_tokens and self.session_tokens[session_token] == player_id
    
    def is_host(self, room_code, player_id):
        room = self.get_room(room_code)
        return room and room.host_player_id == player_id
    
    def add_room(self, room_code, room):
        self.rooms[room_code] = room
    
    def add_session_token(self, token, player_id):
        self.session_tokens[token] = player_id


class MockPlayerManager:
    """Mock player manager for testing"""
    
    def __init__(self):
        self.players_scored_this_round = {}
        self.reset_calls = []
        self.cleanup_calls = []
    
    def reset_player_score(self, player):
        player.score = 0
        player.streak = 0
    
    def reset_round_scoring(self, room_code):
        self.reset_calls.append(room_code)
        self.players_scored_this_round[room_code] = set()
    
    def cleanup_room_scoring(self, room_code):
        self.cleanup_calls.append(room_code)
        if room_code in self.players_scored_this_round:
            del self.players_scored_this_round[room_code]
    
    def get_leaderboard(self, players):
        from pydantic_schemas import LeaderboardEntry
        leaderboard = []
        for player in players.values():
            entry = LeaderboardEntry(
                player_id=player.player_id,
                username=player.username,
                score=player.score
            )
            leaderboard.append(entry)
        return sorted(leaderboard, key=lambda x: x.score, reverse=True)
    
    def get_score_updates(self, players):
        from pydantic_schemas import PlayerScoreUpdate
        updates = []
        for player in players.values():
            update = PlayerScoreUpdate(
                player_id=player.player_id,
                score=player.score,
                streak=player.streak
            )
            updates.append(update)
        return updates


class MockMessageBroadcaster:
    """Mock message broadcaster for testing"""
    
    def __init__(self):
        self.messages = []
    
    async def broadcast_to_room(self, room_code, message, room_manager):
        self.messages.append((room_code, message.type, message.payload))


class TestGameStateManager:
    """Test suite for Game State Manager"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_room_manager = MockRoomManager()
        self.mock_player_manager = MockPlayerManager()
        self.mock_broadcaster = MockMessageBroadcaster()
        
        self.game_state_manager = GameStateManager(
            room_manager=self.mock_room_manager,
            player_manager=self.mock_player_manager,
            message_broadcaster=self.mock_broadcaster
        )
        
        self.room_code = "TEST"
        self.host_id = uuid4()
        self.host_token = "host_token"
        
        # Create test room with host and players
        self.setup_test_room()
    
    def setup_test_room(self):
        """Set up a test room with players"""
        # Create host player
        host_player = PlayerInternal(
            player_id=self.host_id,
            username="Host",
            score=0,
            streak=0,
            session_token=self.host_token,
            joined_at=datetime.now(timezone.utc)
        )
        
        # Create regular player
        player_id = uuid4()
        player = PlayerInternal(
            player_id=player_id,
            username="Player1",
            score=0,
            streak=0,
            session_token="player_token",
            joined_at=datetime.now(timezone.utc)
        )
        
        # Create problems
        problems = []
        for i in range(10):
            problem = Problem(
                numbers=[1, 2, 3, 4],
                canonical_solution="1+2+3+4*6"
            )
            problems.append(problem)
        
        # Create room
        self.test_room = Room(
            room_code=self.room_code,
            host_player_id=self.host_id,
            settings=MVPRoomSettings(),
            players={
                self.host_id: host_player,
                player_id: player
            },
            problems=problems,
            state=RoomState.LOBBY,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        
        # Add to mock managers
        self.mock_room_manager.add_room(self.room_code, self.test_room)
        self.mock_room_manager.add_session_token(self.host_token, self.host_id)
    
    # Game Start Tests
    
    @pytest.mark.asyncio
    async def test_start_game_success(self):
        """Test successful game start"""
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Room should transition to running
        assert self.test_room.state == RoomState.RUNNING
        assert self.test_room.round_index == 0
        
        # Players should have reset scores
        for player in self.test_room.players.values():
            assert player.score == 0
            assert player.streak == 0
        
        # Should have started first round
        assert self.test_room.current_round_state is not None
        assert self.test_room.current_round_state.phase == RoundPhase.COUNTDOWN
        
        # Should have broadcast countdown start
        assert len(self.mock_broadcaster.messages) > 0
        assert self.mock_broadcaster.messages[0][1] == "countdown.start"
    
    @pytest.mark.asyncio
    async def test_start_game_invalid_token(self):
        """Test game start with invalid session token"""
        with pytest.raises(UnauthorizedOperationError):
            await self.game_state_manager.start_game(
                self.room_code, self.host_id, "invalid_token"
            )
    
    @pytest.mark.asyncio
    async def test_start_game_not_host(self):
        """Test game start by non-host player"""
        # Add another player and try to start with their ID
        other_player_id = uuid4()
        other_token = "other_token"
        
        other_player = PlayerInternal(
            player_id=other_player_id,
            username="NotHost",
            score=0,
            streak=0,
            session_token=other_token,
            joined_at=datetime.now(timezone.utc)
        )
        
        self.test_room.players[other_player_id] = other_player
        self.mock_room_manager.add_session_token(other_token, other_player_id)
        
        with pytest.raises(UnauthorizedOperationError):
            await self.game_state_manager.start_game(
                self.room_code, other_player_id, other_token
            )
    
    @pytest.mark.asyncio
    async def test_start_game_room_not_in_lobby(self):
        """Test game start when room not in lobby state"""
        self.test_room.state = RoomState.RUNNING
        
        with pytest.raises(InvalidGameStateError):
            await self.game_state_manager.start_game(
                self.room_code, self.host_id, self.host_token
            )
    
    @pytest.mark.asyncio
    async def test_start_game_insufficient_players(self):
        """Test game start with insufficient players"""
        # Remove one player to leave only host
        player_ids = list(self.test_room.players.keys())
        non_host_id = [pid for pid in player_ids if pid != self.host_id][0]
        del self.test_room.players[non_host_id]
        
        with pytest.raises(InsufficientPlayersError):
            await self.game_state_manager.start_game(
                self.room_code, self.host_id, self.host_token
            )
    
    @pytest.mark.asyncio
    async def test_start_game_nonexistent_room(self):
        """Test game start with nonexistent room"""
        with pytest.raises(ValueError):
            await self.game_state_manager.start_game(
                "FAKE", self.host_id, self.host_token
            )
    
    # Round Management Tests
    
    @pytest.mark.asyncio
    async def test_round_lifecycle(self):
        """Test complete round lifecycle"""
        # Start game
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Should be in countdown phase
        assert self.test_room.current_round_state.phase == RoundPhase.COUNTDOWN
        
        # Simulate countdown completion
        await self.game_state_manager.handle_countdown_complete(self.room_code)
        
        # Should be in active phase
        assert self.test_room.current_round_state.phase == RoundPhase.ACTIVE
        
        # Should have broadcast round start
        round_start_messages = [msg for msg in self.mock_broadcaster.messages if msg[1] == "round.start"]
        assert len(round_start_messages) == 1
        
        # Simulate round timeout
        await self.game_state_manager.handle_round_timeout(self.room_code)
        
        # Should be in results phase
        assert self.test_room.current_round_state.phase == RoundPhase.RESULTS
        
        # Should have broadcast round end
        round_end_messages = [msg for msg in self.mock_broadcaster.messages if msg[1] == "round.end"]
        assert len(round_end_messages) == 1
    
    @pytest.mark.asyncio
    async def test_round_progression(self):
        """Test progression through multiple rounds"""
        # Start game
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        initial_round = self.test_room.round_index
        
        # Complete first round
        await self.game_state_manager.handle_countdown_complete(self.room_code)
        await self.game_state_manager.handle_round_timeout(self.room_code)
        await self.game_state_manager.handle_results_complete(self.room_code)
        
        # Should advance to next round
        assert self.test_room.round_index == initial_round + 1
        
        # Should reset round scoring
        assert self.room_code in self.mock_player_manager.reset_calls
    
    @pytest.mark.asyncio
    async def test_game_completion(self):
        """Test game completion after all rounds"""
        # Start game and set to last round
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Set to last round (9 since 0-indexed, 10 total rounds)
        self.test_room.round_index = 9
        
        # Complete last round
        await self.game_state_manager.handle_countdown_complete(self.room_code)
        await self.game_state_manager.handle_round_timeout(self.room_code)
        await self.game_state_manager.handle_results_complete(self.room_code)
        
        # Game should be finished
        assert self.test_room.state == RoomState.FINISHED
        assert self.test_room.current_round_state is None
        
        # Should have broadcast game end
        game_end_messages = [msg for msg in self.mock_broadcaster.messages if msg[1] == "game.end"]
        assert len(game_end_messages) == 1
        
        # Should have cleaned up scoring
        assert self.room_code in self.mock_player_manager.cleanup_calls
    
    @pytest.mark.asyncio
    async def test_start_round_no_more_problems(self):
        """Test starting round when no more problems available"""
        # Set round index beyond available problems
        self.test_room.round_index = len(self.test_room.problems)
        self.test_room.state = RoomState.RUNNING
        
        await self.game_state_manager.start_round(self.room_code)
        
        # Should end game instead of starting round
        assert self.test_room.state == RoomState.FINISHED
    
    # Timer Management Tests
    
    @pytest.mark.asyncio
    async def test_timer_scheduling_and_cancellation(self):
        """Test timer scheduling and cancellation"""
        # Start game to create timers
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Should have an active timer
        assert self.room_code in self.game_state_manager.active_timers
        
        # Force end game should cancel timers
        await self.game_state_manager.force_end_game(self.room_code, "Test cancellation")
        
        # Timer should be cancelled
        assert self.room_code not in self.game_state_manager.active_timers
    
    @pytest.mark.asyncio
    async def test_timer_replacement(self):
        """Test that new timers replace old ones"""
        # Start game
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        first_timer = self.game_state_manager.active_timers.get(self.room_code)
        
        # Move to next phase
        await self.game_state_manager.handle_countdown_complete(self.room_code)
        
        second_timer = self.game_state_manager.active_timers.get(self.room_code)
        
        # Should be different timer
        assert first_timer != second_timer
        assert first_timer.cancelled()
    
    # State Information Tests
    
    def test_get_current_phase(self):
        """Test getting current game phase"""
        # No current state
        assert self.game_state_manager.get_current_phase(self.room_code) is None
        
        # Set a phase
        self.test_room.current_round_state = RoundState(
            phase=RoundPhase.ACTIVE,
            phase_start_time=datetime.now(timezone.utc),
            phase_end_time=datetime.now(timezone.utc) + timedelta(seconds=30)
        )
        
        assert self.game_state_manager.get_current_phase(self.room_code) == RoundPhase.ACTIVE
    
    def test_get_time_remaining_in_phase(self):
        """Test getting time remaining in current phase"""
        # No current state
        assert self.game_state_manager.get_time_remaining_in_phase(self.room_code) is None
        
        # Set a phase with future end time
        future_time = datetime.now(timezone.utc) + timedelta(seconds=15)
        self.test_room.current_round_state = RoundState(
            phase=RoundPhase.ACTIVE,
            phase_start_time=datetime.now(timezone.utc),
            phase_end_time=future_time
        )
        
        remaining = self.game_state_manager.get_time_remaining_in_phase(self.room_code)
        assert remaining is not None
        assert 0 <= remaining <= 15
        
        # Set past end time
        past_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.test_room.current_round_state.phase_end_time = past_time
        
        remaining = self.game_state_manager.get_time_remaining_in_phase(self.room_code)
        assert remaining == 0.0
    
    def test_get_game_stats_specific_room(self):
        """Test getting statistics for specific room"""
        stats = self.game_state_manager.get_game_stats(self.room_code)
        
        assert stats["room_code"] == self.room_code
        assert stats["state"] == RoomState.LOBBY
        assert stats["current_round"] == 1  # 0-indexed + 1
        assert stats["total_rounds"] == 10
        assert "players_count" in stats
        assert "has_active_timer" in stats
    
    def test_get_game_stats_global(self):
        """Test getting global game statistics"""
        stats = self.game_state_manager.get_game_stats()
        
        assert "global_stats" in stats
        assert "config" in stats
        assert "active_timers" in stats
        assert "games_started" in stats["global_stats"]
        assert "games_completed" in stats["global_stats"]
    
    # Error Handling and Edge Cases
    
    @pytest.mark.asyncio
    async def test_handle_countdown_complete_wrong_phase(self):
        """Test countdown completion when not in countdown phase"""
        # Set room to wrong phase
        self.test_room.current_round_state = RoundState(
            phase=RoundPhase.ACTIVE,
            phase_start_time=datetime.now(timezone.utc),
            phase_end_time=datetime.now(timezone.utc) + timedelta(seconds=30)
        )
        
        # Should handle gracefully (log warning but not crash)
        await self.game_state_manager.handle_countdown_complete(self.room_code)
        
        # Phase should remain unchanged
        assert self.test_room.current_round_state.phase == RoundPhase.ACTIVE
    
    @pytest.mark.asyncio
    async def test_operations_on_nonexistent_room(self):
        """Test operations on nonexistent room"""
        fake_room = "FAKE"
        
        # Should handle gracefully without crashing
        await self.game_state_manager.start_round(fake_room)
        await self.game_state_manager.handle_countdown_complete(fake_room)
        await self.game_state_manager.handle_round_timeout(fake_room)
        await self.game_state_manager.end_round(fake_room)
        await self.game_state_manager.handle_results_complete(fake_room)
        await self.game_state_manager.end_game(fake_room)
        await self.game_state_manager.force_end_game(fake_room)
        
        # Should return None/empty for info methods
        assert self.game_state_manager.get_current_phase(fake_room) is None
        assert self.game_state_manager.get_time_remaining_in_phase(fake_room) is None
        assert self.game_state_manager.get_game_stats(fake_room) == {}
    
    @pytest.mark.asyncio
    async def test_force_end_game(self):
        """Test force ending a game"""
        # Start game
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Force end
        await self.game_state_manager.force_end_game(self.room_code, "Admin intervention")
        
        # Should be finished
        assert self.test_room.state == RoomState.FINISHED
        assert self.test_room.current_round_state is None
        
        # Should have cleaned up
        assert self.room_code in self.mock_player_manager.cleanup_calls
        assert self.room_code not in self.game_state_manager.active_timers
        
        # Should update statistics
        stats = self.game_state_manager.get_game_stats()
        assert stats["global_stats"]["forced_endings"] == 1
    
    # Phase Callback Tests
    
    @pytest.mark.asyncio
    async def test_phase_callbacks(self):
        """Test phase callback registration and execution"""
        callback_calls = []
        
        def sync_callback(room_code, **kwargs):
            callback_calls.append(("sync", room_code, kwargs))
        
        async def async_callback(room_code, **kwargs):
            callback_calls.append(("async", room_code, kwargs))
        
        # Register callbacks
        self.game_state_manager.register_phase_callback(GamePhaseState.LOBBY, sync_callback)
        self.game_state_manager.register_phase_callback(GamePhaseState.COUNTDOWN, async_callback)
        
        # Start game (should trigger lobby callback)
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Should have called both callbacks
        assert len(callback_calls) >= 2
        assert any(call[0] == "sync" and call[1] == self.room_code for call in callback_calls)
        assert any(call[0] == "async" and call[1] == self.room_code for call in callback_calls)
    
    @pytest.mark.asyncio
    async def test_phase_callback_error_handling(self):
        """Test that callback errors don't break game flow"""
        def failing_callback(room_code, **kwargs):
            raise Exception("Callback error")
        
        # Register failing callback
        self.game_state_manager.register_phase_callback(GamePhaseState.LOBBY, failing_callback)
        
        # Should still work despite callback error
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Game should still be running
        assert self.test_room.state == RoomState.RUNNING
    
    # Configuration Tests
    
    def test_configuration_values(self):
        """Test game configuration values"""
        config = self.game_state_manager.config
        
        assert config["min_players"] == 2
        assert config["max_players"] == 4
        assert config["countdown_seconds"] == 3
        assert config["round_seconds"] == 30
        assert config["results_seconds"] == 6
        assert config["total_rounds"] == 10
    
    def test_statistics_tracking(self):
        """Test that statistics are properly tracked"""
        initial_stats = self.game_state_manager.get_game_stats()["global_stats"]
        
        # Perform operations that should update stats
        asyncio.run(self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        ))
        
        asyncio.run(self.game_state_manager.force_end_game(self.room_code))
        
        new_stats = self.game_state_manager.get_game_stats()["global_stats"]
        
        assert new_stats["games_started"] == initial_stats["games_started"] + 1
        assert new_stats["forced_endings"] == initial_stats["forced_endings"] + 1


# Integration Test Class

class TestGameStateManagerIntegration:
    """Integration tests for Game State Manager with realistic scenarios"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_room_manager = MockRoomManager()
        self.mock_player_manager = MockPlayerManager()
        self.mock_broadcaster = MockMessageBroadcaster()
        
        self.game_state_manager = GameStateManager(
            room_manager=self.mock_room_manager,
            player_manager=self.mock_player_manager,
            message_broadcaster=self.mock_broadcaster
        )
        
        self.room_code = "INTG"
        self.setup_integration_room()
    
    def setup_integration_room(self):
        """Set up room for integration testing"""
        # Create 4 players
        self.players = {}
        self.tokens = {}
        
        for i in range(4):
            player_id = uuid4()
            token = f"token_{i}"
            
            player = PlayerInternal(
                player_id=player_id,
                username=f"Player{i+1}",
                score=0,
                streak=0,
                session_token=token,
                joined_at=datetime.now(timezone.utc)
            )
            
            self.players[player_id] = player
            self.tokens[token] = player_id
        
        # First player is host
        self.host_id = list(self.players.keys())[0]
        self.host_token = list(self.tokens.keys())[0]
        
        # Create problems
        problems = []
        for i in range(10):
            problem = Problem(
                numbers=[1, 2, 3, 4 + i],
                canonical_solution=f"1+2+3+{4+i}*6"
            )
            problems.append(problem)
        
        # Create room
        self.test_room = Room(
            room_code=self.room_code,
            host_player_id=self.host_id,
            settings=MVPRoomSettings(),
            players=self.players,
            problems=problems,
            state=RoomState.LOBBY,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        
        # Add to mock managers
        self.mock_room_manager.add_room(self.room_code, self.test_room)
        for token, player_id in self.tokens.items():
            self.mock_room_manager.add_session_token(token, player_id)
    
    @pytest.mark.asyncio
    async def test_complete_game_simulation(self):
        """Test complete game simulation from start to finish"""
        # Start game
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        assert self.test_room.state == RoomState.RUNNING
        
        # Simulate 3 complete rounds
        for round_num in range(3):
            # Countdown phase
            assert self.test_room.current_round_state.phase == RoundPhase.COUNTDOWN
            
            # Complete countdown
            await self.game_state_manager.handle_countdown_complete(self.room_code)
            assert self.test_room.current_round_state.phase == RoundPhase.ACTIVE
            
            # Complete round
            await self.game_state_manager.handle_round_timeout(self.room_code)
            assert self.test_room.current_round_state.phase == RoundPhase.RESULTS
            
            # Complete results
            await self.game_state_manager.handle_results_complete(self.room_code)
            
            # Should advance to next round (unless game complete)
            if round_num < 2:  # Not the last round we're testing
                assert self.test_room.round_index == round_num + 1
        
        # Game should still be running (only did 3 of 10 rounds)
        assert self.test_room.state == RoomState.RUNNING
        
        # Force end remaining game
        await self.game_state_manager.force_end_game(self.room_code, "Test complete")
        assert self.test_room.state == RoomState.FINISHED
    
    @pytest.mark.asyncio
    async def test_message_broadcasting_sequence(self):
        """Test that messages are broadcast in correct sequence"""
        # Start game
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Complete one full round
        await self.game_state_manager.handle_countdown_complete(self.room_code)
        await self.game_state_manager.handle_round_timeout(self.room_code)
        await self.game_state_manager.handle_results_complete(self.room_code)
        
        # Check message sequence
        message_types = [msg[1] for msg in self.mock_broadcaster.messages]
        
        # Should have: countdown.start, round.start, round.end, countdown.start (next round)
        assert "countdown.start" in message_types
        assert "round.start" in message_types
        assert "round.end" in message_types
        
        # First countdown should come before round start
        first_countdown_idx = message_types.index("countdown.start")
        round_start_idx = message_types.index("round.start")
        round_end_idx = message_types.index("round.end")
        
        assert first_countdown_idx < round_start_idx < round_end_idx
    
    @pytest.mark.asyncio
    async def test_concurrent_room_games(self):
        """Test managing multiple games simultaneously"""
        # Create second room
        room2_code = "INT2"
        room2_host_id = uuid4()
        room2_host_token = "host2_token"
        
        # Set up second room (simplified)
        room2 = Room(
            room_code=room2_code,
            host_player_id=room2_host_id,
            settings=MVPRoomSettings(),
            players={room2_host_id: PlayerInternal(
                player_id=room2_host_id,
                username="Host2",
                score=0,
                streak=0,
                session_token=room2_host_token,
                joined_at=datetime.now(timezone.utc)
            ), uuid4(): PlayerInternal(
                player_id=uuid4(),
                username="Player2",
                score=0,
                streak=0,
                session_token="player2_token",
                joined_at=datetime.now(timezone.utc)
            )},
            problems=[Problem(numbers=[1,2,3,4], canonical_solution="1+2+3+4*6") for _ in range(10)],
            state=RoomState.LOBBY,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        
        self.mock_room_manager.add_room(room2_code, room2)
        self.mock_room_manager.add_session_token(room2_host_token, room2_host_id)
        
        # Start both games
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        await self.game_state_manager.start_game(
            room2_code, room2_host_id, room2_host_token
        )
        
        # Both should be running
        assert self.test_room.state == RoomState.RUNNING
        assert room2.state == RoomState.RUNNING
        
        # Should have active timers for both
        assert self.room_code in self.game_state_manager.active_timers
        assert room2_code in self.game_state_manager.active_timers
        
        # Progress one game
        await self.game_state_manager.handle_countdown_complete(self.room_code)
        
        # First game should be in active phase, second still in countdown
        assert self.test_room.current_round_state.phase == RoundPhase.ACTIVE
        assert room2.current_round_state.phase == RoundPhase.COUNTDOWN
        
        # End both games
        await self.game_state_manager.force_end_game(self.room_code)
        await self.game_state_manager.force_end_game(room2_code)
        
        # Both should be finished
        assert self.test_room.state == RoomState.FINISHED
        assert room2.state == RoomState.FINISHED
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test error recovery during game flow"""
        # Start game normally
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Simulate error by removing room mid-game
        self.mock_room_manager.rooms.clear()
        
        # Operations should handle gracefully
        await self.game_state_manager.handle_countdown_complete(self.room_code)
        await self.game_state_manager.handle_round_timeout(self.room_code)
        await self.game_state_manager.end_round(self.room_code)
        
        # Should not crash or raise unhandled exceptions
        # In real implementation, these would be logged as errors
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self):
        """Test performance with rapid operations"""
        # Start game
        await self.game_state_manager.start_game(
            self.room_code, self.host_id, self.host_token
        )
        
        # Rapidly trigger phase transitions
        start_time = datetime.now()
        
        for _ in range(5):
            await self.game_state_manager.handle_countdown_complete(self.room_code)
            await self.game_state_manager.handle_round_timeout(self.room_code)
            await self.game_state_manager.handle_results_complete(self.room_code)
        
        end_time = datetime.now()
        
        # Should complete rapidly (within reasonable time)
        duration = (end_time - start_time).total_seconds()
        assert duration < 1.0  # Should complete within 1 second
        
        # Game should still be in valid state
        assert self.test_room.state in [RoomState.RUNNING, RoomState.FINISHED]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])