import math
import argparse

class Solution:
    def __init__(self, numbers, target=24, max_generated=1024):
        self.numbers = numbers
        self.target = float(target)
        self.max_generated = max_generated
        self.solutions = []
        self.first_solution = []

    def get_all_solutions(self):
        return self.solutions

    def get_first_solution(self):
        return self.first_solution

    def get_max_generated(self):
        return self.max_generated

    def set_max_generated(self, max_generated):
        self.max_generated = max_generated

    def is_valid_input(self):
        # In Python, we can directly use the numbers if they are already floats or ints.
        # The C++ version converts ints to doubles; Python handles mixed types automatically.
        return self._solution_exists([float(n) for n in self.numbers], self.target)

    def find_first_solution(self):
        self.first_solution = []
        output = []
        return self._solve_first([float(n) for n in self.numbers], output, self.target)

    def find_all_solutions(self):
        self.solutions = []
        output = []
        self._solve_all([float(n) for n in self.numbers], output, self.target)

    def print_solutions(self):
        for i, sol in enumerate(self.solutions):
            print(f"Solution {i+1}:")
            self._print_output_python(sol)

    def _print_output_python(self, output):
        for item in output:
            print(item)

    def _solution_exists(self, nums, target):
        if not nums:
            return False
        if len(nums) == 1:
            return math.isclose(nums[0], target)

        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                new_nums_base = [nums[k] for k in range(len(nums)) if k != i and k != j]
                
                # Perform operations
                # Addition
                if self._solution_exists(new_nums_base + [nums[i] + nums[j]], target):
                    return True
                # Multiplication
                if self._solution_exists(new_nums_base + [nums[i] * nums[j]], target):
                    return True
                # Subtraction (nums[i] - nums[j])
                if self._solution_exists(new_nums_base + [nums[i] - nums[j]], target):
                    return True
                # Division (nums[i] / nums[j])
                if not math.isclose(nums[j], 0):
                    if self._solution_exists(new_nums_base + [nums[i] / nums[j]], target):
                        return True
                # Subtraction (nums[j] - nums[i])
                if self._solution_exists(new_nums_base + [nums[j] - nums[i]], target):
                    return True
                # Division (nums[j] / nums[i])
                if not math.isclose(nums[i], 0):
                    if self._solution_exists(new_nums_base + [nums[j] / nums[i]], target):
                        return True
        return False

    def _solve_first(self, nums, prev_ops, target):
        if len(self.first_solution) > 0 : # an optimization from the C++ code isn't present, it's not needed as Python recursion depth is higher
            pass # Python doesn't strictly need this check as it returns immediately upon finding a solution

        if len(nums) == 1:
            if math.isclose(nums[0], target):
                self.first_solution = list(prev_ops) # Store a copy
                # self._print_output_python(prev_ops) # Assuming printing is not desired here, but in the caller
                return True
            return False

        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                new_nums_base = [nums[k] for k in range(len(nums)) if k != i and k != j]
                
                val1_str = str(nums[i])
                val2_str = str(nums[j])

                # Store original ops length to backtrack
                original_ops_len = len(prev_ops)

                # nums[i] op nums[j]
                prev_ops.extend([val1_str, val2_str])

                # Addition
                prev_ops.extend([str(nums[i] + nums[j]), "+"])
                if self._solve_first(new_nums_base + [nums[i] + nums[j]], prev_ops, target):
                    return True
                prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops

                # Multiplication
                prev_ops.extend([str(nums[i] * nums[j]), "*"])
                if self._solve_first(new_nums_base + [nums[i] * nums[j]], prev_ops, target):
                    return True
                prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops

                # Subtraction
                prev_ops.extend([str(nums[i] - nums[j]), "-"])
                if self._solve_first(new_nums_base + [nums[i] - nums[j]], prev_ops, target):
                    return True
                prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops
                
                # Division
                if not math.isclose(nums[j], 0):
                    prev_ops.extend([str(nums[i] / nums[j]), "/"])
                    if self._solve_first(new_nums_base + [nums[i] / nums[j]], prev_ops, target):
                        return True
                    prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops
                
                prev_ops = prev_ops[:original_ops_len] # Backtrack completely for swapped order

                # nums[j] op nums[i]
                prev_ops.extend([val2_str, val1_str])
                original_ops_len_swapped = len(prev_ops)


                # Subtraction
                prev_ops.extend([str(nums[j] - nums[i]), "-"])
                if self._solve_first(new_nums_base + [nums[j] - nums[i]], prev_ops, target):
                    return True
                prev_ops = prev_ops[:original_ops_len_swapped-2+2] # Backtrack ops for swapped

                # Division
                if not math.isclose(nums[i], 0):
                    prev_ops.extend([str(nums[j] / nums[i]), "/"])
                    if self._solve_first(new_nums_base + [nums[j] / nums[i]], prev_ops, target):
                        return True
                    # prev_ops = prev_ops[:original_ops_len_swapped-2+2] # Backtrack ops for swapped. Not strictly needed before full backtrack.

                prev_ops = prev_ops[:original_ops_len] # Full backtrack before next i,j pair

        return False

    def _solve_all(self, nums, prev_ops, target):
        if len(self.solutions) >= self.max_generated:
            return

        if len(nums) == 1:
            if math.isclose(nums[0], target):
                self.solutions.append(list(prev_ops)) # Store a copy
            return

        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if len(self.solutions) >= self.max_generated:
                    return
                
                new_nums_base = [nums[k] for k in range(len(nums)) if k != i and k != j]
                
                val1_str = str(nums[i])
                val2_str = str(nums[j])
                
                original_ops_len = len(prev_ops)

                # nums[i] op nums[j]
                prev_ops.extend([val1_str, val2_str])

                # Addition
                current_op_val = nums[i] + nums[j]
                prev_ops.extend([str(current_op_val), "+"])
                self._solve_all(new_nums_base + [current_op_val], prev_ops, target)
                prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops
                if len(self.solutions) >= self.max_generated: return

                # Multiplication
                current_op_val = nums[i] * nums[j]
                prev_ops.extend([str(current_op_val), "*"])
                self._solve_all(new_nums_base + [current_op_val], prev_ops, target)
                prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops
                if len(self.solutions) >= self.max_generated: return

                # Subtraction
                current_op_val = nums[i] - nums[j]
                prev_ops.extend([str(current_op_val), "-"])
                self._solve_all(new_nums_base + [current_op_val], prev_ops, target)
                prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops
                if len(self.solutions) >= self.max_generated: return
                
                # Division
                if not math.isclose(nums[j], 0):
                    current_op_val = nums[i] / nums[j]
                    prev_ops.extend([str(current_op_val), "/"])
                    self._solve_all(new_nums_base + [current_op_val], prev_ops, target)
                    prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops
                    if len(self.solutions) >= self.max_generated: return
                
                prev_ops = prev_ops[:original_ops_len] # Backtrack completely for swapped order

                # nums[j] op nums[i]
                prev_ops.extend([val2_str, val1_str])
                # original_ops_len_swapped = len(prev_ops) # Not needed, use original_ops_len + 2

                # Subtraction
                current_op_val = nums[j] - nums[i]
                prev_ops.extend([str(current_op_val), "-"])
                self._solve_all(new_nums_base + [current_op_val], prev_ops, target)
                prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops
                if len(self.solutions) >= self.max_generated: return
                
                # Division
                if not math.isclose(nums[i], 0):
                    current_op_val = nums[j] / nums[i]
                    prev_ops.extend([str(current_op_val), "/"])
                    self._solve_all(new_nums_base + [current_op_val], prev_ops, target)
                    # prev_ops = prev_ops[:original_ops_len+2] # Backtrack ops. Not strictly needed.
                    if len(self.solutions) >= self.max_generated: return

                prev_ops = prev_ops[:original_ops_len] # Full backtrack before next i,j pair
        return 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Solve the 24 game.")
    parser.add_argument("--numbers", type=str, help="The numbers to use in the 24 game.")
    parser.add_argument("--target", type=float, default=24, help="The target value.")
    parser.add_argument("--max_generated", type=int, default=1024, help="The maximum number of solutions to generate.")
    args = parser.parse_args()

    numbers = [float(n) for n in args.numbers.split(",")]
    solution = Solution(numbers, args.target, args.max_generated)
    solution.find_all_solutions()
    solution.print_solutions()
