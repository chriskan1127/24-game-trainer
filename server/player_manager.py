"""
Player Manager Service
Handles player authentication, scoring, and session management
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from pydantic_schemas import PlayerInternal, PlayerPublic, PlayerScoreUpdate, LeaderboardEntry

logger = logging.getLogger(__name__)


class PlayerManager:
    """Manages player state, scoring, and session tracking"""
    
    def __init__(self):
        # Track players who have scored in the current round for each room
        self.players_scored_this_round: Dict[str, set] = {}  # room_code -> set of player_ids
        
    def calculate_score(self, time_left: float, time_limit: float = 30.0) -> tuple[int, int]:
        """
        Calculate base score and speed bonus for a correct answer
        Returns (base_points, speed_bonus)
        """
        base_points = 10
        
        # Speed bonus: up to 5 points based on time remaining
        if time_left <= 0:
            speed_bonus = 0
        else:
            # Formula: bonus = ceil((time_left / question_time) * 5)
            bonus_ratio = time_left / time_limit
            speed_bonus = min(5, max(0, int(bonus_ratio * 5) + (1 if bonus_ratio * 5 % 1 > 0 else 0)))
        
        return base_points, speed_bonus
    
    def add_score_to_player(self, player: PlayerInternal, base_points: int, speed_bonus: int) -> int:
        """Add score to a player and return the total points awarded"""
        total_points = base_points + speed_bonus
        player.score += total_points
        
        # Update streak (simple implementation - correct answer extends streak)
        if total_points > 0:
            player.streak += 1
        else:
            player.streak = 0
        
        logger.info(f"Added {total_points} points to player {player.username} (base: {base_points}, bonus: {speed_bonus})")
        return total_points
    
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
        logger.debug(f"Reset round scoring for room {room_code}")
    
    def cleanup_room_scoring(self, room_code: str):
        """Clean up scoring data when a room is finished or removed"""
        if room_code in self.players_scored_this_round:
            del self.players_scored_this_round[room_code]
        logger.debug(f"Cleaned up scoring data for room {room_code}")
    
    async def mark_player_disconnected(self, player_id: UUID, room_code: str):
        """Mark a player as disconnected"""
        # This is handled by the room manager, but we can add additional logic here
        # For example, tracking disconnection statistics
        logger.info(f"Player {player_id} disconnected from room {room_code}")
    
    def get_leaderboard(self, players: Dict[UUID, PlayerInternal]) -> List[LeaderboardEntry]:
        """Generate leaderboard from players, sorted by score (descending)"""
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
    
    def validate_player_in_room(self, room_code: str, player_id: UUID, session_token: str, 
                              room_manager) -> bool:
        """Validate that a player belongs to a room with the correct session token"""
        room = room_manager.get_room(room_code)
        if not room:
            return False
        
        if player_id not in room.players:
            return False
        
        player = room.players[player_id]
        return player.session_token == session_token
    
    def get_player_stats(self, room_code: str) -> dict:
        """Get statistics about players in a room"""
        stats = {
            "players_scored_this_round": len(self.players_scored_this_round.get(room_code, set())),
            "total_rooms_tracked": len(self.players_scored_this_round)
        }
        return stats
    
    def reset_player_score(self, player: PlayerInternal):
        """Reset a player's score and streak (for testing or new games)"""
        player.score = 0
        player.streak = 0
        logger.info(f"Reset score for player {player.username}")
    
    def get_winner_count(self, players: Dict[UUID, PlayerInternal]) -> int:
        """Get the number of players tied for first place"""
        if not players:
            return 0
        
        max_score = max(player.score for player in players.values())
        winners = [player for player in players.values() if player.score == max_score]
        return len(winners)
    
    def get_winners(self, players: Dict[UUID, PlayerInternal]) -> List[PlayerPublic]:
        """Get all players tied for first place"""
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