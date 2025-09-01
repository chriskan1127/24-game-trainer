import enum
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List, Dict, Any

from .database import Base


class GameStatus(enum.Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    BETWEEN_ROUNDS = "between_rounds"
    FINISHED = "finished"


class Game(Base):
    """Game model representing a multiplayer game session."""
    
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(6), unique=True, nullable=False, index=True)
    host_id = Column(String(36), nullable=False)
    status = Column(String(20), default=GameStatus.WAITING.value, index=True)
    target = Column(Integer, default=24)
    time_limit = Column(Integer, default=30)  # Time limit per round in seconds
    max_players = Column(Integer, default=10)
    points_to_win = Column(Integer, default=10)  # Configurable win condition
    current_round = Column(Integer, default=0)
    current_numbers = Column(JSON, nullable=True)  # Current round's numbers
    round_start_time = Column(DateTime, nullable=True)  # When current round started
    round_winner = Column(String(36), nullable=True)  # Player ID who won current round
    game_winner = Column(String(36), nullable=True)  # Player ID who won the game
    solution_revealed = Column(Boolean, default=False)  # Whether solution was auto-revealed
    current_solution = Column(JSON, nullable=True)  # Solution for current round
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    players = relationship("Player", back_populates="game", cascade="all, delete-orphan")
    results = relationship("GameResult", back_populates="game", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_games_status_created', 'status', 'created_at'),
        Index('idx_games_host_status', 'host_id', 'status'),
    )
    
    def __repr__(self):
        return f"<Game(id={self.id}, code={self.code}, status={self.status})>"
    
    @property
    def is_active(self) -> bool:
        """Check if game is currently active."""
        return self.status in ["waiting", "in_progress"]
    
    @property
    def is_full(self) -> bool:
        """Check if game has reached maximum players."""
        return len(self.players) >= self.max_players
    
    @property
    def player_count(self) -> int:
        """Get current number of players."""
        return len(self.players)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert game to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "code": self.code,
            "host_id": self.host_id,
            "status": self.status,
            "target": self.target,
            "time_limit": self.time_limit,
            "max_players": self.max_players,
            "points_to_win": self.points_to_win,
            "current_round": self.current_round,
            "current_numbers": self.current_numbers,
            "round_start_time": self.round_start_time.isoformat() if self.round_start_time else None,
            "round_winner": self.round_winner,
            "game_winner": self.game_winner,
            "solution_revealed": self.solution_revealed,
            "current_solution": self.current_solution if self.solution_revealed else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "players": [player.to_dict() for player in self.players],
        }


class Player(Base):
    """Player model representing a player in a game."""
    
    __tablename__ = "players"
    
    id = Column(String(36), primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    username = Column(String(50), nullable=False)
    is_host = Column(Boolean, default=False)
    is_connected = Column(Boolean, default=True)
    is_ready = Column(Boolean, default=False)
    score = Column(Integer, default=0)  # Total points (wins) in the game
    round_answered = Column(Boolean, default=False)  # Whether answered current round
    round_answer_time = Column(DateTime, nullable=True)  # When they answered current round
    last_activity = Column(DateTime, default=func.now())
    joined_at = Column(DateTime, default=func.now())
    
    # Relationships
    game = relationship("Game", back_populates="players")
    results = relationship("GameResult", back_populates="player", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_players_game_player', 'game_id', 'id'),
        Index('idx_players_username', 'username'),
    )
    
    def __repr__(self):
        return f"<Player(id={self.id}, username={self.username}, game_id={self.game_id})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert player to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "username": self.username,
            "is_host": self.is_host,
            "is_connected": self.is_connected,
            "is_ready": self.is_ready,
            "score": self.score,
            "round_answered": self.round_answered,
            "round_answer_time": self.round_answer_time.isoformat() if self.round_answer_time else None,
            "last_activity": self.last_activity.isoformat(),
            "joined_at": self.joined_at.isoformat(),
        }


class GameResult(Base):
    """Game result model for storing individual player solutions."""
    
    __tablename__ = "game_results"
    
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    player_id = Column(String(36), ForeignKey("players.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    numbers = Column(JSON, nullable=False)
    solution = Column(JSON, nullable=True)
    is_correct = Column(Boolean, nullable=False)
    is_winner = Column(Boolean, default=False)  # Whether this was the winning answer for the round
    time_taken = Column(Integer, nullable=True)  # Seconds taken to answer
    points_awarded = Column(Integer, default=0)  # Points awarded for this round (0 or 1)
    submitted_at = Column(DateTime, default=func.now())
    
    # Relationships
    game = relationship("Game", back_populates="results")
    player = relationship("Player", back_populates="results")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_results_game_time', 'game_id', 'submitted_at'),
        Index('idx_results_player_game', 'player_id', 'game_id'),
    )
    
    def __repr__(self):
        return f"<GameResult(id={self.id}, game_id={self.game_id}, player_id={self.player_id})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "round_number": self.round_number,
            "numbers": self.numbers,
            "solution": self.solution,
            "is_correct": self.is_correct,
            "is_winner": self.is_winner,
            "time_taken": self.time_taken,
            "points_awarded": self.points_awarded,
            "submitted_at": self.submitted_at.isoformat(),
        }


class ServerMetrics(Base):
    """Server metrics model for monitoring and scaling decisions."""
    
    __tablename__ = "server_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=func.now(), index=True)
    active_games = Column(Integer, default=0)
    active_players = Column(Integer, default=0)
    total_games_created = Column(Integer, default=0)
    total_solutions_submitted = Column(Integer, default=0)
    average_response_time = Column(Float, default=0.0)
    memory_usage_mb = Column(Float, default=0.0)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_metrics_timestamp', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<ServerMetrics(id={self.id}, timestamp={self.timestamp})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "active_games": self.active_games,
            "active_players": self.active_players,
            "total_games_created": self.total_games_created,
            "total_solutions_submitted": self.total_solutions_submitted,
            "average_response_time": self.average_response_time,
            "memory_usage_mb": self.memory_usage_mb,
        } 