import sys
import os
from typing import List, Dict, Any, Optional, Tuple
import logging
import json

# Add lib directory to path to import solve_24
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.abspath(os.path.join(current_dir, '..', '..', 'lib'))
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

try:
    from solve_24 import Solution
except ImportError as e:
    logging.error(f"Failed to import solve_24 module: {e}")
    Solution = None

logger = logging.getLogger(__name__)


class SolverService:
    """Service for validating 24-game solutions using the Python solver."""
    
    def __init__(self):
        self.solver_available = Solution is not None
        if not self.solver_available:
            logger.warning("24-game solver not available - solution validation will be limited")
    
    def validate_solution(self, numbers: List[int], solution_steps: List[Any], target: int = 24) -> Tuple[bool, str]:
        """
        Validate a solution for the 24-game.
        
        Args:
            numbers: List of 4 numbers for the game
            solution_steps: List representing the solution steps
            target: Target number (default 24)
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        if not self.solver_available:
            return self._basic_validation(solution_steps, target)
        
        try:
            # Create solver instance
            solver = Solution(numbers, target=target)
            
            # Validate input numbers
            if not solver.is_valid_input():
                return False, "Invalid input numbers"
            
            # Find all valid solutions
            solver.find_all_solutions()
            valid_solutions = solver.get_all_solutions()
            
            if not valid_solutions:
                return False, "No valid solutions exist for these numbers"
            
            # Check if the provided solution matches any valid solution
            if self._solution_matches_any(solution_steps, valid_solutions):
                return True, "Solution is valid"
            else:
                return False, "Solution does not match any valid solution"
                
        except Exception as e:
            logger.error(f"Error validating solution: {e}")
            return False, f"Validation error: {str(e)}"
    
    def generate_valid_numbers(self, target: int = 24) -> List[int]:
        """
        Generate a set of 4 numbers that can form the target.
        
        Args:
            target: Target number (default 24)
            
        Returns:
            List[int]: List of 4 numbers that can form the target
        """
        if not self.solver_available:
            # Fallback to known working combinations
            return self._get_fallback_numbers()
        
        import random
        max_attempts = 1000
        
        for _ in range(max_attempts):
            numbers = [random.randint(1, 13) for _ in range(4)]
            
            try:
                solver = Solution(numbers, target=target)
                if solver.is_valid_input():
                    solver.find_all_solutions()
                    if solver.get_all_solutions():
                        logger.info(f"Generated valid numbers: {numbers}")
                        return numbers
            except Exception as e:
                logger.debug(f"Error checking numbers {numbers}: {e}")
                continue
        
        # If we can't generate valid numbers, return a known working set
        logger.warning("Could not generate valid numbers, using fallback")
        return self._get_fallback_numbers()
    
    def get_solution_for_numbers(self, numbers: List[int], target: int = 24) -> Optional[List[Any]]:
        """
        Get a solution for the given numbers.
        
        Args:
            numbers: List of 4 numbers
            target: Target number (default 24)
            
        Returns:
            Optional[List[Any]]: Solution steps if found, None otherwise
        """
        if not self.solver_available:
            return None
        
        try:
            solver = Solution(numbers, target=target)
            if not solver.is_valid_input():
                return None
            
            solver.find_all_solutions()
            solutions = solver.get_all_solutions()
            
            if solutions:
                # Return the first solution that doesn't use negative numbers
                for solution in solutions:
                    if self._solution_avoids_negatives(solution):
                        return solution
                # If no solution avoids negatives, return the last one
                return solutions[-1]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting solution for numbers {numbers}: {e}")
            return None

    
    def _basic_validation(self, solution_steps: List[Any], target: int) -> Tuple[bool, str]:
        """Basic validation when solver is not available."""
        try:
            # Very basic check - just verify the format
            if not solution_steps or len(solution_steps) < 4:
                return False, "Solution too short"
            
            # For now, assume it's valid if it has proper structure
            return True, "Basic validation passed (full solver not available)"
            
        except Exception as e:
            return False, f"Basic validation error: {str(e)}"
    
    def _solution_matches_any(self, solution_steps: List[Any], valid_solutions: List[List[Any]]) -> bool:
        """Check if solution matches any of the valid solutions."""
        try:
            # Convert solution to comparable format
            solution_str = json.dumps(solution_steps, sort_keys=True)
            
            for valid_solution in valid_solutions:
                valid_str = json.dumps(valid_solution, sort_keys=True)
                if solution_str == valid_str:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error comparing solutions: {e}")
            return False
    
    def _solution_avoids_negatives(self, solution_steps: List[Any]) -> bool:
        """Check if solution avoids negative intermediate results."""
        try:
            # Check intermediate results (every 4th element starting from index 2)
            for i in range(2, len(solution_steps), 4):
                try:
                    result = float(solution_steps[i])
                    if result < 0:
                        return False
                except (ValueError, IndexError):
                    continue
            return True
            
        except Exception as e:
            logger.error(f"Error checking for negatives: {e}")
            return True  # Default to true if can't check
    
    def _get_fallback_numbers(self) -> List[int]:
        """Get a known working set of numbers."""
        # These are known to work for target 24
        fallback_sets = [
            [1, 1, 8, 8],
            [2, 2, 10, 10],
            [3, 3, 8, 8],
            [4, 4, 6, 6],
            [1, 2, 3, 4],
            [2, 3, 4, 5],
        ]
        
        import random
        return random.choice(fallback_sets)


# Global service instance
solver_service = SolverService() 