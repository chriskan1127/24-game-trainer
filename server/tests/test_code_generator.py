import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from ..utils.code_generator import GameCodeGenerator, CodeStatistics, code_generator


class TestGameCodeGenerator:
    """Test suite for GameCodeGenerator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = GameCodeGenerator()
        self.mock_db = Mock(spec=Session)
    
    def test_init(self):
        """Test generator initialization."""
        assert self.generator.code_length == 6
        assert self.generator.max_attempts == 100
        assert "I" not in self.generator.alphabet  # Excluded for clarity
        assert "O" not in self.generator.alphabet  # Excluded for clarity
        assert "0" in self.generator.alphabet
        assert "A" in self.generator.alphabet
    
    def test_generate_random_code_format(self):
        """Test that generated codes have correct format."""
        for _ in range(100):  # Test multiple generations
            code = self.generator._generate_random_code()
            assert len(code) == 6
            assert code.isupper()
            assert all(c in self.generator.alphabet for c in code)
    
    def test_generate_random_code_uniqueness(self):
        """Test that generated codes are reasonably unique."""
        codes = [self.generator._generate_random_code() for _ in range(1000)]
        unique_codes = set(codes)
        
        # Should have high uniqueness (at least 95%)
        uniqueness_ratio = len(unique_codes) / len(codes)
        assert uniqueness_ratio > 0.95
    
    @patch('server.utils.code_generator.GameCodeGenerator._is_code_unique')
    def test_generate_code_success(self, mock_is_unique):
        """Test successful code generation."""
        mock_is_unique.return_value = True
        
        code = self.generator.generate_code(self.mock_db)
        
        assert len(code) == 6
        assert code.isupper()
        mock_is_unique.assert_called_once()
    
    @patch('server.utils.code_generator.GameCodeGenerator._is_code_unique')
    @patch('server.utils.code_generator.GameCodeGenerator._generate_random_code')
    def test_generate_code_collision_retry(self, mock_random_code, mock_is_unique):
        """Test code generation with collisions."""
        mock_random_code.side_effect = ["ABC123", "XYZ789", "DEF456"]
        mock_is_unique.side_effect = [False, False, True]  # First two collide, third succeeds
        
        code = self.generator.generate_code(self.mock_db)
        
        assert code == "DEF456"
        assert mock_random_code.call_count == 3
        assert mock_is_unique.call_count == 3
    
    @patch('server.utils.code_generator.GameCodeGenerator._is_code_unique')
    def test_generate_code_max_attempts_exceeded(self, mock_is_unique):
        """Test code generation failure after max attempts."""
        mock_is_unique.return_value = False  # Always collision
        
        with pytest.raises(RuntimeError, match="Failed to generate unique game code"):
            self.generator.generate_code(self.mock_db)
        
        assert mock_is_unique.call_count == 100  # max_attempts
    
    def test_generate_code_with_exclude_codes(self):
        """Test code generation with excluded codes."""
        exclude_codes = {"ABC123", "XYZ789"}
        
        with patch.object(self.generator, '_generate_random_code') as mock_random:
            with patch.object(self.generator, '_is_code_unique') as mock_unique:
                mock_random.side_effect = ["ABC123", "XYZ789", "DEF456"]
                mock_unique.return_value = True
                
                code = self.generator.generate_code(self.mock_db, exclude_codes)
                
                assert code == "DEF456"
                assert mock_random.call_count == 3  # First two excluded, third accepted
    
    @patch('server.utils.code_generator.Game')
    def test_is_code_unique_true(self, mock_game_model):
        """Test code uniqueness check when code is unique."""
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = self.generator._is_code_unique(self.mock_db, "ABC123")
        
        assert result is True
        self.mock_db.query.assert_called_once()
    
    @patch('server.utils.code_generator.Game')
    def test_is_code_unique_false(self, mock_game_model):
        """Test code uniqueness check when code exists."""
        mock_game = Mock()
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_game
        
        result = self.generator._is_code_unique(self.mock_db, "ABC123")
        
        assert result is False
    
    @patch('server.utils.code_generator.Game')
    def test_is_code_unique_exception(self, mock_game_model):
        """Test code uniqueness check with database exception."""
        self.mock_db.query.side_effect = Exception("Database error")
        
        result = self.generator._is_code_unique(self.mock_db, "ABC123")
        
        assert result is False  # Fail safe on error
    
    def test_validate_code_valid(self):
        """Test code validation with valid codes."""
        valid_codes = ["ABC123", "XYZ789", "123ABC", "ZZZZZZ", "000000"]
        
        for code in valid_codes:
            assert self.generator.validate_code(code)
    
    def test_validate_code_invalid(self):
        """Test code validation with invalid codes."""
        invalid_codes = [
            "",           # Empty
            "ABC12",      # Too short
            "ABC1234",    # Too long
            "ABC12I",     # Contains I
            "ABC12O",     # Contains O
            "abc123",     # Lowercase (should be normalized first)
            None,         # None
        ]
        
        for code in invalid_codes:
            assert not self.generator.validate_code(code)
    
    def test_normalize_code(self):
        """Test code normalization."""
        test_cases = [
            ("abc123", "ABC123"),
            ("  XYZ789  ", "XYZ789"),
            ("AbC123", "ABC123"),
            ("123abc", "123ABC"),
        ]
        
        for input_code, expected in test_cases:
            assert self.generator.normalize_code(input_code) == expected


class TestCodeStatistics:
    """Test suite for CodeStatistics."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = GameCodeGenerator()
        self.stats = CodeStatistics(self.generator)
    
    def test_calculate_collision_probability_zero_games(self):
        """Test collision probability with zero games."""
        probability = self.stats.calculate_collision_probability(0)
        assert probability == 0.0
    
    def test_calculate_collision_probability_one_game(self):
        """Test collision probability with one game."""
        probability = self.stats.calculate_collision_probability(1)
        assert probability == 0.0
    
    def test_calculate_collision_probability_many_games(self):
        """Test collision probability increases with more games."""
        prob_10 = self.stats.calculate_collision_probability(10)
        prob_100 = self.stats.calculate_collision_probability(100)
        prob_1000 = self.stats.calculate_collision_probability(1000)
        
        assert 0 <= prob_10 <= 1
        assert 0 <= prob_100 <= 1
        assert 0 <= prob_1000 <= 1
        assert prob_10 < prob_100 < prob_1000
    
    def test_get_max_safe_games(self):
        """Test maximum safe games calculation."""
        max_games_1_percent = self.stats.get_max_safe_games(0.01)
        max_games_5_percent = self.stats.get_max_safe_games(0.05)
        
        assert max_games_1_percent > 0
        assert max_games_5_percent > 0
        assert max_games_5_percent > max_games_1_percent
    
    def test_get_statistics(self):
        """Test comprehensive statistics generation."""
        stats = self.stats.get_statistics()
        
        required_keys = [
            "alphabet_size", "code_length", "total_combinations",
            "max_safe_games_1_percent", "max_safe_games_5_percent", "alphabet"
        ]
        
        for key in required_keys:
            assert key in stats
        
        assert stats["alphabet_size"] == len(self.generator.alphabet)
        assert stats["code_length"] == 6
        assert stats["total_combinations"] > 0
        assert stats["max_safe_games_1_percent"] > 0
        assert stats["max_safe_games_5_percent"] > 0
        assert stats["alphabet"] == self.generator.alphabet


class TestGlobalInstances:
    """Test global instances."""
    
    def test_code_generator_instance(self):
        """Test global code generator instance."""
        assert isinstance(code_generator, GameCodeGenerator)
        assert code_generator.code_length == 6
    
    def test_code_generator_actual_generation(self):
        """Test actual code generation with mocked database."""
        mock_db = Mock(spec=Session)
        
        with patch.object(code_generator, '_is_code_unique', return_value=True):
            code = code_generator.generate_code(mock_db)
            assert len(code) == 6
            assert code.isupper()


@pytest.mark.integration
class TestCodeGeneratorIntegration:
    """Integration tests for code generator."""
    
    def test_collision_probability_realistic(self):
        """Test collision probabilities with realistic numbers."""
        stats = CodeStatistics(GameCodeGenerator())
        
        # With 32^6 = 1,073,741,824 combinations, should handle many concurrent games
        alphabet_size = len(GameCodeGenerator().alphabet)
        total_combinations = alphabet_size ** 6
        
        # Should handle thousands of concurrent games with low collision probability
        prob_1000_games = stats.calculate_collision_probability(1000)
        assert prob_1000_games < 0.001  # Less than 0.1%
        
        max_safe_games = stats.get_max_safe_games(0.01)
        assert max_safe_games > 1000  # Should handle more than 1000 concurrent games 