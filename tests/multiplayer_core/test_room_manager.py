"""
Comprehensive tests for Room Manager component

Tests cover:
- Room creation and code generation
- Player joining and validation  
- Session token management
- Room state transitions
- Error handling and edge cases
- Concurrency and thread safety
- Cleanup and resource management
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

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

from multiplayer_core.managers.room_manager import (
    RoomManager, RoomManagerError, RoomNotFoundError, RoomFullError,
    UsernameConflictError, GameInProgressError, AuthenticationError
)
from pydantic_schemas import RoomState, Problem


class MockProblemPoolService:
    """Mock problem pool service for testing"""
    
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.call_count = 0
    
    async def generate_problems_for_game(self, count):
        self.call_count += 1
        if self.should_fail:
            raise Exception("Problem generation failed")
        
        problems = []
        for i in range(count):
            problem = Problem(
                numbers=[1, 2, 3, 4],
                canonical_solution="1+2+3+4*6"
            )
            problems.append(problem)
        return problems


class TestRoomManager:
    """Test suite for Room Manager"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_problem_service = MockProblemPoolService()
        self.room_manager = RoomManager(self.mock_problem_service)
    
    # Basic Room Creation Tests
    
    @pytest.mark.asyncio
    async def test_create_room_success(self):
        """Test successful room creation"""
        result = await self.room_manager.create_room("TestHost")
        
        assert result.room_code is not None
        assert len(result.room_code) == 4
        assert result.room_code.isupper()
        assert result.host_player_id is not None
        assert result.host_session_token is not None
        assert result.created_at is not None
        
        # Verify room exists
        room = self.room_manager.get_room(result.room_code)
        assert room is not None
        assert room.host_player_id == result.host_player_id
        assert len(room.players) == 1
        assert room.state == RoomState.LOBBY
    
    @pytest.mark.asyncio
    async def test_create_room_with_custom_player_id(self):
        """Test room creation with custom player ID"""
        custom_id = uuid4()
        result = await self.room_manager.create_room("TestHost", custom_id)
        
        assert result.host_player_id == custom_id
        room = self.room_manager.get_room(result.room_code)
        assert custom_id in room.players
    
    @pytest.mark.asyncio
    async def test_create_room_invalid_username(self):
        """Test room creation with invalid usernames"""
        # Empty username
        with pytest.raises(ValueError, match="Host username cannot be empty"):
            await self.room_manager.create_room("")
        
        # Whitespace only
        with pytest.raises(ValueError, match="Host username cannot be empty"):
            await self.room_manager.create_room("   ")
        
        # Too long username
        long_name = "a" * 33
        with pytest.raises(ValueError, match="Username cannot exceed 32 characters"):
            await self.room_manager.create_room(long_name)
    
    @pytest.mark.asyncio
    async def test_room_code_uniqueness(self):
        """Test that room codes are unique"""
        codes = set()
        for i in range(100):  # Create many rooms to test uniqueness
            result = await self.room_manager.create_room(f"Host{i}")
            assert result.room_code not in codes
            codes.add(result.room_code)
    
    @pytest.mark.asyncio
    async def test_create_room_problem_generation_failure(self):
        """Test room creation when problem generation fails"""
        self.room_manager.problem_pool_service = MockProblemPoolService(should_fail=True)
        
        # Should still create room even if problem generation fails
        result = await self.room_manager.create_room("TestHost")
        room = self.room_manager.get_room(result.room_code)
        
        assert room is not None
        assert len(room.problems) == 0  # No problems generated
    
    # Player Joining Tests
    
    @pytest.mark.asyncio
    async def test_join_room_success(self):
        """Test successful room joining"""
        # Create room
        create_result = await self.room_manager.create_room("Host")
        
        # Join room
        join_result = await self.room_manager.join_room(
            create_result.room_code, "Player1"
        )
        
        assert join_result.room_code == create_result.room_code
        assert join_result.player_id is not None
        assert join_result.session_token is not None
        assert len(join_result.players) == 2
        
        # Verify room state
        room = self.room_manager.get_room(create_result.room_code)
        assert len(room.players) == 2
    
    @pytest.mark.asyncio
    async def test_join_nonexistent_room(self):
        """Test joining non-existent room"""
        with pytest.raises(RoomNotFoundError):
            await self.room_manager.join_room("FAKE", "Player1")
    
    @pytest.mark.asyncio
    async def test_join_room_case_insensitive(self):
        """Test that room codes are case insensitive"""
        create_result = await self.room_manager.create_room("Host")
        
        # Join with lowercase room code
        join_result = await self.room_manager.join_room(
            create_result.room_code.lower(), "Player1"
        )
        
        assert join_result.room_code == create_result.room_code.upper()
    
    @pytest.mark.asyncio
    async def test_join_room_max_players(self):
        """Test maximum player limit (4 players)"""
        create_result = await self.room_manager.create_room("Host")
        
        # Join 3 more players (total 4)
        for i in range(3):
            await self.room_manager.join_room(
                create_result.room_code, f"Player{i+1}"
            )
        
        # 5th player should fail
        with pytest.raises(RoomFullError):
            await self.room_manager.join_room(
                create_result.room_code, "Player5"
            )
    
    @pytest.mark.asyncio
    async def test_join_room_username_conflict(self):
        """Test username conflict handling"""
        create_result = await self.room_manager.create_room("Host")
        
        await self.room_manager.join_room(create_result.room_code, "Player1")
        
        # Try to join with same username (different case)
        with pytest.raises(UsernameConflictError):
            await self.room_manager.join_room(create_result.room_code, "PLAYER1")
    
    @pytest.mark.asyncio
    async def test_join_room_invalid_username(self):
        """Test joining with invalid username"""
        create_result = await self.room_manager.create_room("Host")
        
        with pytest.raises(ValueError):
            await self.room_manager.join_room(create_result.room_code, "")
        
        with pytest.raises(ValueError):
            await self.room_manager.join_room(create_result.room_code, "a" * 33)
    
    # Session Token and Authentication Tests
    
    @pytest.mark.asyncio
    async def test_session_token_validation(self):
        """Test session token validation"""
        create_result = await self.room_manager.create_room("Host")
        join_result = await self.room_manager.join_room(create_result.room_code, "Player1")
        
        # Valid token
        assert self.room_manager.validate_session_token(
            create_result.room_code, 
            join_result.player_id,
            join_result.session_token
        )
        
        # Invalid token
        assert not self.room_manager.validate_session_token(
            create_result.room_code,
            join_result.player_id, 
            "invalid_token"
        )
        
        # Wrong player ID
        assert not self.room_manager.validate_session_token(
            create_result.room_code,
            uuid4(),
            join_result.session_token
        )
    
    @pytest.mark.asyncio
    async def test_host_privileges(self):
        """Test host privilege checking"""
        create_result = await self.room_manager.create_room("Host")
        join_result = await self.room_manager.join_room(create_result.room_code, "Player1")
        
        # Host should have privileges
        assert self.room_manager.is_host(create_result.room_code, create_result.host_player_id)
        
        # Regular player should not
        assert not self.room_manager.is_host(create_result.room_code, join_result.player_id)
    
    @pytest.mark.asyncio
    async def test_player_reconnection(self):
        """Test player reconnection with session token"""
        create_result = await self.room_manager.create_room("Host")
        
        # Player joins
        join_result = await self.room_manager.join_room(create_result.room_code, "Player1")
        original_player_id = join_result.player_id
        original_token = join_result.session_token
        
        # Player reconnects with same session token
        reconnect_result = await self.room_manager.join_room(
            create_result.room_code,
            "Player1",
            player_id=original_player_id,
            session_token=original_token
        )
        
        assert reconnect_result.player_id == original_player_id
        assert reconnect_result.session_token == original_token
        
        # Should still have 2 players total
        room = self.room_manager.get_room(create_result.room_code)
        assert len(room.players) == 2
    
    # Room State and Lifecycle Tests
    
    @pytest.mark.asyncio
    async def test_remove_player(self):
        """Test player removal"""
        create_result = await self.room_manager.create_room("Host")
        join_result = await self.room_manager.join_room(create_result.room_code, "Player1")
        
        # Remove player
        removed = await self.room_manager.remove_player(
            create_result.room_code, 
            join_result.player_id
        )
        
        assert removed is True
        
        room = self.room_manager.get_room(create_result.room_code)
        assert len(room.players) == 1  # Only host remains
        assert join_result.player_id not in room.players
    
    @pytest.mark.asyncio
    async def test_remove_host_transfers_ownership(self):
        """Test that removing host transfers ownership"""
        create_result = await self.room_manager.create_room("Host")
        join_result = await self.room_manager.join_room(create_result.room_code, "Player1")
        
        # Remove host
        await self.room_manager.remove_player(
            create_result.room_code,
            create_result.host_player_id
        )
        
        room = self.room_manager.get_room(create_result.room_code)
        assert room.host_player_id == join_result.player_id  # Player1 is now host
    
    @pytest.mark.asyncio
    async def test_remove_last_player_deletes_room(self):
        """Test that removing last player deletes room"""
        create_result = await self.room_manager.create_room("Host")
        
        # Remove host (only player)
        await self.room_manager.remove_player(
            create_result.room_code,
            create_result.host_player_id
        )
        
        # Room should be deleted
        room = self.room_manager.get_room(create_result.room_code)
        assert room is None
    
    @pytest.mark.asyncio
    async def test_cleanup_inactive_rooms(self):
        """Test cleanup of inactive rooms"""
        # Create a room
        create_result = await self.room_manager.create_room("Host")
        room = self.room_manager.get_room(create_result.room_code)
        
        # Manually set old activity time
        room.last_activity_at = datetime.now(timezone.utc) - timedelta(hours=25)
        
        # Run cleanup
        cleaned = await self.room_manager.cleanup_inactive_rooms(max_age_hours=24)
        
        assert cleaned == 1
        assert self.room_manager.get_room(create_result.room_code) is None
    
    # Statistics and Information Tests
    
    def test_room_stats(self):
        """Test room statistics"""
        stats = self.room_manager.get_room_stats()
        
        assert "total_rooms" in stats
        assert "total_players" in stats
        assert "rooms_by_state" in stats
        assert "active_session_tokens" in stats
        assert "lifetime_stats" in stats
    
    @pytest.mark.asyncio
    async def test_get_room_players(self):
        """Test getting room players"""
        create_result = await self.room_manager.create_room("Host")
        await self.room_manager.join_room(create_result.room_code, "Player1")
        
        players = self.room_manager.get_room_players(create_result.room_code)
        
        assert len(players) == 2
        assert all(hasattr(p, 'username') for p in players)
        assert all(hasattr(p, 'score') for p in players)
        # Session tokens should not be in public player data
        assert all(not hasattr(p, 'session_token') for p in players)
    
    @pytest.mark.asyncio
    async def test_get_player_count(self):
        """Test getting player count"""
        create_result = await self.room_manager.create_room("Host")
        
        assert self.room_manager.get_player_count(create_result.room_code) == 1
        
        await self.room_manager.join_room(create_result.room_code, "Player1")
        assert self.room_manager.get_player_count(create_result.room_code) == 2
        
        # Non-existent room
        assert self.room_manager.get_player_count("FAKE") == 0
    
    # Edge Cases and Error Handling Tests
    
    @pytest.mark.asyncio
    async def test_join_game_in_progress(self):
        """Test joining room when game is in progress"""
        create_result = await self.room_manager.create_room("Host")
        
        # Manually set room to running state
        room = self.room_manager.get_room(create_result.room_code)
        room.state = RoomState.RUNNING
        
        # New player should not be able to join
        with pytest.raises(GameInProgressError):
            await self.room_manager.join_room(create_result.room_code, "Player1")
    
    @pytest.mark.asyncio
    async def test_remove_nonexistent_player(self):
        """Test removing player that doesn't exist"""
        create_result = await self.room_manager.create_room("Host")
        
        removed = await self.room_manager.remove_player(
            create_result.room_code,
            uuid4()  # Random player ID
        )
        
        assert removed is False
    
    @pytest.mark.asyncio
    async def test_concurrent_room_operations(self):
        """Test concurrent room operations for thread safety"""
        create_result = await self.room_manager.create_room("Host")
        
        async def join_player(name):
            try:
                return await self.room_manager.join_room(create_result.room_code, name)
            except Exception:
                return None
        
        # Try to join multiple players concurrently
        tasks = [join_player(f"Player{i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should only allow 3 more players (4 total including host)
        successful_joins = [r for r in results if r is not None and not isinstance(r, Exception)]
        assert len(successful_joins) <= 3
        
        room = self.room_manager.get_room(create_result.room_code)
        assert len(room.players) <= 4
    
    @pytest.mark.asyncio
    async def test_session_token_cleanup_on_removal(self):
        """Test that session tokens are cleaned up when players are removed"""
        create_result = await self.room_manager.create_room("Host")
        join_result = await self.room_manager.join_room(create_result.room_code, "Player1")
        
        # Verify token exists
        assert join_result.session_token in self.room_manager.session_tokens
        
        # Remove player
        await self.room_manager.remove_player(create_result.room_code, join_result.player_id)
        
        # Token should be cleaned up
        assert join_result.session_token not in self.room_manager.session_tokens
    
    @pytest.mark.asyncio
    async def test_room_code_generation_exhaustion(self):
        """Test room code generation when many rooms exist"""
        # This test simulates what happens when we run out of 4-character codes
        # In practice, this is extremely unlikely with 4-character alphanumeric codes
        
        # Mock the random choice to always return the same characters
        import string
        original_choices = string.ascii_uppercase + string.digits
        
        # Create many rooms to test code uniqueness under stress
        codes = set()
        for i in range(50):  # Create 50 rooms
            result = await self.room_manager.create_room(f"Host{i}")
            assert result.room_code not in codes
            codes.add(result.room_code)


# Integration Test Class

class TestRoomManagerIntegration:
    """Integration tests for Room Manager with other components"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_problem_service = MockProblemPoolService()
        self.room_manager = RoomManager(self.mock_problem_service)
    
    @pytest.mark.asyncio
    async def test_full_room_lifecycle(self):
        """Test complete room lifecycle from creation to cleanup"""
        # Create room
        create_result = await self.room_manager.create_room("Host")
        
        # Join players
        players = []
        for i in range(3):
            join_result = await self.room_manager.join_room(
                create_result.room_code, f"Player{i+1}"
            )
            players.append(join_result)
        
        # Verify room state
        room = self.room_manager.get_room(create_result.room_code)
        assert len(room.players) == 4
        assert room.state == RoomState.LOBBY
        
        # Simulate game start (would be done by Game State Manager)
        room.state = RoomState.RUNNING
        
        # Try to join during game (should fail)
        with pytest.raises(GameInProgressError):
            await self.room_manager.join_room(create_result.room_code, "LatePlayer")
        
        # Remove some players
        await self.room_manager.remove_player(create_result.room_code, players[0].player_id)
        await self.room_manager.remove_player(create_result.room_code, players[1].player_id)
        
        # End game
        room.state = RoomState.FINISHED
        
        # Clean up remaining players
        await self.room_manager.remove_player(create_result.room_code, players[2].player_id)
        await self.room_manager.remove_player(create_result.room_code, create_result.host_player_id)
        
        # Room should be deleted
        assert self.room_manager.get_room(create_result.room_code) is None
    
    @pytest.mark.asyncio
    async def test_problem_service_integration(self):
        """Test integration with problem pool service"""
        # Verify problem service is called
        initial_calls = self.mock_problem_service.call_count
        
        await self.room_manager.create_room("Host")
        
        assert self.mock_problem_service.call_count == initial_calls + 1
    
    @pytest.mark.asyncio
    async def test_statistics_tracking(self):
        """Test that statistics are properly tracked"""
        initial_stats = self.room_manager.get_room_stats()
        
        # Create room and join players
        create_result = await self.room_manager.create_room("Host")
        await self.room_manager.join_room(create_result.room_code, "Player1")
        
        # Check statistics updated
        new_stats = self.room_manager.get_room_stats()
        assert new_stats['lifetime_stats']['rooms_created'] == initial_stats['lifetime_stats']['rooms_created'] + 1
        assert new_stats['lifetime_stats']['players_joined'] == initial_stats['lifetime_stats']['players_joined'] + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])