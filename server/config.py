import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server configuration
    host: str = os.getenv("HOST", "localhost")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    environment: str = os.getenv("ENVIRONMENT", "development")
    
    # Database configuration
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./game_server.db")
    
    # Redis configuration (optional for Phase 1)
    redis_url: Optional[str] = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # Security
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Game configuration
    default_time_limit: int = int(os.getenv("DEFAULT_TIME_LIMIT", "30"))
    max_players_per_game: int = int(os.getenv("MAX_PLAYERS_PER_GAME", "10"))
    max_active_games: int = int(os.getenv("MAX_ACTIVE_GAMES", "1000"))
    default_target: int = int(os.getenv("DEFAULT_TARGET", "24"))
    default_points_to_win: int = int(os.getenv("DEFAULT_POINTS_TO_WIN", "10"))
    min_players_to_start: int = int(os.getenv("MIN_PLAYERS_TO_START", "2"))
    
    # Round timing settings
    max_round_time: int = int(os.getenv("MAX_ROUND_TIME", "300"))  # Maximum time per round (5 minutes)
    min_round_time: int = int(os.getenv("MIN_ROUND_TIME", "10"))   # Minimum time per round
    round_transition_delay: int = int(os.getenv("ROUND_TRANSITION_DELAY", "3"))  # Delay between rounds
    solution_reveal_delay: int = int(os.getenv("SOLUTION_REVEAL_DELAY", "5"))   # Extra delay when solution is revealed
    
    # Scoring settings
    points_per_win: int = int(os.getenv("POINTS_PER_WIN", "1"))
    max_points_to_win: int = int(os.getenv("MAX_POINTS_TO_WIN", "100"))
    min_points_to_win: int = int(os.getenv("MIN_POINTS_TO_WIN", "1"))
    
    # Connection settings
    websocket_ping_interval: int = int(os.getenv("WEBSOCKET_PING_INTERVAL", "30"))
    websocket_ping_timeout: int = int(os.getenv("WEBSOCKET_PING_TIMEOUT", "10"))
    max_connections_per_game: int = int(os.getenv("MAX_CONNECTIONS_PER_GAME", "50"))
    
    # Cleanup settings
    cleanup_interval_hours: int = int(os.getenv("CLEANUP_INTERVAL_HOURS", "1"))
    max_game_age_hours: int = int(os.getenv("MAX_GAME_AGE_HOURS", "24"))
    
    # Monitoring settings
    enable_metrics: bool = os.getenv("ENABLE_METRICS", "true").lower() == "true"
    metrics_update_interval: int = int(os.getenv("METRICS_UPDATE_INTERVAL", "60"))
    
    # Rate limiting
    max_solutions_per_minute: int = int(os.getenv("MAX_SOLUTIONS_PER_MINUTE", "10"))
    max_games_per_hour: int = int(os.getenv("MAX_GAMES_PER_HOUR", "10"))
    
    # Logging settings
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def database_echo(self) -> bool:
        """Get database echo setting based on environment."""
        return self.debug and not self.is_production

    def validate_settings(self) -> None:
        """Validate configuration settings."""
        # Validate game settings
        if self.max_players_per_game < self.min_players_to_start:
            raise ValueError("max_players_per_game must be >= min_players_to_start")
        
        if self.default_time_limit < self.min_round_time:
            raise ValueError("default_time_limit must be >= min_round_time")
        
        if self.default_time_limit > self.max_round_time:
            raise ValueError("default_time_limit must be <= max_round_time")
        
        if self.default_points_to_win < self.min_points_to_win:
            raise ValueError("default_points_to_win must be >= min_points_to_win")
        
        if self.default_points_to_win > self.max_points_to_win:
            raise ValueError("default_points_to_win must be <= max_points_to_win")
        
        # Validate security settings
        if self.is_production and self.secret_key == "your-secret-key-change-this-in-production":
            raise ValueError("SECRET_KEY must be changed in production")


# Global settings instance
settings = Settings()

# Validate settings on import
settings.validate_settings() 