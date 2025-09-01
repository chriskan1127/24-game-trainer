import secrets
import string
from typing import Set, Optional
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class GameCodeGenerator:
    """Secure game code generator for room codes."""
    
    def __init__(self):
        # Use digits and uppercase letters for readability (excluding easily confused chars)
        self.alphabet = string.digits + "ABCDEFGHJKLMNPQRSTUVWXYZ"  # Removed I, O for clarity
        self.code_length = 6
        self.max_attempts = 100  # Maximum attempts to generate unique code
    
    def generate_code(self, db: Session, exclude_codes: Optional[Set[str]] = None) -> str:
        """
        Generate a unique 6-digit game code.
        
        Args:
            db: Database session for uniqueness checking
            exclude_codes: Optional set of codes to exclude
            
        Returns:
            str: Unique 6-digit game code
            
        Raises:
            RuntimeError: If unable to generate unique code after max_attempts
        """
        exclude_codes = exclude_codes or set()
        
        for attempt in range(self.max_attempts):
            code = self._generate_random_code()
            
            # Check if code is in excluded set
            if code in exclude_codes:
                continue
            
            # Check database for uniqueness
            if self._is_code_unique(db, code):
                logger.info(f"Generated unique game code: {code} (attempt {attempt + 1})")
                return code
            
            logger.debug(f"Code collision detected: {code} (attempt {attempt + 1})")
        
        # If we reach here, we couldn't generate a unique code
        error_msg = f"Failed to generate unique game code after {self.max_attempts} attempts"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    def _generate_random_code(self) -> str:
        """Generate a random code using cryptographically secure randomness."""
        return ''.join(secrets.choice(self.alphabet) for _ in range(self.code_length))
    
    def _is_code_unique(self, db: Session, code: str) -> bool:
        """Check if code is unique in the database."""
        try:
            # Import here to avoid circular imports
            from database.models import Game
            
            # Check for active games with this code
            existing_game = db.query(Game).filter(
                Game.code == code,
                Game.status.in_(["waiting", "active"])
            ).first()
            
            return existing_game is None
            
        except Exception as e:
            logger.error(f"Error checking code uniqueness: {e}")
            # On error, assume code is not unique to be safe
            return False
    
    def validate_code(self, code: str) -> bool:
        """
        Validate a game code format.
        
        Args:
            code: Code to validate
            
        Returns:
            bool: True if code format is valid
        """
        if not code or len(code) != self.code_length:
            return False
        
        # Check if all characters are in our alphabet
        return all(char in self.alphabet for char in code.upper())
    
    def normalize_code(self, code: str) -> str:
        """
        Normalize a code to standard format (uppercase).
        
        Args:
            code: Code to normalize
            
        Returns:
            str: Normalized code
        """
        return code.upper().strip()


class CodeStatistics:
    """Statistics and analytics for game code generation."""
    
    def __init__(self, generator: GameCodeGenerator):
        self.generator = generator
    
    def calculate_collision_probability(self, active_games: int) -> float:
        """
        Calculate probability of code collision.
        
        Args:
            active_games: Number of currently active games
            
        Returns:
            float: Collision probability (0.0 to 1.0)
        """
        alphabet_size = len(self.generator.alphabet)
        total_combinations = alphabet_size ** self.generator.code_length
        
        # Using birthday paradox approximation
        if active_games == 0:
            return 0.0
        
        probability = 1.0
        for i in range(active_games):
            probability *= (total_combinations - i) / total_combinations
        
        return 1.0 - probability
    
    def get_max_safe_games(self, max_collision_probability: float = 0.01) -> int:
        """
        Calculate maximum number of games for given collision probability.
        
        Args:
            max_collision_probability: Maximum acceptable collision probability
            
        Returns:
            int: Maximum safe number of concurrent games
        """
        alphabet_size = len(self.generator.alphabet)
        total_combinations = alphabet_size ** self.generator.code_length
        
        # Binary search for maximum safe games
        low, high = 0, total_combinations
        
        while low < high:
            mid = (low + high + 1) // 2
            if self.calculate_collision_probability(mid) <= max_collision_probability:
                low = mid
            else:
                high = mid - 1
        
        return low
    
    def get_statistics(self) -> dict:
        """Get comprehensive statistics about the code generation system."""
        alphabet_size = len(self.generator.alphabet)
        total_combinations = alphabet_size ** self.generator.code_length
        
        return {
            "alphabet_size": alphabet_size,
            "code_length": self.generator.code_length,
            "total_combinations": total_combinations,
            "max_safe_games_1_percent": self.get_max_safe_games(0.01),
            "max_safe_games_5_percent": self.get_max_safe_games(0.05),
            "alphabet": self.generator.alphabet,
        }


# Global instances
code_generator = GameCodeGenerator()
code_statistics = CodeStatistics(code_generator) 