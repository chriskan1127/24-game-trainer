"""
Room Manager Service
Handles room creation, joining, and lifecycle management
"""

import random
import string
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from pydantic_schemas import (
    Room, PlayerInternal, PlayerPublic, RoomState, MVPRoomSettings,
    CreateRoomResult, JoinRoomResult
)

logger = logging.getLogger(__name__)


class RoomManager:
    """Manages game rooms and player membership"""
    
    def __init__(self, problem_pool_service):
        self.rooms: Dict[str, Room] = {}
        self.problem_pool_service = problem_pool_service
        self.session_tokens: Dict[str, UUID] = {}  # session_token -> player_id
        
    def generate_room_code(self) -> str:
        """Generate a unique 4-character room code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            if code not in self.rooms:
                return code
    
    def generate_session_token(self) -> str:
        """Generate a unique session token for player authentication"""
        return str(uuid4())
    
    async def create_room(self, host_username: str, host_player_id: UUID) -> CreateRoomResult:
        """Create a new game room with the specified host"""
        room_code = self.generate_room_code()
        session_token = self.generate_session_token()
        
        # Create host player
        host_player = PlayerInternal(
            player_id=host_player_id,
            username=host_username,
            score=0,
            streak=0,
            session_token=session_token,
            joined_at=datetime.now(timezone.utc)
        )
        
        # Create room with dynamically generated problems
        room = Room(
            room_code=room_code,
            host_player_id=host_player_id,
            settings=MVPRoomSettings(),
            players={host_player_id: host_player},
            problems=await self.problem_pool_service.generate_problems_for_game(10),
            state=RoomState.LOBBY,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        
        self.rooms[room_code] = room
        self.session_tokens[session_token] = host_player_id
        
        logger.info(f"Created room {room_code} with host {host_username} ({host_player_id})")
        
        return CreateRoomResult(
            room_code=room_code,
            host_player_id=host_player_id,
            host_session_token=session_token,
            created_at=room.created_at
        )
    
    async def join_room(self, room_code: str, username: str, player_id: UUID, 
                       session_token: Optional[str] = None) -> JoinRoomResult:
        """Join an existing room or reconnect with session token"""
        room_code = room_code.upper()
        
        if room_code not in self.rooms:
            raise ValueError(f"Room {room_code} does not exist")
        
        room = self.rooms[room_code]
        
        # Check if room is full (max 4 players)
        if len(room.players) >= 4 and player_id not in room.players:
            raise ValueError("Room is full (maximum 4 players)")
        
        # Check if room is locked (game in progress)
        if room.state != RoomState.LOBBY and player_id not in room.players:
            raise ValueError("Cannot join room - game in progress")
        
        # Handle reconnection with existing session token
        if session_token and session_token in self.session_tokens:
            existing_player_id = self.session_tokens[session_token]
            if existing_player_id in room.players:
                # Reconnecting player
                player = room.players[existing_player_id]
                player.last_seen_at = datetime.now(timezone.utc)
                player.disconnected_at = None
                logger.info(f"Player {username} ({existing_player_id}) reconnected to room {room_code}")
                
                return JoinRoomResult(
                    room_code=room_code,
                    player_id=existing_player_id,
                    session_token=session_token,
                    players=[self._to_public_player(p) for p in room.players.values()],
                    state=room.state
                )
        
        # Check for username conflicts
        for existing_player in room.players.values():
            if existing_player.username.lower() == username.lower() and existing_player.player_id != player_id:
                raise ValueError(f"Username '{username}' is already taken in this room")
        
        # Create new session token if not reconnecting
        if not session_token:
            session_token = self.generate_session_token()
        
        # Add new player or update existing
        if player_id in room.players:
            # Update existing player
            player = room.players[player_id]
            player.username = username
            player.session_token = session_token
            player.last_seen_at = datetime.now(timezone.utc)
            player.disconnected_at = None
        else:
            # Create new player
            player = PlayerInternal(
                player_id=player_id,
                username=username,
                score=0,
                streak=0,
                session_token=session_token,
                joined_at=datetime.now(timezone.utc)
            )
            room.players[player_id] = player
        
        room.last_activity_at = datetime.now(timezone.utc)
        self.session_tokens[session_token] = player_id
        
        logger.info(f"Player {username} ({player_id}) joined room {room_code}")
        
        return JoinRoomResult(
            room_code=room_code,
            player_id=player_id,
            session_token=session_token,
            players=[self._to_public_player(p) for p in room.players.values()],
            state=room.state
        )
    
    def get_room(self, room_code: str) -> Optional[Room]:
        """Get room by code"""
        return self.rooms.get(room_code.upper())
    
    def validate_session_token(self, room_code: str, player_id: UUID, session_token: str) -> bool:
        """Validate that a session token belongs to the specified player in the room"""
        room = self.get_room(room_code)
        if not room or player_id not in room.players:
            return False
        
        player = room.players[player_id]
        return player.session_token == session_token
    
    def is_host(self, room_code: str, player_id: UUID) -> bool:
        """Check if a player is the host of a room"""
        room = self.get_room(room_code)
        return room is not None and room.host_player_id == player_id
    
    def remove_player(self, room_code: str, player_id: UUID) -> bool:
        """Remove a player from a room and cleanup if empty"""
        room = self.get_room(room_code)
        if not room or player_id not in room.players:
            return False
        
        player = room.players[player_id]
        
        # Remove session token
        if player.session_token in self.session_tokens:
            del self.session_tokens[player.session_token]
        
        # Remove player from room
        del room.players[player_id]
        
        # If room is empty, remove it
        if not room.players:
            del self.rooms[room_code]
            logger.info(f"Removed empty room {room_code}")
        else:
            # If the host left, transfer host to another player
            if room.host_player_id == player_id:
                new_host_id = next(iter(room.players.keys()))
                room.host_player_id = new_host_id
                logger.info(f"Transferred host of room {room_code} to player {new_host_id}")
        
        room.last_activity_at = datetime.now(timezone.utc)
        logger.info(f"Removed player {player_id} from room {room_code}")
        return True
    
    def cleanup_inactive_rooms(self, max_age_hours: int = 24) -> int:
        """Remove rooms that have been inactive for too long"""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        rooms_to_remove = []
        
        for room_code, room in self.rooms.items():
            if room.last_activity_at.timestamp() < cutoff_time:
                rooms_to_remove.append(room_code)
        
        for room_code in rooms_to_remove:
            room = self.rooms[room_code]
            # Remove all session tokens for this room
            for player in room.players.values():
                if player.session_token in self.session_tokens:
                    del self.session_tokens[player.session_token]
            del self.rooms[room_code]
        
        if rooms_to_remove:
            logger.info(f"Cleaned up {len(rooms_to_remove)} inactive rooms")
        
        return len(rooms_to_remove)
    
    def get_room_stats(self) -> dict:
        """Get statistics about active rooms"""
        total_rooms = len(self.rooms)
        total_players = sum(len(room.players) for room in self.rooms.values())
        rooms_by_state = {}
        
        for room in self.rooms.values():
            state = room.state
            rooms_by_state[state] = rooms_by_state.get(state, 0) + 1
        
        return {
            "total_rooms": total_rooms,
            "total_players": total_players,
            "rooms_by_state": rooms_by_state,
            "active_session_tokens": len(self.session_tokens)
        }
    
    def _to_public_player(self, player: PlayerInternal) -> PlayerPublic:
        """Convert internal player to public representation"""
        return PlayerPublic(
            player_id=player.player_id,
            username=player.username,
            score=player.score,
            streak=player.streak
        )