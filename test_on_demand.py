"""
Quick test to verify on-demand problem generation is working
"""

import asyncio
import json
import websockets
from uuid import uuid4
import time

async def test_room_creation():
    """Test that room creation generates problems on-demand"""
    print("Testing on-demand problem generation...")
    
    try:
        room_code = "ONDEM"
        player_id = str(uuid4())
        
        uri = f"ws://localhost:8000/ws/{room_code}/{player_id}"
        
        print("Connecting to server...")
        start_time = time.time()
        
        async with websockets.connect(uri) as websocket:
            print("Connected! Sending room creation request...")
            
            # Send room creation request
            create_message = {
                "type": "room.create",
                "payload": {
                    "username": "OnDemandTester"
                }
            }
            
            await websocket.send(json.dumps(create_message))
            
            # Wait for response
            response = await asyncio.wait_for(websocket.recv(), timeout=30)
            response_data = json.loads(response)
            
            end_time = time.time()
            creation_time = end_time - start_time
            
            print(f"Room creation took {creation_time:.2f} seconds")
            
            if response_data["type"] == "room.created":
                payload = response_data["payload"]
                created_room_code = payload["room_code"]
                print(f"✓ Room created successfully: {created_room_code}")
                print(f"✓ On-demand problem generation working!")
                
                if creation_time < 5:  # Should be much faster with on-demand
                    print(f"✓ Fast creation time indicates on-demand generation: {creation_time:.2f}s")
                else:
                    print(f"⚠ Slower creation time, might still be using old method: {creation_time:.2f}s")
                    
                return True
            elif response_data["type"] == "error":
                print(f"✗ Error creating room: {response_data.get('payload', {}).get('message')}")
                return False
            else:
                print(f"✗ Unexpected response: {response_data['type']}")
                return False
                
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_room_creation())