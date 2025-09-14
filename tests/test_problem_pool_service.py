"""
Test cases for Problem Pool Service
"""

import pytest
import asyncio
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
server_dir = os.path.join(project_root, 'server')
lib_dir = os.path.join(project_root, 'lib')
plans_dir = os.path.join(project_root, 'plans')

for path in [server_dir, lib_dir, plans_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from problem_pool_service import ProblemPoolService
from pydantic_schemas import Problem
from solve_24 import Solution


class TestProblemPoolService:
    """Test Problem Pool Service functionality"""

    @pytest.fixture
    async def problem_pool_service(self):
        """Create and initialize a problem pool service"""
        service = ProblemPoolService()
        await service.initialize()
        return service

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test that problem pool service initializes correctly"""
        service = ProblemPoolService()
        await service.initialize()
        # Should not raise any exceptions

    @pytest.mark.asyncio
    async def test_generate_problems_for_game(self, problem_pool_service):
        """Test generating problems for a game"""
        problems = await problem_pool_service.generate_problems_for_game(10)
        
        assert len(problems) == 10
        assert all(isinstance(p, Problem) for p in problems)
        
        # Verify each problem has valid structure
        for problem in problems:
            assert len(problem.numbers) == 4
            assert all(1 <= n <= 13 for n in problem.numbers)
            assert problem.problem_id is not None
            assert problem.canonical_solution is not None

    @pytest.mark.asyncio
    async def test_generate_problems_different_counts(self, problem_pool_service):
        """Test generating different numbers of problems"""
        for count in [1, 5, 10, 15]:
            problems = await problem_pool_service.generate_problems_for_game(count)
            assert len(problems) == count

    @pytest.mark.asyncio
    async def test_problems_have_valid_solutions(self, problem_pool_service):
        """Test that generated problems actually have valid solutions"""
        problems = await problem_pool_service.generate_problems_for_game(5)
        
        for problem in problems:
            # Verify using the solver
            solver = Solution(problem.numbers, target=24)
            solver.find_all_solutions()
            solutions = solver.get_all_solutions()
            
            assert len(solutions) > 0, f"Problem {problem.numbers} should have at least one solution"

    @pytest.mark.asyncio
    async def test_problems_are_unique(self, problem_pool_service):
        """Test that problems in a set are unique (no duplicate multisets)"""
        problems = await problem_pool_service.generate_problems_for_game(20)
        
        # Create multisets from problems
        multisets = [tuple(sorted(p.numbers)) for p in problems]
        
        # Check for uniqueness
        unique_multisets = set(multisets)
        assert len(unique_multisets) == len(multisets), "Generated problems should have unique multisets"

    @pytest.mark.asyncio
    async def test_canonical_solution_format(self, problem_pool_service):
        """Test that canonical solutions are properly formatted"""
        problems = await problem_pool_service.generate_problems_for_game(5)
        
        for problem in problems:
            assert isinstance(problem.canonical_solution, str)
            assert len(problem.canonical_solution) > 0
            # Should contain the numbers from the problem
            for number in problem.numbers:
                assert str(number) in problem.canonical_solution

    @pytest.mark.asyncio
    async def test_edge_cases(self, problem_pool_service):
        """Test edge cases for problem generation"""
        
        # Test minimum problem count
        problems = await problem_pool_service.generate_problems_for_game(1)
        assert len(problems) == 1
        
        # Test zero problems
        problems = await problem_pool_service.generate_problems_for_game(0)
        assert len(problems) == 0

    @pytest.mark.asyncio
    async def test_concurrent_generation(self, problem_pool_service):
        """Test concurrent problem generation"""
        # Generate multiple sets concurrently
        tasks = [
            problem_pool_service.generate_problems_for_game(5),
            problem_pool_service.generate_problems_for_game(5),
            problem_pool_service.generate_problems_for_game(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert len(results) == 3
        assert all(len(problems) == 5 for problems in results)

    def test_validate_numbers_basic(self):
        """Test basic number validation"""
        service = ProblemPoolService()
        
        # Valid numbers
        assert service.validate_numbers([1, 2, 3, 4]) == True
        assert service.validate_numbers([13, 13, 13, 13]) == True
        assert service.validate_numbers([1, 1, 8, 8]) == True
        
    def test_validate_numbers_invalid(self):
        """Test invalid number validation"""
        service = ProblemPoolService()
        
        # Invalid counts
        assert service.validate_numbers([1, 2, 3]) == False
        assert service.validate_numbers([1, 2, 3, 4, 5]) == False
        assert service.validate_numbers([]) == False
        
        # Invalid ranges
        assert service.validate_numbers([0, 2, 3, 4]) == False
        assert service.validate_numbers([1, 2, 3, 14]) == False
        assert service.validate_numbers([-1, 2, 3, 4]) == False

    def test_get_best_solution(self):
        """Test getting the best solution from multiple solutions"""
        service = ProblemPoolService()
        
        # Test with known problem
        numbers = [1, 1, 8, 8]
        solution = service.get_best_solution(numbers)
        
        assert solution is not None
        assert len(solution) > 0
        
        # Verify solution format (should be steps)
        # Format should be [operand1, operand2, result, operator, ...]
        assert len(solution) >= 4