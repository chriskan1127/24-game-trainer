"""
Game State Manager Component

Controls game flow, round progression, and timing for the multiplayer 24-game system.

Key responsibilities:
- Start games when host triggers (validate room has players)
- Manage round phases: COUNTDOWN (3s) → ACTIVE (30s) → RESULTS (6s)  
- Track current round index (0-9 for 10 rounds)
- Coordinate transitions between rounds
- Determine game end conditions and trigger final scoring
- Handle timer management and synchronization
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, List, Any, Tuple
from uuid import UUID
from enum import Enum

# Add project paths for imports
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from pydantic_schemas import (
    RoomState, RoundPhase, RoundState,
    CountdownStartMessage, CountdownStartPayload,
    RoundStartMessage, RoundStartPayload,
    RoundEndMessage, RoundEndPayload,
    GameEndMessage, GameEndPayload,
    PlayerScored, PlayerScoreUpdate, LeaderboardEntry,
    ProblemPercentEntry
)

logger = logging.getLogger(__name__)


class GameStateError(Exception):
    """Base exception for game state operations"""
    pass


class InvalidGameStateError(GameStateError):
    """Raised when game is in invalid state for operation"""
    pass


class InsufficientPlayersError(GameStateError):
    """Raised when there aren't enough players to start a game"""
    pass


class UnauthorizedOperationError(GameStateError):
    """Raised when non-host tries to perform host-only operations"""
    pass


class RoundTransitionError(GameStateError):
    """Raised when round transition fails"""
    pass


class GamePhaseState(Enum):
    """Enumeration of game phases for better state management"""
    LOBBY = "LOBBY"
    COUNTDOWN = "COUNTDOWN"
    ACTIVE = "ACTIVE"
    RESULTS = "RESULTS"
    FINISHED = "FINISHED"


class GameStateManager:
    """
    Manages game flow and state transitions.
    
    Features:
    - State machine for game phases with validation
    - Timer management for precise phase transitions
    - Comprehensive error handling and recovery
    - Statistics tracking and performance monitoring
    - Thread-safe operations with proper locking
    """
    
    def __init__(self, room_manager, player_manager, message_broadcaster=None, timer_service=None):
        self.room_manager = room_manager
        self.player_manager = player_manager
        self.message_broadcaster = message_broadcaster
        self.timer_service = timer_service
        
        # Active timers for each room
        self.active_timers: Dict[str, asyncio.Task] = {}
        
        # Game statistics
        self.stats = {
            'games_started': 0,
            'games_completed': 0,
            'rounds_played': 0,
            'forced_endings': 0,
            'timer_cancellations': 0
        }
        
        # Phase callbacks for extensibility
        self.phase_callbacks: Dict[GamePhaseState, List[Callable]] = {
            phase: [] for phase in GamePhaseState
        }
        
        # Configuration
        self.config = {
            'min_players': 2,
            'max_players': 4,
            'countdown_seconds': 3,
            'round_seconds': 30,
            'results_seconds': 6,
            'total_rounds': 10
        }
    
    def register_phase_callback(self, phase: GamePhaseState, callback: Callable):
        """Register a callback for a specific game phase"""
        self.phase_callbacks[phase].append(callback)
    
    async def _execute_phase_callbacks(self, phase: GamePhaseState, room_code: str, **kwargs):
        """Execute all registered callbacks for a phase"""
        for callback in self.phase_callbacks[phase]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(room_code, **kwargs)
                else:
                    callback(room_code, **kwargs)
            except Exception as e:
                logger.error(f"Error in phase callback for {phase}: {e}")
    
    async def start_game(self, room_code: str, host_player_id: UUID, session_token: str):
        """
        Start a game in the specified room (host only).
        
        Args:
            room_code: Room code
            host_player_id: Host player UUID
            session_token: Host session token
            
        Raises:
            UnauthorizedOperationError: If not host or invalid token
            InvalidGameStateError: If room not in lobby state
            InsufficientPlayersError: If less than 2 players
        """
        # Validate host permissions
        if not self.room_manager.validate_session_token(room_code, host_player_id, session_token):
            raise UnauthorizedOperationError("Invalid session token")
        
        if not self.room_manager.is_host(room_code, host_player_id):
            raise UnauthorizedOperationError("Only the host can start the game")
        
        room = self.room_manager.get_room(room_code)
        if not room:
            raise ValueError("Room not found")
        
        if room.state != RoomState.LOBBY:
            raise InvalidGameStateError("Game cannot be started - room not in lobby state")
        
        if len(room.players) < self.config['min_players']:
            raise InsufficientPlayersError(f"Need at least {self.config['min_players']} players to start the game")
        
        # Transition room to running state
        room.state = RoomState.RUNNING
        room.round_index = 0
        
        # Reset player scores and streaks for new game
        for player in room.players.values():
            self.player_manager.reset_player_score(player)
        
        # Execute phase callbacks
        await self._execute_phase_callbacks(GamePhaseState.LOBBY, room_code, 
                                          players=list(room.players.values()))
        
        # Start the first round
        await self.start_round(room_code)
        
        # Update statistics
        self.stats['games_started'] += 1
        
        logger.info(f"Game started in room {room_code} by host {host_player_id} with {len(room.players)} players")
    
    async def start_round(self, room_code: str):
        """
        Start a new round with countdown phase.
        
        Args:
            room_code: Room code
            
        Raises:
            InvalidGameStateError: If room not in valid state
        """
        room = self.room_manager.get_room(room_code)
        if not room:
            logger.error(f"Cannot start round - room {room_code} not found")
            return
        
        if room.round_index >= len(room.problems):
            # Game is finished
            await self.end_game(room_code)
            return
        
        if room.state != RoomState.RUNNING:
            raise InvalidGameStateError(f"Cannot start round - room state is {room.state}")
        
        # Reset round scoring
        self.player_manager.reset_round_scoring(room_code)
        
        # Start countdown phase
        countdown_seconds = self.config['countdown_seconds']
        now = datetime.now(timezone.utc)
        countdown_end = now + timedelta(seconds=countdown_seconds)
        
        room.current_round_state = RoundState(
            phase=RoundPhase.COUNTDOWN,
            phase_start_time=now,
            phase_end_time=countdown_end
        )
        
        # Broadcast countdown start if broadcaster available
        if self.message_broadcaster:
            countdown_message = CountdownStartMessage(
                type="countdown.start",
                payload=CountdownStartPayload(
                    round_index=room.round_index,
                    countdown_seconds=countdown_seconds,
                    server_time=now
                )
            )
            await self.message_broadcaster.broadcast_to_room(room_code, countdown_message, self.room_manager)
        
        # Execute phase callbacks
        await self._execute_phase_callbacks(GamePhaseState.COUNTDOWN, room_code, 
                                          round_index=room.round_index)
        
        # Schedule countdown timer
        await self._schedule_timer(room_code, countdown_seconds, self.handle_countdown_complete)
        
        logger.info(f"Started countdown for round {room.round_index + 1} in room {room_code}")
    
    async def handle_countdown_complete(self, room_code: str):
        """Handle countdown completion and start active round"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Verify we're still in countdown phase
        if (not room.current_round_state or 
            room.current_round_state.phase != RoundPhase.COUNTDOWN):
            logger.warning(f"Countdown complete but room {room_code} not in countdown phase")
            return
        
        # Start active phase
        round_duration = self.config['round_seconds']
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
        
        # Broadcast round start if broadcaster available
        if self.message_broadcaster:
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
        
        # Execute phase callbacks
        await self._execute_phase_callbacks(GamePhaseState.ACTIVE, room_code,
                                          problem=current_problem,
                                          round_index=room.round_index)
        
        # Schedule round timer
        await self._schedule_timer(room_code, round_duration, self.handle_round_timeout)
        
        logger.info(f"Started active round {room.round_index + 1} in room {room_code}")
    
    async def handle_round_timeout(self, room_code: str):
        """Handle round timeout - end the round"""
        await self.end_round(room_code)
    
    async def end_round(self, room_code: str):
        """End the current round and show results"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Cancel any active timer
        await self._cancel_timer(room_code)
        
        # Transition to results phase
        results_duration = self.config['results_seconds']
        now = datetime.now(timezone.utc)
        results_end = now + timedelta(seconds=results_duration)
        
        room.current_round_state = RoundState(
            phase=RoundPhase.RESULTS,
            phase_start_time=now,
            phase_end_time=results_end
        )
        
        # Get current problem and solution
        current_problem = room.problems[room.round_index]
        
        # Generate list of players who scored this round
        players_correct = self._generate_round_results(room_code, room)
        
        # Get updated scores
        updated_scores = self.player_manager.get_score_updates(room.players)
        
        # Broadcast round end if broadcaster available
        if self.message_broadcaster:
            round_end_message = RoundEndMessage(
                type="round.end",
                payload=RoundEndPayload(
                    round_index=room.round_index,
                    problem_id=current_problem.problem_id,
                    canonical_solution=current_problem.canonical_solution,
                    players_correct=players_correct,
                    updated_scores=updated_scores
                )
            )
            await self.message_broadcaster.broadcast_to_room(room_code, round_end_message, self.room_manager)
        
        # Execute phase callbacks
        await self._execute_phase_callbacks(GamePhaseState.RESULTS, room_code,
                                          players_correct=players_correct,
                                          problem=current_problem)
        
        # Schedule results timer
        await self._schedule_timer(room_code, results_duration, self.handle_results_complete)
        
        # Update statistics
        self.stats['rounds_played'] += 1
        
        logger.info(f"Ended round {room.round_index + 1} in room {room_code}, {len(players_correct)} players scored")
    
    async def handle_results_complete(self, room_code: str):
        """Handle results display completion - move to next round or end game"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Move to next round
        room.round_index += 1
        
        # Check if game is complete
        if room.round_index >= self.config['total_rounds']:
            await self.end_game(room_code)
        else:
            await self.start_round(room_code)
    
    async def end_game(self, room_code: str):
        """End the game and show final results"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Cancel any active timers
        await self._cancel_timer(room_code)
        
        # Transition room to finished state
        room.state = RoomState.FINISHED
        room.current_round_state = None
        
        # Generate final leaderboard
        leaderboard = self.player_manager.get_leaderboard(room.players)
        
        # Calculate problem statistics (if we have submission data)
        most_correct, least_correct = self._calculate_problem_stats(room_code, room)
        
        # Broadcast game end if broadcaster available
        if self.message_broadcaster:
            game_end_message = GameEndMessage(
                type="game.end",
                payload=GameEndPayload(
                    leaderboard=leaderboard,
                    most_correct=most_correct,
                    least_correct=least_correct
                )
            )
            await self.message_broadcaster.broadcast_to_room(room_code, game_end_message, self.room_manager)
        
        # Execute phase callbacks
        await self._execute_phase_callbacks(GamePhaseState.FINISHED, room_code,
                                          leaderboard=leaderboard)
        
        # Clean up player scoring data
        self.player_manager.cleanup_room_scoring(room_code)
        
        # Update statistics
        self.stats['games_completed'] += 1
        
        logger.info(f"Game ended in room {room_code}, final leaderboard: {[f'{entry.username}: {entry.score}' for entry in leaderboard]}")
    
    async def force_end_game(self, room_code: str, reason: str = "Game force-ended"):
        """
        Force end a game (for cleanup or admin purposes).
        
        Args:
            room_code: Room code
            reason: Reason for force ending
        """
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        
        # Cancel all timers
        await self._cancel_timer(room_code)
        
        # Set room to finished state
        room.state = RoomState.FINISHED
        room.current_round_state = None
        
        # Clean up
        self.player_manager.cleanup_room_scoring(room_code)
        
        # Update statistics
        self.stats['forced_endings'] += 1
        
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
    
    def get_game_stats(self, room_code: str = None) -> dict:
        """
        Get statistics about games.
        
        Args:
            room_code: Optional specific room to get stats for
            
        Returns:
            dict: Game statistics
        """
        if room_code:
            room = self.room_manager.get_room(room_code)
            if not room:
                return {}
            
            return {
                "room_code": room_code,
                "state": room.state,
                "current_round": room.round_index + 1,
                "total_rounds": self.config['total_rounds'],
                "current_phase": room.current_round_state.phase if room.current_round_state else None,
                "time_remaining": self.get_time_remaining_in_phase(room_code),
                "players_count": len(room.players),
                "players_scored_this_round": len(self.player_manager.players_scored_this_round.get(room_code, set())),
                "has_active_timer": room_code in self.active_timers
            }
        else:
            return {
                "global_stats": self.stats.copy(),
                "config": self.config.copy(),
                "active_timers": list(self.active_timers.keys())
            }
    
    async def _schedule_timer(self, room_code: str, delay_seconds: float, callback: Callable):
        """Schedule a timer for a room"""
        # Cancel existing timer if any
        await self._cancel_timer(room_code)
        
        # Create new timer task
        async def timer_task():
            try:
                await asyncio.sleep(delay_seconds)
                await callback(room_code)
            except asyncio.CancelledError:
                logger.debug(f"Timer cancelled for room {room_code}")
            except Exception as e:
                logger.error(f"Timer error for room {room_code}: {e}")
        
        self.active_timers[room_code] = asyncio.create_task(timer_task())
    
    async def _cancel_timer(self, room_code: str):
        """Cancel active timer for a room"""
        if room_code in self.active_timers:
            self.active_timers[room_code].cancel()
            try:
                await self.active_timers[room_code]
            except asyncio.CancelledError:
                pass
            del self.active_timers[room_code]
            self.stats['timer_cancellations'] += 1
    
    def _generate_round_results(self, room_code: str, room) -> List[PlayerScored]:
        """Generate PlayerScored objects for players who scored this round"""
        players_correct = []
        
        # Get players who scored this round
        scored_player_ids = self.player_manager.players_scored_this_round.get(room_code, set())
        
        for player_id in scored_player_ids:
            if player_id in room.players:
                player = room.players[player_id]
                # This is simplified - in a full implementation, you'd get actual submission data
                players_correct.append(PlayerScored(
                    player_id=player_id,
                    username=player.username,
                    points_gained=10,  # Would come from actual submission
                    base_points=10,
                    speed_bonus=0,  # Would come from actual submission
                    time_left=15.0,  # Would come from actual submission
                    time_submitted=datetime.now(timezone.utc),
                    submission_rank=len(players_correct) + 1
                ))
        
        return players_correct
    
    def _calculate_problem_stats(self, room_code: str, room) -> Tuple[Optional[ProblemPercentEntry], Optional[ProblemPercentEntry]]:
        """Calculate most and least correct problems (simplified implementation)"""
        # This would require tracking problem statistics across all games
        # For now, return None to indicate no stats available
        return None, None
    
    def cleanup_room_timers(self, room_code: str):
        """Clean up any active timers for a room (sync version for external cleanup)"""
        if room_code in self.active_timers:
            self.active_timers[room_code].cancel()
            del self.active_timers[room_code]