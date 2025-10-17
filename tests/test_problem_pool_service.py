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

    def test_best_solution_avoids_fractions(self):
        """Test that best solution prefers solutions without fractions"""
        service = ProblemPoolService()

        # Find solutions for a problem
        numbers = [3, 3, 8, 8]  # Has solutions with and without fractions
        solver = Solution(numbers, target=24)
        solver.find_all_solutions()
        all_solutions = solver.get_all_solutions()

        if len(all_solutions) > 1:
            best_solution = service._get_best_solution(all_solutions)

            # Check that the best solution doesn't have fractions
            has_fraction = False
            for i in range(2, len(best_solution), 4):
                try:
                    result = float(best_solution[i])
                    if result != int(result):
                        has_fraction = True
                        break
                except (ValueError, IndexError):
                    continue

            # If there exists a solution without fractions, it should be chosen
            # Check if any solution exists without fractions
            solutions_without_fractions = []
            for sol in all_solutions:
                sol_has_fraction = False
                for i in range(2, len(sol), 4):
                    try:
                        result = float(sol[i])
                        if result != int(result):
                            sol_has_fraction = True
                            break
                    except (ValueError, IndexError):
                        continue
                if not sol_has_fraction:
                    solutions_without_fractions.append(sol)

            # If there are solutions without fractions, best should be one of them
            if solutions_without_fractions:
                assert not has_fraction, "Best solution should not have fractions when alternatives exist"

    def test_best_solution_avoids_negatives(self):
        """Test that best solution prefers solutions without negative numbers"""
        service = ProblemPoolService()

        # Find solutions for a problem that might have negative intermediates
        numbers = [1, 2, 3, 6]  # Some solutions might have negative intermediates
        solver = Solution(numbers, target=24)
        solver.find_all_solutions()
        all_solutions = solver.get_all_solutions()

        if len(all_solutions) > 1:
            best_solution = service._get_best_solution(all_solutions)

            # Check that the best solution doesn't have negative numbers
            has_negative = False
            for i in range(2, len(best_solution), 4):
                try:
                    result = float(best_solution[i])
                    if result < 0:
                        has_negative = True
                        break
                except (ValueError, IndexError):
                    continue

            # Check if any solution exists without negatives
            solutions_without_negatives = []
            for sol in all_solutions:
                sol_has_negative = False
                for i in range(2, len(sol), 4):
                    try:
                        result = float(sol[i])
                        if result < 0:
                            sol_has_negative = True
                            break
                    except (ValueError, IndexError):
                        continue
                if not sol_has_negative:
                    solutions_without_negatives.append(sol)

            # If there are solutions without negatives, best should be one of them
            if solutions_without_negatives:
                assert not has_negative, "Best solution should not have negatives when alternatives exist"

    def test_best_solution_no_fractions_and_no_negatives(self):
        """Test that best solution prefers solutions without both fractions and negatives"""
        service = ProblemPoolService()

        # Test with a problem known to have clean solutions
        numbers = [4, 1, 8, 7]  # (8-4) * (7-1) = 4*6 = 24
        solver = Solution(numbers, target=24)
        solver.find_all_solutions()
        all_solutions = solver.get_all_solutions()

        best_solution = service._get_best_solution(all_solutions)

        # Verify best solution has no fractions and no negatives
        has_fraction = False
        has_negative = False
        for i in range(2, len(best_solution), 4):
            try:
                result = float(best_solution[i])
                if result < 0:
                    has_negative = True
                if result != int(result):
                    has_fraction = True
            except (ValueError, IndexError):
                continue

        # For this problem, there should be clean solutions
        assert not has_fraction, "Best solution should not have fractions"
        assert not has_negative, "Best solution should not have negatives"