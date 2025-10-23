"""
24-Game Multiplayer Server
FastAPI + WebSocket server for multiplayer 24-game competitions
"""

import asyncio
import json
import logging
import sys
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from uuid import UUID, uuid4

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
plans_dir = os.path.join(project_root, 'plans')
lib_dir = os.path.join(project_root, 'lib')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

# Import schemas and solver
from pydantic_schemas import (
    IncomingWSMessage, OutgoingWSMessage,
    RoomCreateMessage, RoomJoinMessage, GameStartMessage, AnswerSubmitMessage,
    RoomCreatedMessage, RoomJoinedMessage, CountdownStartMessage, RoundStartMessage,
    AnswerAckMessage, RoundEndMessage, GameEndMessage, PlayerJoinedMessage,
    PlayerLeftMessage, ErrorMessage,
    RoomCreatedPayload, RoomJoinedPayload, CountdownStartPayload, RoundStartPayload,
    AnswerAckPayload, RoundEndPayload, GameEndPayload, PlayerJoinedPayload,
    PlayerLeftPayload, ErrorPayload,
    Room, PlayerInternal, PlayerPublic, Problem, MVPRoomSettings,
    RoomState, RoundPhase, RoundState, SubmissionRecord, PlayerScored, PlayerScoreUpdate,
    LeaderboardEntry
)
from solve_24 import Solution

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import service components
from room_manager import RoomManager
from game_state_manager import GameStateManager
from player_manager import PlayerManager
from problem_pool_service import ProblemPoolService
from submission_processor import SubmissionProcessor
from message_broadcaster import MessageBroadcaster
from timer_service import TimerService

# Global service instances
room_manager: Optional[RoomManager] = None
game_state_manager: Optional[GameStateManager] = None
player_manager: Optional[PlayerManager] = None
problem_pool_service: Optional[ProblemPoolService] = None
submission_processor: Optional[SubmissionProcessor] = None
message_broadcaster: Optional[MessageBroadcaster] = None
timer_service: Optional[TimerService] = None

# WebSocket connection tracking
active_connections: Dict[str, WebSocket] = {}  # connection_id -> websocket
player_connections: Dict[UUID, str] = {}  # player_id -> connection_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    Replaces deprecated @app.on_event decorators
    """
    # Startup
    global room_manager, game_state_manager, player_manager, problem_pool_service
    global submission_processor, message_broadcaster, timer_service

    logger.info("Starting 24-Game Multiplayer Server...")

    # Initialize services in dependency order
    problem_pool_service = ProblemPoolService()
    await problem_pool_service.initialize()

    message_broadcaster = MessageBroadcaster()
    room_manager = RoomManager(problem_pool_service)
    player_manager = PlayerManager()
    timer_service = TimerService()
    submission_processor = SubmissionProcessor(player_manager)
    game_state_manager = GameStateManager(
        room_manager, player_manager, message_broadcaster, timer_service
    )

    # Set up cross-service dependencies
    message_broadcaster.set_connection_manager(active_connections, player_connections)
    timer_service.set_game_state_manager(game_state_manager)

    logger.info("All services initialized successfully")

    yield  # Server runs here

    # Shutdown
    logger.info("Shutting down 24-Game Multiplayer Server...")

    # Cancel any running timers
    if timer_service:
        await timer_service.cleanup()

    # Close all WebSocket connections
    for connection in active_connections.values():
        try:
            await connection.close()
        except:
            pass

    logger.info("Server shutdown complete")


# FastAPI app with lifespan
app = FastAPI(
    title="24-Game Multiplayer Server",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/{room_code}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, player_id: str):
    """WebSocket endpoint for game connections"""
    await websocket.accept()
    
    connection_id = str(uuid4())
    active_connections[connection_id] = websocket
    
    try:
        player_uuid = UUID(player_id)
        player_connections[player_uuid] = connection_id
        
        logger.info(f"Player {player_id} connected to room {room_code}")
        
        # Handle incoming messages
        async for message in websocket.iter_text():
            try:
                await handle_websocket_message(websocket, connection_id, player_uuid, message)
            except Exception as e:
                logger.error(f"Error handling message: {e}", exc_info=True)
                await send_error(websocket, "MESSAGE_ERROR", f"Error processing message: {str(e)}")
                
    except WebSocketDisconnect:
        logger.info(f"Player {player_id} disconnected from room {room_code}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # Cleanup connection
        if connection_id in active_connections:
            del active_connections[connection_id]
        if player_uuid in player_connections:
            del player_connections[player_uuid]
        
        # Handle player disconnection in game logic
        if player_manager and room_manager:
            await handle_player_disconnect(player_uuid, room_code)


async def handle_websocket_message(websocket: WebSocket, connection_id: str, player_id: UUID, message: str):
    """Process incoming WebSocket messages"""
    try:
        # Parse JSON message
        data = json.loads(message)
        message_type = data.get("type")
        payload = data.get("payload", {})
        
        logger.info(f"Received message type: {message_type} from player: {player_id}")
        
        # Route message to appropriate handler
        if message_type == "room.create":
            await handle_room_create(websocket, player_id, payload)
        elif message_type == "room.join":
            await handle_room_join(websocket, player_id, payload)
        elif message_type == "game.start":
            await handle_game_start(websocket, player_id, payload)
        elif message_type == "answer.submit":
            await handle_answer_submit(websocket, player_id, payload)
        else:
            await send_error(websocket, "UNKNOWN_MESSAGE_TYPE", f"Unknown message type: {message_type}")
            
    except json.JSONDecodeError:
        await send_error(websocket, "INVALID_JSON", "Invalid JSON message")
    except Exception as e:
        logger.error(f"Error in handle_websocket_message: {e}", exc_info=True)
        await send_error(websocket, "MESSAGE_PROCESSING_ERROR", str(e))


async def handle_room_create(websocket: WebSocket, player_id: UUID, payload: dict):
    """Handle room creation request"""
    try:
        username = payload.get("username")
        if not username:
            await send_error(websocket, "MISSING_USERNAME", "Username is required")
            return
        
        # Create room through room manager
        result = await room_manager.create_room(username, player_id)
        
        # Send success response
        response = RoomCreatedMessage(
            type="room.created",
            payload=RoomCreatedPayload(
                room_code=result.room_code,
                host_player_id=result.host_player_id,
                session_token=result.host_session_token,
                settings=MVPRoomSettings()
            )
        )
        
        await websocket.send_text(response.json())
        logger.info(f"Room {result.room_code} created by player {player_id}")
        
    except Exception as e:
        logger.error(f"Error creating room: {e}", exc_info=True)
        await send_error(websocket, "ROOM_CREATE_ERROR", str(e))


async def handle_room_join(websocket: WebSocket, player_id: UUID, payload: dict):
    """Handle room join request"""
    try:
        room_code = payload.get("room_code")
        username = payload.get("username")
        session_token = payload.get("session_token")
        
        if not room_code or not username:
            await send_error(websocket, "MISSING_REQUIRED_FIELDS", "Room code and username are required")
            return
        
        # Join room through room manager
        result = await room_manager.join_room(room_code, username, player_id, session_token)
        
        # Send success response to the joining player
        response = RoomJoinedMessage(
            type="room.joined",
            payload=RoomJoinedPayload(
                room_code=result.room_code,
                player_id=result.player_id,
                session_token=result.session_token,
                players=result.players,
                state=result.state
            )
        )
        
        await websocket.send_text(response.json())
        
        # Broadcast player joined to other players in the room
        if message_broadcaster:
            room = room_manager.get_room(room_code)
            if room:
                player = room.players.get(player_id)
                if player:
                    await message_broadcaster.broadcast_to_room_except(
                        room_code,
                        PlayerJoinedMessage(
                            type="player.joined",
                            payload=PlayerJoinedPayload(
                                player=PlayerPublic(
                                    player_id=player.player_id,
                                    username=player.username,
                                    score=player.score,
                                    streak=player.streak
                                ),
                                total_players=len(room.players)
                            )
                        ),
                        room_manager,
                        exclude_player_id=player_id
                    )
        
        logger.info(f"Player {player_id} ({username}) joined room {room_code}")
        
    except Exception as e:
        logger.error(f"Error joining room: {e}", exc_info=True)
        await send_error(websocket, "ROOM_JOIN_ERROR", str(e))


async def handle_game_start(websocket: WebSocket, player_id: UUID, payload: dict):
    """Handle game start request"""
    try:
        room_code = payload.get("room_code")
        session_token = payload.get("session_token")
        
        if not room_code or not session_token:
            await send_error(websocket, "MISSING_REQUIRED_FIELDS", "Room code and session token are required")
            return
        
        # Validate host permissions and start game
        await game_state_manager.start_game(room_code, player_id, session_token)
        
        logger.info(f"Game started in room {room_code} by player {player_id}")
        
    except Exception as e:
        logger.error(f"Error starting game: {e}", exc_info=True)
        await send_error(websocket, "GAME_START_ERROR", str(e))


async def handle_answer_submit(websocket: WebSocket, player_id: UUID, payload: dict):
    """Handle answer submission"""
    try:
        room_code = payload.get("room_code")
        session_token = payload.get("session_token")
        round_index = payload.get("round_index")
        expression = payload.get("expression")
        used_numbers = payload.get("used_numbers")
        client_eval_value = payload.get("client_eval_value")
        client_eval_is_valid = payload.get("client_eval_is_valid", False)
        client_timestamp = payload.get("client_timestamp")
        
        if not all([room_code, session_token, expression, used_numbers]):
            await send_error(websocket, "MISSING_REQUIRED_FIELDS", 
                           "Room code, session token, expression, and used_numbers are required")
            return
        
        # Process submission
        result = await submission_processor.process_submission(
            room_code=room_code,
            player_id=player_id,
            session_token=session_token,
            round_index=round_index,
            expression=expression,
            used_numbers=used_numbers,
            client_eval_value=client_eval_value,
            client_eval_is_valid=client_eval_is_valid,
            client_timestamp=client_timestamp,
            room_manager=room_manager
        )

        # Record submission in game state manager for use in round results
        if result and result.accepted:
            game_state_manager.record_submission(room_code, round_index, result)

        # Send acknowledgment
        response = AnswerAckMessage(
            type="answer.ack",
            payload=AnswerAckPayload(
                submission_id=result.submission_id if result else None,
                accepted=result.accepted if result else False,
                server_receive_time=datetime.now(timezone.utc),
                time_left_seconds=result.time_left_at_submission if result else None,
                reason=result.reason if result else "Submission failed"
            )
        )

        await websocket.send_text(response.json())
        logger.info(f"Answer submitted by player {player_id} in room {room_code}: {result.accepted if result else False}")
        
    except Exception as e:
        logger.error(f"Error processing answer submission: {e}", exc_info=True)
        await send_error(websocket, "ANSWER_SUBMIT_ERROR", str(e))


async def handle_player_disconnect(player_id: UUID, room_code: str):
    """Handle player disconnection"""
    try:
        if player_manager and room_manager:
            # Mark player as disconnected
            await player_manager.mark_player_disconnected(player_id, room_code)
            
            # Broadcast player left to other players
            room = room_manager.get_room(room_code)
            if room and message_broadcaster:
                player = room.players.get(player_id)
                if player:
                    await message_broadcaster.broadcast_to_room_except(
                        room_code,
                        PlayerLeftMessage(
                            type="player.left",
                            payload=PlayerLeftPayload(
                                player_id=player_id,
                                username=player.username,
                                total_players=len([p for p in room.players.values() if not p.disconnected_at])
                            )
                        ),
                        room_manager,
                        exclude_player_id=player_id
                    )
        
        logger.info(f"Player {player_id} disconnected from room {room_code}")
        
    except Exception as e:
        logger.error(f"Error handling player disconnect: {e}", exc_info=True)


async def send_error(websocket: WebSocket, error_code: str, message: str, details=None):
    """Send error message to client"""
    try:
        error_msg = ErrorMessage(
            type="error",
            payload=ErrorPayload(
                code=error_code,
                message=message,
                details=details
            )
        )
        await websocket.send_text(error_msg.json())
    except Exception as e:
        logger.error(f"Failed to send error message: {e}")


# HTTP endpoints for REST API integration (optional)
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/stats")
async def get_server_stats():
    """Get server statistics"""
    stats = {
        "active_connections": len(active_connections),
        "active_rooms": len(room_manager.rooms) if room_manager else 0,
        "total_players": sum(len(room.players) for room in room_manager.rooms.values()) if room_manager else 0
    }
    return stats


# Pydantic models for REST API request/response validation
from pydantic import BaseModel

class CreateGameRequest(BaseModel):
    host_username: str
    target: int = 24
    time_limit: int = 30
    max_players: int = 10
    points_to_win: int = 10

class JoinGameRequest(BaseModel):
    username: str

# REST API endpoints for game management
@app.post("/api/games/create")
async def create_game_api(request_data: CreateGameRequest):
    """
    REST API endpoint to create a new game
    Expected payload: {
        "host_username": str,
        "target": int (optional, default 24),
        "time_limit": int (optional, default 30),
        "max_players": int (optional, default 10),
        "points_to_win": int (optional, default 10)
    }
    Returns: {
        "success": bool,
        "data": {
            "game_code": str,
            "host_id": str,
            "session_token": str
        },
        "message": str (optional)
    }
    """
    try:
        host_username = request_data.host_username
        if not host_username:
            return {
                "success": False,
                "message": "host_username is required"
            }

        # Generate host player ID
        host_player_id = uuid4()

        # Create room through room manager
        result = await room_manager.create_room(host_username, host_player_id)

        logger.info(f"Game created via REST API: {result.room_code} by {host_username}")

        # Broadcast room.created to the host if they're connected via WebSocket
        if message_broadcaster and host_player_id in player_connections:
            from pydantic_schemas import RoomCreatedMessage, RoomCreatedPayload, MVPRoomSettings
            room_created_msg = RoomCreatedMessage(
                type="room.created",
                payload=RoomCreatedPayload(
                    room_code=result.room_code,
                    host_player_id=host_player_id,
                    session_token=result.host_session_token,
                    settings=MVPRoomSettings()
                )
            )
            await message_broadcaster.send_to_player(host_player_id, room_created_msg)

            # Also send room.joined message so host sees themselves in the lobby
            room = room_manager.get_room(result.room_code)
            if room:
                room_joined_msg = RoomJoinedMessage(
                    type="room.joined",
                    payload=RoomJoinedPayload(
                        room_code=result.room_code,
                        player_id=host_player_id,
                        session_token=result.host_session_token,
                        players=[room_manager._to_public_player(p) for p in room.players.values()],
                        state=room.state
                    )
                )
                await message_broadcaster.send_to_player(host_player_id, room_joined_msg)

        return {
            "success": True,
            "data": {
                "game_code": result.room_code,
                "host_id": str(result.host_player_id),
                "session_token": result.host_session_token
            }
        }

    except Exception as e:
        logger.error(f"Error creating game via REST API: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to create game: {str(e)}"
        }


@app.post("/api/games/{game_code}/join")
async def join_game_api(game_code: str, request_data: JoinGameRequest):
    """
    REST API endpoint to join an existing game
    Expected payload: {
        "username": str
    }
    Returns: {
        "success": bool,
        "data": {
            "player_id": str,
            "session_token": str,
            "game_code": str
        },
        "message": str (optional)
    }
    """
    try:
        username = request_data.username
        if not username:
            return {
                "success": False,
                "message": "username is required"
            }

        # Generate player ID
        player_id = uuid4()

        # Join room through room manager
        result = await room_manager.join_room(
            game_code.upper(),
            username,
            player_id
        )

        logger.info(f"Player {username} joined game {game_code} via REST API")

        # Broadcast player.joined to all other players in the room
        if message_broadcaster:
            room = room_manager.get_room(game_code.upper())
            if room:
                player = room.players.get(player_id)
                if player:
                    from pydantic_schemas import PlayerJoinedMessage, PlayerJoinedPayload, PlayerPublic
                    await message_broadcaster.broadcast_to_room_except(
                        game_code.upper(),
                        PlayerJoinedMessage(
                            type="player.joined",
                            payload=PlayerJoinedPayload(
                                player=PlayerPublic(
                                    player_id=player.player_id,
                                    username=player.username,
                                    score=player.score,
                                    streak=player.streak
                                ),
                                total_players=len(room.players)
                            )
                        ),
                        exclude_player_id=player_id,
                        room_manager=room_manager
                    )

        return {
            "success": True,
            "data": {
                "player_id": str(result.player_id),
                "session_token": result.session_token,
                "game_code": result.room_code
            }
        }

    except ValueError as e:
        logger.warning(f"Failed to join game {game_code}: {e}")
        return {
            "success": False,
            "message": str(e)
        }
    except Exception as e:
        logger.error(f"Error joining game {game_code} via REST API: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to join game: {str(e)}"
        }


@app.get("/api/games/{game_code}/status")
async def get_game_status_api(game_code: str):
    """
    REST API endpoint to get the current status of a game
    Returns: {
        "success": bool,
        "data": {
            "game": {
                "room_code": str,
                "status": str,
                "players": list,
                "current_round": dict (optional)
            }
        },
        "message": str (optional)
    }
    """
    try:
        # Get room from room manager
        room = room_manager.get_room(game_code.upper())
        if not room:
            return {
                "success": False,
                "message": f"Game {game_code} not found"
            }

        # Build player list
        players = []
        for player_id, player in room.players.items():
            players.append({
                "player_id": str(player.player_id),
                "username": player.username,
                "score": player.score,
                "streak": player.streak,
                "is_host": player.player_id == room.host_player_id,
                "is_ready": False  # MVP: no ready status yet
            })

        # Build game data
        status_str = room.state.value if hasattr(room.state, 'value') else str(room.state).lower()
        game_data = {
            "room_code": room.room_code,
            "status": status_str,
            "players": players
        }

        # Add current round info if game is running
        if status_str.upper() == "RUNNING" and hasattr(room, 'current_round_state') and room.current_round_state:
            game_data["current_round"] = {
                "round_number": room.round_index + 1,
                "numbers": room.problems[room.round_index].numbers if room.round_index < len(room.problems) else [],
                "time_remaining": 30  # TODO: Calculate actual time remaining
            }

        return {
            "success": True,
            "data": {
                "game": game_data
            }
        }

    except Exception as e:
        logger.error(f"Error getting game status for {game_code}: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to get game status: {str(e)}"
        }


@app.post("/api/games/{game_code}/start")
async def start_game_api(game_code: str, player_id: str):
    """
    REST API endpoint to start a game (host only)
    Query params:
        player_id: str - The player ID attempting to start the game
    Returns: {
        "success": bool,
        "message": str (optional)
    }
    """
    try:
        # Get room
        room = room_manager.get_room(game_code.upper())
        if not room:
            return {
                "success": False,
                "message": f"Game {game_code} not found"
            }

        # Verify the player is the host
        player_uuid = UUID(player_id)
        if room.host_player_id != player_uuid:
            return {
                "success": False,
                "message": "Only the host can start the game"
            }

        # Get the player's session token (from room)
        player = room.players.get(player_uuid)
        if not player:
            return {
                "success": False,
                "message": "Player not found in room"
            }

        # Start the game through game state manager
        await game_state_manager.start_game(
            game_code.upper(),
            player_uuid,
            player.session_token
        )

        logger.info(f"Game {game_code} started via REST API by {player_id}")

        return {
            "success": True,
            "message": "Game started successfully"
        }

    except ValueError as e:
        logger.warning(f"Failed to start game {game_code}: {e}")
        return {
            "success": False,
            "message": str(e)
        }
    except Exception as e:
        logger.error(f"Error starting game {game_code} via REST API: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to start game: {str(e)}"
        }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")