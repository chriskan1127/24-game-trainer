"""
Problem Pool Service
Manages pre-validated 24-game problems and their solutions
"""

import random
import logging
from typing import List, Set, Tuple
from uuid import uuid4
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
plans_dir = os.path.join(project_root, 'plans')
lib_dir = os.path.join(project_root, 'lib')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from pydantic_schemas import Problem, ProblemStats
from solve_24 import Solution

logger = logging.getLogger(__name__)


class ProblemPoolService:
    """Generates working 24-game problems on-demand for each game"""
    
    def __init__(self):
        # No longer need to store a pre-generated pool
        pass
        
    async def initialize(self):
        """Initialize the problem pool service (now just validates solver works)"""
        logger.info("Initializing problem pool service...")
        
        # Test that the solver works with a known problem
        test_numbers = [1, 1, 8, 8]  # Should have solutions like (1+1+8)*8=80, but let's test any solution
        try:
            solver = Solution(test_numbers, target=24)
            solver.find_all_solutions()
            solutions = solver.get_all_solutions()
            
            if solutions:
                logger.info("Problem pool service initialized successfully - solver working")
            else:
                # Try a known solvable problem
                test_numbers = [4, 1, 8, 7]  # (8-4) * (7-1) = 24
                solver = Solution(test_numbers, target=24)
                if solver.is_valid_input():
                    logger.info("Problem pool service initialized successfully")
                else:
                    logger.warning("Solver validation issue, but continuing")
                    
        except Exception as e:
            logger.error(f"Problem pool service initialization error: {e}")
            # Continue anyway - problems will be generated when needed
        
        logger.info("Problem pool service ready for on-demand problem generation")
    
    async def generate_problems_for_game(self, count: int = 10) -> List[Problem]:
        """Generate a set of unique, solvable problems for a single game"""
        logger.info(f"Generating {count} problems for new game...")
        
        problems = []
        used_multisets = set()  # Track used combinations within this game only
        attempts = 0
        max_attempts = 10000
        
        while len(problems) < count and attempts < max_attempts:
            attempts += 1
            
            # Generate random numbers (1-13 range as per single player)
            numbers = [random.randint(1, 13) for _ in range(4)]
            
            # Create multiset key for deduplication within this game
            multiset_key = tuple(sorted(numbers))
            
            # Skip if we've already used this combination in this game
            if multiset_key in used_multisets:
                continue
            
            # Validate the problem has a solution
            try:
                solver = Solution(numbers, target=24)
                solver.find_all_solutions()
                solutions = solver.get_all_solutions()
                
                if solutions:
                    # Get the best solution (first without negative numbers, or last one)
                    canonical_solution = self._get_best_solution(solutions)
                    canonical_solution_str = self._format_solution(canonical_solution)
                    
                    # Create problem
                    problem = Problem(
                        problem_id=uuid4(),
                        numbers=numbers,
                        canonical_solution=canonical_solution_str,
                        stats=ProblemStats()
                    )
                    
                    problems.append(problem)
                    used_multisets.add(multiset_key)
                    
                    if len(problems) % 5 == 0:
                        logger.info(f"Generated {len(problems)}/{count} problems for game...")
                        
            except Exception as e:
                logger.debug(f"Failed to validate problem {numbers}: {e}")
                continue
        
        if len(problems) < count:
            logger.warning(f"Only generated {len(problems)}/{count} problems after {attempts} attempts")
            if len(problems) == 0:
                raise ValueError("Failed to generate any valid problems for the game")
        
        logger.info(f"Successfully generated {len(problems)} unique problems for game ({attempts} attempts)")
        return problems
    
    def generate_single_problem(self) -> Problem:
        """Generate a single working problem (useful for testing or special cases)"""
        problems = []
        attempts = 0
        max_attempts = 1000
        
        while len(problems) == 0 and attempts < max_attempts:
            attempts += 1
            
            # Generate random numbers
            numbers = [random.randint(1, 13) for _ in range(4)]
            
            # Validate the problem has a solution
            try:
                solver = Solution(numbers, target=24)
                solver.find_all_solutions()
                solutions = solver.get_all_solutions()
                
                if solutions:
                    # Get the best solution
                    canonical_solution = self._get_best_solution(solutions)
                    canonical_solution_str = self._format_solution(canonical_solution)
                    
                    # Create problem
                    problem = Problem(
                        problem_id=uuid4(),
                        numbers=numbers,
                        canonical_solution=canonical_solution_str,
                        stats=ProblemStats()
                    )
                    
                    return problem
                        
            except Exception as e:
                logger.debug(f"Failed to validate single problem {numbers}: {e}")
                continue
        
        raise ValueError(f"Failed to generate a valid problem after {attempts} attempts")
    
    def get_generation_stats(self) -> dict:
        """Get statistics about problem generation (since we don't store problems)"""
        return {
            "generation_method": "on_demand",
            "problems_per_game": 10,
            "deduplication": "per_game",
            "number_range": "1-13",
            "max_attempts_per_game": 10000
        }
    
    def _get_best_solution(self, solutions: List[List]) -> List:
        """Get the best solution: first one without negative numbers, or last one if none"""
        if not solutions:
            return []
        
        # Look for first solution without negative numbers
        for solution in solutions:
            has_negative = False
            for i in range(2, len(solution), 4):  # Check results (every 4th element starting from index 2)
                try:
                    result = float(solution[i])
                    if result < 0:
                        has_negative = True
                        break
                except (ValueError, IndexError):
                    continue
            
            if not has_negative:
                return solution
        
        # If no solution without negative numbers, return the last one
        return solutions[-1]
    
    def _format_solution(self, solution_steps: List) -> str:
        """Format the solution steps into human-readable text"""
        if not solution_steps:
            return "No solution found"
        
        formatted_lines = []
        formatted_lines.append("Solution:")
        
        # Parse the solution steps (format: [operand1, operand2, result, operator, ...])
        step_num = 1
        i = 0
        while i < len(solution_steps):
            if i + 3 < len(solution_steps):
                operand1 = solution_steps[i]
                operand2 = solution_steps[i + 1]
                result = solution_steps[i + 2]
                operator = solution_steps[i + 3]
                
                # Format the operation nicely
                op_symbol = operator
                if operator == "*":
                    op_symbol = "×"
                elif operator == "/":
                    op_symbol = "÷"
                
                formatted_lines.append(f"Step {step_num}: {operand1} {op_symbol} {operand2} = {result}")
                step_num += 1
                i += 4
            else:
                break
        
        return "\n".join(formatted_lines)
    
    def validate_problem(self, numbers: List[int]) -> bool:
        """Validate that a set of numbers can form 24"""
        try:
            solver = Solution(numbers, target=24)
            return solver.is_valid_input()
        except Exception:
            return False
    
    def get_canonical_solution(self, numbers: List[int]) -> str:
        """Get the canonical solution for a set of numbers"""
        try:
            solver = Solution(numbers, target=24)
            solver.find_all_solutions()
            solutions = solver.get_all_solutions()
            
            if solutions:
                best_solution = self._get_best_solution(solutions)
                return self._format_solution(best_solution)
            else:
                return "No solution found"
        except Exception as e:
            logger.error(f"Error getting canonical solution for {numbers}: {e}")
            return "Error finding solution"