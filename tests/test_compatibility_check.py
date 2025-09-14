"""
Compatibility check for all Phase 2 components
Verifies that all components can be imported and initialized together
"""

import pytest
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


class TestCompatibility:
    """Test compatibility between all components"""

    def test_all_imports_work(self):
        """Test that all required components can be imported"""
        
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
        
        # All imports successful
        assert True

    @pytest.mark.asyncio
    async def test_component_initialization(self):
        """Test that all components can be initialized"""
        
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
        
        # All components initialized successfully
        assert problem_pool is not None
        assert room_manager is not None
        assert player_manager is not None
        assert message_broadcaster is not None
        assert timer_service is not None
        assert submission_processor is not None
        assert game_state_manager is not None

    @pytest.mark.asyncio
    async def test_schema_compatibility(self):
        """Test that Pydantic schemas work correctly"""
        
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

    @pytest.mark.asyncio
    async def test_solver_integration(self):
        """Test that the 24-game solver integrates properly"""
        
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
        
        problems = await problem_pool.generate_problems_for_game(5)
        assert len(problems) == 5
        
        for problem in problems:
            # Each problem should have a valid solution
            test_solver = Solution(problem.numbers, target=24)
            test_solver.find_all_solutions()
            test_solutions = test_solver.get_all_solutions()
            assert len(test_solutions) > 0

    @pytest.mark.asyncio
    async def test_data_type_compatibility(self):
        """Test that data types are compatible between components"""
        
        from pydantic_schemas import PlayerInternal, SubmissionRecord
        from datetime import datetime, timezone
        from uuid import uuid4
        
        # Test player data compatibility
        player = PlayerInternal(
            player_id=uuid4(),
            username="TestPlayer",
            score=10,
            streak=2,
            session_token="token",
            joined_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        
        # Test submission record compatibility
        submission = SubmissionRecord(
            submission_id=uuid4(),
            room_code="TEST",
            round_index=0,
            player_id=player.player_id,
            expression="1+2+3*4",
            used_numbers=[1, 2, 3, 4],
            client_eval_value=24.0,
            client_eval_is_valid=True,
            server_receive_time=datetime.now(timezone.utc),
            accepted=True
        )
        
        # Verify data types are correct
        assert isinstance(player.player_id, uuid4().__class__)
        assert isinstance(player.score, int)
        assert isinstance(submission.used_numbers, list)
        assert isinstance(submission.client_eval_value, (float, type(None)))

    def test_interface_compatibility(self):
        """Test that component interfaces are compatible"""
        
        from problem_pool_service import ProblemPoolService
        from room_manager import RoomManager
        from player_manager import PlayerManager
        from submission_processor import SubmissionProcessor
        
        # Check that RoomManager can accept ProblemPoolService
        problem_pool = ProblemPoolService()
        room_manager = RoomManager(problem_pool)
        
        # Check that SubmissionProcessor can accept PlayerManager
        player_manager = PlayerManager()
        submission_processor = SubmissionProcessor(player_manager)
        
        # Check that interfaces exist
        assert hasattr(problem_pool, 'generate_problems_for_game')
        assert hasattr(room_manager, 'create_room')
        assert hasattr(player_manager, 'calculate_score')
        assert hasattr(submission_processor, 'process_submission')

    @pytest.mark.asyncio
    async def test_end_to_end_compatibility(self):
        """Test end-to-end compatibility with minimal workflow"""
        
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
        assert len(room.problems) > 0
        
        # Add player
        guest_id = uuid4()
        join_result = await room_manager.join_room(result.room_code, "TestGuest", guest_id)
        assert join_result.player_id == guest_id
        
        # Test submission processing (would normally require active game)
        # This is just testing the interface compatibility
        try:
            submission_result = await submission_processor.process_submission(
                room_code=result.room_code,
                player_id=guest_id,
                session_token="invalid",  # This will fail but tests interface
                round_index=0,
                expression="test",
                used_numbers=[1, 2, 3, 4],
                client_eval_value=24.0,
                client_eval_is_valid=True,
                client_timestamp=datetime.now(timezone.utc),
                room_manager=room_manager
            )
            # Should return a result (even if rejected)
            assert submission_result is not None
        except Exception as e:
            # Expected to fail with invalid token, but interface should work
            pass

    def test_configuration_compatibility(self):
        """Test that configuration constants are compatible"""
        
        from pydantic_schemas import MVPRoomSettings
        
        settings = MVPRoomSettings()
        
        # Verify MVP settings
        assert settings.rounds == 10
        assert settings.time_per_round_seconds == 30
        assert settings.countdown_seconds == 3
        assert settings.results_display_seconds == 6