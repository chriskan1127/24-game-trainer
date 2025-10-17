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
from datetime import datetime, timezone
from uuid import UUID, uuid4

# Add lib directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.abspath(os.path.join(current_dir, '..', 'lib'))
plans_dir = os.path.abspath(os.path.join(current_dir, '..', 'plans'))
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)
if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from solve_24 import Solution # Import the Python Solution class
from pydantic_schemas import (
    RoomCreateMessage, RoomCreatePayload, RoomJoinMessage, RoomJoinPayload,
    GameStartMessage, GameStartPayload, AnswerSubmitMessage, AnswerSubmitPayload,
    OutgoingWSMessage, IncomingWSMessage, MVPRoomSettings
)

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
    """Enhanced WebSocket client compatible with the current server implementation"""

    def __init__(self, room_code: str, player_id: UUID, message_handler):
        self.room_code = room_code
        self.player_id = player_id
        self.message_handler = message_handler
        self.websocket = None
        self.connected = False
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 2.0

    async def connect(self):
        """Connect to the WebSocket server with retry logic"""
        while self.reconnect_attempts < self.max_reconnect_attempts and not self.connected:
            try:
                uri = f"{WS_BASE_URL}/ws/{self.room_code}/{str(self.player_id)}"
                print(f"Attempting to connect to {uri}")

                self.websocket = await websockets.connect(uri)
                self.connected = True
                self.running = True
                self.reconnect_attempts = 0

                print(f"Successfully connected to room {self.room_code}")

                # Listen for messages
                while self.running and self.connected:
                    try:
                        message = await self.websocket.recv()
                        data = json.loads(message)
                        # Schedule message handling on main thread
                        Clock.schedule_once(lambda dt, msg=data: self.message_handler(msg), 0)
                    except websockets.exceptions.ConnectionClosed:
                        print("WebSocket connection closed")
                        self.connected = False
                        break
                    except Exception as e:
                        print(f"WebSocket receive error: {e}")
                        break

            except Exception as e:
                print(f"Failed to connect to WebSocket (attempt {self.reconnect_attempts + 1}): {e}")
                self.reconnect_attempts += 1

                if self.reconnect_attempts < self.max_reconnect_attempts:
                    print(f"Retrying in {self.reconnect_delay} seconds...")
                    await asyncio.sleep(self.reconnect_delay)
                    self.reconnect_delay *= 1.5  # Exponential backoff
                else:
                    # Final failure - notify the UI
                    Clock.schedule_once(lambda dt: self.message_handler({
                        "type": "error",
                        "payload": {
                            "code": "CONNECTION_FAILED",
                            "message": f"Failed to connect after {self.max_reconnect_attempts} attempts: {e}"
                        }
                    }), 0)
                    break

    async def send_message(self, message_obj: IncomingWSMessage):
        """Send a Pydantic message object to the server"""
        if self.websocket and self.connected:
            try:
                json_message = message_obj.model_dump_json()
                await self.websocket.send(json_message)
                print(f"Sent message: {message_obj.type}")
            except Exception as e:
                print(f"Failed to send message: {e}")
                # Try to reconnect on send failure
                self.connected = False

    def disconnect(self):
        """Disconnect from the server"""
        self.running = False
        self.connected = False
        if self.websocket:
            try:
                asyncio.create_task(self.websocket.close())
            except:
                pass

    def start_connection(self):
        """Start the WebSocket connection in a separate thread"""
        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.connect())
            finally:
                loop.close()

        thread = threading.Thread(target=run_async)
        thread.daemon = True
        thread.start()

class MenuScreen(Widget):
    def create_game(self, player_name: str):
        """Create a new room via WebSocket"""
        if not player_name.strip():
            self.show_status("Please enter your name")
            return

        try:
            player_name = player_name.strip()
            if len(player_name) > 32:
                self.show_status("Name must be 32 characters or less")
                return

            # Generate a player ID for the host
            player_id = uuid4()

            # Create WebSocket client and connect
            ws_client = WebSocketClient(
                room_code="TEMP",  # Will be updated after room creation
                player_id=player_id,
                message_handler=self.handle_create_response
            )

            # Store for later use
            self.ws_client = ws_client
            self.player_name = player_name
            self.player_id = player_id

            # Start connection and then send create message
            ws_client.start_connection()

            # Give connection time to establish, then send create message
            Clock.schedule_once(lambda dt: self.send_create_message(), 1.0)

        except Exception as e:
            self.show_status(f"Error creating game: {e}")

    def send_create_message(self):
        """Send room creation message after connection is established"""
        if hasattr(self, 'ws_client') and self.ws_client.connected:
            create_message = RoomCreateMessage(
                type="room.create",
                payload=RoomCreatePayload(
                    username=self.player_name,
                    settings=MVPRoomSettings()
                )
            )

            # Use asyncio to send the message
            def send_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.ws_client.send_message(create_message))
                finally:
                    loop.close()

            threading.Thread(target=send_async, daemon=True).start()
        else:
            # Retry if not connected yet
            Clock.schedule_once(lambda dt: self.send_create_message(), 0.5)

    def handle_create_response(self, data: dict):
        """Handle response to room creation"""
        msg_type = data.get("type")
        payload = data.get("payload", {})

        if msg_type == "room.created":
            room_code = payload.get("room_code")
            host_player_id = payload.get("host_player_id")
            session_token = payload.get("session_token")

            # Create initial players list with host
            host_player_data = {
                "player_id": host_player_id,
                "username": self.player_name,
                "score": 0,
                "streak": 0
            }
            initial_players = [host_player_data]

            # Pass the existing WebSocket client to lobby (don't disconnect)
            existing_ws_client = None
            if hasattr(self, 'ws_client'):
                existing_ws_client = self.ws_client
                # Don't disconnect - we'll reuse this connection

            # Navigate to lobby with the new room
            app = App.get_running_app()
            app.root.show_lobby(
                room_code,
                self.player_name,
                UUID(host_player_id),
                session_token,
                is_host=True,
                initial_players=initial_players,
                existing_ws_client=existing_ws_client
            )
        elif msg_type == "error":
            error_msg = payload.get("message", "Failed to create room")
            self.show_status(error_msg)
            if hasattr(self, 'ws_client'):
                self.ws_client.disconnect()

    def join_game(self, game_code: str, player_name: str):
        """Join an existing room via WebSocket"""
        if not game_code.strip() or not player_name.strip():
            self.show_status("Please enter both game code and name")
            return

        try:
            game_code = game_code.strip().upper()
            player_name = player_name.strip()

            if len(player_name) > 32:
                self.show_status("Name must be 32 characters or less")
                return

            if len(game_code) != 4:
                self.show_status("Game code must be 4 characters")
                return

            # Generate player ID
            player_id = uuid4()

            # Create WebSocket client
            ws_client = WebSocketClient(
                room_code=game_code,
                player_id=player_id,
                message_handler=self.handle_join_response
            )

            # Store for later use
            self.ws_client = ws_client
            self.join_game_code = game_code
            self.join_player_name = player_name
            self.join_player_id = player_id

            # Start connection and then send join message
            ws_client.start_connection()
            Clock.schedule_once(lambda dt: self.send_join_message(), 1.0)

        except Exception as e:
            self.show_status(f"Connection error: {e}")

    def send_join_message(self):
        """Send room join message after connection is established"""
        if hasattr(self, 'ws_client') and self.ws_client.connected:
            join_message = RoomJoinMessage(
                type="room.join",
                payload=RoomJoinPayload(
                    room_code=self.join_game_code,
                    username=self.join_player_name,
                    session_token=None  # No existing session
                )
            )

            # Use asyncio to send the message
            def send_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.ws_client.send_message(join_message))
                finally:
                    loop.close()

            threading.Thread(target=send_async, daemon=True).start()
        else:
            # Retry if not connected yet
            Clock.schedule_once(lambda dt: self.send_join_message(), 0.5)

    def handle_join_response(self, data: dict):
        """Handle response to room join"""
        msg_type = data.get("type")
        payload = data.get("payload", {})

        if msg_type == "room.joined":
            room_code = payload.get("room_code")
            player_id = payload.get("player_id")
            session_token = payload.get("session_token")
            players_list = payload.get("players", [])

            # Convert players to the format we need
            initial_players = []
            for player in players_list:
                initial_players.append({
                    "player_id": player.get("player_id"),
                    "username": player.get("username"),
                    "score": player.get("score", 0),
                    "streak": player.get("streak", 0)
                })

            # Pass the existing WebSocket client to lobby (don't disconnect)
            existing_ws_client = None
            if hasattr(self, 'ws_client'):
                existing_ws_client = self.ws_client
                # Don't disconnect - we'll reuse this connection

            # Navigate to lobby
            app = App.get_running_app()
            app.root.show_lobby(
                room_code,
                self.join_player_name,
                UUID(player_id),
                session_token,
                is_host=False,
                initial_players=initial_players,
                existing_ws_client=existing_ws_client
            )
        elif msg_type == "error":
            error_msg = payload.get("message", "Failed to join room")
            self.show_status(error_msg)
            if hasattr(self, 'ws_client'):
                self.ws_client.disconnect()

    def show_status(self, message: str):
        """Show a status message to the user"""
        if hasattr(self, 'ids') and 'status_label' in self.ids:
            self.ids.status_label.text = message
        print(f"Menu Status: {message}")

class LobbyScreen(Widget):
    game_code = StringProperty('')

    def __init__(self, room_code: str, player_name: str, player_id: UUID,
                 session_token: str, is_host: bool = False, initial_players: list = None,
                 existing_ws_client=None, **kwargs):
        super().__init__(**kwargs)
        self.room_code = room_code
        self.game_code = room_code  # For compatibility with KV file
        self.player_name = player_name
        self.player_id = player_id
        self.session_token = session_token
        self.is_host = is_host
        self.players = initial_players if initial_players else []
        self.room_state = "LOBBY"

        # Countdown state for game start
        self.countdown_active = False
        self.countdown_seconds = 0

        # Use existing WebSocket client or create new one
        if existing_ws_client and existing_ws_client.connected:
            self.ws_client = existing_ws_client
            # Update the message handler to point to this lobby screen
            self.ws_client.message_handler = self.handle_websocket_message
            # Update display immediately since we're already connected
            Clock.schedule_once(lambda dt: self.update_players_display(), 0.1)
        else:
            self.ws_client = None
            # Connect to WebSocket
            Clock.schedule_once(self.connect_websocket, 0.1)
            # Update display with initial players
            Clock.schedule_once(lambda dt: self.update_players_display(), 0.2)

    def connect_websocket(self, dt):
        """Connect to the WebSocket server (only if no existing connection)"""
        if not self.ws_client:
            self.ws_client = WebSocketClient(
                self.room_code,
                self.player_id,
                self.handle_websocket_message
            )
            self.ws_client.start_connection()

            # Schedule a check to see if connection is established
            Clock.schedule_once(lambda dt: self.check_connection_status(), 2.0)

    def check_connection_status(self):
        """Check if WebSocket connection is established"""
        if self.ws_client and self.ws_client.connected:
            self.show_status("Connected - ready for multiplayer")
        else:
            self.show_status("Connection issue - may miss updates")
            # Try to reconnect
            if self.ws_client:
                self.ws_client.start_connection()

    def handle_websocket_message(self, data: dict):
        """Handle incoming WebSocket messages"""
        msg_type = data.get("type")
        payload = data.get("payload", {})

        if msg_type == "player.joined":
            self.handle_player_joined(payload)
        elif msg_type == "player.left":
            self.handle_player_left(payload)
        elif msg_type == "countdown.start":
            self.handle_countdown_start(payload)
        elif msg_type == "round.start":
            self.handle_round_start(payload)
        elif msg_type == "error":
            error_msg = payload.get("message", "Unknown error")
            self.show_status(error_msg)
        else:
            print(f"Lobby received unknown message type: {msg_type}")

    def handle_player_joined(self, payload: dict):
        """Handle a new player joining the room"""
        player = payload.get("player", {})
        total_players = payload.get("total_players", 0)


        # Add player to our list if not already present
        player_id = player.get("player_id")
        existing_player = next((p for p in self.players if str(p.get("player_id")) == str(player_id)), None)
        if not existing_player:
            # Convert the player data to our expected format
            player_data = {
                "player_id": player_id,
                "username": player.get("username"),
                "score": player.get("score", 0),
                "streak": player.get("streak", 0)
            }
            self.players.append(player_data)
            self.update_players_display()
            self.show_status(f"{player.get('username')} joined ({total_players} players)")
        else:
            # Player already in list, just update display
            self.update_players_display()


    def handle_player_left(self, payload: dict):
        """Handle a player leaving the room"""
        player_id = payload.get("player_id")
        username = payload.get("username")
        total_players = payload.get("total_players", 0)

        # Remove player from our list
        self.players = [p for p in self.players if p.get("player_id") != player_id]

        self.update_players_display()
        self.show_status(f"{username} left ({total_players} players)")

    def handle_countdown_start(self, payload: dict):
        """Handle countdown start for game beginning - live countdown"""
        round_index = payload.get("round_index", 0)
        countdown_seconds = payload.get("countdown_seconds", 3)

        # Start live countdown
        self.start_game_countdown(countdown_seconds)

    def start_game_countdown(self, seconds: int):
        """Start live countdown for game beginning"""
        from kivy.clock import Clock

        self.countdown_active = True
        self.countdown_seconds = seconds
        self.update_countdown_display()

        # Schedule countdown updates every second
        Clock.schedule_interval(self.countdown_tick, 1)

    def countdown_tick(self, dt):
        """Update countdown every second"""
        from kivy.clock import Clock

        if not self.countdown_active:
            return False  # Stop the clock

        self.countdown_seconds -= 1
        self.update_countdown_display()

        if self.countdown_seconds <= 0:
            self.countdown_active = False
            self.show_status("Starting game...")
            return False  # Stop the clock

        return True  # Continue the clock

    def update_countdown_display(self):
        """Update the countdown status display"""
        if self.countdown_active and self.countdown_seconds > 0:
            self.show_status(f"Game starting in {self.countdown_seconds}...")

    def stop_game_countdown(self):
        """Stop the game countdown timer"""
        from kivy.clock import Clock

        self.countdown_active = False
        Clock.unschedule(self.countdown_tick)

    def handle_round_start(self, payload: dict):
        """Handle round start - transition to game screen"""
        round_index = payload.get("round_index", 0)
        numbers = payload.get("numbers", [1, 2, 3, 4])
        time_limit = payload.get("time_limit_seconds", 30)

        # Stop any active countdown
        self.stop_game_countdown()

        # Transition to game screen
        app = App.get_running_app()
        app.root.show_game(
            self.room_code, self.player_name, self.player_id,
            self.session_token, numbers, round_index + 1, self.ws_client
        )

    def update_players_display(self):
        """Update the players list display"""

        if hasattr(self, 'ids') and 'players_list' in self.ids:
            self.ids.players_list.clear_widgets()
            for player in self.players:
                from kivy.uix.label import Label
                # Check if this player is the host (first player in list when host creates room)
                # For simplicity, we'll mark the current user as host if they are the host
                is_host_player = str(player.get("player_id")) == str(self.player_id) and self.is_host
                status_text = " (Host)" if is_host_player else ""

                # If this player is ourselves, mark it
                if str(player.get("player_id")) == str(self.player_id):
                    status_text += " (You)"

                player_label = Label(
                    text=f"{player.get('username', 'Unknown')}{status_text} - Score: {player.get('score', 0)}",
                    size_hint_y=None,
                    height=40,
                    color=(0.2, 0.2, 0.3, 1),
                    font_size=16
                )
                self.ids.players_list.add_widget(player_label)

        # Update start button
        if hasattr(self, 'ids') and 'start_button' in self.ids:
            can_start = (self.is_host and len(self.players) >= 2 and self.room_state == "LOBBY")
            self.ids.start_button.disabled = not can_start
            if not self.is_host:
                self.ids.start_button.text = "Waiting for host..."
                self.ids.start_button.disabled = True
            else:
                self.ids.start_button.text = "Start Game" if can_start else "Need 2+ players"


    def start_game(self):
        """Start the game (host only)"""
        if self.is_host and self.ws_client and self.ws_client.connected:
            start_message = GameStartMessage(
                type="game.start",
                payload=GameStartPayload(
                    room_code=self.room_code,
                    session_token=self.session_token
                )
            )

            # Send the start message
            def send_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.ws_client.send_message(start_message))
                finally:
                    loop.close()

            threading.Thread(target=send_async, daemon=True).start()
            self.show_status("Starting game...")
        else:
            self.show_status("Cannot start game - not connected or not host")

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
        print(f"Lobby Status: {message}")

#Note about the code: For Numberpanel and OperationPanel, the floatlayout is within the widget. 
#Thus, use self.parent.parent to access outermost layer

class RoundResultsScreen(Widget):
    """Dedicated screen to show round results, solution, and leaderboard"""

    def __init__(self, round_index: int, canonical_solution: str, players_correct: list,
                 leaderboard: list, current_player_id: UUID, points_earned: int = 0,
                 current_score: int = 0, **kwargs):
        super().__init__(**kwargs)
        self.round_index = round_index
        self.canonical_solution = canonical_solution
        self.players_correct = players_correct
        self.leaderboard = leaderboard
        self.current_player_id = current_player_id
        self.points_earned = points_earned
        self.current_score = current_score

        # Countdown state
        self.countdown_active = False
        self.countdown_seconds = 0
        self.countdown_label = None

        # Create the UI dynamically
        self.create_results_ui()

    def create_results_ui(self):
        """Create the results screen UI - clean, centered, and aesthetic"""
        from kivy.uix.label import Label
        from kivy.uix.boxlayout import BoxLayout

        # The canvas and layout structure is now defined in multiplayer.kv
        # We just need to populate the content_container with widgets

        # Get the content container from the .kv file
        if not hasattr(self, 'ids') or 'content_container' not in self.ids:
            # Fallback: if .kv didn't load properly, create minimal structure
            print("Warning: .kv file structure not found, using fallback")
            content_container = BoxLayout(orientation='vertical', spacing=15)
            self.add_widget(content_container)
        else:
            content_container = self.ids.content_container

        # Round title - large and prominent
        round_title = Label(
            text=f"Round {self.round_index + 1} Results",
            font_size='32sp',
            size_hint_y=None,
            height='60dp',
            color=(1, 1, 1, 1),
            bold=True
        )
        content_container.add_widget(round_title)

        # Personal results section
        personal_section = BoxLayout(orientation='vertical', size_hint_y=None, height='80dp', spacing=10)

        # Check if current player got it correct
        player_correct = any(str(p.get('player_id')) == str(self.current_player_id) for p in self.players_correct)

        if player_correct:
            result_text = f"You got it correct! +{self.points_earned} points"
            result_color = (0.2, 0.8, 0.2, 1)  # Green
        else:
            result_text = "You didn't solve this round"
            result_color = (0.9, 0.6, 0.2, 1)  # Orange

        result_label = Label(
            text=result_text,
            font_size='20sp',
            color=result_color,
            size_hint_y=None,
            height='40dp',
            bold=True
        )
        personal_section.add_widget(result_label)

        # Current score
        score_label = Label(
            text=f"Your Score: {self.current_score}",
            font_size='18sp',
            color=(0.9, 0.9, 1, 1),
            size_hint_y=None,
            height='30dp'
        )
        personal_section.add_widget(score_label)

        content_container.add_widget(personal_section)

        # Solution section
        solution_label = Label(
            text=f"Solution: {self.canonical_solution}",
            font_size='18sp',
            color=(0.7, 0.9, 1, 1),  # Light blue
            size_hint_y=None,
            height='50dp',
            text_size=(520, None),
            halign='center'
        )
        content_container.add_widget(solution_label)

        # Leaderboard section
        leaderboard_title = Label(
            text="Leaderboard",
            font_size='22sp',
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height='40dp',
            bold=True
        )
        content_container.add_widget(leaderboard_title)

        # Leaderboard entries
        leaderboard_section = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)

        # Calculate dynamic height based on number of players
        max_players_to_show = min(5, len(self.leaderboard))
        leaderboard_section.height = max_players_to_show * 30

        for i in range(max_players_to_show):
            if i < len(self.leaderboard):
                entry = self.leaderboard[i]
                player_id_str = str(entry.get('player_id'))
                username = entry.get('username', f"Player {player_id_str[:8]}")
                score = entry.get('score', 0)

                # Highlight current player
                if player_id_str == str(self.current_player_id):
                    username += " (You)"
                    color = (1, 0.8, 0.2, 1)  # Gold/Yellow
                    font_size = '16sp'
                    bold = True
                else:
                    color = (0.9, 0.9, 0.9, 1)  # Light gray
                    font_size = '16sp'
                    bold = False

                leaderboard_entry = Label(
                    text=f"{i + 1}. {username}: {score} pts",
                    font_size=font_size,
                    color=color,
                    size_hint_y=None,
                    height='25dp',
                    bold=bold
                )
                leaderboard_section.add_widget(leaderboard_entry)

        content_container.add_widget(leaderboard_section)

        # Next round info / countdown
        self.countdown_label = Label(
            text="Next round starting soon...",
            font_size='18sp',
            color=(0.8, 0.9, 1, 1),
            size_hint_y=None,
            height='40dp',
            bold=True
        )
        content_container.add_widget(self.countdown_label)

    def start_countdown(self, seconds: int):
        """Start countdown timer on the results screen"""
        from kivy.clock import Clock

        self.countdown_active = True
        self.countdown_seconds = seconds
        self.update_countdown_display()

        # Schedule countdown updates every second
        Clock.schedule_interval(self.countdown_tick, 1)

    def countdown_tick(self, dt):
        """Update countdown every second"""
        from kivy.clock import Clock

        if not self.countdown_active:
            return False  # Stop the clock

        self.countdown_seconds -= 1
        self.update_countdown_display()

        if self.countdown_seconds <= 0:
            self.countdown_active = False
            return False  # Stop the clock

        return True  # Continue the clock

    def update_countdown_display(self):
        """Update the countdown label text"""
        if self.countdown_label and self.countdown_active:
            if self.countdown_seconds > 0:
                self.countdown_label.text = f"Next round in {self.countdown_seconds}..."
            else:
                self.countdown_label.text = "Starting next round..."

    def stop_countdown(self):
        """Stop the countdown timer"""
        from kivy.clock import Clock

        self.countdown_active = False
        Clock.unschedule(self.countdown_tick)


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
    current_score = NumericProperty(0)

    def __init__(self, room_code: str, player_name: str, player_id: UUID,
                 session_token: str, numbers: list, round_num: int,
                 ws_client: WebSocketClient, **kwargs):
        super().__init__(**kwargs)
        self.room_code = room_code
        self.game_code = room_code  # For compatibility
        self.player_name = player_name
        self.player_id = player_id
        self.session_token = session_token
        self.current_numbers = numbers
        self.round_num = round_num
        self.round_index = round_num - 1  # Convert to 0-based
        self.ws_client = ws_client
        self.solver = None
        self.time_duration = 30
        self.has_submitted = False
        self.round_start_time = None
        self.round_end_time = None
        # current_score is now a NumericProperty, initialized to 0 by default

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
        """Get the best solution: first one without fractions AND without negative numbers, or last one if none"""
        solver = Solution([int(n) for n in numbers], target=24)
        solver.find_all_solutions()
        solutions = solver.get_all_solutions()

        if not solutions:
            return []

        # Look for first solution without negative numbers AND without fractions
        for solution in solutions:
            has_negative = False
            has_fraction = False

            for i in range(2, len(solution), 4):  # Check results (every 4th element starting from index 2)
                try:
                    result = float(solution[i])
                    if result < 0:
                        has_negative = True
                        break
                    # Check if result is a fraction (not a whole number)
                    if result != int(result):
                        has_fraction = True
                        break
                except (ValueError, IndexError):
                    continue

            # If solution has neither negative numbers nor fractions, use it
            if not has_negative and not has_fraction:
                return solution

        # If no solution without both negative numbers and fractions, return the last one
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
        # Re-enable undo button at the start of each round
        if hasattr(self.operationpanel, 'undo'):
            self.operationpanel.undo.disabled = False
        Clock.schedule_interval(self.timer_tick, 1)
    
    def out_of_time(self, instance, value):
        # In multiplayer mode, the server handles round timeouts
        # The server will send a round.end message when time is up
        # So we don't need to do anything here - just let the timer continue
        pass

    def clear_operations(self):
        self.operationpanel.ids[self.operationpanel.operation_id].remove_operation()
    
    def finishedgame_callback(self, instance, value):
        if value == 1 and not self.has_submitted:
            if self.main_numberpanel.ids[self.main_numberpanel.first_operation].int_value == self.targetlabel.target_number:
                # Keep timer running so player can see remaining time
                # Timer will be stopped when round officially ends

                # Create the expression from the current state
                expression = self.build_expression_from_state()

                # Submit the answer
                self.submit_answer(expression, True)
                    
    def handle_websocket_message(self, data: dict):
        """Handle WebSocket messages during gameplay"""
        msg_type = data.get("type")
        payload = data.get("payload", {})

        if msg_type == "answer.ack":
            self.handle_answer_ack(payload)
        elif msg_type == "round.end":
            self.handle_round_end(payload)
        elif msg_type == "game.end":
            self.handle_game_end(payload)
        elif msg_type == "countdown.start":
            self.handle_countdown_start(payload)
        elif msg_type == "round.start":
            self.handle_new_round_start(payload)
        elif msg_type == "error":
            error_msg = payload.get("message", "Unknown error")
            self.update_display(f"Error: {error_msg}")
        else:
            print(f"Game received unknown message type: {msg_type}")

    def handle_answer_ack(self, payload: dict):
        """Handle acknowledgment of submitted answer"""
        accepted = payload.get("accepted", False)
        reason = payload.get("reason")
        time_left = payload.get("time_left_seconds")

        if accepted:
            self.update_display(f"Answer accepted! Time left: {time_left:.1f}s")
            self.has_submitted = True
            # Disable undo button after successful submission
            if hasattr(self, 'operationpanel') and self.operationpanel and hasattr(self.operationpanel, 'undo'):
                self.operationpanel.undo.disabled = True
        else:
            self.update_display(f"Answer rejected: {reason}")

    def handle_round_end(self, payload: dict):
        """Handle round end with results - show dedicated results screen"""
        Clock.unschedule(self.timer_tick)

        round_index = payload.get("round_index", 0)
        canonical_solution = payload.get("canonical_solution", "No solution")
        players_correct = payload.get("players_correct", [])
        updated_scores = payload.get("updated_scores", [])
        leaderboard = payload.get("leaderboard", [])

        # Calculate points earned by current player this round
        points_earned = 0
        current_player_correct = None
        for player in players_correct:
            if str(player.get("player_id")) == str(self.player_id):
                points_earned = player.get("points_gained", 0)
                current_player_correct = player
                break

        # Get current player's total score from leaderboard
        current_score = 0
        for entry in leaderboard:
            if str(entry.get("player_id")) == str(self.player_id):
                current_score = entry.get("score", 0)
                break

        # Store the current score for use in get_current_score
        self.current_score = current_score

        # Remove the current game UI (numbers panel, etc.)
        self.clear_game_ui()

        # Create and show the results screen
        results_screen = RoundResultsScreen(
            round_index=round_index,
            canonical_solution=canonical_solution,
            players_correct=players_correct,
            leaderboard=leaderboard,
            current_player_id=self.player_id,
            points_earned=points_earned,
            current_score=current_score
        )

        # Add the results screen to the main layout (full screen)
        results_screen.size = self.ids.floatlayout.size  # Match parent size
        results_screen.pos = self.ids.floatlayout.pos  # Match parent position
        results_screen.size_hint = (1, 1)  # Fill entire screen
        self.ids.floatlayout.add_widget(results_screen)

        # Store reference for cleanup later
        self.current_results_screen = results_screen

        # Wait for next round or game end (server will send next message)

    def clear_game_ui(self):
        """Clear ALL game UI components to show clean results screen"""
        # Remove numbers panel (widget removal prevents any interaction)
        if hasattr(self, 'main_numberpanel') and self.main_numberpanel:
            if self.main_numberpanel in self.ids.floatlayout.children:
                self.ids.floatlayout.remove_widget(self.main_numberpanel)
            self.main_numberpanel = None

        # Hide timer, score, target, and operation panel elements
        if hasattr(self, 'timelabel') and self.timelabel:
            self.timelabel.opacity = 0
        if hasattr(self, 'scorelabel') and self.scorelabel:
            self.scorelabel.opacity = 0
        if hasattr(self, 'targetlabel') and self.targetlabel:
            self.targetlabel.opacity = 0
        if hasattr(self, 'operationpanel') and self.operationpanel:
            self.operationpanel.opacity = 0

        # Clear any existing results screen
        if hasattr(self, 'current_results_screen') and self.current_results_screen:
            # Stop any active countdown
            self.current_results_screen.stop_countdown()
            # Remove the results screen
            if self.current_results_screen in self.ids.floatlayout.children:
                self.ids.floatlayout.remove_widget(self.current_results_screen)
            self.current_results_screen = None

    def restore_game_ui(self):
        """Restore game UI elements for next round"""
        # Show timer, score, target, and operation panel elements
        if hasattr(self, 'timelabel') and self.timelabel:
            self.timelabel.opacity = 1
        if hasattr(self, 'scorelabel') and self.scorelabel:
            self.scorelabel.opacity = 1
        if hasattr(self, 'targetlabel') and self.targetlabel:
            self.targetlabel.opacity = 1
        if hasattr(self, 'operationpanel') and self.operationpanel:
            self.operationpanel.opacity = 1

    def handle_game_end(self, payload: dict):
        """Handle game end with final results"""
        Clock.unschedule(self.timer_tick)

        leaderboard = payload.get("leaderboard", [])

        if leaderboard:
            winner = leaderboard[0]
            if str(winner.get("player_id")) == str(self.player_id):
                self.update_display("🏆 YOU WON THE GAME! 🏆")
            else:
                self.update_display(f"🏆 {winner.get('username')} won the game! 🏆")
        else:
            self.update_display("Game ended")

        # Return to lobby after delay
        Clock.schedule_once(lambda dt: self.return_to_lobby(), 5)

    def handle_countdown_start(self, payload: dict):
        """Handle countdown before next round"""
        countdown_seconds = payload.get("countdown_seconds", 3)

        # If we have an active results screen, start countdown on it
        if hasattr(self, 'current_results_screen') and self.current_results_screen:
            self.current_results_screen.start_countdown(countdown_seconds)
        else:
            # Fallback: clear UI and show countdown message
            self.clear_game_ui()
            self.update_display(f"Next round in {countdown_seconds} seconds...")

    def handle_new_round_start(self, payload: dict):
        """Handle start of a new round"""
        # Clear results screen and prepare for new round
        round_index = payload.get("round_index", 0)
        numbers = payload.get("numbers", [1, 2, 3, 4])
        round_end_time = payload.get("round_end")

        self.round_index = round_index
        self.round_num = round_index + 1
        self.current_numbers = numbers
        self.has_submitted = False

        # Clear any existing UI (results screen, old game panels)
        self.clear_game_ui()

        # Clear any persistent messages (like "Answer accepted!")
        self.update_display(f"Round {self.round_num} - Score: {self.get_current_score()}")

        # Restore game UI elements
        self.restore_game_ui()

        # Start the new round
        self.start_state()
            
    def update_scores_from_list(self, updated_scores: list):
        """Update player scores display from score update list"""
        if updated_scores:
            # Find our own score and update the current_score property
            our_score = next(
                (s.get('score', 0) for s in updated_scores if str(s.get('player_id')) == str(self.player_id)),
                0
            )
            self.current_score = our_score

    def update_display(self, message: str):
        """Display a message (now using console output)"""
        # Messages are now shown in console or via other mechanisms
        print(f"Game Display: {message}")

    def get_current_score(self):
        """Get the current player's score"""
        return self.current_score
            
    def submit_answer(self, expression: str, is_valid: bool):
        """Submit an answer to the server"""
        if self.has_submitted:
            return

        if not self.ws_client or not self.ws_client.connected:
            self.update_display("Not connected to server")
            return

        # Create submission message
        answer_message = AnswerSubmitMessage(
            type="answer.submit",
            payload=AnswerSubmitPayload(
                room_code=self.room_code,
                player_id=self.player_id,
                session_token=self.session_token,
                round_index=self.round_index,
                expression=expression,
                used_numbers=self.current_numbers,
                client_eval_value=24 if is_valid else None,
                client_eval_is_valid=is_valid,
                client_timestamp=datetime.now(timezone.utc)
            )
        )

        # Send the message
        def send_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.ws_client.send_message(answer_message))
            finally:
                loop.close()

        threading.Thread(target=send_async, daemon=True).start()
        self.update_display("Submitting answer...")

    def build_expression_from_state(self) -> str:
        """Build expression string from current game state"""
        # This is a simplified version - in a full implementation,
        # you'd track the operations history to build the actual expression
        return f"Solution using {self.current_numbers}"

    def return_to_lobby(self):
        """Return to the lobby"""
        app = App.get_running_app()
        # Note: We need to recreate the lobby with proper parameters
        # For simplicity, going back to menu
        if self.ws_client:
            self.ws_client.disconnect()
        app.root.show_menu()

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
        # Safety check: ensure widget hierarchy is intact
        try:
            if not self.parent or not self.parent.parent or not self.parent.parent.parent or not self.parent.parent.parent.parent:
                return  # Widget is being removed, ignore the event

            if self.activated:
                self.remove_operation()
            else:
                if len(self.parent.parent.parent.parent.ops) < 1:
                    self.background_color = self.normal_color
                else:
                    if self.parent.parent.operation_id != 'None':
                        self.parent.parent.ids[self.parent.parent.operation_id].remove_operation()
                    self.add_operation()
        except (AttributeError, ReferenceError):
            # Widget hierarchy broken during round transition, safely ignore
            return

class UndoBlock(Button, Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.normal_color = COLORS['warning']
        self.background_color = self.normal_color
    
    def on_press(self):
        # Skip intermediate color, go directly to action
        pass
    
    def on_release(self):
        # Safety check: ensure widget hierarchy is intact
        try:
            if not self.parent or not self.parent.parent or not self.parent.parent.parent or not self.parent.parent.parent.parent:
                return  # Widget is being removed, ignore the event

            # Check if main_numberpanel exists
            game_screen = self.parent.parent.parent.parent
            if not hasattr(game_screen, 'main_numberpanel') or not game_screen.main_numberpanel:
                return  # Game is ending, ignore the event

            # Perform action without color change
            if len(game_screen.main_numberpanel.operation_list) > 0:
                prev_state = game_screen.main_numberpanel.operation_list.pop()
                game_screen.main_numberpanel.assign_numblock_vals(prev_state)
                game_screen.remaining_nums += 1
                if game_screen.main_numberpanel.first_operation != "None":
                    game_screen.main_numberpanel.remove_first_op()
        except (AttributeError, ReferenceError):
            # Widget hierarchy broken during round transition, safely ignore
            return


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
        if operation == '+':
            output = int1 + int2
        elif operation == '-':
            output = int1 - int2
        elif operation == 'x':
            output = int1 * int2
        elif operation == '/':
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
        # Safety check: ensure widget hierarchy is intact
        try:
            if not self.disabled:
                # Check parent chain exists
                if not self.parent or not self.parent.parent or not self.parent.parent.parent or not self.parent.parent.parent.parent:
                    return  # Widget is being removed, ignore the event

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
        except (AttributeError, ReferenceError):
            # Widget hierarchy broken during round transition, safely ignore
            return

class MainContainer(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.show_menu()

    def show_menu(self):
        self.clear_widgets()
        self.add_widget(MenuScreen())

    def show_lobby(self, room_code: str, player_name: str, player_id: UUID,
                   session_token: str, is_host: bool = False, initial_players: list = None,
                   existing_ws_client=None):
        self.clear_widgets()
        self.add_widget(LobbyScreen(room_code, player_name, player_id, session_token, is_host, initial_players, existing_ws_client))

    def show_game(self, room_code: str, player_name: str, player_id: UUID,
                  session_token: str, numbers: list, round_num: int, ws_client: WebSocketClient):
        self.clear_widgets()
        game_screen = MultiplayerGameScreen(
            room_code, player_name, player_id, session_token, numbers, round_num, ws_client
        )
        self.add_widget(game_screen)
        game_screen.start_state()

class Multiplayer24App(App):
    def build(self):
        # Load the multiplayer.kv file explicitly
        from kivy.lang import Builder
        Builder.load_file('multiplayer.kv')
        return MainContainer()
        
    def on_stop(self):
        for widget in self.root.walk():
            if hasattr(widget, 'ws_client') and widget.ws_client:
                widget.ws_client.disconnect()

if __name__ == '__main__':
    Multiplayer24App().run() 