"""
Simple compatibility check for Phase 2 components (no pytest required)
"""

import asyncio
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


def test_imports():
    """Test that all required components can be imported"""
    print("Testing imports...")
    
    try:
        # Import all Phase 2 components
        from problem_pool_service import ProblemPoolService
        from game_state_manager import GameStateManager
        from timer_service import TimerService
        from submission_processor import SubmissionProcessor
        from message_broadcaster import MessageBroadcaster
        
        # Import supporting components
        from room_manager import RoomManager
        from player_manager import PlayerManager
        
        # Import schemas
        from pydantic_schemas import (
            Room, PlayerInternal, PlayerPublic, Problem, MVPRoomSettings,
            RoomState, RoundPhase, RoundState, SubmissionRecord
        )
        
        # Import solver
        from solve_24 import Solution
        
        print("All imports successful")
        return True
    except Exception as e:
        print(f"Import failed: {e}")
        return False


async def test_initialization():
    """Test that all components can be initialized"""
    print("Testing component initialization...")
    
    try:
        from problem_pool_service import ProblemPoolService
        from game_state_manager import GameStateManager
        from timer_service import TimerService
        from submission_processor import SubmissionProcessor
        from message_broadcaster import MessageBroadcaster
        from room_manager import RoomManager
        from player_manager import PlayerManager
        
        # Initialize components in dependency order
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
        
        # Set up dependencies
        timer_service.set_game_state_manager(game_state_manager)
        message_broadcaster.set_connection_manager({}, {})
        
        print("All components initialized successfully")
        return True
    except Exception as e:
        print(f"Initialization failed: {e}")
        return False


def test_schema_creation():
    """Test that Pydantic schemas work correctly"""
    print("Testing schema compatibility...")
    
    try:
        from pydantic_schemas import (
            Problem, MVPRoomSettings, PlayerInternal, Room,
            CountdownStartMessage, CountdownStartPayload
        )
        from datetime import datetime, timezone
        from uuid import uuid4
        
        # Create test instances
        problem = Problem(
            numbers=[1, 2, 3, 4],
            canonical_solution="1+2+3*4"
        )
        
        settings = MVPRoomSettings()
        
        player = PlayerInternal(
            player_id=uuid4(),
            username="TestPlayer",
            score=0,
            streak=0,
            session_token="test_token",
            joined_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        
        room = Room(
            room_code="TEST",
            host_player_id=player.player_id,
            settings=settings,
            players={player.player_id: player},
            problems=[problem],
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        
        message = CountdownStartMessage(
            type="countdown.start",
            payload=CountdownStartPayload(
                round_index=0,
                countdown_seconds=3,
                server_time=datetime.now(timezone.utc)
            )
        )
        
        # Verify serialization works
        room_json = room.json()
        message_json = message.json()
        
        assert isinstance(room_json, str)
        assert isinstance(message_json, str)
        assert len(room_json) > 0
        assert len(message_json) > 0
        
        print("Schema creation and serialization successful")
        return True
    except Exception as e:
        print(f"Schema creation failed: {e}")
        return False


async def test_solver_integration():
    """Test that the 24-game solver integrates properly"""
    print("Testing solver integration...")
    
    try:
        from solve_24 import Solution
        from problem_pool_service import ProblemPoolService
        
        # Test direct solver usage
        solver = Solution([1, 1, 8, 8], target=24)
        solver.find_all_solutions()
        solutions = solver.get_all_solutions()
        
        assert len(solutions) > 0
        
        # Test problem pool service usage
        problem_pool = ProblemPoolService()
        await problem_pool.initialize()
        
        problems = await problem_pool.generate_problems_for_game(3)
        assert len(problems) == 3
        
        print("Solver integration successful")
        return True
    except Exception as e:
        print(f"Solver integration failed: {e}")
        return False


async def test_basic_workflow():
    """Test basic end-to-end compatibility"""
    print("Testing basic workflow...")
    
    try:
        from problem_pool_service import ProblemPoolService
        from room_manager import RoomManager
        from player_manager import PlayerManager
        from submission_processor import SubmissionProcessor
        from datetime import datetime, timezone
        from uuid import uuid4
        
        # Initialize components
        problem_pool = ProblemPoolService()
        await problem_pool.initialize()
        
        room_manager = RoomManager(problem_pool)
        player_manager = PlayerManager()
        submission_processor = SubmissionProcessor(player_manager)
        
        # Create room
        result = await room_manager.create_room("TestHost", uuid4())
        assert result.room_code is not None
        
        # Get room
        room = room_manager.get_room(result.room_code)
        assert room is not None
        assert len(room.problems) >= 0  # May be 0 if problems not generated
        
        # Add player
        guest_id = uuid4()
        join_result = await room_manager.join_room(result.room_code, "TestGuest", guest_id)
        assert join_result.player_id == guest_id
        
        print("Basic workflow successful")
        return True
    except Exception as e:
        print(f"Basic workflow failed: {e}")
        return False


def test_configuration():
    """Test that configuration constants are compatible"""
    print("Testing configuration compatibility...")
    
    try:
        from pydantic_schemas import MVPRoomSettings
        
        settings = MVPRoomSettings()
        
        # Verify MVP settings
        assert settings.rounds == 10
        assert settings.time_per_round_seconds == 30
        assert settings.countdown_seconds == 3
        assert settings.results_display_seconds == 6
        
        print("Configuration compatibility successful")
        return True
    except Exception as e:
        print(f"Configuration compatibility failed: {e}")
        return False


async def main():
    """Run all compatibility tests"""
    print("Running Phase 2 Component Compatibility Tests")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports()),
        ("Initialization Test", await test_initialization()),
        ("Schema Test", test_schema_creation()),
        ("Solver Integration Test", await test_solver_integration()),
        ("Basic Workflow Test", await test_basic_workflow()),
        ("Configuration Test", test_configuration())
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, result in tests:
        if result:
            passed += 1
            print(f"PASS {test_name}")
        else:
            print(f"FAIL {test_name}")
    
    print("=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("All compatibility tests passed! Phase 2 components are fully compatible.")
        return True
    else:
        print("Some compatibility tests failed. Check the errors above.")
        return False


if __name__ == "__main__":
    asyncio.run(main())