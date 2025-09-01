from typing import Dict, List, Optional, Set, Any
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for multiplayer games."""
    
    def __init__(self):
        # Store connections by game code -> player_id -> websocket
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # Store player info for quick lookups
        self.player_info: Dict[str, Dict[str, str]] = {}  # player_id -> {game_code, username}
    
    async def connect(self, websocket: WebSocket, game_code: str, player_id: str):
        """Accept a WebSocket connection and add to game room."""
        await websocket.accept()
        
        # Initialize game room if it doesn't exist
        if game_code not in self.active_connections:
            self.active_connections[game_code] = {}
        
        # Add player to the game room
        self.active_connections[game_code][player_id] = websocket
        
        logger.info(f"Player {player_id} connected to game {game_code}")
        
        # Notify other players in the game about the new connection
        await self.broadcast_to_game(
            game_code,
            {
                "type": "player_connected",
                "player_id": player_id,
                "timestamp": datetime.utcnow().isoformat()
            },
            exclude=player_id
        )
    
    def disconnect(self, game_code: str, player_id: str):
        """Remove a WebSocket connection."""
        if game_code in self.active_connections:
            if player_id in self.active_connections[game_code]:
                del self.active_connections[game_code][player_id]
                logger.info(f"Player {player_id} disconnected from game {game_code}")
                
                # If no players left in game, remove the game room
                if not self.active_connections[game_code]:
                    del self.active_connections[game_code]
                    logger.info(f"Game room {game_code} removed (no active connections)")
                else:
                    # Notify remaining players about the disconnection
                    asyncio.create_task(
                        self.broadcast_to_game(
                            game_code,
                            {
                                "type": "player_disconnected",
                                "player_id": player_id,
                                "timestamp": datetime.utcnow().isoformat()
                            },
                            exclude=player_id
                        )
                    )
        
        # Clean up player info
        if player_id in self.player_info:
            del self.player_info[player_id]
    
    async def send_to_player(self, player_id: str, message: Dict[str, Any]) -> bool:
        """Send message to a specific player."""
        # Find the player's connection
        for game_code, players in self.active_connections.items():
            if player_id in players:
                websocket = players[player_id]
                try:
                    await websocket.send_json(message)
                    return True
                except Exception as e:
                    logger.error(f"Error sending message to player {player_id}: {e}")
                    # Remove broken connection
                    self.disconnect(game_code, player_id)
                    return False
        
        logger.warning(f"Player {player_id} not found in active connections")
        return False
    
    async def broadcast_to_game(
        self, 
        game_code: str, 
        message: Dict[str, Any], 
        exclude: Optional[str] = None
    ):
        """Broadcast message to all players in a game."""
        if game_code not in self.active_connections:
            logger.warning(f"Game {game_code} not found in active connections")
            return
        
        players = self.active_connections[game_code].copy()  # Copy to avoid modification during iteration
        disconnected_players = []
        
        for player_id, websocket in players.items():
            if exclude and player_id == exclude:
                continue
            
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to player {player_id} in game {game_code}: {e}")
                disconnected_players.append(player_id)
        
        # Clean up disconnected players
        for player_id in disconnected_players:
            self.disconnect(game_code, player_id)
    
    async def send_game_state(self, game_code: str, game_data: Dict[str, Any]):
        """Send updated game state to all players in a game."""
        await self.broadcast_to_game(
            game_code,
            {
                "type": "game_state_updated",
                "game": game_data,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    async def notify_round_started(self, game_code: str, round_data: Dict[str, Any]):
        """Notify all players that a new round has started."""
        await self.broadcast_to_game(
            game_code,
            {
                "type": "round_started",
                "round": round_data,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    async def notify_round_ended(
        self, 
        game_code: str, 
        winner: Optional[str], 
        solution_revealed: bool, 
        solution: Optional[List[Any]] = None
    ):
        """Notify all players that a round has ended."""
        message = {
            "type": "round_ended",
            "winner": winner,
            "solution_revealed": solution_revealed,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if solution_revealed and solution:
            message["solution"] = solution
        
        await self.broadcast_to_game(game_code, message)
    
    async def notify_game_finished(self, game_code: str, winner: str, final_scores: Dict[str, int]):
        """Notify all players that the game has finished."""
        await self.broadcast_to_game(
            game_code,
            {
                "type": "game_finished",
                "winner": winner,
                "final_scores": final_scores,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    async def send_error_to_player(self, player_id: str, error_message: str, error_code: str = "GENERAL_ERROR"):
        """Send error message to a specific player."""
        await self.send_to_player(
            player_id,
            {
                "type": "error",
                "message": error_message,
                "code": error_code,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def get_game_connections(self, game_code: str) -> Dict[str, WebSocket]:
        """Get all active connections for a game."""
        return self.active_connections.get(game_code, {})
    
    def get_connected_players(self, game_code: str) -> List[str]:
        """Get list of connected player IDs for a game."""
        return list(self.active_connections.get(game_code, {}).keys())
    
    def is_player_connected(self, game_code: str, player_id: str) -> bool:
        """Check if a player is connected to a game."""
        return (
            game_code in self.active_connections and 
            player_id in self.active_connections[game_code]
        )
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        total_connections = sum(len(players) for players in self.active_connections.values())
        active_games = len(self.active_connections)
        
        return {
            "active_games": active_games,
            "total_connections": total_connections,
            "games": {
                game_code: len(players) 
                for game_code, players in self.active_connections.items()
            }
        }
    
    async def cleanup_stale_connections(self):
        """Clean up stale WebSocket connections."""
        stale_connections = []
        
        for game_code, players in self.active_connections.items():
            for player_id, websocket in players.items():
                try:
                    # Try to ping the connection
                    await websocket.ping()
                except Exception:
                    stale_connections.append((game_code, player_id))
        
        # Remove stale connections
        for game_code, player_id in stale_connections:
            logger.info(f"Removing stale connection: {player_id} from {game_code}")
            self.disconnect(game_code, player_id)
        
        if stale_connections:
            logger.info(f"Cleaned up {len(stale_connections)} stale connections")


# Global connection manager instance
connection_manager = ConnectionManager() 