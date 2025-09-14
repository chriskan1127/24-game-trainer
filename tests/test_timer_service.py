"""
Test cases for Timer Service
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
server_dir = os.path.join(project_root, 'server')

if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from timer_service import TimerService


class MockGameStateManager:
    """Mock game state manager for testing"""
    
    def __init__(self):
        self.countdown_complete_calls = []
        self.round_timeout_calls = []
        self.results_complete_calls = []
        
    async def handle_countdown_complete(self, room_code):
        self.countdown_complete_calls.append(room_code)
        
    async def handle_round_timeout(self, room_code):
        self.round_timeout_calls.append(room_code)
        
    async def handle_results_complete(self, room_code):
        self.results_complete_calls.append(room_code)


class TestTimerService:
    """Test Timer Service functionality"""

    @pytest.fixture
    def timer_service(self):
        """Create a timer service"""
        return TimerService()

    @pytest.fixture
    def mock_game_state_manager(self):
        """Create mock game state manager"""
        return MockGameStateManager()

    @pytest.fixture
    def timer_with_game_manager(self, timer_service, mock_game_state_manager):
        """Create timer service with mock game state manager"""
        timer_service.set_game_state_manager(mock_game_state_manager)
        return timer_service, mock_game_state_manager

    @pytest.mark.asyncio
    async def test_schedule_countdown(self, timer_with_game_manager):
        """Test scheduling a countdown timer"""
        timer_service, game_manager = timer_with_game_manager
        
        room_code = "TEST"
        countdown_seconds = 1  # Short time for testing
        
        # Schedule countdown
        timer_id = await timer_service.schedule_countdown(room_code, countdown_seconds)
        
        # Timer should be active
        assert timer_id in timer_service.active_timers
        
        # Wait for countdown to complete
        await asyncio.sleep(countdown_seconds + 0.1)
        
        # Game manager should have been called
        assert room_code in game_manager.countdown_complete_calls
        
        # Timer should be cleaned up
        assert timer_id not in timer_service.active_timers

    @pytest.mark.asyncio
    async def test_schedule_round_timer(self, timer_with_game_manager):
        """Test scheduling a round timer"""
        timer_service, game_manager = timer_with_game_manager
        
        room_code = "TEST"
        round_seconds = 1  # Short time for testing
        
        # Schedule round timer
        timer_id = await timer_service.schedule_round_timer(room_code, round_seconds)
        
        # Timer should be active
        assert timer_id in timer_service.active_timers
        
        # Wait for timer to complete
        await asyncio.sleep(round_seconds + 0.1)
        
        # Game manager should have been called
        assert room_code in game_manager.round_timeout_calls
        
        # Timer should be cleaned up
        assert timer_id not in timer_service.active_timers

    @pytest.mark.asyncio
    async def test_schedule_results_timer(self, timer_with_game_manager):
        """Test scheduling a results display timer"""
        timer_service, game_manager = timer_with_game_manager
        
        room_code = "TEST"
        results_seconds = 1  # Short time for testing
        
        # Schedule results timer
        timer_id = await timer_service.schedule_results_timer(room_code, results_seconds)
        
        # Timer should be active
        assert timer_id in timer_service.active_timers
        
        # Wait for timer to complete
        await asyncio.sleep(results_seconds + 0.1)
        
        # Game manager should have been called
        assert room_code in game_manager.results_complete_calls
        
        # Timer should be cleaned up
        assert timer_id not in timer_service.active_timers

    @pytest.mark.asyncio
    async def test_cancel_timer(self, timer_service):
        """Test canceling a timer"""
        room_code = "TEST"
        
        # Schedule a long timer
        timer_id = await timer_service.schedule_countdown(room_code, 10)
        
        # Timer should be active
        assert timer_id in timer_service.active_timers
        
        # Cancel the timer
        await timer_service.cancel_timer(timer_id)
        
        # Timer should be removed
        assert timer_id not in timer_service.active_timers

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_timer(self, timer_service):
        """Test canceling a timer that doesn't exist"""
        # Should not raise an exception
        await timer_service.cancel_timer("nonexistent_timer")

    @pytest.mark.asyncio
    async def test_cancel_all_timers_for_room(self, timer_service):
        """Test canceling all timers for a specific room"""
        room_code = "TEST"
        
        # Schedule multiple timers for the room
        timer1 = await timer_service.schedule_countdown(room_code, 10)
        timer2 = await timer_service.schedule_round_timer(room_code, 10)
        timer3 = await timer_service.schedule_results_timer(room_code, 10)
        
        # Schedule timer for different room
        timer4 = await timer_service.schedule_countdown("OTHER", 10)
        
        # All timers should be active
        assert timer1 in timer_service.active_timers
        assert timer2 in timer_service.active_timers
        assert timer3 in timer_service.active_timers
        assert timer4 in timer_service.active_timers
        
        # Cancel all timers for TEST room
        await timer_service.cancel_all_timers_for_room(room_code)
        
        # TEST room timers should be canceled
        assert timer1 not in timer_service.active_timers
        assert timer2 not in timer_service.active_timers
        assert timer3 not in timer_service.active_timers
        
        # OTHER room timer should still be active
        assert timer4 in timer_service.active_timers
        
        # Clean up
        await timer_service.cancel_timer(timer4)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_timers(self, timer_with_game_manager):
        """Test multiple concurrent timers"""
        timer_service, game_manager = timer_with_game_manager
        
        # Schedule multiple timers with different durations
        rooms = ["ROOM1", "ROOM2", "ROOM3"]
        durations = [0.1, 0.2, 0.3]
        
        timer_ids = []
        for room, duration in zip(rooms, durations):
            timer_id = await timer_service.schedule_countdown(room, duration)
            timer_ids.append(timer_id)
        
        # All timers should be active
        for timer_id in timer_ids:
            assert timer_id in timer_service.active_timers
        
        # Wait for all timers to complete
        await asyncio.sleep(0.4)
        
        # All game manager callbacks should have been called
        for room in rooms:
            assert room in game_manager.countdown_complete_calls
        
        # All timers should be cleaned up
        for timer_id in timer_ids:
            assert timer_id not in timer_service.active_timers

    @pytest.mark.asyncio
    async def test_timer_without_game_manager(self, timer_service):
        """Test timer behavior when game manager is not set"""
        room_code = "TEST"
        
        # Schedule countdown without game manager
        timer_id = await timer_service.schedule_countdown(room_code, 0.1)
        
        # Timer should be active
        assert timer_id in timer_service.active_timers
        
        # Wait for timer to complete
        await asyncio.sleep(0.2)
        
        # Timer should be cleaned up even without game manager
        assert timer_id not in timer_service.active_timers

    @pytest.mark.asyncio
    async def test_cleanup_on_shutdown(self, timer_service):
        """Test cleanup method for shutting down service"""
        room_code = "TEST"
        
        # Schedule several timers
        timer_ids = []
        for i in range(3):
            timer_id = await timer_service.schedule_countdown(f"{room_code}{i}", 10)
            timer_ids.append(timer_id)
        
        # All should be active
        for timer_id in timer_ids:
            assert timer_id in timer_service.active_timers
        
        # Cleanup all
        await timer_service.cleanup()
        
        # All should be canceled
        for timer_id in timer_ids:
            assert timer_id not in timer_service.active_timers

    @pytest.mark.asyncio
    async def test_timer_precision(self, timer_with_game_manager):
        """Test timer precision"""
        timer_service, game_manager = timer_with_game_manager
        
        room_code = "TEST"
        expected_duration = 0.1
        
        # Record start time
        start_time = asyncio.get_event_loop().time()
        
        # Schedule timer
        await timer_service.schedule_countdown(room_code, expected_duration)
        
        # Wait for completion
        await asyncio.sleep(expected_duration + 0.05)
        
        # Check that callback was called
        assert room_code in game_manager.countdown_complete_calls
        
        # The actual duration should be close to expected
        # (allowing for some variance due to system scheduling)
        end_time = asyncio.get_event_loop().time()
        actual_duration = end_time - start_time
        
        # Should be within reasonable tolerance
        assert abs(actual_duration - expected_duration) < 0.05

    @pytest.mark.asyncio
    async def test_timer_ids_are_unique(self, timer_service):
        """Test that timer IDs are unique"""
        room_code = "TEST"
        
        # Schedule multiple timers
        timer_ids = []
        for i in range(10):
            timer_id = await timer_service.schedule_countdown(room_code, 10)
            timer_ids.append(timer_id)
        
        # All IDs should be unique
        assert len(set(timer_ids)) == len(timer_ids)
        
        # Clean up
        for timer_id in timer_ids:
            await timer_service.cancel_timer(timer_id)

    @pytest.mark.asyncio
    async def test_get_active_timers_for_room(self, timer_service):
        """Test getting active timers for a specific room"""
        room_code = "TEST"
        other_room = "OTHER"
        
        # Schedule timers for different rooms
        timer1 = await timer_service.schedule_countdown(room_code, 10)
        timer2 = await timer_service.schedule_round_timer(room_code, 10)
        timer3 = await timer_service.schedule_countdown(other_room, 10)
        
        # Get active timers for TEST room
        test_timers = timer_service.get_active_timers_for_room(room_code)
        
        # Should return timers for TEST room only
        assert timer1 in test_timers
        assert timer2 in test_timers
        assert timer3 not in test_timers
        
        # Clean up
        await timer_service.cleanup()

    def test_timer_service_stats(self, timer_service):
        """Test getting timer service statistics"""
        stats = timer_service.get_stats()
        
        # Should return dictionary with statistics
        assert isinstance(stats, dict)
        assert "active_timers" in stats
        assert "total_timers_scheduled" in stats
        assert "total_timers_completed" in stats
        assert "total_timers_cancelled" in stats
        
        # Values should be non-negative
        for key, value in stats.items():
            if isinstance(value, int):
                assert value >= 0