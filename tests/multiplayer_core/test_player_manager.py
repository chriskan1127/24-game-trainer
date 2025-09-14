"""
Comprehensive tests for Player Manager component

Tests cover:
- Score calculation algorithms
- Player submission processing
- Round scoring and streak management
- Leaderboard generation
- Session validation
- Statistics and performance tracking
- Edge cases and error handling
"""

import pytest
import math
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock

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

from multiplayer_core.managers.player_manager import (
    PlayerManager, PlayerManagerError, InvalidScoreCalculationError,
    PlayerNotFoundError, RoundScoringError
)
from pydantic_schemas import PlayerInternal, PlayerPublic, SubmissionRecord


class TestPlayerManager:
    """Test suite for Player Manager"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.player_manager = PlayerManager()
        self.room_code = "TEST"
        
        # Create test players
        self.player1 = PlayerInternal(
            player_id=uuid4(),
            username="Player1",
            score=0,
            streak=0,
            session_token="token1",
            joined_at=datetime.now(timezone.utc)
        )
        
        self.player2 = PlayerInternal(
            player_id=uuid4(),
            username="Player2", 
            score=50,
            streak=3,
            session_token="token2",
            joined_at=datetime.now(timezone.utc)
        )
    
    # Score Calculation Tests
    
    def test_calculate_score_basic(self):
        """Test basic score calculation"""
        # Test with perfect timing (full time remaining)
        base, speed, streak = self.player_manager.calculate_score(
            time_left=30.0, time_limit=30.0, current_streak=0
        )
        
        assert base == 10  # Base points
        assert speed == 5  # Maximum speed bonus
        assert streak == 0  # No streak
    
    def test_calculate_score_with_streak(self):
        """Test score calculation with streak"""
        base, speed, streak = self.player_manager.calculate_score(
            time_left=15.0, time_limit=30.0, current_streak=2
        )
        
        assert base == 10
        assert speed == math.ceil((15.0 / 30.0) * 5)  # Should be 3
        assert streak == 2 * 2  # streak_bonus = streak * 2
    
    def test_calculate_score_no_time_left(self):
        """Test score calculation with no time remaining"""
        base, speed, streak = self.player_manager.calculate_score(
            time_left=0.0, time_limit=30.0, current_streak=1
        )
        
        assert base == 10
        assert speed == 0  # No speed bonus
        assert streak == 2  # Still get streak bonus
    
    def test_calculate_score_negative_time(self):
        """Test score calculation with negative time (grace period)"""
        base, speed, streak = self.player_manager.calculate_score(
            time_left=-5.0, time_limit=30.0, current_streak=0
        )
        
        assert base == 10
        assert speed == 0  # Negative time treated as 0
        assert streak == 0
    
    def test_calculate_score_various_timings(self):
        """Test score calculation with various time remainings"""
        test_cases = [
            (30.0, 5),  # Full time = max bonus
            (24.0, 4),  # 80% time = 4 bonus
            (15.0, 3),  # 50% time = 3 bonus  
            (6.0, 1),   # 20% time = 1 bonus
            (3.0, 1),   # 10% time = 1 bonus
            (0.1, 1),   # Tiny amount = 1 bonus
        ]
        
        for time_left, expected_bonus in test_cases:
            _, speed, _ = self.player_manager.calculate_score(
                time_left=time_left, time_limit=30.0, current_streak=0
            )
            assert speed == expected_bonus, f"Time {time_left} should give bonus {expected_bonus}, got {speed}"
    
    def test_calculate_score_invalid_params(self):
        """Test score calculation with invalid parameters"""
        # Invalid time limit
        with pytest.raises(InvalidScoreCalculationError):
            self.player_manager.calculate_score(15.0, time_limit=0)
        
        with pytest.raises(InvalidScoreCalculationError):
            self.player_manager.calculate_score(15.0, time_limit=-5)
        
        # Invalid streak
        with pytest.raises(InvalidScoreCalculationError):
            self.player_manager.calculate_score(15.0, time_limit=30.0, current_streak=-1)
    
    # Player Score Application Tests
    
    def test_apply_score_to_player(self):
        """Test applying calculated score to player"""
        initial_score = self.player1.score
        initial_streak = self.player1.streak
        
        points_awarded = self.player_manager.apply_score_to_player(
            self.player1, base_points=10, speed_bonus=3, streak_bonus=4
        )
        
        assert points_awarded == 17
        assert self.player1.score == initial_score + 17
        assert self.player1.streak == initial_streak + 1  # Streak incremented for correct answer
    
    def test_apply_score_zero_points_resets_streak(self):
        """Test that zero points resets streak"""
        self.player1.streak = 5
        
        self.player_manager.apply_score_to_player(
            self.player1, base_points=0, speed_bonus=0, streak_bonus=0
        )
        
        assert self.player1.streak == 0
    
    # Submission Processing Tests
    
    def test_process_submission_success(self):
        """Test successful submission processing"""
        submission = SubmissionRecord(
            room_code=self.room_code,
            round_index=0,
            player_id=self.player1.player_id,
            expression="1+2+3+4*6",
            used_numbers=[1, 2, 3, 4],
            client_eval_is_valid=True
        )
        
        points, player_scored = self.player_manager.process_submission(
            self.room_code, self.player1, submission, time_left=20.0
        )
        
        assert points > 0
        assert player_scored.player_id == self.player1.player_id
        assert player_scored.username == self.player1.username
        assert player_scored.time_left == 20.0
        assert submission.accepted is True
        assert submission.server_receive_time is not None
    
    def test_process_submission_already_scored(self):
        """Test processing submission when player already scored"""
        self.player_manager.mark_player_scored_this_round(self.room_code, self.player1.player_id)
        
        submission = SubmissionRecord(
            room_code=self.room_code,
            round_index=0,
            player_id=self.player1.player_id,
            expression="1+2+3+4*6",
            used_numbers=[1, 2, 3, 4],
            client_eval_is_valid=True
        )
        
        with pytest.raises(RoundScoringError):
            self.player_manager.process_submission(
                self.room_code, self.player1, submission, time_left=20.0
            )
    
    def test_process_submission_with_existing_streak(self):
        """Test submission processing with existing streak"""
        self.player1.streak = 3  # Player has a streak
        
        submission = SubmissionRecord(
            room_code=self.room_code,
            round_index=0,
            player_id=self.player1.player_id,
            expression="1+2+3+4*6",
            used_numbers=[1, 2, 3, 4],
            client_eval_is_valid=True
        )
        
        points, player_scored = self.player_manager.process_submission(
            self.room_code, self.player1, submission, time_left=15.0
        )
        
        # Should include streak bonus for previous streak
        expected_streak_bonus = 3 * 2  # 3 previous correct * 2 points each
        assert points >= 10 + expected_streak_bonus  # Base + streak + speed
        assert self.player1.streak == 4  # Streak incremented
    
    # Round Scoring Management Tests
    
    def test_mark_and_check_player_scored(self):
        """Test marking and checking if player scored this round"""
        assert not self.player_manager.has_player_scored_this_round(
            self.room_code, self.player1.player_id
        )
        
        self.player_manager.mark_player_scored_this_round(
            self.room_code, self.player1.player_id
        )
        
        assert self.player_manager.has_player_scored_this_round(
            self.room_code, self.player1.player_id
        )
    
    def test_reset_round_scoring(self):
        """Test resetting round scoring"""
        # Mark players as scored
        self.player_manager.mark_player_scored_this_round(self.room_code, self.player1.player_id)
        self.player_manager.mark_player_scored_this_round(self.room_code, self.player2.player_id)
        
        # Reset
        self.player_manager.reset_round_scoring(self.room_code)
        
        # Should be cleared
        assert not self.player_manager.has_player_scored_this_round(
            self.room_code, self.player1.player_id
        )
        assert not self.player_manager.has_player_scored_this_round(
            self.room_code, self.player2.player_id
        )
    
    def test_cleanup_room_scoring(self):
        """Test cleaning up room scoring data"""
        # Add some scoring data
        self.player_manager.mark_player_scored_this_round(self.room_code, self.player1.player_id)
        
        # Cleanup
        self.player_manager.cleanup_room_scoring(self.room_code)
        
        # Data should be removed
        assert self.room_code not in self.player_manager.players_scored_this_round
        assert self.room_code not in self.player_manager.round_submissions
    
    # Leaderboard and Scoring Tests
    
    def test_get_leaderboard(self):
        """Test leaderboard generation"""
        players = {
            self.player1.player_id: self.player1,  # Score: 0
            self.player2.player_id: self.player2,  # Score: 50
        }
        
        # Add a third player
        player3 = PlayerInternal(
            player_id=uuid4(),
            username="Player3",
            score=25,
            streak=1,
            session_token="token3",
            joined_at=datetime.now(timezone.utc)
        )
        players[player3.player_id] = player3
        
        leaderboard = self.player_manager.get_leaderboard(players)
        
        assert len(leaderboard) == 3
        assert leaderboard[0].username == "Player2"  # Highest score first
        assert leaderboard[0].score == 50
        assert leaderboard[1].username == "Player3"  # Second highest
        assert leaderboard[1].score == 25
        assert leaderboard[2].username == "Player1"  # Lowest score last
        assert leaderboard[2].score == 0
    
    def test_get_leaderboard_tie_breaking(self):
        """Test leaderboard tie-breaking by username"""
        # Create players with same score
        player_a = PlayerInternal(
            player_id=uuid4(),
            username="Alpha",
            score=100,
            streak=0,
            session_token="token_a",
            joined_at=datetime.now(timezone.utc)
        )
        
        player_z = PlayerInternal(
            player_id=uuid4(),
            username="Zulu",
            score=100,
            streak=0,
            session_token="token_z",
            joined_at=datetime.now(timezone.utc)
        )
        
        players = {
            player_a.player_id: player_a,
            player_z.player_id: player_z
        }
        
        leaderboard = self.player_manager.get_leaderboard(players)
        
        # Should be sorted by username when scores are tied
        assert leaderboard[0].username == "Alpha"
        assert leaderboard[1].username == "Zulu"
    
    def test_get_score_updates(self):
        """Test getting score updates"""
        players = {
            self.player1.player_id: self.player1,
            self.player2.player_id: self.player2
        }
        
        updates = self.player_manager.get_score_updates(players)
        
        assert len(updates) == 2
        assert any(u.player_id == self.player1.player_id and u.score == 0 for u in updates)
        assert any(u.player_id == self.player2.player_id and u.score == 50 for u in updates)
    
    def test_get_winners(self):
        """Test getting winners (tied for first place)"""
        # Create players with tied highest scores
        player3 = PlayerInternal(
            player_id=uuid4(),
            username="Player3",
            score=50,  # Tied with player2
            streak=1,
            session_token="token3",
            joined_at=datetime.now(timezone.utc)
        )
        
        players = {
            self.player1.player_id: self.player1,  # Score: 0
            self.player2.player_id: self.player2,  # Score: 50
            player3.player_id: player3              # Score: 50
        }
        
        winners = self.player_manager.get_winners(players)
        
        assert len(winners) == 2  # Two players tied for first
        winner_names = {w.username for w in winners}
        assert "Player2" in winner_names
        assert "Player3" in winner_names
        assert all(w.score == 50 for w in winners)
    
    # Player Management Tests
    
    def test_reset_player_score(self):
        """Test resetting player score and streak"""
        self.player2.score = 100
        self.player2.streak = 5
        
        self.player_manager.reset_player_score(self.player2)
        
        assert self.player2.score == 0
        assert self.player2.streak == 0
    
    def test_validate_player_in_room(self):
        """Test player validation in room"""
        # Mock room manager
        mock_room_manager = Mock()
        mock_room_manager.validate_session_token.return_value = True
        
        result = self.player_manager.validate_player_in_room(
            self.room_code, self.player1.player_id, self.player1.session_token, mock_room_manager
        )
        
        assert result is True
        mock_room_manager.validate_session_token.assert_called_once_with(
            self.room_code, self.player1.player_id, self.player1.session_token
        )
    
    # Statistics and Information Tests
    
    def test_get_player_stats_room_specific(self):
        """Test getting player statistics for specific room"""
        # Add some data
        self.player_manager.mark_player_scored_this_round(self.room_code, self.player1.player_id)
        
        stats = self.player_manager.get_player_stats(self.room_code)
        
        assert stats["room_code"] == self.room_code
        assert stats["players_scored_this_round"] == 1
        assert "submissions_this_round" in stats
    
    def test_get_player_stats_global(self):
        """Test getting global player statistics"""
        stats = self.player_manager.get_player_stats()
        
        assert "global_stats" in stats
        assert "scoring_config" in stats
        assert "total_score_calculations" in stats["global_stats"]
    
    def test_get_submission_history(self):
        """Test getting submission history"""
        # Initially empty
        history = self.player_manager.get_submission_history(self.room_code)
        assert len(history) == 0
        
        # Process a submission
        submission = SubmissionRecord(
            room_code=self.room_code,
            round_index=0,
            player_id=self.player1.player_id,
            expression="1+2+3+4*6",
            used_numbers=[1, 2, 3, 4],
            client_eval_is_valid=True
        )
        
        self.player_manager.process_submission(
            self.room_code, self.player1, submission, time_left=20.0
        )
        
        # Should have one submission
        history = self.player_manager.get_submission_history(self.room_code)
        assert len(history) == 1
        assert history[0].player_id == self.player1.player_id
    
    def test_calculate_player_performance(self):
        """Test calculating player performance metrics"""
        self.player2.score = 120
        self.player2.streak = 3
        
        performance = self.player_manager.calculate_player_performance(self.player2, total_rounds=10)
        
        assert performance["total_score"] == 120
        assert performance["current_streak"] == 3
        assert performance["average_points_per_round"] == 12.0
        assert performance["streak_ratio"] == 0.3
        assert performance["total_rounds_played"] == 10
    
    def test_calculate_player_performance_zero_rounds(self):
        """Test player performance calculation with zero rounds"""
        performance = self.player_manager.calculate_player_performance(self.player1, total_rounds=0)
        
        assert performance == {}
    
    # Edge Cases and Error Handling Tests
    
    def test_multiple_room_scoring(self):
        """Test handling multiple rooms simultaneously"""
        room2 = "TEST2"
        
        # Mark players in different rooms
        self.player_manager.mark_player_scored_this_round(self.room_code, self.player1.player_id)
        self.player_manager.mark_player_scored_this_round(room2, self.player1.player_id)
        
        # Should be tracked separately
        assert self.player_manager.has_player_scored_this_round(self.room_code, self.player1.player_id)
        assert self.player_manager.has_player_scored_this_round(room2, self.player1.player_id)
        
        # Reset one room shouldn't affect the other
        self.player_manager.reset_round_scoring(self.room_code)
        
        assert not self.player_manager.has_player_scored_this_round(self.room_code, self.player1.player_id)
        assert self.player_manager.has_player_scored_this_round(room2, self.player1.player_id)
    
    def test_scoring_with_extreme_values(self):
        """Test scoring with extreme values"""
        # Very high streak
        base, speed, streak = self.player_manager.calculate_score(
            time_left=30.0, time_limit=30.0, current_streak=100
        )
        
        assert base == 10
        assert speed == 5
        assert streak == 200  # 100 * 2
        
        # Very long time limit
        base, speed, streak = self.player_manager.calculate_score(
            time_left=300.0, time_limit=300.0, current_streak=0
        )
        
        assert base == 10
        assert speed == 5  # Still capped at max
        assert streak == 0
    
    def test_concurrent_submission_processing(self):
        """Test that submission processing handles race conditions"""
        # This is more of a conceptual test since we don't have actual concurrency
        # In a real scenario, you'd use threading or asyncio to test this
        
        submission1 = SubmissionRecord(
            room_code=self.room_code,
            round_index=0,
            player_id=self.player1.player_id,
            expression="1+2+3+4*6",
            used_numbers=[1, 2, 3, 4],
            client_eval_is_valid=True
        )
        
        # First submission should succeed
        self.player_manager.process_submission(
            self.room_code, self.player1, submission1, time_left=20.0
        )
        
        submission2 = SubmissionRecord(
            room_code=self.room_code,
            round_index=0,
            player_id=self.player1.player_id,
            expression="2+3+4+5*6",
            used_numbers=[2, 3, 4, 5],
            client_eval_is_valid=True
        )
        
        # Second submission from same player should fail
        with pytest.raises(RoundScoringError):
            self.player_manager.process_submission(
                self.room_code, self.player1, submission2, time_left=15.0
            )
    
    def test_statistics_tracking(self):
        """Test that statistics are properly tracked"""
        initial_stats = self.player_manager.get_player_stats()["global_stats"]
        
        # Calculate some scores
        self.player_manager.calculate_score(30.0, 30.0, 0)
        self.player_manager.calculate_score(15.0, 30.0, 2)
        
        new_stats = self.player_manager.get_player_stats()["global_stats"]
        
        assert new_stats["total_score_calculations"] == initial_stats["total_score_calculations"] + 2
        assert new_stats["total_bonuses_awarded"] >= initial_stats["total_bonuses_awarded"]


# Integration Test Class

class TestPlayerManagerIntegration:
    """Integration tests for Player Manager with realistic scenarios"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.player_manager = PlayerManager()
        self.room_code = "INTG"
        
        # Create multiple test players
        self.players = {}
        for i in range(4):
            player = PlayerInternal(
                player_id=uuid4(),
                username=f"Player{i+1}",
                score=0,
                streak=0,
                session_token=f"token{i+1}",
                joined_at=datetime.now(timezone.utc)
            )
            self.players[player.player_id] = player
    
    def test_full_round_simulation(self):
        """Test simulation of a complete round"""
        # Round 1: Everyone answers, different times
        times = [25.0, 20.0, 15.0, 10.0]  # Different answer times
        
        for i, (player_id, player) in enumerate(self.players.items()):
            submission = SubmissionRecord(
                room_code=self.room_code,
                round_index=0,
                player_id=player_id,
                expression=f"1+2+3+{i+4}*6",
                used_numbers=[1, 2, 3, i+4],
                client_eval_is_valid=True
            )
            
            points, player_scored = self.player_manager.process_submission(
                self.room_code, player, submission, time_left=times[i]
            )
            
            assert points > 0
            assert player.score > 0
            assert player.streak == 1
        
        # Check leaderboard after round 1
        leaderboard = self.player_manager.get_leaderboard(self.players)
        assert leaderboard[0].score > leaderboard[-1].score  # First answerer should have higher score
        
        # Start round 2
        self.player_manager.reset_round_scoring(self.room_code)
        
        # Round 2: Only 2 players answer
        for i, (player_id, player) in enumerate(list(self.players.items())[:2]):
            submission = SubmissionRecord(
                room_code=self.room_code,
                round_index=1,
                player_id=player_id,
                expression=f"2+3+4+{i+5}*6",
                used_numbers=[2, 3, 4, i+5],
                client_eval_is_valid=True
            )
            
            points, player_scored = self.player_manager.process_submission(
                self.room_code, player, submission, time_left=20.0
            )
            
            # Should get streak bonus now
            assert player.streak == 2
        
        # Players who didn't answer should have their streaks reset (in a real game)
        # This would be handled by the game logic when round ends
    
    def test_competitive_scoring_scenario(self):
        """Test competitive scoring with realistic timing"""
        player_list = list(self.players.values())
        
        # Simulate multiple rounds with different performance patterns
        scenarios = [
            # Round 1: Close race
            [(25.0, True), (24.0, True), (23.0, True), (22.0, True)],
            # Round 2: One fast answer, others slower
            [(28.0, True), (15.0, True), (10.0, True), (5.0, True)],
            # Round 3: Only two answer
            [(20.0, True), (18.0, True), (0.0, False), (0.0, False)],
            # Round 4: Mixed results
            [(30.0, True), (0.0, False), (12.0, True), (8.0, True)],
        ]
        
        for round_idx, round_scenario in enumerate(scenarios):
            self.player_manager.reset_round_scoring(self.room_code)
            
            for player_idx, (time_left, answered) in enumerate(round_scenario):
                player = player_list[player_idx]
                
                if answered:
                    submission = SubmissionRecord(
                        room_code=self.room_code,
                        round_index=round_idx,
                        player_id=player.player_id,
                        expression="1+2+3+18",
                        used_numbers=[1, 2, 3, 18],
                        client_eval_is_valid=True
                    )
                    
                    points, player_scored = self.player_manager.process_submission(
                        self.room_code, player, submission, time_left=time_left
                    )
                    
                    assert points > 0
                else:
                    # Simulate wrong answer or timeout - reset streak
                    player.streak = 0
        
        # Check final standings
        leaderboard = self.player_manager.get_leaderboard(self.players)
        
        # Verify leaderboard is sorted correctly
        for i in range(len(leaderboard) - 1):
            assert leaderboard[i].score >= leaderboard[i + 1].score
        
        # Performance analysis
        for player in player_list:
            performance = self.player_manager.calculate_player_performance(player, total_rounds=4)
            assert "average_points_per_round" in performance
            assert performance["total_rounds_played"] == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])