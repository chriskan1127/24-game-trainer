"""
Room Manager Component

Handles room creation, joining, and lifecycle management for the multiplayer 24-game system.

Key responsibilities:
- Generate unique 4-character room codes
- Handle room creation with host assignment
- Manage player joining (max 4 players, duplicate username checks)  
- Track room states (LOBBY → RUNNING → FINISHED)
- Handle room cleanup when empty
- Manage session tokens for authentication
"""

import random
import string
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set
from uuid import UUID, uuid4
import asyncio

# Add project paths for imports
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

from pydantic_schemas import (
    Room, PlayerInternal, PlayerPublic, RoomState, MVPRoomSettings,
    CreateRoomResult, JoinRoomResult
)

logger = logging.getLogger(__name__)


class RoomManagerError(Exception):
    """Base exception for room manager operations"""
    pass


class RoomNotFoundError(RoomManagerError):
    """Raised when a room is not found"""
    pass


class RoomFullError(RoomManagerError):
    """Raised when attempting to join a full room"""
    pass


class UsernameConflictError(RoomManagerError):
    """Raised when username already exists in room"""
    pass


class GameInProgressError(RoomManagerError):
    """Raised when attempting to join a room with game in progress"""
    pass


class AuthenticationError(RoomManagerError):
    """Raised when session token validation fails"""
    pass


class RoomManager:
    """
    Manages game rooms and player membership.
    
    Features:
    - Thread-safe room operations with asyncio locks
    - Automatic room cleanup for inactive rooms
    - Session token based authentication
    - Host privilege management
    - Comprehensive error handling with specific exceptions
    """
    
    def __init__(self, problem_pool_service=None, room_timeout_hours: int = 24):
        self.rooms: Dict[str, Room] = {}
        self.problem_pool_service = problem_pool_service
        self.session_tokens: Dict[str, UUID] = {}  # session_token -> player_id
        self.room_locks: Dict[str, asyncio.Lock] = {}  # room_code -> lock for thread safety
        self.room_timeout_hours = room_timeout_hours
        
        # Statistics tracking
        self.stats = {
            'rooms_created': 0,
            'players_joined': 0,
            'rooms_cleaned_up': 0
        }
        
    def _get_room_lock(self, room_code: str) -> asyncio.Lock:
        """Get or create a lock for a specific room"""
        if room_code not in self.room_locks:
            self.room_locks[room_code] = asyncio.Lock()
        return self.room_locks[room_code]
    
    def generate_room_code(self) -> str:
        """
        Generate a unique 4-character room code.
        
        Returns:
            str: Unique room code (4 uppercase alphanumeric characters)
        """
        max_attempts = 1000  # Prevent infinite loop
        attempts = 0
        
        while attempts < max_attempts:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            if code not in self.rooms:
                return code
            attempts += 1
        
        # If we can't find a unique code, expand the space
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return code
    
    def generate_session_token(self) -> str:
        """
        Generate a unique session token for player authentication.
        
        Returns:
            str: Unique session token
        """
        return str(uuid4())
    
    async def create_room(self, host_username: str, host_player_id: Optional[UUID] = None) -> CreateRoomResult:
        """
        Create a new game room with the specified host.
        
        Args:
            host_username: Name of the host player
            host_player_id: Optional UUID for host (auto-generated if not provided)
            
        Returns:
            CreateRoomResult: Room creation details including room code and session token
            
        Raises:
            ValueError: If username is invalid
        """
        if not host_username or not host_username.strip():
            raise ValueError("Host username cannot be empty")
        
        host_username = host_username.strip()
        
        if len(host_username) > 32:
            raise ValueError("Username cannot exceed 32 characters")
        
        # Generate IDs
        room_code = self.generate_room_code()
        session_token = self.generate_session_token()
        
        if host_player_id is None:
            host_player_id = uuid4()
        
        # Create host player
        host_player = PlayerInternal(
            player_id=host_player_id,
            username=host_username,
            score=0,
            streak=0,
            session_token=session_token,
            joined_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        
        # Generate problems if service is available
        problems = []
        if self.problem_pool_service:
            try:
                problems = await self.problem_pool_service.generate_problems_for_game(10)
            except Exception as e:
                logger.warning(f"Failed to generate problems for room {room_code}: {e}")
                # Continue without problems - they can be generated later
        
        # Create room
        room = Room(
            room_code=room_code,
            host_player_id=host_player_id,
            settings=MVPRoomSettings(),
            players={host_player_id: host_player},
            problems=problems,
            state=RoomState.LOBBY,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        
        # Store room and session token
        async with self._get_room_lock(room_code):
            self.rooms[room_code] = room
            self.session_tokens[session_token] = host_player_id
        
        # Update statistics
        self.stats['rooms_created'] += 1
        
        logger.info(f"Created room {room_code} with host {host_username} ({host_player_id})")
        
        return CreateRoomResult(
            room_code=room_code,
            host_player_id=host_player_id,
            host_session_token=session_token,
            created_at=room.created_at
        )
    
    async def join_room(self, room_code: str, username: str, player_id: Optional[UUID] = None, 
                       session_token: Optional[str] = None) -> JoinRoomResult:
        """
        Join an existing room or reconnect with session token.
        
        Args:
            room_code: 4-character room code
            username: Player username
            player_id: Optional player UUID (auto-generated if not provided)
            session_token: Optional session token for reconnection
            
        Returns:
            JoinRoomResult: Join result with player info and room state
            
        Raises:
            RoomNotFoundError: If room doesn't exist
            RoomFullError: If room has 4 players already
            GameInProgressError: If game is running and player not already in room
            UsernameConflictError: If username is taken by another player
        """
        room_code = room_code.upper()
        username = username.strip()
        
        # Validation
        if not username:
            raise ValueError("Username cannot be empty")
        
        if len(username) > 32:
            raise ValueError("Username cannot exceed 32 characters")
        
        if room_code not in self.rooms:
            raise RoomNotFoundError(f"Room {room_code} does not exist")
        
        room = self.rooms[room_code]
        
        async with self._get_room_lock(room_code):
            # Handle reconnection with existing session token
            if session_token and session_token in self.session_tokens:
                existing_player_id = self.session_tokens[session_token]
                if existing_player_id in room.players:
                    # Reconnecting player
                    player = room.players[existing_player_id]
                    player.last_seen_at = datetime.now(timezone.utc)
                    player.disconnected_at = None
                    room.last_activity_at = datetime.now(timezone.utc)
                    
                    logger.info(f"Player {username} ({existing_player_id}) reconnected to room {room_code}")
                    
                    return JoinRoomResult(
                        room_code=room_code,
                        player_id=existing_player_id,
                        session_token=session_token,
                        players=[self._to_public_player(p) for p in room.players.values()],
                        state=room.state
                    )
            
            # Generate player ID if not provided
            if player_id is None:
                player_id = uuid4()
            
            # Check if room is full (max 4 players)
            if len(room.players) >= 4 and player_id not in room.players:
                raise RoomFullError("Room is full (maximum 4 players)")
            
            # Check if room is locked (game in progress)
            if room.state != RoomState.LOBBY and player_id not in room.players:
                raise GameInProgressError("Cannot join room - game in progress")
            
            # Check for username conflicts
            for existing_player in room.players.values():
                if (existing_player.username.lower() == username.lower() and 
                    existing_player.player_id != player_id):
                    raise UsernameConflictError(f"Username '{username}' is already taken in this room")
            
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
                    joined_at=datetime.now(timezone.utc),
                    last_seen_at=datetime.now(timezone.utc)
                )
                room.players[player_id] = player
                self.stats['players_joined'] += 1
            
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
        """
        Get room by code.
        
        Args:
            room_code: Room code to lookup
            
        Returns:
            Room object if found, None otherwise
        """
        return self.rooms.get(room_code.upper())
    
    def validate_session_token(self, room_code: str, player_id: UUID, session_token: str) -> bool:
        """
        Validate that a session token belongs to the specified player in the room.
        
        Args:
            room_code: Room code
            player_id: Player UUID
            session_token: Session token to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        room = self.get_room(room_code)
        if not room or player_id not in room.players:
            return False
        
        player = room.players[player_id]
        return player.session_token == session_token
    
    def is_host(self, room_code: str, player_id: UUID) -> bool:
        """
        Check if a player is the host of a room.
        
        Args:
            room_code: Room code
            player_id: Player UUID
            
        Returns:
            bool: True if player is host, False otherwise
        """
        room = self.get_room(room_code)
        return room is not None and room.host_player_id == player_id
    
    async def remove_player(self, room_code: str, player_id: UUID) -> bool:
        """
        Remove a player from a room and cleanup if empty.
        
        Args:
            room_code: Room code
            player_id: Player UUID to remove
            
        Returns:
            bool: True if player was removed, False if player wasn't in room
        """
        room = self.get_room(room_code)
        if not room or player_id not in room.players:
            return False
        
        async with self._get_room_lock(room_code):
            player = room.players[player_id]
            
            # Remove session token
            if player.session_token in self.session_tokens:
                del self.session_tokens[player.session_token]
            
            # Remove player from room
            del room.players[player_id]
            
            # If room is empty, remove it
            if not room.players:
                del self.rooms[room_code]
                if room_code in self.room_locks:
                    del self.room_locks[room_code]
                logger.info(f"Removed empty room {room_code}")
                self.stats['rooms_cleaned_up'] += 1
            else:
                # If the host left, transfer host to another player
                if room.host_player_id == player_id:
                    new_host_id = next(iter(room.players.keys()))
                    room.host_player_id = new_host_id
                    logger.info(f"Transferred host of room {room_code} to player {new_host_id}")
                
                room.last_activity_at = datetime.now(timezone.utc)
        
        logger.info(f"Removed player {player_id} from room {room_code}")
        return True
    
    async def cleanup_inactive_rooms(self, max_age_hours: Optional[int] = None) -> int:
        """
        Remove rooms that have been inactive for too long.
        
        Args:
            max_age_hours: Maximum age in hours (defaults to instance setting)
            
        Returns:
            int: Number of rooms cleaned up
        """
        if max_age_hours is None:
            max_age_hours = self.room_timeout_hours
            
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        rooms_to_remove = []
        
        for room_code, room in self.rooms.items():
            if room.last_activity_at < cutoff_time:
                rooms_to_remove.append(room_code)
        
        # Remove inactive rooms
        for room_code in rooms_to_remove:
            async with self._get_room_lock(room_code):
                room = self.rooms[room_code]
                # Remove all session tokens for this room
                for player in room.players.values():
                    if player.session_token in self.session_tokens:
                        del self.session_tokens[player.session_token]
                del self.rooms[room_code]
                if room_code in self.room_locks:
                    del self.room_locks[room_code]
        
        if rooms_to_remove:
            logger.info(f"Cleaned up {len(rooms_to_remove)} inactive rooms")
            self.stats['rooms_cleaned_up'] += len(rooms_to_remove)
        
        return len(rooms_to_remove)
    
    def get_room_stats(self) -> dict:
        """
        Get statistics about active rooms.
        
        Returns:
            dict: Statistics including room counts, player counts, etc.
        """
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
            "active_session_tokens": len(self.session_tokens),
            "lifetime_stats": self.stats.copy()
        }
    
    def get_room_players(self, room_code: str) -> List[PlayerPublic]:
        """
        Get public player info for a room.
        
        Args:
            room_code: Room code
            
        Returns:
            List of PlayerPublic objects
        """
        room = self.get_room(room_code)
        if not room:
            return []
        
        return [self._to_public_player(player) for player in room.players.values()]
    
    def get_player_count(self, room_code: str) -> int:
        """
        Get the number of players in a room.
        
        Args:
            room_code: Room code
            
        Returns:
            int: Number of players (0 if room doesn't exist)
        """
        room = self.get_room(room_code)
        return len(room.players) if room else 0
    
    def _to_public_player(self, player: PlayerInternal) -> PlayerPublic:
        """
        Convert internal player to public representation.
        
        Args:
            player: PlayerInternal object
            
        Returns:
            PlayerPublic object with safe public fields
        """
        return PlayerPublic(
            player_id=player.player_id,
            username=player.username,
            score=player.score,
            streak=player.streak
        )