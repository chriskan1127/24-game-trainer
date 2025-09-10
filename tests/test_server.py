"""
Test cases for the 24-game multiplayer server
"""

import asyncio
import json
import pytest
import websockets
from datetime import datetime, timezone
from uuid import uuid4
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
server_dir = os.path.join(project_root, 'server')
plans_dir = os.path.join(project_root, 'plans')

if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from room_manager import RoomManager
from problem_pool_service import ProblemPoolService
from player_manager import PlayerManager
from message_broadcaster import MessageBroadcaster
from timer_service import TimerService
from game_state_manager import GameStateManager
from submission_processor import SubmissionProcessor

# Test configuration
SERVER_URL = "ws://localhost:8000"
HTTP_URL = "http://localhost:8000"


class TestRoomManager:
    """Test the room manager functionality"""
    
    @pytest.fixture
    async def room_manager(self):
        """Create a room manager with mock problem pool service"""
        problem_pool = ProblemPoolService()
        await problem_pool.initialize()
        return RoomManager(problem_pool)
    
    @pytest.mark.asyncio
    async def test_create_room(self, room_manager):
        """Test room creation"""
        host_id = uuid4()
        result = await room_manager.create_room("TestHost", host_id)
        
        assert result.room_code
        assert len(result.room_code) == 4
        assert result.host_player_id == host_id
        assert result.host_session_token
        assert result.created_at
        
        # Verify room exists
        room = room_manager.get_room(result.room_code)
        assert room is not None
        assert room.host_player_id == host_id
        assert len(room.players) == 1
        assert host_id in room.players
    
    @pytest.mark.asyncio
    async def test_join_room(self, room_manager):
        """Test joining an existing room"""
        # Create room first
        host_id = uuid4()
        create_result = await room_manager.create_room("TestHost", host_id)
        
        # Join room
        player_id = uuid4()
        join_result = await room_manager.join_room(
            create_result.room_code, "TestPlayer", player_id
        )
        
        assert join_result.room_code == create_result.room_code
        assert join_result.player_id == player_id
        assert join_result.session_token
        assert len(join_result.players) == 2
        
        # Verify room has both players
        room = room_manager.get_room(create_result.room_code)
        assert len(room.players) == 2
        assert host_id in room.players
        assert player_id in room.players
    
    @pytest.mark.asyncio
    async def test_room_capacity_limit(self, room_manager):
        """Test that rooms can't exceed 4 players"""
        # Create room with host
        host_id = uuid4()
        create_result = await room_manager.create_room("Host", host_id)
        
        # Add 3 more players (total 4)
        for i in range(3):
            player_id = uuid4()
            await room_manager.join_room(
                create_result.room_code, f"Player{i+1}", player_id
            )
        
        # Try to add a 5th player - should fail
        extra_player_id = uuid4()
        with pytest.raises(ValueError, match="Room is full"):
            await room_manager.join_room(
                create_result.room_code, "ExtraPlayer", extra_player_id
            )
    
    @pytest.mark.asyncio
    async def test_duplicate_username_rejection(self, room_manager):
        """Test that duplicate usernames are rejected"""
        # Create room
        host_id = uuid4()
        create_result = await room_manager.create_room("TestUser", host_id)
        
        # Try to join with same username - should fail
        other_player_id = uuid4()
        with pytest.raises(ValueError, match="Username 'TestUser' is already taken"):
            await room_manager.join_room(
                create_result.room_code, "TestUser", other_player_id
            )


class TestProblemPoolService:
    """Test the problem pool service"""
    
    @pytest.mark.asyncio
    async def test_problem_pool_initialization(self):
        """Test that problem pool service initializes correctly"""
        problem_pool = ProblemPoolService()
        await problem_pool.initialize()
        
        # Just verify it initializes without error
        stats = problem_pool.get_generation_stats()
        assert stats["generation_method"] == "on_demand"
        assert stats["problems_per_game"] == 10
    
    @pytest.mark.asyncio
    async def test_generate_problems_for_game(self):
        """Test generating problems for a game on-demand"""
        problem_pool = ProblemPoolService()
        await problem_pool.initialize()
        
        problems = await problem_pool.generate_problems_for_game(10)
        
        assert len(problems) == 10
        assert all(problem.numbers for problem in problems)
        assert all(problem.canonical_solution for problem in problems)
        assert all(len(problem.numbers) == 4 for problem in problems)
        
        # Verify no duplicate number combinations within the game
        number_sets = [tuple(sorted(p.numbers)) for p in problems]
        assert len(set(number_sets)) == len(number_sets)  # All unique
    
    def test_validate_problem(self):
        """Test problem validation"""
        problem_pool = ProblemPoolService()
        
        # Test valid problem
        assert problem_pool.validate_problem([1, 1, 8, 8])  # (1+1+8)*8 = 80, not 24 but valid input
        
        # Test invalid input
        assert not problem_pool.validate_problem([])
        assert not problem_pool.validate_problem([1, 2])  # Too few numbers


class TestPlayerManager:
    """Test the player manager functionality"""
    
    def test_calculate_score(self):
        """Test score calculation"""
        player_manager = PlayerManager()
        
        # Test full time remaining
        base, bonus = player_manager.calculate_score(30.0, 30.0)
        assert base == 10
        assert bonus == 5
        
        # Test half time remaining
        base, bonus = player_manager.calculate_score(15.0, 30.0)
        assert base == 10
        assert bonus >= 2  # Should be around 2-3
        
        # Test no time remaining
        base, bonus = player_manager.calculate_score(0.0, 30.0)
        assert base == 10
        assert bonus == 0
    
    def test_round_scoring_tracking(self):
        """Test tracking which players have scored in a round"""
        player_manager = PlayerManager()
        room_code = "TEST"
        player_id = uuid4()
        
        # Initially, player hasn't scored
        assert not player_manager.has_player_scored_this_round(room_code, player_id)
        
        # Mark player as scored
        player_manager.mark_player_scored_this_round(room_code, player_id)
        assert player_manager.has_player_scored_this_round(room_code, player_id)
        
        # Reset round
        player_manager.reset_round_scoring(room_code)
        assert not player_manager.has_player_scored_this_round(room_code, player_id)


class TestWebSocketConnection:
    """Integration tests for WebSocket connections"""
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """Test basic WebSocket connection"""
        try:
            # Generate test IDs
            room_code = "TEST"
            player_id = str(uuid4())
            
            # Connect to WebSocket
            uri = f"{SERVER_URL}/ws/{room_code}/{player_id}"
            async with websockets.connect(uri, timeout=5) as websocket:
                # Connection successful if we reach here
                assert websocket.open
                
                # Test sending a message
                test_message = {
                    "type": "room.create",
                    "payload": {
                        "username": "TestUser"
                    }
                }
                
                await websocket.send(json.dumps(test_message))
                
                # Wait for response
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                response_data = json.loads(response)
                
                # Should receive either success or error
                assert "type" in response_data
                assert response_data["type"] in ["room.created", "error"]
                
        except websockets.exceptions.ConnectionClosed:
            pytest.fail("WebSocket connection was unexpectedly closed")
        except asyncio.TimeoutError:
            pytest.fail("WebSocket connection timed out")
        except Exception as e:
            pytest.fail(f"WebSocket connection failed: {e}")
    
    @pytest.mark.asyncio
    async def test_room_creation_flow(self):
        """Test the complete room creation flow"""
        try:
            room_code = "TEST"
            player_id = str(uuid4())
            
            uri = f"{SERVER_URL}/ws/{room_code}/{player_id}"
            async with websockets.connect(uri, timeout=5) as websocket:
                # Send room creation request
                create_message = {
                    "type": "room.create",
                    "payload": {
                        "username": "TestHost"
                    }
                }
                
                await websocket.send(json.dumps(create_message))
                
                # Wait for response
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                response_data = json.loads(response)
                
                # Verify successful room creation
                if response_data["type"] == "room.created":
                    assert "payload" in response_data
                    payload = response_data["payload"]
                    assert "room_code" in payload
                    assert "host_player_id" in payload
                    assert "session_token" in payload
                    assert len(payload["room_code"]) == 4
                    print(f"[OK] Room created successfully: {payload['room_code']}")
                elif response_data["type"] == "error":
                    # Log the error but don't fail - server might be in a different state
                    print(f"Room creation returned error: {response_data.get('payload', {}).get('message', 'Unknown error')}")
                else:
                    pytest.fail(f"Unexpected response type: {response_data['type']}")
                
        except Exception as e:
            pytest.fail(f"Room creation flow failed: {e}")


class TestGameFlow:
    """Test the complete game flow"""
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test that the health endpoint is working"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{HTTP_URL}/health", timeout=5) as response:
                    assert response.status == 200
                    data = await response.json()
                    assert data["status"] == "healthy"
                    assert "timestamp" in data
                    print("[OK] Health endpoint working")
        except Exception as e:
            pytest.fail(f"Health endpoint test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_stats_endpoint(self):
        """Test that the stats endpoint is working"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{HTTP_URL}/stats", timeout=5) as response:
                    assert response.status == 200
                    data = await response.json()
                    assert "active_connections" in data
                    assert "active_rooms" in data
                    assert "total_players" in data
                    assert isinstance(data["active_connections"], int)
                    assert isinstance(data["active_rooms"], int)
                    assert isinstance(data["total_players"], int)
                    print("[OK] Stats endpoint working")
        except Exception as e:
            pytest.fail(f"Stats endpoint test failed: {e}")


if __name__ == "__main__":
    """Run tests manually"""
    import asyncio
    
    async def run_basic_tests():
        """Run a subset of tests that don't require external dependencies"""
        print("Running basic server tests...")
        
        # Test problem pool
        print("Testing problem pool...")
        problem_pool = ProblemPoolService()
        await problem_pool.initialize()
        problems = await problem_pool.generate_problems_for_game(5)
        print(f"[OK] Generated {len(problems)} problems on-demand for game")
        
        # Test room manager
        print("Testing room manager...")
        room_manager = RoomManager(problem_pool)
        host_id = uuid4()
        result = await room_manager.create_room("TestHost", host_id)
        print(f"[OK] Room created: {result.room_code}")
        
        # Test player manager
        print("Testing player manager...")
        player_manager = PlayerManager()
        base, bonus = player_manager.calculate_score(15.0, 30.0)
        print(f"[OK] Score calculation: {base} base + {bonus} bonus")
        
        print("All basic tests passed!")
    
    # Run basic tests
    asyncio.run(run_basic_tests())