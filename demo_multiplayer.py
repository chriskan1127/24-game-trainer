#!/usr/bin/env python3
"""
Demo script for testing the 24-game multiplayer functionality.
This script demonstrates the complete multiplayer flow:
1. Server connection
2. Game creation
3. Player joining
4. WebSocket communication
5. Gameplay simulation
"""

import requests
import asyncio
import websockets
import json
import time
from typing import Dict, Any
import random

# Configuration
SERVER_BASE_URL = "http://localhost:8000"
WS_BASE_URL = "ws://localhost:8000"

class MultiplayerDemo:
    def __init__(self):
        self.game_code = None
        self.host_id = None
        self.player_id = None
        self.host_ws = None
        self.player_ws = None
        
    async def test_server_connection(self):
        """Test if the server is running and responsive"""
        print("🔍 Testing server connection...")
        try:
            response = requests.get(f"{SERVER_BASE_URL}/api/health", timeout=5)
            print(response.json())
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Server is healthy!")
                print(f"   - Active games: {data.get('active_games', 0)}")
                print(f"   - Active players: {data.get('active_players', 0)}")
                print(f"   - WebSocket connections: {data.get('websocket_connections', 0)}")
                return True
            else:
                print(f"❌ Server health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            print("   Make sure the server is running with: python run_system.py server")
            return False
    
    def create_game(self, host_name: str = "Alice_Host"):
        """Create a new game"""
        print(f"\n🎮 Creating game with host: {host_name}")
        try:
            response = requests.post(
                f"{SERVER_BASE_URL}/api/games/create",
                json={
                    "host_username": host_name,
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
                    self.game_code = data["data"]["game_code"]
                    self.host_id = data["data"]["host_id"]
                    print(f"✅ Game created successfully!")
                    print(f"   - Game code: {self.game_code}")
                    print(f"   - Host ID: {self.host_id}")
                    return True
                else:
                    print(f"❌ Failed to create game: {data.get('message')}")
                    return False
            else:
                print(f"❌ Server error: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def join_game(self, player_name: str = "Bob_Player"):
        """Join the created game"""
        print(f"\n👥 Player {player_name} joining game {self.game_code}")
        try:
            response = requests.post(
                f"{SERVER_BASE_URL}/api/games/{self.game_code}/join",
                json={"username": player_name},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self.player_id = data["data"]["player_id"]
                    print(f"✅ Player joined successfully!")
                    print(f"   - Player ID: {self.player_id}")
                    return True
                else:
                    print(f"❌ Failed to join game: {data.get('message')}")
                    return False
            else:
                print(f"❌ Server error: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def get_game_status(self):
        """Get current game status"""
        print(f"\n📊 Getting game status for {self.game_code}")
        try:
            response = requests.get(
                f"{SERVER_BASE_URL}/api/games/{self.game_code}/status",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    game = data["data"]["game"]
                    print(f"✅ Game status retrieved!")
                    print(f"   - Status: {game.get('status')}")
                    print(f"   - Players: {len(game.get('players', []))}")
                    for player in game.get('players', []):
                        host_marker = " (Host)" if player.get('is_host') else ""
                        print(f"     • {player['username']}{host_marker} - Score: {player.get('score', 0)}")
                    return game
                else:
                    print(f"❌ Failed to get status: {data.get('message')}")
                    return None
            else:
                print(f"❌ Server error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return None
    
    async def connect_websockets(self):
        """Connect both host and player via WebSocket"""
        print(f"\n🔌 Connecting WebSockets...")
        
        try:
            # Connect host
            host_uri = f"{WS_BASE_URL}/ws/{self.game_code}/{self.host_id}"
            self.host_ws = await websockets.connect(host_uri)
            print(f"✅ Host WebSocket connected")
            
            # Connect player
            player_uri = f"{WS_BASE_URL}/ws/{self.game_code}/{self.player_id}"
            self.player_ws = await websockets.connect(player_uri)
            print(f"✅ Player WebSocket connected")
            
            # Set player as ready via WebSocket
            ready_message = {
                "type": "ready_status",
                "is_ready": True
            }
            await self.player_ws.send(json.dumps(ready_message))
            print(f"✅ Player marked as ready via WebSocket")
            
            # Small delay to let server process the ready status
            await asyncio.sleep(0.5)
            
            return True
            
        except Exception as e:
            print(f"❌ WebSocket connection failed: {e}")
            return False
    
    async def listen_to_messages(self, websocket, name: str, duration: int = 5):
        """Listen to WebSocket messages for a specified duration"""
        print(f"👂 Listening to {name} messages for {duration}s...")
        
        end_time = time.time() + duration
        while time.time() < end_time:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                data = json.loads(message)
                print(f"📨 {name} received: {data.get('type', 'unknown')} - {data}")
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"❌ {name} message error: {e}")
                break
    
    def start_game(self):
        """Start the game (host only)"""
        print(f"\n🚀 Host starting the game...")
        try:
            response = requests.post(
                f"{SERVER_BASE_URL}/api/games/{self.game_code}/start",
                params={"player_id": self.host_id},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    print(f"✅ Game started successfully!")
                    return True
                else:
                    print(f"❌ Failed to start game: {data.get('message')}")
                    return False
            else:
                print(f"❌ Server error: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    async def simulate_solution_submission(self):
        """Simulate a player submitting a solution"""
        print(f"\n🧮 Simulating solution submission...")
        
        # Host submits a solution
        solution_message = {
            "type": "solution_submitted",
            "solution": [2, 3, 6, '*', 4, 6, 24, '+']
        }
        
        await self.host_ws.send(json.dumps(solution_message))
        print(f"📤 Host submitted solution")
        
        # Listen for responses
        await self.listen_to_messages(self.host_ws, "Host", 3)
        await self.listen_to_messages(self.player_ws, "Player", 3)
    
    async def cleanup(self):
        """Close WebSocket connections"""
        if self.host_ws:
            await self.host_ws.close()
        if self.player_ws:
            await self.player_ws.close()
        print("🧹 Cleaned up WebSocket connections")

async def run_demo():
    """Run the complete multiplayer demo"""
    print("🎯 24-Game Multiplayer Demo")
    print("=" * 50)
    
    demo = MultiplayerDemo()
    
    try:
        # Test server connection
        if not await demo.test_server_connection():
            return
        
        # Create game
        if not demo.create_game("Alice_Host"):
            return
        
        # Join game
        if not demo.join_game("Bob_Player"):
            return
        
        # Get game status
        game_status = demo.get_game_status()
        if not game_status:
            return
        
        # Connect WebSockets
        if not await demo.connect_websockets():
            return
        
        # Listen to initial messages
        await asyncio.gather(
            demo.listen_to_messages(demo.host_ws, "Host", 3),
            demo.listen_to_messages(demo.player_ws, "Player", 3)
        )
        
        # Start game
        if demo.start_game():
            print("\n🎮 Game is now in progress!")
            
            # Listen for game started messages
            await asyncio.gather(
                demo.listen_to_messages(demo.host_ws, "Host", 3),
                demo.listen_to_messages(demo.player_ws, "Player", 3)
            )
            
            # Simulate gameplay
            await demo.simulate_solution_submission()
        
        print("\n🎉 Demo completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
    
    finally:
        await demo.cleanup()

if __name__ == "__main__":
    print("Starting multiplayer demo...")
    print("Make sure the server is running: python run_system.py server")
    print()
    
    asyncio.run(run_demo()) 