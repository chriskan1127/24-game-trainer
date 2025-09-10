"""
Submission Processor Service
Validates and scores player answer submissions
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
plans_dir = os.path.join(project_root, 'plans')
lib_dir = os.path.join(project_root, 'lib')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from pydantic_schemas import SubmissionRecord, RoundPhase
from solve_24 import Solution

logger = logging.getLogger(__name__)


class SubmissionProcessor:
    """Processes and validates player submissions"""
    
    def __init__(self, player_manager):
        self.player_manager = player_manager
        self.submission_history = []  # Store all submissions for debugging/analysis
    
    async def process_submission(self, room_code: str, player_id: UUID, session_token: str,
                               round_index: int, expression: str, used_numbers: list,
                               client_eval_value: Optional[float], client_eval_is_valid: bool,
                               client_timestamp: Optional[datetime], room_manager=None) -> Optional[SubmissionRecord]:
        """
        Process a player's answer submission
        Returns SubmissionRecord if successful, None if rejected
        """
        
        server_receive_time = datetime.now(timezone.utc)
        
        # Create submission record
        submission = SubmissionRecord(
            submission_id=uuid4(),
            room_code=room_code,
            round_index=round_index,
            player_id=player_id,
            expression=expression,
            used_numbers=used_numbers,
            client_eval_value=client_eval_value,
            client_eval_is_valid=client_eval_is_valid,
            client_timestamp=client_timestamp,
            server_receive_time=server_receive_time,
            accepted=False,
            reason=None
        )
        
        try:
            # Validate room manager dependency
            if not room_manager:
                submission.reason = "Room manager not available"
                self.submission_history.append(submission)
                return submission
            
            # Validate session token
            if not room_manager.validate_session_token(room_code, player_id, session_token):
                submission.reason = "Invalid session token"
                self.submission_history.append(submission)
                logger.warning(f"Invalid session token for player {player_id} in room {room_code}")
                return submission
            
            # Get room and validate state
            room = room_manager.get_room(room_code)
            if not room:
                submission.reason = "Room not found"
                self.submission_history.append(submission)
                return submission
            
            # Check if game is in active phase
            if (not room.current_round_state or 
                room.current_round_state.phase != RoundPhase.ACTIVE):
                submission.reason = "Round not in active phase"
                self.submission_history.append(submission)
                return submission
            
            # Check if this is the correct round
            if round_index != room.round_index:
                submission.reason = f"Wrong round index: expected {room.round_index}, got {round_index}"
                self.submission_history.append(submission)
                return submission
            
            # Check if player has already scored this round
            if self.player_manager.has_player_scored_this_round(room_code, player_id):
                submission.reason = "Player already scored this round"
                self.submission_history.append(submission)
                return submission
            
            # Calculate time remaining
            time_remaining = self._calculate_time_remaining(room.current_round_state)
            if time_remaining <= 0:
                submission.reason = "Round time expired"
                self.submission_history.append(submission)
                return submission
            
            submission.time_left_at_submission = time_remaining
            
            # Get current problem
            if round_index >= len(room.problems):
                submission.reason = "Invalid round index"
                self.submission_history.append(submission)
                return submission
            
            current_problem = room.problems[round_index]
            
            # For MVP: Accept client validation (as per design spec)
            # In production, we would also do server-side validation
            if not client_eval_is_valid:
                submission.reason = "Client reported invalid solution"
                self.submission_history.append(submission)
                return submission
            
            # Optional: Server-side validation for extra security
            if not self._validate_solution_server_side(used_numbers, current_problem.numbers):
                submission.reason = "Numbers don't match problem"
                self.submission_history.append(submission)
                return submission
            
            # Calculate score
            base_points, speed_bonus = self.player_manager.calculate_score(
                time_remaining, room.settings.time_per_round_seconds
            )
            
            submission.speed_bonus_awarded = speed_bonus
            submission.points_awarded = base_points + speed_bonus
            submission.accepted = True
            submission.reason = "Accepted"
            
            # Update player score
            player = room.players[player_id]
            self.player_manager.add_score_to_player(player, base_points, speed_bonus)
            
            # Mark player as having scored this round
            self.player_manager.mark_player_scored_this_round(room_code, player_id)
            
            # Note: With on-demand problem generation, we no longer track per-problem statistics
            # since problems are generated fresh for each game and not reused
            
            self.submission_history.append(submission)
            
            logger.info(f"Accepted submission from player {player_id} in room {room_code}: "
                       f"{base_points + speed_bonus} points ({base_points} base + {speed_bonus} speed bonus)")
            
            return submission
            
        except Exception as e:
            submission.reason = f"Processing error: {str(e)}"
            submission.accepted = False
            self.submission_history.append(submission)
            logger.error(f"Error processing submission from player {player_id} in room {room_code}: {e}")
            return submission
    
    def _calculate_time_remaining(self, round_state) -> float:
        """Calculate time remaining in the current round"""
        if not round_state or round_state.phase != RoundPhase.ACTIVE:
            return 0.0
        
        now = datetime.now(timezone.utc)
        time_remaining = (round_state.phase_end_time - now).total_seconds()
        return max(0.0, time_remaining)
    
    def _validate_solution_server_side(self, used_numbers: list, problem_numbers: list) -> bool:
        """Basic server-side validation that used numbers match problem numbers"""
        try:
            # Check that used numbers match the problem numbers (as multisets)
            if sorted(used_numbers) != sorted(problem_numbers):
                return False
            
            # Optional: Additional validation using the solver
            # For MVP, we trust client validation, but this could be enhanced
            solver = Solution(used_numbers, target=24)
            return solver.is_valid_input()
            
        except Exception as e:
            logger.error(f"Error in server-side validation: {e}")
            return False
    
    def _evaluate_expression_server_side(self, expression: str, used_numbers: list) -> tuple[bool, float]:
        """
        Server-side expression evaluation (not used in MVP but available for future)
        Returns (is_valid, result)
        """
        try:
            # This would require parsing the expression and validating it
            # For MVP, we trust client evaluation
            # In production, this would be a full mathematical expression parser
            return True, 24.0
        except Exception as e:
            logger.error(f"Error evaluating expression '{expression}': {e}")
            return False, 0.0
    
    def get_submission_stats(self, room_code: Optional[str] = None) -> dict:
        """Get statistics about submissions"""
        if room_code:
            room_submissions = [s for s in self.submission_history if s.room_code == room_code]
            submissions = room_submissions
        else:
            submissions = self.submission_history
        
        if not submissions:
            return {
                "total_submissions": 0,
                "accepted_submissions": 0,
                "rejection_rate": 0.0,
                "average_time_left": 0.0
            }
        
        accepted = [s for s in submissions if s.accepted]
        rejected = [s for s in submissions if not s.accepted]
        
        # Calculate average time left for accepted submissions
        accepted_with_time = [s for s in accepted if s.time_left_at_submission is not None]
        avg_time_left = (sum(s.time_left_at_submission for s in accepted_with_time) / 
                        len(accepted_with_time)) if accepted_with_time else 0.0
        
        # Group rejections by reason
        rejection_reasons = {}
        for s in rejected:
            reason = s.reason or "Unknown"
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        
        return {
            "total_submissions": len(submissions),
            "accepted_submissions": len(accepted),
            "rejected_submissions": len(rejected),
            "acceptance_rate": len(accepted) / len(submissions) if submissions else 0.0,
            "rejection_rate": len(rejected) / len(submissions) if submissions else 0.0,
            "average_time_left": avg_time_left,
            "rejection_reasons": rejection_reasons
        }
    
    def clear_submission_history(self, room_code: Optional[str] = None):
        """Clear submission history (for cleanup or testing)"""
        if room_code:
            self.submission_history = [s for s in self.submission_history if s.room_code != room_code]
            logger.info(f"Cleared submission history for room {room_code}")
        else:
            count = len(self.submission_history)
            self.submission_history.clear()
            logger.info(f"Cleared all submission history ({count} records)")
    
    def get_recent_submissions(self, room_code: str, limit: int = 10) -> list:
        """Get recent submissions for a room"""
        room_submissions = [s for s in self.submission_history if s.room_code == room_code]
        # Sort by server receive time, most recent first
        room_submissions.sort(key=lambda x: x.server_receive_time, reverse=True)
        return room_submissions[:limit]