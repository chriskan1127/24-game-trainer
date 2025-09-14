"""
Player Manager Component

Handles player authentication, scoring, and session management for the multiplayer 24-game system.

Key responsibilities:
- Generate and validate session tokens for players
- Track player scores and streaks within rooms
- Handle player reconnection using room code + username
- Maintain player state (connected/disconnected/last_seen)
- Calculate final leaderboards and rankings
- Manage scoring rules and bonuses
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID
import asyncio

# Add project paths for imports
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from pydantic_schemas import (
    PlayerInternal, PlayerPublic, PlayerScoreUpdate, LeaderboardEntry,
    PlayerScored, SubmissionRecord
)

logger = logging.getLogger(__name__)


class PlayerManagerError(Exception):
    """Base exception for player manager operations"""
    pass


class InvalidScoreCalculationError(PlayerManagerError):
    """Raised when score calculation parameters are invalid"""
    pass


class PlayerNotFoundError(PlayerManagerError):
    """Raised when player is not found in the specified context"""
    pass


class RoundScoringError(PlayerManagerError):
    """Raised when there's an issue with round scoring logic"""
    pass


class PlayerManager:
    """
    Manages player state, scoring, and session tracking.
    
    Features:
    - Thread-safe player operations
    - Advanced scoring algorithm with speed bonuses and streaks
    - Session management and authentication
    - Comprehensive statistics tracking
    - Round-by-round submission tracking
    """
    
    def __init__(self):
        # Track players who have scored in the current round for each room
        self.players_scored_this_round: Dict[str, Set[UUID]] = {}  # room_code -> set of player_ids
        
        # Track submission details for scoring calculations
        self.round_submissions: Dict[str, List[SubmissionRecord]] = {}  # room_code -> submissions
        
        # Statistics tracking
        self.stats = {
            'total_score_calculations': 0,
            'total_bonuses_awarded': 0,
            'highest_speed_bonus': 0,
            'longest_streak': 0,
            'total_submissions_processed': 0
        }
        
        # Scoring configuration (following design spec)
        self.scoring_config = {
            'base_points': 10,
            'max_speed_bonus': 5,
            'streak_bonus_multiplier': 2,
            'default_time_limit': 30.0
        }
        
    def calculate_score(self, time_left: float, time_limit: float = None, current_streak: int = 0) -> Tuple[int, int, int]:
        """
        Calculate score components for a correct answer following the design specification.
        
        Formula from spec:
        - BASE = 10
        - MAX_SPEED_BONUS = 5 
        - speed_bonus = ceil((time_left_seconds / round_time_seconds) * MAX_SPEED_BONUS)
        - streak_bonus = 2 * streak_count (consecutive correct answers before this round)
        - points_gained = BASE + speed_bonus + streak_bonus
        
        Args:
            time_left: Seconds remaining when answer was submitted
            time_limit: Total time limit for the round (defaults to 30.0)
            current_streak: Number of consecutive correct answers before this round
            
        Returns:
            Tuple[int, int, int]: (base_points, speed_bonus, streak_bonus)
            
        Raises:
            InvalidScoreCalculationError: If parameters are invalid
        """
        if time_limit is None:
            time_limit = self.scoring_config['default_time_limit']
            
        if time_limit <= 0:
            raise InvalidScoreCalculationError("Time limit must be positive")
        
        if time_left < 0:
            time_left = 0  # Treat negative as 0 for grace period submissions
        
        if current_streak < 0:
            raise InvalidScoreCalculationError("Streak cannot be negative")
        
        # Base points for correct answer
        base_points = self.scoring_config['base_points']
        
        # Speed bonus calculation
        if time_left <= 0:
            speed_bonus = 0
        else:
            bonus_ratio = time_left / time_limit
            speed_bonus = min(
                self.scoring_config['max_speed_bonus'],
                math.ceil(bonus_ratio * self.scoring_config['max_speed_bonus'])
            )
        
        # Streak bonus (based on streak BEFORE this round)
        streak_bonus = current_streak * self.scoring_config['streak_bonus_multiplier']
        
        # Update statistics
        self.stats['total_score_calculations'] += 1
        if speed_bonus > 0:
            self.stats['total_bonuses_awarded'] += 1
        if speed_bonus > self.stats['highest_speed_bonus']:
            self.stats['highest_speed_bonus'] = speed_bonus
        if current_streak > self.stats['longest_streak']:
            self.stats['longest_streak'] = current_streak
        
        logger.debug(f"Score calculation: time_left={time_left:.2f}, time_limit={time_limit}, "
                    f"streak={current_streak} -> base={base_points}, speed={speed_bonus}, "
                    f"streak_bonus={streak_bonus}, total={base_points + speed_bonus + streak_bonus}")
        
        return base_points, speed_bonus, streak_bonus
    
    def apply_score_to_player(self, player: PlayerInternal, base_points: int, 
                             speed_bonus: int, streak_bonus: int) -> int:
        """
        Apply calculated score to a player and update their streak.
        
        Args:
            player: Player to update
            base_points: Base points earned
            speed_bonus: Speed bonus points
            streak_bonus: Streak bonus points (already calculated)
            
        Returns:
            int: Total points awarded
        """
        total_points = base_points + speed_bonus + streak_bonus
        player.score += total_points
        
        # Update streak: correct answer extends streak
        if base_points > 0:  # Only extend streak on correct answers
            player.streak += 1
        else:
            player.streak = 0
        
        logger.info(f"Applied {total_points} points to player {player.username} "
                   f"(base: {base_points}, speed: {speed_bonus}, streak_bonus: {streak_bonus})")
        
        return total_points
    
    def process_submission(self, room_code: str, player: PlayerInternal, 
                          submission: SubmissionRecord, time_left: float, 
                          time_limit: float = None) -> Tuple[int, PlayerScored]:
        """
        Process a player submission and calculate scoring.
        
        Args:
            room_code: Room code where submission occurred
            player: Player who submitted
            submission: Submission record
            time_left: Time remaining when submitted
            time_limit: Round time limit
            
        Returns:
            Tuple[int, PlayerScored]: (points_awarded, player_scored_info)
            
        Raises:
            RoundScoringError: If player already scored this round
        """
        if self.has_player_scored_this_round(room_code, player.player_id):
            raise RoundScoringError(f"Player {player.player_id} has already scored this round")
        
        # Calculate score components (streak is current streak BEFORE this round)
        current_streak_before = player.streak
        base_points, speed_bonus, streak_bonus = self.calculate_score(
            time_left, time_limit, current_streak_before
        )
        
        # Apply score to player
        total_points = self.apply_score_to_player(player, base_points, speed_bonus, streak_bonus)
        
        # Mark player as scored this round
        self.mark_player_scored_this_round(room_code, player.player_id)
        
        # Store submission
        if room_code not in self.round_submissions:
            self.round_submissions[room_code] = []
        
        submission.accepted = True
        submission.time_left_at_submission = time_left
        submission.speed_bonus_awarded = speed_bonus
        submission.points_awarded = total_points
        submission.server_receive_time = datetime.now(timezone.utc)
        
        self.round_submissions[room_code].append(submission)
        self.stats['total_submissions_processed'] += 1
        
        # Calculate submission rank
        submissions_this_round = [s for s in self.round_submissions[room_code] 
                                if s.accepted and s.server_receive_time]
        submissions_this_round.sort(key=lambda s: s.server_receive_time)
        submission_rank = next(i+1 for i, s in enumerate(submissions_this_round) 
                             if s.submission_id == submission.submission_id)
        
        # Create PlayerScored object
        player_scored = PlayerScored(
            player_id=player.player_id,
            username=player.username,
            points_gained=total_points,
            base_points=base_points,
            speed_bonus=speed_bonus,
            time_left=time_left,
            time_submitted=submission.server_receive_time,
            submission_rank=submission_rank
        )
        
        logger.info(f"Processed submission for {player.username} in room {room_code}: "
                   f"{total_points} points, rank #{submission_rank}")
        
        return total_points, player_scored
    
    def mark_player_scored_this_round(self, room_code: str, player_id: UUID):
        """Mark that a player has scored in the current round"""
        if room_code not in self.players_scored_this_round:
            self.players_scored_this_round[room_code] = set()
        self.players_scored_this_round[room_code].add(player_id)
    
    def has_player_scored_this_round(self, room_code: str, player_id: UUID) -> bool:
        """Check if a player has already scored in the current round"""
        return (room_code in self.players_scored_this_round and 
                player_id in self.players_scored_this_round[room_code])
    
    def reset_round_scoring(self, room_code: str):
        """Reset scoring tracking for a new round"""
        if room_code in self.players_scored_this_round:
            self.players_scored_this_round[room_code].clear()
        
        if room_code in self.round_submissions:
            self.round_submissions[room_code].clear()
            
        logger.debug(f"Reset round scoring for room {room_code}")
    
    def cleanup_room_scoring(self, room_code: str):
        """Clean up scoring data when a room is finished or removed"""
        if room_code in self.players_scored_this_round:
            del self.players_scored_this_round[room_code]
        
        if room_code in self.round_submissions:
            del self.round_submissions[room_code]
            
        logger.debug(f"Cleaned up scoring data for room {room_code}")
    
    def get_leaderboard(self, players: Dict[UUID, PlayerInternal]) -> List[LeaderboardEntry]:
        """
        Generate leaderboard from players, sorted by score (descending).
        
        Args:
            players: Dictionary of players in the room
            
        Returns:
            List[LeaderboardEntry]: Sorted leaderboard entries
        """
        leaderboard = []
        
        for player in players.values():
            entry = LeaderboardEntry(
                player_id=player.player_id,
                username=player.username,
                score=player.score
            )
            leaderboard.append(entry)
        
        # Sort by score (descending), then by username for tie-breaking
        leaderboard.sort(key=lambda x: (-x.score, x.username))
        
        return leaderboard
    
    def get_score_updates(self, players: Dict[UUID, PlayerInternal]) -> List[PlayerScoreUpdate]:
        """Get current score updates for all players"""
        updates = []
        
        for player in players.values():
            update = PlayerScoreUpdate(
                player_id=player.player_id,
                score=player.score,
                streak=player.streak
            )
            updates.append(update)
        
        return updates
    
    def get_round_results(self, room_code: str) -> List[PlayerScored]:
        """
        Get results for the current round showing who scored.
        
        Args:
            room_code: Room code to get results for
            
        Returns:
            List[PlayerScored]: List of players who scored this round, sorted by submission time
        """
        if room_code not in self.round_submissions:
            return []
        
        # Get accepted submissions from this round
        accepted_submissions = [s for s in self.round_submissions[room_code] if s.accepted]
        
        # Sort by submission time (fastest first)
        accepted_submissions.sort(key=lambda s: s.server_receive_time)
        
        # Create PlayerScored objects
        results = []
        for i, submission in enumerate(accepted_submissions):
            # This would need player data - simplified for now
            # In a real implementation, you'd need access to the room/players
            player_scored = PlayerScored(
                player_id=submission.player_id,
                username="Unknown",  # Would need lookup
                points_gained=submission.points_awarded or 0,
                base_points=10,  # Would calculate from submission
                speed_bonus=submission.speed_bonus_awarded or 0,
                time_left=submission.time_left_at_submission or 0,
                time_submitted=submission.server_receive_time,
                submission_rank=i + 1
            )
            results.append(player_scored)
        
        return results
    
    def validate_player_in_room(self, room_code: str, player_id: UUID, session_token: str, 
                              room_manager) -> bool:
        """
        Validate that a player belongs to a room with the correct session token.
        
        Args:
            room_code: Room code
            player_id: Player UUID
            session_token: Session token to validate
            room_manager: Room manager instance for validation
            
        Returns:
            bool: True if validation passes
        """
        return room_manager.validate_session_token(room_code, player_id, session_token)
    
    def reset_player_score(self, player: PlayerInternal):
        """Reset a player's score and streak (for testing or new games)"""
        player.score = 0
        player.streak = 0
        logger.info(f"Reset score for player {player.username}")
    
    def get_winners(self, players: Dict[UUID, PlayerInternal]) -> List[PlayerPublic]:
        """
        Get all players tied for first place.
        
        Args:
            players: Dictionary of players in the room
            
        Returns:
            List[PlayerPublic]: Players tied for highest score
        """
        if not players:
            return []
        
        max_score = max(player.score for player in players.values())
        winners = [player for player in players.values() if player.score == max_score]
        
        # Convert to public representation
        public_winners = [
            PlayerPublic(
                player_id=player.player_id,
                username=player.username,
                score=player.score,
                streak=player.streak
            )
            for player in winners
        ]
        
        return public_winners
    
    def get_player_stats(self, room_code: str = None) -> dict:
        """
        Get statistics about players and scoring.
        
        Args:
            room_code: Optional specific room to get stats for
            
        Returns:
            dict: Player statistics
        """
        if room_code:
            return {
                "room_code": room_code,
                "players_scored_this_round": len(self.players_scored_this_round.get(room_code, set())),
                "submissions_this_round": len(self.round_submissions.get(room_code, [])),
                "accepted_submissions": len([
                    s for s in self.round_submissions.get(room_code, []) if s.accepted
                ])
            }
        else:
            return {
                "total_rooms_tracked": len(self.players_scored_this_round),
                "global_stats": self.stats.copy(),
                "scoring_config": self.scoring_config.copy()
            }
    
    def get_submission_history(self, room_code: str) -> List[SubmissionRecord]:
        """
        Get all submissions for a room.
        
        Args:
            room_code: Room code
            
        Returns:
            List[SubmissionRecord]: All submissions for the room
        """
        return self.round_submissions.get(room_code, []).copy()
    
    async def mark_player_disconnected(self, player_id: UUID, room_code: str):
        """
        Mark a player as disconnected and handle any cleanup.
        
        Args:
            player_id: Player UUID
            room_code: Room code
        """
        # Additional disconnection logic could go here
        # For example, tracking disconnection statistics
        logger.info(f"Player {player_id} disconnected from room {room_code}")
    
    def calculate_player_performance(self, player: PlayerInternal, total_rounds: int) -> dict:
        """
        Calculate performance metrics for a player.
        
        Args:
            player: Player to analyze
            total_rounds: Total number of rounds played
            
        Returns:
            dict: Performance metrics
        """
        if total_rounds <= 0:
            return {}
        
        # Calculate average points per round
        avg_points = player.score / total_rounds if total_rounds > 0 else 0
        
        # Calculate streak performance
        streak_ratio = player.streak / total_rounds if total_rounds > 0 else 0
        
        return {
            "total_score": player.score,
            "current_streak": player.streak,
            "average_points_per_round": round(avg_points, 2),
            "streak_ratio": round(streak_ratio, 2),
            "total_rounds_played": total_rounds
        }