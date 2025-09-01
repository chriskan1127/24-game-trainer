import pytest
from unittest.mock import Mock, patch
from ..services.solver_service import SolverService, solver_service


class TestSolverService:
    """Test suite for SolverService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = SolverService()
    
    def test_get_fallback_numbers(self):
        """Test fallback number generation."""
        numbers = self.service._get_fallback_numbers()
        
        assert len(numbers) == 4
        assert all(isinstance(n, int) for n in numbers)


class TestGlobalSolverService:
    """Test global solver service instance."""
    
    def test_global_instance(self):
        """Test that global instance exists."""
        assert isinstance(solver_service, SolverService) 