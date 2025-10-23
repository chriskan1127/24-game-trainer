"""
Game State Manager Service
Controls game flow, round progression, and timing
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from pydantic_schemas import (
    RoomState, RoundPhase, RoundState,
    CountdownStartMessage, CountdownStartPayload,
    RoundStartMessage, RoundStartPayload,
    RoundEndMessage, RoundEndPayload,
    GameEndMessage, GameEndPayload,
    PlayerScored, PlayerScoreUpdate, LeaderboardEntry
)

logger = logging.getLogger(__name__)


class GameStateManager:
    """Manages game flow and state transitions"""

    def __init__(self, room_manager, player_manager, message_broadcaster, timer_service):
        self.room_manager = room_manager
        self.player_manager = player_manager
        self.message_broadcaster = message_broadcaster
        self.timer_service = timer_service
        # Track submissions by room and round: {room_code: {round_index: [SubmissionRecord]}}
        self.round_submissions = {}
        
    async def start_game(self, room_code: str, host_player_id: UUID, session_token: str):
        """Start a game in the specified room (host only)"""
        # Validate host permissions
        if not self.room_manager.validate_session_token(room_code, host_player_id, session_token):
            raise ValueError("Invalid session token")
        
        if not self.room_manager.is_host(room_code, host_player_id):
            raise ValueError("Only the host can start the game")
        
        room = self.room_manager.get_room(room_code)
        if not room:
            raise ValueError("Room not found")
        
        if room.state != RoomState.LOBBY:
            raise ValueError("Game cannot be started - room not in lobby state")
        
        if len(room.players) < 2:
            raise ValueError("Need at least 2 players to start the game")
        
        # Transition room to running state
        room.state = RoomState.RUNNING
        room.round_index = 0
        
        # Reset player scores and streaks for new game
        for player in room.players.values():
            self.player_manager.reset_player_score(player)
        
        # Start the first round
        await self.start_round(room_code)
        
        logger.info(f"Game started in room {room_code} by host {host_player_id}")
    
    def record_submission(self, room_code: str, round_index: int, submission):
        """Record a submission for later use in round results"""
        if room_code not in self.round_submissions:
            self.round_submissions[room_code] = {}
        if round_index not in self.round_submissions[room_code]:
            self.round_submissions[room_code][round_index] = []
        self.round_submissions[room_code][round_index].append(submission)

    async def start_round(self, room_code: str):
        """Start a new round with countdown"""
        room = self.room_manager.get_room(room_code)
        if not room:
            logger.error(f"Cannot start round - room {room_code} not found")
            return

        if room.round_index >= len(room.problems):
            # Game is finished
            await self.end_game(room_code)
            return

        # Reset round scoring
        self.player_manager.reset_round_scoring(room_code)
        
        # Start countdown phase
        countdown_seconds = room.settings.countdown_seconds
        now = datetime.now(timezone.utc)
        countdown_end = now + timedelta(seconds=countdown_seconds)
        
        room.current_round_state = RoundState(
            phase=RoundPhase.COUNTDOWN,
            phase_start_time=now,
            phase_end_time=countdown_end
        )
        
        # Broadcast countdown start
        countdown_message = CountdownStartMessage(
            type="countdown.start",
            payload=CountdownStartPayload(
                round_index=room.round_index,
                countdown_seconds=countdown_seconds,
                server_time=now
            )
        )
        
        await self.message_broadcaster.broadcast_to_room(room_code, countdown_message, self.room_manager)
        
        # Schedule countdown timer
        await self.timer_service.schedule_countdown(room_code, countdown_seconds)
        
        logger.info(f"Started countdown for round {room.round_index + 1} in room {room_code}")
    
    async def handle_countdown_complete(self, room_code: str):
        """Handle countdown completion and start active round"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Start active phase
        round_duration = room.settings.time_per_round_seconds
        now = datetime.now(timezone.utc)
        round_end = now + timedelta(seconds=round_duration)
        
        room.current_round_state = RoundState(
            phase=RoundPhase.ACTIVE,
            phase_start_time=now,
            phase_end_time=round_end,
            round_start_time=now,
            round_end_time=round_end
        )
        
        # Get current problem
        current_problem = room.problems[room.round_index]
        
        # Broadcast round start
        round_start_message = RoundStartMessage(
            type="round.start",
            payload=RoundStartPayload(
                round_index=room.round_index,
                problem_id=current_problem.problem_id,
                numbers=current_problem.numbers,
                time_limit_seconds=round_duration,
                server_time=now,
                round_end=round_end
            )
        )
        
        await self.message_broadcaster.broadcast_to_room(room_code, round_start_message, self.room_manager)
        
        # Schedule round timer
        await self.timer_service.schedule_round_timer(room_code, round_duration)
        
        logger.info(f"Started active round {room.round_index + 1} in room {room_code}")
    
    async def handle_round_timeout(self, room_code: str):
        """Handle round timeout - end the round"""
        await self.end_round(room_code)
    
    async def end_round(self, room_code: str):
        """End the current round and show results"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Transition to results phase
        results_duration = room.settings.results_display_seconds
        now = datetime.now(timezone.utc)
        results_end = now + timedelta(seconds=results_duration)
        
        room.current_round_state = RoundState(
            phase=RoundPhase.RESULTS,
            phase_start_time=now,
            phase_end_time=results_end
        )
        
        # Get current problem and solution
        current_problem = room.problems[room.round_index]

        # Get submissions for this round
        round_submissions_list = []
        if room_code in self.round_submissions and room.round_index in self.round_submissions[room_code]:
            round_submissions_list = self.round_submissions[room_code][room.round_index]

        # Generate list of players who scored this round
        players_correct = []
        for player_id, player in room.players.items():
            if self.player_manager.has_player_scored_this_round(room_code, player_id):
                # Find the submission for this player
                submission = next((s for s in round_submissions_list if s.player_id == player_id and s.accepted), None)

                if submission and submission.points_awarded is not None:
                    # Use actual submission data
                    # base_points is always 10 (constant defined in player_manager.calculate_score)
                    base_points = 10
                    speed_bonus = submission.speed_bonus_awarded if submission.speed_bonus_awarded is not None else 0

                    # Ensure points_awarded matches base_points + speed_bonus for validation
                    # If there's a mismatch, recalculate points_gained from components
                    expected_total = base_points + speed_bonus
                    points_gained = expected_total

                    if submission.points_awarded != expected_total:
                        logger.warning(
                            f"Points mismatch for player {player_id} in round {room.round_index}: "
                            f"submission.points_awarded={submission.points_awarded} but "
                            f"base_points ({base_points}) + speed_bonus ({speed_bonus}) = {expected_total}. "
                            f"Using calculated total {expected_total}."
                        )

                    players_correct.append(PlayerScored(
                        player_id=player_id,
                        username=player.username,
                        points_gained=points_gained,
                        base_points=base_points,
                        speed_bonus=speed_bonus,
                        time_left=submission.time_left_at_submission or 0.0,
                        time_submitted=submission.server_receive_time or now,
                        submission_rank=len(players_correct) + 1
                    ))
                else:
                    # Fallback if submission not found (shouldn't happen)
                    logger.warning(f"No submission found for player {player_id} who scored in round {room.round_index}")
                    players_correct.append(PlayerScored(
                        player_id=player_id,
                        username=player.username,
                        points_gained=10,
                        base_points=10,
                        speed_bonus=0,
                        time_left=0.0,
                        time_submitted=now,
                        submission_rank=len(players_correct) + 1
                    ))
        
        # Get updated scores
        updated_scores = self.player_manager.get_score_updates(room.players)

        # Get current leaderboard
        leaderboard = self.player_manager.get_leaderboard(room.players)

        # Broadcast round end
        round_end_message = RoundEndMessage(
            type="round.end",
            payload=RoundEndPayload(
                round_index=room.round_index,
                problem_id=current_problem.problem_id,
                canonical_solution=current_problem.canonical_solution,
                players_correct=players_correct,
                updated_scores=updated_scores,
                leaderboard=leaderboard
            )
        )
        
        await self.message_broadcaster.broadcast_to_room(room_code, round_end_message, self.room_manager)
        
        # Schedule results timer
        await self.timer_service.schedule_results_timer(room_code, results_duration)
        
        logger.info(f"Ended round {room.round_index + 1} in room {room_code}, {len(players_correct)} players scored")
    
    async def handle_results_complete(self, room_code: str):
        """Handle results display completion - move to next round or end game"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Move to next round
        room.round_index += 1
        
        # Check if game is complete
        if room.round_index >= room.settings.rounds:
            await self.end_game(room_code)
        else:
            await self.start_round(room_code)
    
    async def end_game(self, room_code: str):
        """End the game and show final results"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Transition room to finished state
        room.state = RoomState.FINISHED
        room.current_round_state = None
        
        # Cancel any active timers for this room
        self.timer_service.cancel_room_timers(room_code)
        
        # Generate final leaderboard
        leaderboard = self.player_manager.get_leaderboard(room.players)
        
        # Broadcast game end
        game_end_message = GameEndMessage(
            type="game.end",
            payload=GameEndPayload(
                leaderboard=leaderboard,
                most_correct=None,  # Could be implemented with problem statistics
                least_correct=None  # Could be implemented with problem statistics
            )
        )
        
        await self.message_broadcaster.broadcast_to_room(room_code, game_end_message, self.room_manager)
        
        # Clean up player scoring data
        self.player_manager.cleanup_room_scoring(room_code)
        
        logger.info(f"Game ended in room {room_code}, final leaderboard: {[f'{entry.username}: {entry.score}' for entry in leaderboard]}")
    
    async def force_end_game(self, room_code: str, reason: str = "Game force-ended"):
        """Force end a game (for cleanup or admin purposes)"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Cancel all timers
        self.timer_service.cancel_room_timers(room_code)
        
        # Set room to finished state
        room.state = RoomState.FINISHED
        room.current_round_state = None
        
        # Clean up
        self.player_manager.cleanup_room_scoring(room_code)
        
        logger.info(f"Force-ended game in room {room_code}: {reason}")
    
    def get_current_phase(self, room_code: str) -> Optional[str]:
        """Get the current phase of a game"""
        room = self.room_manager.get_room(room_code)
        if not room or not room.current_round_state:
            return None
        return room.current_round_state.phase
    
    def get_time_remaining_in_phase(self, room_code: str) -> Optional[float]:
        """Get time remaining in the current phase"""
        room = self.room_manager.get_room(room_code)
        if not room or not room.current_round_state:
            return None
        
        now = datetime.now(timezone.utc)
        remaining = (room.current_round_state.phase_end_time - now).total_seconds()
        return max(0.0, remaining)
    
    def get_game_stats(self, room_code: str) -> dict:
        """Get statistics about a game"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return {}
        
        return {
            "room_code": room_code,
            "state": room.state,
            "current_round": room.round_index + 1,
            "total_rounds": room.settings.rounds,
            "current_phase": room.current_round_state.phase if room.current_round_state else None,
            "time_remaining": self.get_time_remaining_in_phase(room_code),
            "players_count": len(room.players),
            "players_scored_this_round": len(self.player_manager.players_scored_this_round.get(room_code, set()))
        }