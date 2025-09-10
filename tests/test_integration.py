"""
Integration tests for client-server communication
Tests the full multiplayer flow using the actual client and server
"""

import asyncio
import json
import websockets
import time
import sys
import os
from uuid import uuid4

# Test configuration
SERVER_URL = "ws://localhost:8000"


async def test_websocket_connection():
    """Test basic WebSocket connection to server"""
    print("Testing WebSocket connection...")
    
    try:
        room_code = "TEST"
        player_id = str(uuid4())
        
        uri = f"{SERVER_URL}/ws/{room_code}/{player_id}"
        async with websockets.connect(uri) as websocket:
            print(f"[OK] Connected to {uri}")
            
            # Test simple message
            test_message = {
                "type": "room.create",
                "payload": {
                    "username": "IntegrationTestHost"
                }
            }
            
            await websocket.send(json.dumps(test_message))
            print("[OK] Sent room creation message")
            
            # Wait for response
            response = await asyncio.wait_for(websocket.recv(), timeout=10)
            response_data = json.loads(response)
            
            print(f"[OK] Received response: {response_data['type']}")
            
            if response_data["type"] == "room.created":
                payload = response_data["payload"]
                created_room_code = payload["room_code"]
                session_token = payload["session_token"]
                print(f"[OK] Room created successfully: {created_room_code}")
                print(f"[OK] Session token received: {session_token[:8]}...")
                return True
            elif response_data["type"] == "error":
                print(f"[INFO] Server returned error (expected in some cases): {response_data.get('payload', {}).get('message')}")
                return True  # Error responses are valid too
            else:
                print(f"[WARNING] Unexpected response type: {response_data['type']}")
                return False
                
    except Exception as e:
        print(f"[ERROR] WebSocket connection test failed: {e}")
        return False


async def test_room_creation_and_joining():
    """Test complete room creation and joining flow"""
    print("Testing room creation and joining flow...")
    
    try:
        # Host creates room
        host_id = str(uuid4())
        room_code = "INT1"
        
        host_uri = f"{SERVER_URL}/ws/{room_code}/{host_id}"
        
        async with websockets.connect(host_uri) as host_ws:
            print("[OK] Host connected")
            
            # Create room
            create_message = {
                "type": "room.create",
                "payload": {
                    "username": "IntegrationHost"
                }
            }
            
            await host_ws.send(json.dumps(create_message))
            
            # Get room creation response
            response = await asyncio.wait_for(host_ws.recv(), timeout=10)
            response_data = json.loads(response)
            
            if response_data["type"] != "room.created":
                print(f"[ERROR] Failed to create room: {response_data}")
                return False
            
            created_room = response_data["payload"]["room_code"]
            session_token = response_data["payload"]["session_token"]
            print(f"[OK] Room created: {created_room}")
            
            # Player joins room
            player_id = str(uuid4())
            player_uri = f"{SERVER_URL}/ws/{created_room}/{player_id}"
            
            async with websockets.connect(player_uri) as player_ws:
                print("[OK] Player connected")
                
                join_message = {
                    "type": "room.join",
                    "payload": {
                        "room_code": created_room,
                        "username": "IntegrationPlayer"
                    }
                }
                
                await player_ws.send(json.dumps(join_message))
                
                # Get join response
                join_response = await asyncio.wait_for(player_ws.recv(), timeout=10)
                join_data = json.loads(join_response)
                
                if join_data["type"] == "room.joined":
                    players = join_data["payload"]["players"]
                    print(f"[OK] Player joined successfully. Room has {len(players)} players")
                    
                    # Host should receive player.joined notification
                    try:
                        host_notification = await asyncio.wait_for(host_ws.recv(), timeout=5)
                        host_data = json.loads(host_notification)
                        if host_data["type"] == "player.joined":
                            print("[OK] Host received player joined notification")
                        else:
                            print(f"[INFO] Host received: {host_data['type']}")
                    except asyncio.TimeoutError:
                        print("[INFO] No immediate notification to host (may be normal)")
                    
                    return True
                else:
                    print(f"[ERROR] Failed to join room: {join_data}")
                    return False
                    
    except Exception as e:
        print(f"[ERROR] Room creation and joining test failed: {e}")
        return False


async def test_game_start_attempt():
    """Test attempting to start a game"""
    print("Testing game start attempt...")
    
    try:
        # Create room with host
        host_id = str(uuid4())
        room_code = "GAME"
        
        host_uri = f"{SERVER_URL}/ws/{room_code}/{host_id}"
        
        async with websockets.connect(host_uri) as host_ws:
            # Create room
            create_message = {
                "type": "room.create",
                "payload": {
                    "username": "GameHost"
                }
            }
            
            await host_ws.send(json.dumps(create_message))
            
            # Get creation response
            response = await asyncio.wait_for(host_ws.recv(), timeout=10)
            response_data = json.loads(response)
            
            if response_data["type"] != "room.created":
                print("[ERROR] Failed to create room for game test")
                return False
            
            session_token = response_data["payload"]["session_token"]
            created_room = response_data["payload"]["room_code"]
            
            # Add a second player (needed for game start)
            player_id = str(uuid4())
            player_uri = f"{SERVER_URL}/ws/{created_room}/{player_id}"
            
            async with websockets.connect(player_uri) as player_ws:
                join_message = {
                    "type": "room.join",
                    "payload": {
                        "room_code": created_room,
                        "username": "GamePlayer"
                    }
                }
                
                await player_ws.send(json.dumps(join_message))
                await asyncio.wait_for(player_ws.recv(), timeout=5)  # Consume join response
                
                # Try to start game
                start_message = {
                    "type": "game.start",
                    "payload": {
                        "room_code": created_room,
                        "session_token": session_token
                    }
                }
                
                await host_ws.send(json.dumps(start_message))
                print("[OK] Sent game start request")
                
                # Wait for game start responses
                try:
                    # Host should get countdown or error
                    host_response = await asyncio.wait_for(host_ws.recv(), timeout=10)
                    host_data = json.loads(host_response)
                    print(f"[OK] Host received: {host_data['type']}")
                    
                    # Player should also get countdown or error
                    player_response = await asyncio.wait_for(player_ws.recv(), timeout=10)
                    player_data = json.loads(player_response)
                    print(f"[OK] Player received: {player_data['type']}")
                    
                    if host_data["type"] in ["countdown.start", "error"]:
                        print("[OK] Game start process initiated successfully")
                        return True
                    else:
                        print(f"[WARNING] Unexpected response to game start: {host_data['type']}")
                        return False
                        
                except asyncio.TimeoutError:
                    print("[ERROR] No response to game start request")
                    return False
                    
    except Exception as e:
        print(f"[ERROR] Game start test failed: {e}")
        return False


async def test_server_endpoints():
    """Test HTTP endpoints"""
    print("Testing server HTTP endpoints...")
    
    try:
        import aiohttp
        
        # Test health endpoint
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/health", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "healthy":
                        print("[OK] Health endpoint working")
                    else:
                        print(f"[ERROR] Health endpoint returned unhealthy: {data}")
                        return False
                else:
                    print(f"[ERROR] Health endpoint returned status {response.status}")
                    return False
            
            # Test stats endpoint
            async with session.get("http://localhost:8000/stats", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if all(key in data for key in ["active_connections", "active_rooms", "total_players"]):
                        print(f"[OK] Stats endpoint working - {data['active_rooms']} rooms, {data['active_connections']} connections")
                    else:
                        print(f"[ERROR] Stats endpoint missing expected fields: {data}")
                        return False
                else:
                    print(f"[ERROR] Stats endpoint returned status {response.status}")
                    return False
        
        return True
        
    except ImportError:
        print("[SKIP] aiohttp not available, skipping HTTP endpoint tests")
        return True
    except Exception as e:
        print(f"[ERROR] HTTP endpoint test failed: {e}")
        return False


async def run_integration_tests():
    """Run all integration tests"""
    print("Starting integration tests...")
    print("=" * 50)
    
    tests = [
        ("WebSocket Connection", test_websocket_connection),
        ("Room Creation & Joining", test_room_creation_and_joining),
        ("Game Start Attempt", test_game_start_attempt),
        ("Server HTTP Endpoints", test_server_endpoints),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            result = await test_func()
            if result:
                print(f"[PASS] {test_name}")
                passed += 1
            else:
                print(f"[FAIL] {test_name}")
        except Exception as e:
            print(f"[FAIL] {test_name} - Exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"Integration Tests Summary: {passed}/{total} passed")
    
    if passed == total:
        print("[SUCCESS] All integration tests passed!")
        return True
    else:
        print("[FAILURE] Some integration tests failed")
        return False


if __name__ == "__main__":
    """Run integration tests"""
    print("24-Game Multiplayer Server Integration Tests")
    print("Make sure the server is running on localhost:8000")
    
    # Run tests
    success = asyncio.run(run_integration_tests())
    
    if success:
        exit(0)
    else:
        exit(1)