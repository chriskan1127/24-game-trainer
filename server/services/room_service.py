from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import logging
import asyncio

from database.models import Game, Player, GameResult, GameStatus
from utils.code_generator import code_generator
from services.solver_service import solver_service

logger = logging.getLogger(__name__)


class RoomService:
    """Service for managing game rooms and competitive gameplay."""
    
    def __init__(self):
        self.active_timers: Dict[str, asyncio.Task] = {}  # Track round timers
    
    def create_game(
        self,
        db: Session,
        host_username: str,
        target: int = 24,
        time_limit: int = 30,
        max_players: int = 10,
        points_to_win: int = 10
    ) -> Tuple[bool, str, Optional[Game]]:
        """
        Create a new game room.
        
        Args:
            db: Database session
            host_username: Username of the host
            target: Target number for the game (default 24)
            time_limit: Time limit per round in seconds (default 30)
            max_players: Maximum players allowed (default 10)
            points_to_win: Points needed to win the game (default 10)
            
        Returns:
            Tuple[bool, str, Optional[Game]]: (success, message, game)
        """
        try:
            # Generate unique game code
            game_code = code_generator.generate_code(db)
            host_id = str(uuid.uuid4())
            
            # Create game
            game = Game(
                code=game_code,
                host_id=host_id,
                target=target,
                time_limit=time_limit,
                max_players=max_players,
                points_to_win=points_to_win,
                status=GameStatus.WAITING.value
            )
            
            # Create host player
            host_player = Player(
                id=host_id,
                game_id=None,  # Will be set after game is created
                username=host_username,
                is_host=True,
                is_ready=True
            )
            
            db.add(game)
            db.flush()  # Get game ID
            
            host_player.game_id = game.id
            game.players.append(host_player)
            
            db.commit()
            
            logger.info(f"Game created: {game_code} by {host_username}")
            return True, f"Game created with code: {game_code}", game
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating game: {e}")
            return False, f"Failed to create game: {str(e)}", None
    
    def join_game(
        self,
        db: Session,
        game_code: str,
        username: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Join an existing game.
        
        Args:
            db: Database session
            game_code: Game code to join
            username: Player's username
            
        Returns:
            Tuple[bool, str, Optional[str]]: (success, message, player_id)
        """
        try:
            game = db.query(Game).filter(Game.code == game_code).first()
            
            if not game:
                return False, "Game not found", None
            
            if game.status not in [GameStatus.WAITING.value]:
                return False, "Game is not accepting new players", None
            
            if len(game.players) >= game.max_players:
                return False, "Game is full", None
            
            # Check if username is already taken
            existing_player = db.query(Player).filter(
                Player.game_id == game.id,
                Player.username == username
            ).first()
            
            if existing_player:
                return False, "Username already taken in this game", None
            
            # Create new player
            player_id = str(uuid.uuid4())
            player = Player(
                id=player_id,
                game_id=game.id,
                username=username,
                is_host=False,
                is_ready=False
            )
            
            game.players.append(player)
            db.commit()
            
            logger.info(f"Player {username} joined game {game_code}")
            return True, "Successfully joined game", player_id
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error joining game: {e}")
            return False, f"Failed to join game: {str(e)}", None
    
    def start_game(
        self,
        db: Session,
        game_code: str,
        player_id: str
    ) -> Tuple[bool, str, Optional[Game]]:
        """
        Start a game (host only).
        
        Args:
            db: Database session
            game_code: Game code
            player_id: Player attempting to start (must be host)
            
        Returns:
            Tuple[bool, str, Optional[Game]]: (success, message, game)
        """
        try:
            game = db.query(Game).filter(Game.code == game_code).first()
            
            if not game:
                return False, "Game not found", None
            
            if game.host_id != player_id:
                return False, "Only the host can start the game", None
            
            if game.status != GameStatus.WAITING.value:
                return False, "Game cannot be started in current state", None
            
            if len(game.players) < 2:
                return False, "Need at least 2 players to start", None
            
            # Check if all players are ready (except host who's always ready)
            for player in game.players:
                if not player.is_ready:
                    return False, f"Player {player.username} is not ready", None
            
            # Start the first round
            success, message = self._start_new_round(db, game)
            if not success:
                return False, message, None
            
            logger.info(f"Game {game_code} started with {len(game.players)} players")
            return True, "Game started", game
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error starting game: {e}")
            return False, f"Failed to start game: {str(e)}", None
    
    def submit_solution(
        self,
        db: Session,
        game_code: str,
        player_id: str,
        solution: List[Any]
    ) -> Tuple[bool, str, Optional[GameResult]]:
        """
        Submit a solution for the current round.
        
        Args:
            db: Database session
            game_code: Game code
            player_id: Player submitting solution
            solution: Solution steps
            
        Returns:
            Tuple[bool, str, Optional[GameResult]]: (success, message, result)
        """
        try:
            game = db.query(Game).filter(Game.code == game_code).first()
            
            if not game:
                return False, "Game not found", None
            
            if game.status != GameStatus.IN_PROGRESS.value:
                return False, "Game is not in progress", None
            
            if not game.current_numbers:
                return False, "No active round", None
            
            player = db.query(Player).filter(
                Player.id == player_id,
                Player.game_id == game.id
            ).first()
            
            if not player:
                return False, "Player not found in this game", None
            
            if player.round_answered:
                return False, "You have already answered this round", None
            
            # Check if round has timed out
            if game.round_start_time:
                elapsed = (datetime.utcnow() - game.round_start_time).total_seconds()
                if elapsed > game.time_limit:
                    return False, "Round has timed out", None
            
            # Validate solution
            is_correct, validation_message = solver_service.validate_solution(
                game.current_numbers, solution, game.target
            )
            
            # Calculate time taken
            time_taken = None
            if game.round_start_time:
                time_taken = int((datetime.utcnow() - game.round_start_time).total_seconds())
            
            # Create result record
            result = GameResult(
                game_id=game.id,
                player_id=player_id,
                round_number=game.current_round,
                numbers=game.current_numbers,
                solution=solution,
                is_correct=is_correct,
                time_taken=time_taken
            )
            
            # Mark player as having answered
            player.round_answered = True
            player.round_answer_time = datetime.utcnow()
            
            # If correct and no one has won this round yet
            if is_correct and not game.round_winner:
                result.is_winner = True
                result.points_awarded = 1
                player.score += 1
                game.round_winner = player_id
                
                # Check if player won the game
                if player.score >= game.points_to_win:
                    game.game_winner = player_id
                    game.status = GameStatus.FINISHED.value
                    self._cancel_round_timer(game_code)
                else:
                    game.status = GameStatus.BETWEEN_ROUNDS.value
                    # Schedule next round
                    self._schedule_next_round(db, game, delay=3)  # 3 second delay
            
            db.add(result)
            db.commit()
            
            logger.info(f"Solution submitted by {player.username} in game {game_code}: {'correct' if is_correct else 'incorrect'}")
            return True, validation_message, result
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error submitting solution: {e}")
            return False, f"Failed to submit solution: {str(e)}", None
    
    def set_player_ready(
        self,
        db: Session,
        game_code: str,
        player_id: str,
        is_ready: bool
    ) -> Tuple[bool, str]:
        """Set player ready status."""
        try:
            game = db.query(Game).filter(Game.code == game_code).first()
            if not game:
                return False, "Game not found"
            
            player = db.query(Player).filter(
                Player.id == player_id,
                Player.game_id == game.id
            ).first()
            
            if not player:
                return False, "Player not found"
            
            player.is_ready = is_ready
            player.last_activity = datetime.utcnow()
            db.commit()
            
            return True, f"Ready status set to {is_ready}"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error setting ready status: {e}")
            return False, str(e)
    
    def get_game_status(self, db: Session, game_code: str) -> Optional[Game]:
        """Get current game status."""
        return db.query(Game).filter(Game.code == game_code).first()
    
    def leave_game(
        self,
        db: Session,
        game_code: str,
        player_id: str
    ) -> Tuple[bool, str]:
        """Remove player from game."""
        try:
            game = db.query(Game).filter(Game.code == game_code).first()
            if not game:
                return False, "Game not found"
            
            player = db.query(Player).filter(
                Player.id == player_id,
                Player.game_id == game.id
            ).first()
            
            if not player:
                return False, "Player not found in game"
            
            # If host leaves, end the game
            if player.is_host:
                game.status = GameStatus.FINISHED.value
                self._cancel_round_timer(game_code)
                logger.info(f"Host left game {game_code}, ending game")
            
            db.delete(player)
            db.commit()
            
            return True, "Player removed from game"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error leaving game: {e}")
            return False, str(e)
    
    def _start_new_round(self, db: Session, game: Game) -> Tuple[bool, str]:
        """Start a new round with fresh numbers."""
        try:
            # Generate new numbers
            numbers = solver_service.generate_valid_numbers(game.target)
            solution = solver_service.get_solution_for_numbers(numbers, game.target)
            
            # Update game state
            game.current_round += 1
            game.current_numbers = numbers
            game.current_solution = solution
            game.round_start_time = datetime.utcnow()
            game.round_winner = None
            game.solution_revealed = False
            game.status = GameStatus.IN_PROGRESS.value
            
            # Reset all players' round status
            for player in game.players:
                player.round_answered = False
                player.round_answer_time = None
            
            db.commit()
            
            # Start round timer
            self._start_round_timer(db, game)
            
            logger.info(f"Started round {game.current_round} in game {game.code} with numbers {numbers}")
            return True, "Round started"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error starting new round: {e}")
            return False, str(e)
    
    def _start_round_timer(self, db: Session, game: Game):
        """Start timer for current round."""
        async def round_timer():
            try:
                await asyncio.sleep(game.time_limit)
                
                # Refresh game state
                db.refresh(game)
                
                # If round is still in progress and no one won
                if game.status == GameStatus.IN_PROGRESS.value and not game.round_winner:
                    game.solution_revealed = True
                    game.status = GameStatus.BETWEEN_ROUNDS.value
                    db.commit()
                    
                    logger.info(f"Round {game.current_round} in game {game.code} timed out, revealing solution")
                    
                    # Check if game should end (no one has enough points yet)
                    max_score = max((p.score for p in game.players), default=0)
                    if max_score < game.points_to_win:
                        # Schedule next round
                        self._schedule_next_round(db, game, delay=5)  # 5 second delay
                    else:
                        game.status = GameStatus.FINISHED.value
                        db.commit()
                
            except Exception as e:
                logger.error(f"Error in round timer: {e}")
        
        # Cancel existing timer
        self._cancel_round_timer(game.code)
        
        # Start new timer
        timer_task = asyncio.create_task(round_timer())
        self.active_timers[game.code] = timer_task
    
    def _schedule_next_round(self, db: Session, game: Game, delay: int = 3):
        """Schedule the next round after a delay."""
        async def next_round_scheduler():
            try:
                await asyncio.sleep(delay)
                
                # Refresh game state
                db.refresh(game)
                
                if game.status == GameStatus.BETWEEN_ROUNDS.value:
                    self._start_new_round(db, game)
                
            except Exception as e:
                logger.error(f"Error scheduling next round: {e}")
        
        asyncio.create_task(next_round_scheduler())
    
    def _cancel_round_timer(self, game_code: str):
        """Cancel active round timer."""
        if game_code in self.active_timers:
            timer = self.active_timers[game_code]
            if not timer.done():
                timer.cancel()
            del self.active_timers[game_code]
    
    def cleanup_inactive_games(self, db: Session, max_age_hours: int = 24):
        """Clean up old inactive games."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            old_games = db.query(Game).filter(
                Game.created_at < cutoff_time,
                Game.status.in_([GameStatus.WAITING.value, GameStatus.FINISHED.value])
            ).all()
            
            for game in old_games:
                self._cancel_round_timer(game.code)
                db.delete(game)
            
            db.commit()
            
            if old_games:
                logger.info(f"Cleaned up {len(old_games)} inactive games")
                
        except Exception as e:
            db.rollback()
            logger.error(f"Error cleaning up games: {e}")


# Global service instance
room_service = RoomService() 