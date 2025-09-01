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
import json
import asyncio
import threading
import websockets
import requests
from typing import Dict, List, Optional, Any

# Add lib directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.abspath(os.path.join(current_dir, '..', 'lib'))
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from solve_24 import Solution # Import the Python Solution class

# Configuration
SERVER_BASE_URL = "http://localhost:8000"
WS_BASE_URL = "ws://localhost:8000"

# Color palette for modern, accessible design
COLORS = {
    'primary': (0.3, 0.6, 0.9, 1),        # Soft blue
    'success': (0.2, 0.7, 0.4, 1),        # Soft green
    'warning': (0.9, 0.6, 0.2, 1),        # Soft orange
    'surface': (0.98, 0.98, 0.99, 1),     # Off-white
    'accent': (0.6, 0.4, 0.8, 1),         # Soft purple
    'disabled': (0.8, 0.8, 0.8, 1),       # Light gray for disabled
}

class WebSocketClient:
    """Handles WebSocket communication with the game server"""
    
    def __init__(self, game_code: str, player_id: str, message_handler):
        self.game_code = game_code
        self.player_id = player_id
        self.message_handler = message_handler
        self.websocket = None
        self.connected = False
        self.running = False
        
    async def connect(self):
        """Connect to the WebSocket server"""
        try:
            uri = f"{WS_BASE_URL}/ws/{self.game_code}/{self.player_id}"
            self.websocket = await websockets.connect(uri)
            self.connected = True
            self.running = True
            
            # Listen for messages
            while self.running:
                try:
                    message = await self.websocket.recv()
                    data = json.loads(message)
                    Clock.schedule_once(lambda dt: self.message_handler(data), 0)
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    print(f"WebSocket error: {e}")
                    break
                    
        except Exception as e:
            print(f"Failed to connect to WebSocket: {e}")
            Clock.schedule_once(lambda dt: self.message_handler({
                "type": "error",
                "message": f"Failed to connect: {e}"
            }), 0)
            
    async def send_message(self, message: dict):
        """Send a message to the server"""
        if self.websocket and self.connected:
            try:
                await self.websocket.send(json.dumps(message))
            except Exception as e:
                print(f"Failed to send message: {e}")
                
    def disconnect(self):
        """Disconnect from the server"""
        self.running = False
        self.connected = False
            
    def start_connection(self):
        """Start the WebSocket connection in a separate thread"""
        def run_async():
            asyncio.run(self.connect())
            
        thread = threading.Thread(target=run_async)
        thread.daemon = True
        thread.start()

class MenuScreen(Widget):
    def create_game(self, player_name: str):
        """Create a new game on the server"""
        if not player_name.strip():
            self.show_status("Please enter your name")
            return
            
        try:
            response = requests.post(
                f"{SERVER_BASE_URL}/api/games/create",
                json={
                    "host_username": player_name.strip(),
                    "target": 24,
                    "time_limit": 30,
                    "max_players": 10,
                    "points_to_win": 10
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    game_code = data["data"]["game_code"]
                    host_id = data["data"]["host_id"]
                    app = App.get_running_app()
                    app.root.show_lobby(game_code, player_name.strip(), host_id, is_host=True)
                else:
                    self.show_status(data.get("message", "Failed to create game"))
            else:
                error_msg = response.json().get("detail", "Failed to create game")
                self.show_status(error_msg)
                
        except Exception as e:
            self.show_status(f"Connection error: {e}")
    
    def join_game(self, game_code: str, player_name: str):
        """Join an existing game"""
        if not game_code.strip() or not player_name.strip():
            self.show_status("Please enter both game code and name")
            return
            
        try:
            response = requests.post(
                f"{SERVER_BASE_URL}/api/games/{game_code.upper()}/join",
                json={"username": player_name.strip()},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    player_id = data["data"]["player_id"]
                    app = App.get_running_app()
                    app.root.show_lobby(game_code.upper(), player_name.strip(), player_id, is_host=False)
                else:
                    self.show_status(data.get("message", "Failed to join game"))
            else:
                error_msg = response.json().get("detail", "Failed to join game")
                self.show_status(error_msg)
                
        except Exception as e:
            self.show_status(f"Connection error: {e}")
    
    def show_status(self, message: str):
        """Show a status message to the user"""
        if hasattr(self, 'ids') and 'status_label' in self.ids:
            self.ids.status_label.text = message

class LobbyScreen(Widget):
    game_code = StringProperty('')
    
    def __init__(self, game_code: str, player_name: str, player_id: str, is_host: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.game_code = game_code
        self.player_name = player_name
        self.player_id = player_id
        self.is_host = is_host
        self.ws_client = None
        self.players = []
        
        # Connect to WebSocket
        Clock.schedule_once(self.connect_websocket, 0.1)
        
    def connect_websocket(self, dt):
        """Connect to the WebSocket server"""
        self.ws_client = WebSocketClient(
            self.game_code, 
            self.player_id, 
            self.handle_websocket_message
        )
        self.ws_client.start_connection()
        
    def handle_websocket_message(self, data: dict):
        """Handle incoming WebSocket messages"""
        msg_type = data.get("type")
        
        if msg_type == "game_state":
            self.update_game_state(data.get("game", {}))
        elif msg_type == "game_started":
            self.start_game_with_data(data.get("game", {}))
        elif msg_type == "error":
            self.show_status(data.get("message", "Unknown error"))
        elif msg_type == "player_ready_changed":
            # Refresh game state when player ready status changes
            self.refresh_game_state()
            
    def refresh_game_state(self):
        """Refresh game state from server"""
        try:
            response = requests.get(
                f"{SERVER_BASE_URL}/api/games/{self.game_code}/status",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self.update_game_state(data["data"]["game"])
        except Exception as e:
            print(f"Failed to refresh game state: {e}")
            
    def update_game_state(self, game_data: dict):
        """Update the lobby with current game state"""
        self.players = game_data.get("players", [])
        
        # Update players list
        if hasattr(self, 'ids') and 'players_list' in self.ids:
            self.ids.players_list.clear_widgets()
            for player in self.players:
                from kivy.uix.label import Label
                status_text = " (Host)" if player.get("is_host") else ""
                ready_text = " - Ready" if player.get("is_ready") else " - Not Ready"
                player_label = Label(
                    text=f"{player['username']}{status_text} - Score: {player.get('score', 0)}{ready_text}",
                    size_hint_y=None,
                    height=40,
                    color=(0.2, 0.2, 0.3, 1),
                    font_size=16
                )
                self.ids.players_list.add_widget(player_label)
        
        # Update start button (only show for host, and only if enough players)
        if hasattr(self, 'ids') and 'start_button' in self.ids:
            can_start = (self.is_host and 
                        len(self.players) >= 2 and 
                        game_data.get("status") == "waiting")
            self.ids.start_button.disabled = not can_start
            if not self.is_host:
                self.ids.start_button.text = "Waiting for host..."
                self.ids.start_button.disabled = True
            
    def start_game(self):
        """Start the game (host only)"""
        if self.is_host and self.ws_client:
            try:
                response = requests.post(
                    f"{SERVER_BASE_URL}/api/games/{self.game_code}/start",
                    params={"player_id": self.player_id},
                    timeout=5
                )
                if response.status_code != 200:
                    error_msg = response.json().get("detail", "Failed to start game")
                    self.show_status(error_msg)
            except Exception as e:
                self.show_status(f"Failed to start game: {e}")
            
    def start_game_with_data(self, game_data: dict):
        """Start a game round with the given game data"""
        current_round = game_data.get("current_round", {})
        numbers = current_round.get("numbers", [1, 2, 3, 4])
        round_num = current_round.get("round_number", 1)
        
        app = App.get_running_app()
        app.root.show_game(self.game_code, self.player_name, self.player_id, numbers, round_num, self.ws_client)
            
    def leave_game(self):
        """Leave the current game"""
        if self.ws_client:
            self.ws_client.disconnect()
        app = App.get_running_app()
        app.root.show_menu()
        
    def show_status(self, message: str):
        """Show a status message"""
        if hasattr(self, 'ids') and 'status_label' in self.ids:
            self.ids.status_label.text = message

#Note about the code: For Numberpanel and OperationPanel, the floatlayout is within the widget. 
#Thus, use self.parent.parent to access outermost layer

class MultiplayerGameScreen(Widget):
    remaining_nums = BoundedNumericProperty(4, min=0, max=4, errorvalue=4)
    time_passed = BoundedNumericProperty(0, min=0, max=30, errorvalue=30)
    ops = ListProperty([])
    ops_state = OptionProperty("None", options=["Undo", "+", "-", "x", "/", "None"])
    operationpanel = ObjectProperty(None) 
    timelabel = ObjectProperty(None)
    scorelabel = ObjectProperty(None)
    targetlabel = ObjectProperty(None)
    round_num = NumericProperty(1)
    
    def __init__(self, game_code: str, player_name: str, player_id: str, numbers: list,
                 round_num: int, ws_client: WebSocketClient, **kwargs):
        super().__init__(**kwargs)
        self.game_code = game_code
        self.player_name = player_name
        self.player_id = player_id
        self.current_numbers = numbers
        self.round_num = round_num
        self.ws_client = ws_client
        self.solver = None
        self.time_duration = 30
        
        # Listen for WebSocket messages
        self.ws_client.message_handler = self.handle_websocket_message
    
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
        
        self.ids.floatlayout.add_widget(new_numberpanel)
        self.main_numberpanel = new_numberpanel
        self.time_passed = 0
        self.timelabel.time_remaining = self.time_duration
        self.main_numberpanel.start(self.current_numbers)  # Pass the valid numbers
        self.bind(remaining_nums=self.finishedgame_callback)
        self.bind(time_passed=self.out_of_time)
        self.ops_state = "None"
        if len(self.ops) > 0:
            self.ops.pop()
        self.operationpanel.operation_id = 'None'
        Clock.schedule_interval(self.timer_tick, 1)
    
    def out_of_time(self, instance, value):
        if value == self.time_duration:
            # Show game over screen instead of restarting immediately
            Clock.unschedule(self.timer_tick)
            
            # Get the solution for current numbers
            solution_steps = self.get_best_solution(self.current_numbers)
            solution_text = self.format_solution(solution_steps)
            
            # Notify server of timeout
            if self.ws_client:
                asyncio.create_task(self.ws_client.send_message({
                    "type": "solution_submitted",
                    "solution": solution_text
                }))

    def clear_operations(self):
        self.operationpanel.ids[self.operationpanel.operation_id].remove_operation()
    
    def finishedgame_callback(self, instance, value):
        if value == 1:
            if self.main_numberpanel.ids[self.main_numberpanel.first_operation].int_value == self.targetlabel.target_number:
                Clock.unschedule(self.timer_tick)
                
                # Send solution to server
                if self.ws_client:
                    asyncio.create_task(self.ws_client.send_message({
                        "type": "solution_submitted",
                        "solution": ["Player solved it manually"]
                    }))
                    
    def handle_websocket_message(self, data: dict):
        """Handle WebSocket messages during gameplay"""
        msg_type = data.get("type")
        
        if msg_type == "solution_response":
            if data.get("is_winner"):
                self.update_display("You won this round!")
            Clock.schedule_once(lambda dt: self.return_to_lobby(), 3)
        elif msg_type == "player_answered":
            player_name = data.get("username", "Someone")
            if data.get("is_winner"):
                self.update_display(f"{player_name} won this round!")
                Clock.schedule_once(lambda dt: self.return_to_lobby(), 3)
        elif msg_type == "round_ended":
            Clock.unschedule(self.timer_tick)
            winner = data.get("winner")
            if winner:
                self.update_display(f"{winner} won this round!")
            # Return to lobby after delay
            Clock.schedule_once(lambda dt: self.return_to_lobby(), 3)
        elif msg_type == "game_finished":
            Clock.unschedule(self.timer_tick)
            Clock.schedule_once(lambda dt: self.return_to_lobby(), 5)
        elif msg_type == "game_state":
            self.update_scores(data.get("game", {}))
            
    def update_scores(self, game_data: dict):
        """Update player scores display"""
        players = game_data.get("players", [])
        if players and hasattr(self, 'ids') and 'players_score_label' in self.ids:
            score_text = "Players: " + ", ".join([f"{p['username']}: {p.get('score', 0)}" for p in players])
            self.ids.players_score_label.text = score_text
            
    def update_display(self, message: str):
        """Update the display with a message"""
        if hasattr(self, 'ids') and 'players_score_label' in self.ids:
            self.ids.players_score_label.text = message
            
    def return_to_lobby(self):
        """Return to the lobby"""
        app = App.get_running_app()
        app.root.show_lobby(self.game_code, self.player_name, self.player_id, is_host=False)

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

class MainContainer(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.show_menu()
    
    def show_menu(self):
        self.clear_widgets()
        self.add_widget(MenuScreen())
    
    def show_lobby(self, game_code: str, player_name: str, player_id: str, is_host: bool = False):
        self.clear_widgets()
        self.add_widget(LobbyScreen(game_code, player_name, player_id, is_host))
    
    def show_game(self, game_code: str, player_name: str, player_id: str, numbers: list, 
                 round_num: int, ws_client: WebSocketClient):
        self.clear_widgets()
        game_screen = MultiplayerGameScreen(game_code, player_name, player_id, numbers, round_num, ws_client)
        self.add_widget(game_screen)
        game_screen.start_state()

class Multiplayer24App(App):
    def build(self):
        # Load the multiplayer.kv file explicitly
        from kivy.lang import Builder
        Builder.load_file('src/multiplayer.kv')
        return MainContainer()
        
    def on_stop(self):
        for widget in self.root.walk():
            if hasattr(widget, 'ws_client') and widget.ws_client:
                widget.ws_client.disconnect()

if __name__ == '__main__':
    Multiplayer24App().run() 