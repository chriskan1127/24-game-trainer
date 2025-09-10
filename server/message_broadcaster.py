"""
Message Broadcaster Service
Handles broadcasting messages to players in rooms
"""

import asyncio
import json
import logging
from typing import Dict, Optional, Set
from uuid import UUID

import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from pydantic_schemas import OutgoingWSMessage

logger = logging.getLogger(__name__)


class MessageBroadcaster:
    """Handles broadcasting messages to WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Optional[Dict[str, any]] = None  # connection_id -> websocket
        self.player_connections: Optional[Dict[UUID, str]] = None  # player_id -> connection_id
        
    def set_connection_manager(self, active_connections: Dict[str, any], 
                             player_connections: Dict[UUID, str]):
        """Set references to the connection management dictionaries"""
        self.active_connections = active_connections
        self.player_connections = player_connections
    
    async def broadcast_to_room(self, room_code: str, message: OutgoingWSMessage, room_manager):
        """Broadcast a message to all players in a room"""
        if not self.active_connections or not self.player_connections:
            logger.error("Connection manager not initialized")
            return
        
        room = room_manager.get_room(room_code)
        if not room:
            logger.warning(f"Attempted to broadcast to non-existent room {room_code}")
            return
        
        message_json = message.json()
        successful_sends = 0
        failed_sends = 0
        
        # Send to all players in the room
        for player_id in room.players.keys():
            try:
                connection_id = self.player_connections.get(player_id)
                if connection_id and connection_id in self.active_connections:
                    websocket = self.active_connections[connection_id]
                    await websocket.send_text(message_json)
                    successful_sends += 1
                else:
                    # Player is not currently connected
                    logger.debug(f"Player {player_id} not connected during broadcast to room {room_code}")
            except Exception as e:
                logger.warning(f"Failed to send message to player {player_id} in room {room_code}: {e}")
                failed_sends += 1
        
        logger.info(f"Broadcast to room {room_code}: {successful_sends} successful, {failed_sends} failed")
    
    async def broadcast_to_room_except(self, room_code: str, message: OutgoingWSMessage, 
                                     room_manager, exclude_player_id: UUID):
        """Broadcast a message to all players in a room except one"""
        if not self.active_connections or not self.player_connections:
            logger.error("Connection manager not initialized")
            return
        
        room = room_manager.get_room(room_code)
        if not room:
            logger.warning(f"Attempted to broadcast to non-existent room {room_code}")
            return
        
        message_json = message.json()
        successful_sends = 0
        failed_sends = 0
        
        # Send to all players in the room except the excluded one
        for player_id in room.players.keys():
            if player_id == exclude_player_id:
                continue
                
            try:
                connection_id = self.player_connections.get(player_id)
                if connection_id and connection_id in self.active_connections:
                    websocket = self.active_connections[connection_id]
                    await websocket.send_text(message_json)
                    successful_sends += 1
                else:
                    # Player is not currently connected
                    logger.debug(f"Player {player_id} not connected during broadcast to room {room_code}")
            except Exception as e:
                logger.warning(f"Failed to send message to player {player_id} in room {room_code}: {e}")
                failed_sends += 1
        
        logger.info(f"Broadcast to room {room_code} (excluding {exclude_player_id}): {successful_sends} successful, {failed_sends} failed")
    
    async def send_to_player(self, player_id: UUID, message: OutgoingWSMessage):
        """Send a message to a specific player"""
        if not self.active_connections or not self.player_connections:
            logger.error("Connection manager not initialized")
            return False
        
        try:
            connection_id = self.player_connections.get(player_id)
            if connection_id and connection_id in self.active_connections:
                websocket = self.active_connections[connection_id]
                await websocket.send_text(message.json())
                logger.debug(f"Sent message to player {player_id}")
                return True
            else:
                logger.debug(f"Player {player_id} not connected")
                return False
        except Exception as e:
            logger.warning(f"Failed to send message to player {player_id}: {e}")
            return False
    
    async def send_to_players(self, player_ids: Set[UUID], message: OutgoingWSMessage):
        """Send a message to multiple specific players"""
        if not self.active_connections or not self.player_connections:
            logger.error("Connection manager not initialized")
            return
        
        message_json = message.json()
        successful_sends = 0
        failed_sends = 0
        
        for player_id in player_ids:
            try:
                connection_id = self.player_connections.get(player_id)
                if connection_id and connection_id in self.active_connections:
                    websocket = self.active_connections[connection_id]
                    await websocket.send_text(message_json)
                    successful_sends += 1
                else:
                    # Player is not currently connected
                    logger.debug(f"Player {player_id} not connected during multi-send")
            except Exception as e:
                logger.warning(f"Failed to send message to player {player_id}: {e}")
                failed_sends += 1
        
        logger.info(f"Multi-send to {len(player_ids)} players: {successful_sends} successful, {failed_sends} failed")
    
    def get_connected_players_in_room(self, room_code: str, room_manager) -> Set[UUID]:
        """Get the set of currently connected players in a room"""
        if not self.player_connections:
            return set()
        
        room = room_manager.get_room(room_code)
        if not room:
            return set()
        
        connected_players = set()
        for player_id in room.players.keys():
            connection_id = self.player_connections.get(player_id)
            if connection_id and connection_id in self.active_connections:
                connected_players.add(player_id)
        
        return connected_players
    
    def get_broadcaster_stats(self) -> dict:
        """Get statistics about the broadcaster"""
        if not self.active_connections or not self.player_connections:
            return {
                "active_connections": 0,
                "player_connections": 0,
                "initialized": False
            }
        
        return {
            "active_connections": len(self.active_connections),
            "player_connections": len(self.player_connections),
            "initialized": True
        }