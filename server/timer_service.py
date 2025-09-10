"""
Timer Service
Provides precise timing for round phases and game events
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


class TimerService:
    """Manages timing for game rounds and phases"""
    
    def __init__(self):
        self.active_timers: Dict[str, asyncio.Task] = {}
        self.game_state_manager = None
        
    def set_game_state_manager(self, game_state_manager):
        """Set reference to game state manager for callbacks"""
        self.game_state_manager = game_state_manager
    
    async def schedule_countdown(self, room_code: str, countdown_seconds: int = 3) -> str:
        """
        Schedule a countdown timer for a room
        Returns timer_id for cancellation
        """
        timer_id = f"countdown_{room_code}_{uuid4()}"
        
        async def countdown_task():
            try:
                logger.info(f"Starting countdown for room {room_code}: {countdown_seconds} seconds")
                await asyncio.sleep(countdown_seconds)
                
                # Notify game state manager that countdown is complete
                if self.game_state_manager:
                    await self.game_state_manager.handle_countdown_complete(room_code)
                
                # Clean up timer
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
                    
            except asyncio.CancelledError:
                logger.info(f"Countdown timer {timer_id} for room {room_code} was cancelled")
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
                raise
            except Exception as e:
                logger.error(f"Error in countdown timer {timer_id} for room {room_code}: {e}")
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
        
        # Start the countdown task
        task = asyncio.create_task(countdown_task())
        self.active_timers[timer_id] = task
        
        return timer_id
    
    async def schedule_round_timer(self, room_code: str, round_duration: int = 30) -> str:
        """
        Schedule a round timer for active gameplay
        Returns timer_id for cancellation
        """
        timer_id = f"round_{room_code}_{uuid4()}"
        
        async def round_task():
            try:
                logger.info(f"Starting round timer for room {room_code}: {round_duration} seconds")
                await asyncio.sleep(round_duration)
                
                # Notify game state manager that round is complete
                if self.game_state_manager:
                    await self.game_state_manager.handle_round_timeout(room_code)
                
                # Clean up timer
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
                    
            except asyncio.CancelledError:
                logger.info(f"Round timer {timer_id} for room {room_code} was cancelled")
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
                raise
            except Exception as e:
                logger.error(f"Error in round timer {timer_id} for room {room_code}: {e}")
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
        
        # Start the round task
        task = asyncio.create_task(round_task())
        self.active_timers[timer_id] = task
        
        return timer_id
    
    async def schedule_results_timer(self, room_code: str, results_duration: int = 6) -> str:
        """
        Schedule a results display timer
        Returns timer_id for cancellation
        """
        timer_id = f"results_{room_code}_{uuid4()}"
        
        async def results_task():
            try:
                logger.info(f"Starting results timer for room {room_code}: {results_duration} seconds")
                await asyncio.sleep(results_duration)
                
                # Notify game state manager that results period is complete
                if self.game_state_manager:
                    await self.game_state_manager.handle_results_complete(room_code)
                
                # Clean up timer
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
                    
            except asyncio.CancelledError:
                logger.info(f"Results timer {timer_id} for room {room_code} was cancelled")
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
                raise
            except Exception as e:
                logger.error(f"Error in results timer {timer_id} for room {room_code}: {e}")
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
        
        # Start the results task
        task = asyncio.create_task(results_task())
        self.active_timers[timer_id] = task
        
        return timer_id
    
    async def schedule_custom_timer(self, name: str, duration: float, 
                                  callback: Callable[[], None]) -> str:
        """
        Schedule a custom timer with callback
        Returns timer_id for cancellation
        """
        timer_id = f"custom_{name}_{uuid4()}"
        
        async def custom_task():
            try:
                logger.info(f"Starting custom timer {name}: {duration} seconds")
                await asyncio.sleep(duration)
                
                # Execute callback
                if callback:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                
                # Clean up timer
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
                    
            except asyncio.CancelledError:
                logger.info(f"Custom timer {timer_id} ({name}) was cancelled")
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
                raise
            except Exception as e:
                logger.error(f"Error in custom timer {timer_id} ({name}): {e}")
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
        
        # Start the custom task
        task = asyncio.create_task(custom_task())
        self.active_timers[timer_id] = task
        
        return timer_id
    
    def cancel_timer(self, timer_id: str) -> bool:
        """Cancel a specific timer by ID"""
        if timer_id in self.active_timers:
            task = self.active_timers[timer_id]
            task.cancel()
            del self.active_timers[timer_id]
            logger.info(f"Cancelled timer {timer_id}")
            return True
        else:
            logger.warning(f"Attempted to cancel non-existent timer {timer_id}")
            return False
    
    def cancel_room_timers(self, room_code: str) -> int:
        """Cancel all timers for a specific room"""
        cancelled_count = 0
        timers_to_cancel = []
        
        # Find all timers for this room
        for timer_id in self.active_timers:
            if room_code in timer_id:
                timers_to_cancel.append(timer_id)
        
        # Cancel found timers
        for timer_id in timers_to_cancel:
            if self.cancel_timer(timer_id):
                cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} timers for room {room_code}")
        return cancelled_count
    
    async def cleanup(self):
        """Cancel all active timers (for shutdown)"""
        timer_ids = list(self.active_timers.keys())
        
        for timer_id in timer_ids:
            self.cancel_timer(timer_id)
        
        # Wait a bit for graceful cancellation
        if timer_ids:
            await asyncio.sleep(0.1)
        
        logger.info(f"Cleaned up {len(timer_ids)} active timers")
    
    def get_active_timers_for_room(self, room_code: str) -> list:
        """Get list of active timer IDs for a specific room"""
        room_timers = []
        for timer_id in self.active_timers:
            if room_code in timer_id:
                room_timers.append(timer_id)
        return room_timers
    
    def get_timer_stats(self) -> dict:
        """Get statistics about active timers"""
        timer_types = {}
        
        for timer_id in self.active_timers:
            timer_type = timer_id.split('_')[0]
            timer_types[timer_type] = timer_types.get(timer_type, 0) + 1
        
        return {
            "total_active_timers": len(self.active_timers),
            "timers_by_type": timer_types
        }
    
    def calculate_time_remaining(self, start_time: datetime, duration_seconds: int) -> float:
        """Calculate time remaining for a timer that started at a specific time"""
        now = datetime.now(timezone.utc)
        elapsed = (now - start_time).total_seconds()
        remaining = max(0, duration_seconds - elapsed)
        return remaining