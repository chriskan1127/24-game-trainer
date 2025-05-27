from kivy.app import App
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.properties import *
from kivy.uix.button import Button
from kivy.vector import Vector
from kivy.clock import Clock
from kivy.animation import Animation
from random import randint 
from copy import copy
from kivy.uix.floatlayout import FloatLayout
import sys # Add sys import for path manipulation
import os # Add os import for path manipulation

# Add lib directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.abspath(os.path.join(current_dir, '..', 'lib'))
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from solve_24 import Solution # Import the Python Solution class

# Color palette for modern, accessible design
COLORS = {
    'primary': (0.3, 0.6, 0.9, 1),        # Soft blue
    'success': (0.2, 0.7, 0.4, 1),        # Soft green
    'warning': (0.9, 0.6, 0.2, 1),        # Soft orange
    'surface': (0.98, 0.98, 0.99, 1),     # Off-white
    'accent': (0.6, 0.4, 0.8, 1),         # Soft purple
    'disabled': (0.8, 0.8, 0.8, 1),       # Light gray for disabled
}

class StartScreen(Widget):
    def start_game(self):
        # Get the main app and switch to game screen
        app = App.get_running_app()
        app.root.show_game()

class GameOverScreen(Widget):
    score_text = ObjectProperty(None)
    numbers_text = ObjectProperty(None)
    solution_text = ObjectProperty(None)
    
    def restart_game(self):
        # Get the main app and restart
        app = App.get_running_app()
        app.root.show_start_screen()
    
    def set_game_over_data(self, score, numbers, solution_text):
        self.score_text.text = f"Final Score: {score}"
        self.numbers_text.text = f"Numbers: {', '.join(map(str, numbers))}"
        self.solution_text.text = solution_text

#Note about the code: For Numberpanel and OperationPanel, the floatlayout is within the widget. 
#Thus, use self.parent.parent to access outermost layer

class Solve24Game(Widget):
    remaining_nums = BoundedNumericProperty(4, min=0, max=4, errorvalue=4)
    time_passed = BoundedNumericProperty(0, min=0, max=30, errorvalue=30)
    ops = ListProperty([])
    ops_state = OptionProperty("None", options=["Undo", "+", "-", "x", "/", "None"])
    operationpanel = ObjectProperty(None) 
    timelabel = ObjectProperty(None)
    scorelabel = ObjectProperty(None)
    targetlabel = ObjectProperty(None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.solver = None
        self.time_duration = 30
        self.current_numbers = []
    
    def format_solution(self, solution_steps):
        """Format the solution steps into human-readable text"""
        if not solution_steps:
            return "No solution found"
        
        formatted_lines = []
        formatted_lines.append("Solution:")
        formatted_lines.append("")
        
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
    
    def get_best_solution(self, numbers):
        """Get the best solution: first one without negative numbers, or last one if none"""
        solver = Solution([int(n) for n in numbers], target=24)
        solver.find_all_solutions()
        solutions = solver.get_all_solutions()
        
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
    
    def validate_numbers(self, numbers):
        """Validate if the given numbers can form the target (default 24) using the Python solver"""
        # Convert numbers to int if they are not, as the solver expects integers
        # The Python solver internally converts them to float for calculations.
        int_numbers = [int(n) for n in numbers]
        if self.solver is None:
            # Assuming the target is fetched from targetlabel or a default (24)
            # We can refine this if the target is dynamic and available.
            self.solver = Solution(int_numbers, target=self.targetlabel.target_number if self.targetlabel else 24)
        else:
            self.solver.numbers = int_numbers
            # Update target if necessary, e.g., self.solver.target = self.targetlabel.target_number
        return self.solver.is_valid_input()
    
    def timer_tick(self, dt=None):
        self.time_passed = self.time_passed + 1
        self.timelabel.time_remaining = self.timelabel.time_remaining - 1

    def start_state(self):
        self.remaining_nums = 4
        self.main_numberpanel = ObjectProperty(None)
        new_numberpanel = NumberPanel(pos_hint = {'x': 0.18, 'y': 0.3})
        
        # Generate valid numbers that can form 24
        while True:
            numbers = [randint(1, 13) for _ in range(4)]
            if self.validate_numbers(numbers):
                break
        
        self.current_numbers = numbers  # Store current numbers for game over screen
        self.ids.floatlayout.add_widget(new_numberpanel)
        self.main_numberpanel = new_numberpanel
        self.time_passed = 0
        self.timelabel.time_remaining = self.time_duration
        self.main_numberpanel.start(numbers)  # Pass the valid numbers
        self.bind(remaining_nums=self.finishedgame_callback)
        self.bind(time_passed=self.out_of_time)
        self.ops_state = "None"
        if len(self.ops) > 0:
            self.ops.pop()
        self.operationpanel.operation_id = 'None'
    
    def out_of_time(self, instance, value):
        if value == self.time_duration:
            # Show game over screen instead of restarting immediately
            app = App.get_running_app()
            score = self.scorelabel.score_number
            
            # Get the solution for current numbers
            solution_steps = self.get_best_solution(self.current_numbers)
            solution_text = self.format_solution(solution_steps)
            
            app.root.show_game_over(score, self.current_numbers, solution_text)

    def clear_operations(self):
        self.operationpanel.ids[self.operationpanel.operation_id].remove_operation()
    
    def finishedgame_callback(self, instance, value):
        if value == 1:
            if self.main_numberpanel.ids[self.main_numberpanel.first_operation].int_value == self.targetlabel.target_number:
                #self.ops.pop()
                self.scorelabel.score_number = self.scorelabel.score_number + 1
                self.ids.floatlayout.remove_widget(self.main_numberpanel)
                self.start_state()

class OperationPanel(Widget):
    operation_id = OptionProperty("None", options=["undo", "add", "subtract", "multiply", "divide", "None"])
    undo = ObjectProperty(None)
    add = ObjectProperty(None)
    subtract = ObjectProperty(None)
    divide = ObjectProperty(None)
    multiply = ObjectProperty(None)

    def add_op(self, block_instance):
        for block_id, block in self.ids.items():
            if block == block_instance:
                self.operation_id = block_id
                break

class OperationBlock(Button, Widget):
    activated = BooleanProperty(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.normal_color = COLORS['primary']
        self.activated_color = COLORS['success']
        self.disabled_color = COLORS['disabled']
        self.background_color = self.normal_color
    
    def remove_operation(self):
        self.background_color = self.normal_color
        self.parent.parent.parent.parent.ops_state = 'None'
        self.parent.parent.operation_id = 'None'
        self.activated = False
    
    def add_operation(self):
        self.parent.parent.parent.parent.ops_state = self.text
        self.parent.parent.add_op(self)
        self.background_color = self.activated_color
        self.activated = True
    
    def on_press(self):
        # Skip intermediate color, go directly to final state
        pass
    
    def on_release(self):
        if self.activated:
            self.remove_operation()
        else:
            if len(self.parent.parent.parent.parent.ops) < 1:
                self.background_color = self.normal_color
            else:
                if self.parent.parent.operation_id != 'None':
                    self.parent.parent.ids[self.parent.parent.operation_id].remove_operation()
                self.add_operation()

class UndoBlock(Button, Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.normal_color = COLORS['warning']
        self.background_color = self.normal_color
    
    def on_press(self):
        # Skip intermediate color, go directly to action
        pass
    
    def on_release(self):
        # Perform action without color change
        if len(self.parent.parent.parent.parent.main_numberpanel.operation_list) > 0:
            prev_state = self.parent.parent.parent.parent.main_numberpanel.operation_list.pop()
            self.parent.parent.parent.parent.main_numberpanel.assign_numblock_vals(prev_state)
            self.parent.parent.parent.parent.remaining_nums += 1 
            if self.parent.parent.parent.parent.main_numberpanel.first_operation != "None":
                self.parent.parent.parent.parent.main_numberpanel.remove_first_op()


class NumberPanel(Widget):
    number1 = ObjectProperty(None)
    number2 = ObjectProperty(None)
    number3 = ObjectProperty(None)
    number4 = ObjectProperty(None)
    operation_list = ListProperty([])

    first_operation = OptionProperty("None", options=["number1", "number2", "number3", "number4", "None"])
    
    def add_first_op(self, block_instance):
        for block_id, block in self.ids.items():
            if block == block_instance:
                self.first_operation = block_id
                break
    
    def remove_first_op(self):
        block_id = self.first_operation
        self.ids[block_id].remove_operation()
        self.first_operation = "None"

    def start(self, numbers=None):
        if numbers is None:
            self.number1.generate_value()
            self.number2.generate_value()
            self.number3.generate_value()
            self.number4.generate_value()
        else:
            self.number1.adjust_value(numbers[0])
            self.number2.adjust_value(numbers[1])
            self.number3.adjust_value(numbers[2])
            self.number4.adjust_value(numbers[3])
        self.remaining_nums = 4
    
    def compute(self, block_instance):
        self.operation_list.append(self.get_current_state())
        block_id = self.first_operation
        int1 = self.ids[block_id].int_value
        int2 = block_instance.int_value
        operation = self.parent.parent.ops_state
        output = 0
        if operation is '+':
            output = int1 + int2
        elif operation is '-':
            output = int1 - int2
        elif operation is 'x':
            output = int1 * int2
        elif operation is '/':
            output = '%.3f'%(int1 / int2)
        anim1 = Animation(x=block_instance.x, y=block_instance.y, duration=0.6)
        anim1.start(self.ids[block_id])
        self.ids[block_id].disable()
        anim2 = Animation(size_hint_value = 0.49, duration=0.10) + Animation(size_hint_value = 0.45, duration=0.09)
        anim2.start(block_instance)
        block_instance.adjust_value(output) #change block's number
        block_instance.remove_operation()
        block_instance.background_color = block_instance.success_color
        block_instance.add_operation()
        self.parent.parent.clear_operations()
        self.parent.parent.remaining_nums = self.parent.parent.remaining_nums - 1
        
    
    def get_current_state(self):
        ret_list = []
        ret_list.append(None if self.number1.disabled else self.number1.int_value)
        ret_list.append(None if self.number2.disabled else self.number2.int_value)
        ret_list.append(None if self.number3.disabled else self.number3.int_value)
        ret_list.append(None if self.number4.disabled else self.number4.int_value)
        return ret_list

    def assign_numblock_vals(self, num_list):
        self.number1.adjust_value_2(num_list[0])
        self.number2.adjust_value_2(num_list[1])
        self.number3.adjust_value_2(num_list[2])
        self.number4.adjust_value_2(num_list[3])

        

class NumberBlock(Button, Widget):
    int_value = NumericProperty(0)
    activated = BooleanProperty(0)
    disabled = BooleanProperty(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.normal_color = COLORS['surface']
        self.activated_color = COLORS['accent']
        self.pressed_color = COLORS['primary']
        self.success_color = COLORS['success']
        self.disabled_color = COLORS['disabled']
        self.background_color = self.normal_color
    
    def remove_operation(self):
        self.background_color = self.normal_color
        if len(self.parent.parent.parent.parent.ops) > 0:
            self.parent.parent.parent.parent.ops.pop()
        self.parent.parent.first_operation = "None"
        self.activated = False

    def add_operation(self):
        self.parent.parent.parent.parent.ops.append(self.int_value)
        self.parent.parent.add_first_op(self)
        self.background_color = self.activated_color
        self.activated = True
    
    def generate_value(self):
        value = randint(1, 13)
        self.text = str(value)
        self.int_value = value
        self.disabled = False
        self.background_color = self.normal_color

    def adjust_value(self, int):
        self.int_value = int
        self.text = str(int)
        self.background_color = self.normal_color

    def adjust_value_2(self, int): 
        if int is not None:
            self.int_value = int
            self.text = str(int)
            self.reinstate()
        else:
            self.int_value = 0
            self.disable()

    def disable(self):
        self.size_hint_value = 0
        self.opacity = 0
        self.disabled = True

    def reinstate(self):
        self.background_color = self.normal_color
        self.size_hint_value = 0.45
        self.opacity = 1
        self.disabled = False
        self.activated = False
    
    def on_press(self):
        if not self.disabled:
            # Immediately go to purple selection color and provide size feedback
            self.background_color = self.activated_color
            self.size_hint_value = 0.41

    def on_release(self):
        if not self.disabled:
            self.size_hint_value = 0.45
            if self.activated:
                # If already activated, deactivate and return to normal color
                self.remove_operation()
            else:
                if len(self.parent.parent.parent.parent.ops) < 1:
                    # If no operations, activate this button (keep purple)
                    self.add_operation()
                elif self.parent.parent.parent.parent.ops_state == 'None':
                    # If no operation selected, deactivate previous and activate this
                    self.parent.parent.ids[self.parent.parent.first_operation].remove_operation()
                    self.add_operation()
                else:
                    # Perform computation, color will be set by compute method
                    self.parent.parent.compute(self)

class Solve24App(App):
    def build(self):
        return MainContainer()

class MainContainer(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.start_screen = None
        self.game_screen = None
        self.game_over_screen = None
        self.show_start_screen()
    
    def show_start_screen(self):
        self.clear_widgets()
        self.start_screen = StartScreen()
        self.add_widget(self.start_screen)
    
    def show_game(self):
        self.clear_widgets()
        self.game_screen = Solve24Game()
        self.add_widget(self.game_screen)
        self.game_screen.start_state()
        Clock.schedule_interval(self.game_screen.timer_tick, 1)
    
    def show_game_over(self, score, numbers, solution_text):
        if hasattr(self, 'game_screen') and self.game_screen:
            Clock.unschedule(self.game_screen.timer_tick)
        self.clear_widgets()
        self.game_over_screen = GameOverScreen()
        self.game_over_screen.set_game_over_data(score, numbers, solution_text)
        self.add_widget(self.game_over_screen)
    
if __name__ == '__main__':
    Solve24App().run()
