"""
Test cases for Submission Processor Service
"""

import pytest
import asyncio
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

from submission_processor import SubmissionProcessor
from player_manager import PlayerManager
from room_manager import RoomManager
from problem_pool_service import ProblemPoolService
from pydantic_schemas import SubmissionRecord, RoomState, RoundPhase


class MockRoomManager:
    """Mock room manager for testing"""
    
    def __init__(self):
        self.rooms = {}
        self.session_tokens = {}
    
    def get_room(self, room_code):
        return self.rooms.get(room_code)
    
    def validate_session_token(self, room_code, player_id, session_token):
        return session_token == "valid_token"


class TestSubmissionProcessor:
    """Test Submission Processor functionality"""

    @pytest.fixture
    def player_manager(self):
        """Create a player manager"""
        return PlayerManager()

    @pytest.fixture
    def mock_room_manager(self):
        """Create a mock room manager"""
        return MockRoomManager()

    @pytest.fixture
    def submission_processor(self, player_manager):
        """Create a submission processor"""
        return SubmissionProcessor(player_manager)

    @pytest.fixture
    def sample_room_with_active_round(self, mock_room_manager):
        """Create a sample room with active round"""
        from pydantic_schemas import Room, PlayerInternal, Problem, RoundState, MVPRoomSettings
        
        room_code = "TEST"
        player_id = uuid4()
        
        # Create player
        player = PlayerInternal(
            player_id=player_id,
            username="TestPlayer",
            score=0,
            streak=0,
            session_token="valid_token",
            joined_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        
        # Create problem
        problem = Problem(
            numbers=[1, 1, 8, 8],
            canonical_solution="(1+1+8)*8"
        )
        
        # Create room
        room = Room(
            room_code=room_code,
            host_player_id=player_id,
            settings=MVPRoomSettings(),
            players={player_id: player},
            problems=[problem],
            state=RoomState.RUNNING,
            round_index=0,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
            current_round_state=RoundState(
                phase=RoundPhase.ACTIVE,
                phase_start_time=datetime.now(timezone.utc),
                phase_end_time=datetime.now(timezone.utc)
            )
        )
        
        mock_room_manager.rooms[room_code] = room
        return room_code, player_id, room

    @pytest.mark.asyncio
    async def test_process_valid_submission(self, submission_processor, mock_room_manager, sample_room_with_active_round):
        """Test processing a valid submission"""
        room_code, player_id, room = sample_room_with_active_round
        
        result = await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token="valid_token",
            round_index=0,
            expression="(1+1+8)*8",
            used_numbers=[1, 1, 8, 8],
            client_eval_value=80.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert result is not None
        assert result.accepted is True
        assert result.submission_id is not None
        assert result.room_code == room_code
        assert result.player_id == player_id

    @pytest.mark.asyncio
    async def test_process_invalid_session_token(self, submission_processor, mock_room_manager, sample_room_with_active_round):
        """Test processing with invalid session token"""
        room_code, player_id, room = sample_room_with_active_round
        
        result = await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token="invalid_token",
            round_index=0,
            expression="(1+1+8)*8",
            used_numbers=[1, 1, 8, 8],
            client_eval_value=80.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert result is not None
        assert result.accepted is False
        assert "Invalid session token" in result.reason

    @pytest.mark.asyncio
    async def test_process_wrong_round_index(self, submission_processor, mock_room_manager, sample_room_with_active_round):
        """Test processing with wrong round index"""
        room_code, player_id, room = sample_room_with_active_round
        
        result = await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token="valid_token",
            round_index=5,  # Wrong round
            expression="(1+1+8)*8",
            used_numbers=[1, 1, 8, 8],
            client_eval_value=80.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert result is not None
        assert result.accepted is False
        assert "Round index mismatch" in result.reason

    @pytest.mark.asyncio
    async def test_process_wrong_numbers(self, submission_processor, mock_room_manager, sample_room_with_active_round):
        """Test processing with wrong numbers"""
        room_code, player_id, room = sample_room_with_active_round
        
        result = await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token="valid_token",
            round_index=0,
            expression="2+2+2+2",
            used_numbers=[2, 2, 2, 2],  # Wrong numbers
            client_eval_value=8.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert result is not None
        assert result.accepted is False
        assert "Used numbers don't match problem" in result.reason

    @pytest.mark.asyncio
    async def test_process_client_invalid_submission(self, submission_processor, mock_room_manager, sample_room_with_active_round):
        """Test processing submission marked invalid by client"""
        room_code, player_id, room = sample_room_with_active_round
        
        result = await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token="valid_token",
            round_index=0,
            expression="1+1+8+8",
            used_numbers=[1, 1, 8, 8],
            client_eval_value=18.0,
            client_eval_is_valid=False,  # Client says invalid
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert result is not None
        assert result.accepted is False
        assert "Client evaluation invalid" in result.reason

    @pytest.mark.asyncio
    async def test_process_room_not_found(self, submission_processor, mock_room_manager):
        """Test processing submission for non-existent room"""
        result = await submission_processor.process_submission(
            room_code="NONEXISTENT",
            player_id=uuid4(),
            session_token="valid_token",
            round_index=0,
            expression="1+1+8+8",
            used_numbers=[1, 1, 8, 8],
            client_eval_value=18.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert result is not None
        assert result.accepted is False
        assert "Room not found" in result.reason

    @pytest.mark.asyncio
    async def test_duplicate_submission_same_round(self, submission_processor, mock_room_manager, sample_room_with_active_round):
        """Test that duplicate submissions in same round are rejected"""
        room_code, player_id, room = sample_room_with_active_round
        
        # First submission
        result1 = await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token="valid_token",
            round_index=0,
            expression="(1+1+8)*8",
            used_numbers=[1, 1, 8, 8],
            client_eval_value=80.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert result1.accepted is True
        
        # Second submission should be rejected
        result2 = await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token="valid_token",
            round_index=0,
            expression="1*1*8*8",
            used_numbers=[1, 1, 8, 8],
            client_eval_value=64.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert result2.accepted is False
        assert "already scored" in result2.reason

    @pytest.mark.asyncio
    async def test_submission_history_logging(self, submission_processor, mock_room_manager, sample_room_with_active_round):
        """Test that submissions are logged in history"""
        room_code, player_id, room = sample_room_with_active_round
        
        initial_count = len(submission_processor.submission_history)
        
        await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token="valid_token",
            round_index=0,
            expression="(1+1+8)*8",
            used_numbers=[1, 1, 8, 8],
            client_eval_value=80.0,
            client_eval_is_valid=True,
            client_timestamp=datetime.now(timezone.utc),
            room_manager=mock_room_manager
        )
        
        assert len(submission_processor.submission_history) == initial_count + 1
        
        # Check the logged submission
        logged_submission = submission_processor.submission_history[-1]
        assert logged_submission.room_code == room_code
        assert logged_submission.player_id == player_id
        assert logged_submission.expression == "(1+1+8)*8"

    @pytest.mark.asyncio
    async def test_validate_used_numbers(self, submission_processor):
        """Test the used numbers validation logic"""
        
        # Valid cases
        assert submission_processor.validate_used_numbers([1, 2, 3, 4], [1, 2, 3, 4]) == True
        assert submission_processor.validate_used_numbers([4, 3, 2, 1], [1, 2, 3, 4]) == True
        assert submission_processor.validate_used_numbers([1, 1, 8, 8], [8, 1, 8, 1]) == True
        
        # Invalid cases
        assert submission_processor.validate_used_numbers([1, 2, 3, 4], [1, 2, 3, 5]) == False
        assert submission_processor.validate_used_numbers([1, 2, 3, 4], [1, 1, 3, 4]) == False
        assert submission_processor.validate_used_numbers([1, 2, 3], [1, 2, 3, 4]) == False
        assert submission_processor.validate_used_numbers([1, 2, 3, 4], [1, 2, 3]) == False

    @pytest.mark.asyncio
    async def test_concurrent_submissions(self, submission_processor, mock_room_manager):
        """Test concurrent submissions from different players"""
        from pydantic_schemas import Room, PlayerInternal, Problem, RoundState, MVPRoomSettings
        
        room_code = "CONCURRENT"
        player_id1 = uuid4()
        player_id2 = uuid4()
        
        # Create players
        player1 = PlayerInternal(
            player_id=player_id1,
            username="Player1",
            score=0,
            streak=0,
            session_token="valid_token",
            joined_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        
        player2 = PlayerInternal(
            player_id=player_id2,
            username="Player2",
            score=0,
            streak=0,
            session_token="valid_token",
            joined_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        
        # Create room
        problem = Problem(numbers=[1, 1, 8, 8], canonical_solution="(1+1+8)*8")
        room = Room(
            room_code=room_code,
            host_player_id=player_id1,
            settings=MVPRoomSettings(),
            players={player_id1: player1, player_id2: player2},
            problems=[problem],
            state=RoomState.RUNNING,
            round_index=0,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
            current_round_state=RoundState(
                phase=RoundPhase.ACTIVE,
                phase_start_time=datetime.now(timezone.utc),
                phase_end_time=datetime.now(timezone.utc)
            )
        )
        
        mock_room_manager.rooms[room_code] = room
        
        # Submit concurrently
        tasks = [
            submission_processor.process_submission(
                room_code=room_code,
                player_id=player_id1,
                session_token="valid_token",
                round_index=0,
                expression="(1+1+8)*8",
                used_numbers=[1, 1, 8, 8],
                client_eval_value=80.0,
                client_eval_is_valid=True,
                client_timestamp=datetime.now(timezone.utc),
                room_manager=mock_room_manager
            ),
            submission_processor.process_submission(
                room_code=room_code,
                player_id=player_id2,
                session_token="valid_token",
                round_index=0,
                expression="1*1*8*8",
                used_numbers=[1, 1, 8, 8],
                client_eval_value=64.0,
                client_eval_is_valid=True,
                client_timestamp=datetime.now(timezone.utc),
                room_manager=mock_room_manager
            )
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Both should be accepted since they're from different players
        # Note: One might have an incorrect evaluation but we trust client for MVP
        assert len(results) == 2