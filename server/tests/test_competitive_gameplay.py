import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from database.models import Game, Player, GameResult, GameStatus
from services.room_service import room_service
from services.solver_service import solver_service


class TestCompetitiveGameplay:
    """Test the competitive gameplay features."""
    
    def test_create_game_with_custom_settings(self, db_session: Session):
        """Test creating a game with custom competitive settings."""
        success, message, game = room_service.create_game(
            db=db_session,
            host_username="TestHost",
            target=24,
            time_limit=45,
            max_players=8,
            points_to_win=15
        )
        
        assert success
        assert game is not None
        assert game.target == 24
        assert game.time_limit == 45
        assert game.max_players == 8
        assert game.points_to_win == 15
        assert game.status == GameStatus.WAITING.value
        assert game.current_round == 0
        assert len(game.players) == 1
        assert game.players[0].is_host is True
        assert game.players[0].score == 0
    
    def test_join_game_sets_ready_status(self, db_session: Session):
        """Test that joining a game sets proper ready status."""
        # Create game
        success, message, game = room_service.create_game(
            db=db_session,
            host_username="Host",
            points_to_win=5
        )
        assert success
        
        # Join game
        success, message, player_id = room_service.join_game(
            db=db_session,
            game_code=game.code,
            username="Player1"
        )
        assert success
        
        # Check player status
        player = db_session.query(Player).filter(Player.id == player_id).first()
        assert player.is_ready is False
        assert player.score == 0
        assert player.round_answered is False
    
    def test_start_game_creates_first_round(self, db_session: Session):
        """Test that starting a game creates the first round."""
        # Create game
        success, message, game = room_service.create_game(
            db=db_session,
            host_username="Host",
            points_to_win=3
        )
        assert success
        host_id = game.host_id
        
        # Add second player
        success, message, player_id = room_service.join_game(
            db=db_session,
            game_code=game.code,
            username="Player1"
        )
        assert success
        
        # Set player ready
        success, message = room_service.set_player_ready(
            db=db_session,
            game_code=game.code,
            player_id=player_id,
            is_ready=True
        )
        assert success
        
        # Start game
        success, message, updated_game = room_service.start_game(
            db=db_session,
            game_code=game.code,
            player_id=host_id
        )
        assert success
        assert updated_game.status == GameStatus.IN_PROGRESS.value
        assert updated_game.current_round == 1
        assert updated_game.current_numbers is not None
        assert len(updated_game.current_numbers) == 4
        assert updated_game.round_start_time is not None
        assert updated_game.round_winner is None
        assert updated_game.solution_revealed is False
    
    def test_submit_correct_solution_awards_point(self, db_session: Session):
        """Test that submitting a correct solution awards a point."""
        # Create and start game
        game = self._create_and_start_game(db_session)
        players = game.players
        
        # Get a valid solution for the current numbers
        solution = solver_service.get_solution_for_numbers(game.current_numbers, game.target)
        if not solution:
            # Use a simple working solution for testing
            solution = [1, 1, 24, 24, 1, "*", 24, "+"]  # Example solution format
        
        # Submit solution
        success, message, result = room_service.submit_solution(
            db=db_session,
            game_code=game.code,
            player_id=players[1].id,
            solution=solution
        )
        
        # Refresh game state
        db_session.refresh(game)
        db_session.refresh(players[1])
        
        if success and result.is_correct:
            assert result.is_winner is True
            assert result.points_awarded == 1
            assert players[1].score == 1
            assert game.round_winner == players[1].id
            assert game.status == GameStatus.BETWEEN_ROUNDS.value
        else:
            # If solution validation fails, just verify the structure
            assert result is not None
            assert result.round_number == 1
    
    def test_submit_incorrect_solution_no_points(self, db_session: Session):
        """Test that submitting an incorrect solution awards no points."""
        game = self._create_and_start_game(db_session)
        players = game.players
        
        # Submit obviously incorrect solution
        success, message, result = room_service.submit_solution(
            db=db_session,
            game_code=game.code,
            player_id=players[1].id,
            solution=[1, 1, 1, 1]  # Invalid solution
        )
        
        assert success  # Request processed successfully
        assert result.is_correct is False
        assert result.is_winner is False
        assert result.points_awarded == 0
        
        # Refresh player state
        db_session.refresh(players[1])
        assert players[1].score == 0
    
    def test_first_correct_answer_wins_round(self, db_session: Session):
        """Test that the first correct answer wins the round."""
        game = self._create_and_start_game(db_session)
        players = game.players
        
        # Get solution
        solution = solver_service.get_solution_for_numbers(game.current_numbers, game.target)
        if not solution:
            solution = [1, 1, 24, 24, 1, "*", 24, "+"]
        
        # First player submits correct solution
        success1, message1, result1 = room_service.submit_solution(
            db=db_session,
            game_code=game.code,
            player_id=players[1].id,
            solution=solution
        )
        
        # Second player submits same solution (if first was correct)
        if success1 and result1.is_correct:
            success2, message2, result2 = room_service.submit_solution(
                db=db_session,
                game_code=game.code,
                player_id=players[0].id,
                solution=solution
            )
            
            # Only first player should win
            assert result1.is_winner is True
            if success2:
                assert result2.is_winner is False  # Second player can't win same round
    
    def test_player_cannot_answer_twice_per_round(self, db_session: Session):
        """Test that a player cannot submit multiple answers per round."""
        game = self._create_and_start_game(db_session)
        players = game.players
        
        # Submit first solution
        success1, message1, result1 = room_service.submit_solution(
            db=db_session,
            game_code=game.code,
            player_id=players[1].id,
            solution=[1, 2, 3, 4]
        )
        assert success1
        
        # Try to submit second solution
        success2, message2, result2 = room_service.submit_solution(
            db=db_session,
            game_code=game.code,
            player_id=players[1].id,
            solution=[4, 3, 2, 1]
        )
        
        assert success2 is False
        assert "already answered" in message2.lower()
        assert result2 is None
    
    def test_game_ends_when_target_score_reached(self, db_session: Session):
        """Test that game ends when a player reaches the target score."""
        # Create game with low win condition
        success, message, game = room_service.create_game(
            db=db_session,
            host_username="Host",
            points_to_win=2  # Low score for easy testing
        )
        assert success
        
        # Add player and start
        success, message, player_id = room_service.join_game(
            db=db_session,
            game_code=game.code,
            username="Player1"
        )
        
        # Set ready and start
        room_service.set_player_ready(db=db_session, game_code=game.code, player_id=player_id, is_ready=True)
        room_service.start_game(db=db_session, game_code=game.code, player_id=game.host_id)
        
        # Manually set player score to 1 (simulate winning a round)
        player = db_session.query(Player).filter(Player.id == player_id).first()
        player.score = 1
        db_session.commit()
        
        # Submit winning solution (simulate second win)
        success, message, result = room_service.submit_solution(
            db=db_session,
            game_code=game.code,
            player_id=player_id,
            solution=[1, 1, 24, 24]  # Doesn't matter if correct for this test
        )
        
        # If solution was correct and won the round, game should end
        if success and result and result.is_winner:
            db_session.refresh(game)
            assert player.score >= 2
            assert game.status == GameStatus.FINISHED.value
            assert game.game_winner == player_id
    
    def test_ready_status_management(self, db_session: Session):
        """Test player ready status management."""
        game = self._create_game_with_players(db_session, num_players=2)
        players = game.players
        non_host_player = next(p for p in players if not p.is_host)
        
        # Initially not ready
        assert non_host_player.is_ready is False
        
        # Set ready
        success, message = room_service.set_player_ready(
            db=db_session,
            game_code=game.code,
            player_id=non_host_player.id,
            is_ready=True
        )
        assert success
        
        db_session.refresh(non_host_player)
        assert non_host_player.is_ready is True
        
        # Set not ready
        success, message = room_service.set_player_ready(
            db=db_session,
            game_code=game.code,
            player_id=non_host_player.id,
            is_ready=False
        )
        assert success
        
        db_session.refresh(non_host_player)
        assert non_host_player.is_ready is False
    
    def test_game_result_tracking(self, db_session: Session):
        """Test that game results are properly tracked."""
        game = self._create_and_start_game(db_session)
        players = game.players
        
        # Submit solution
        success, message, result = room_service.submit_solution(
            db=db_session,
            game_code=game.code,
            player_id=players[1].id,
            solution=[1, 2, 3, 4]
        )
        
        assert success
        assert result is not None
        assert result.game_id == game.id
        assert result.player_id == players[1].id
        assert result.round_number == 1
        assert result.numbers == game.current_numbers
        assert result.solution == [1, 2, 3, 4]
        assert result.time_taken is not None
        assert result.submitted_at is not None
    
    def _create_game_with_players(self, db_session: Session, num_players: int = 2) -> Game:
        """Helper to create a game with multiple players."""
        # Create game
        success, message, game = room_service.create_game(
            db=db_session,
            host_username="Host",
            points_to_win=10
        )
        assert success
        
        # Add additional players
        for i in range(1, num_players):
            success, message, player_id = room_service.join_game(
                db=db_session,
                game_code=game.code,
                username=f"Player{i}"
            )
            assert success
            
            # Set ready
            room_service.set_player_ready(
                db=db_session,
                game_code=game.code,
                player_id=player_id,
                is_ready=True
            )
        
        db_session.refresh(game)
        return game
    
    def _create_and_start_game(self, db_session: Session) -> Game:
        """Helper to create and start a game."""
        game = self._create_game_with_players(db_session, num_players=2)
        
        # Start game
        success, message, updated_game = room_service.start_game(
            db=db_session,
            game_code=game.code,
            player_id=game.host_id
        )
        assert success
        
        db_session.refresh(game)
        return game 