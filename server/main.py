import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List
import uuid

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
import uvicorn
from fastapi.responses import RedirectResponse

from database.database import get_db, init_db
from database.models import Game, Player, GameResult, GameStatus
from services.room_service import room_service
from services.solver_service import solver_service
from websocket.connection_manager import connection_manager
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="24-Game Multiplayer Server",
    description="Real-time multiplayer server for the 24-game with competitive scoring",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for API requests/responses
class CreateGameRequest(BaseModel):
    host_username: str = Field(..., min_length=1, max_length=50)
    target: int = Field(default=24, ge=1, le=100)
    time_limit: int = Field(default=30, ge=10, le=300)
    max_players: int = Field(default=10, ge=2, le=50)
    points_to_win: int = Field(default=10, ge=1, le=100)

class CreateGameResponse(BaseModel):
    game_code: str
    host_player_id: str
    game: Dict[str, Any]

class JoinGameRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)

class JoinGameResponse(BaseModel):
    player_id: str
    game: Dict[str, Any]

class GameStatusResponse(BaseModel):
    game: Dict[str, Any]
    players: List[Dict[str, Any]]
    player_count: int
    is_full: bool
    can_start: bool

class ReadyStatusRequest(BaseModel):
    is_ready: bool

class SolutionRequest(BaseModel):
    solution: List[Any]

class GameResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)

# Background task for cleanup
async def cleanup_task():
    """Background task to clean up inactive games."""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            
            # Get database session
            db_gen = get_db()
            db = next(db_gen)
            
            try:
                room_service.cleanup_inactive_games(db)
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")

@app.on_event("startup")
async def startup_event():
    """Initialize database and start background tasks."""
    try:
        init_db()
        logger.info("Database initialized")
        
        # Start cleanup task
        asyncio.create_task(cleanup_task())
        logger.info("Background tasks started")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise

# API Routes
@app.get("/")
async def root():
    """Redirect to API documentation."""
    return RedirectResponse(url="/docs")

@app.post("/api/games/create", response_model=GameResponse)
async def create_game(request: CreateGameRequest, db: Session = Depends(get_db)):
    """Create a new game room."""
    try:
        success, message, game = room_service.create_game(
            db=db,
            host_username=request.host_username,
            target=request.target,
            time_limit=request.time_limit,
            max_players=request.max_players,
            points_to_win=request.points_to_win
        )
        
        if success and game:
            return GameResponse(
                success=True,
                message=message,
                data={
                    "game_code": game.code,
                    "host_id": game.host_id,
                    "game": game.to_dict()
                }
            )
        else:
            raise HTTPException(status_code=400, detail=message)
            
    except Exception as e:
        logger.error(f"Error creating game: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/games/{game_code}/join", response_model=GameResponse)
async def join_game(game_code: str, request: JoinGameRequest, db: Session = Depends(get_db)):
    """Join an existing game."""
    try:
        success, message, player_id = room_service.join_game(
            db=db,
            game_code=game_code.upper(),
            username=request.username
        )
        
        if success and player_id:
            # Get updated game status
            game = room_service.get_game_status(db, game_code.upper())
            
            return GameResponse(
                success=True,
                message=message,
                data={
                    "player_id": player_id,
                    "game": game.to_dict() if game else None
                }
            )
        else:
            raise HTTPException(status_code=400, detail=message)
            
    except Exception as e:
        logger.error(f"Error joining game: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/games/{game_code}/status", response_model=GameResponse)
async def get_game_status(game_code: str, db: Session = Depends(get_db)):
    """Get current game status."""
    try:
        game = room_service.get_game_status(db, game_code.upper())
        
        if game:
            return GameResponse(
                success=True,
                message="Game status retrieved",
                data={"game": game.to_dict()}
            )
        else:
            raise HTTPException(status_code=404, detail="Game not found")
            
    except Exception as e:
        logger.error(f"Error getting game status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/games/{game_code}/start", response_model=GameResponse)
async def start_game(game_code: str, player_id: str, db: Session = Depends(get_db)):
    """Start a game (host only)."""
    try:
        success, message, game = room_service.start_game(
            db=db,
            game_code=game_code.upper(),
            player_id=player_id
        )
        
        if success and game:
            # Notify all players via WebSocket
            await connection_manager.broadcast_to_game(
                game_code.upper(),
                {
                    "type": "game_started",
                    "game": game.to_dict()
                }
            )
            
            return GameResponse(
                success=True,
                message=message,
                data={"game": game.to_dict()}
            )
        else:
            raise HTTPException(status_code=400, detail=message)
            
    except Exception as e:
        logger.error(f"Error starting game: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/games/{game_code}")
async def delete_game(game_code: str, player_id: str, db: Session = Depends(get_db)):
    """Delete a game (host only)."""
    try:
        success, message = room_service.leave_game(
            db=db,
            game_code=game_code.upper(),
            player_id=player_id
        )
        
        if success:
            # Notify all players that game was deleted
            await connection_manager.broadcast_to_game(
                game_code.upper(),
                {
                    "type": "game_deleted",
                    "message": "Game was deleted by host"
                }
            )
            
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=400, detail=message)
            
    except Exception as e:
        logger.error(f"Error deleting game: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        
        # Get basic metrics
        active_games = db.query(Game).filter(
            Game.status.in_([GameStatus.WAITING.value, GameStatus.IN_PROGRESS.value])
        ).count()
        
        active_players = db.query(Player).filter(Player.is_connected == True).count()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "connected",
            "active_games": active_games,
            "active_players": active_players,
            "websocket_connections": len(connection_manager.active_connections)
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")

@app.get("/api/metrics")
async def get_metrics(db: Session = Depends(get_db)):
    """Get server metrics."""
    try:
        active_games = db.query(Game).filter(
            Game.status.in_([GameStatus.WAITING.value, GameStatus.IN_PROGRESS.value])
        ).count()
        
        total_games = db.query(Game).count()
        total_results = db.query(GameResult).count()
        active_players = db.query(Player).filter(Player.is_connected == True).count()
        
        return {
            "active_games": active_games,
            "total_games_created": total_games,
            "total_solutions_submitted": total_results,
            "active_players": active_players,
            "websocket_connections": len(connection_manager.active_connections)
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# WebSocket endpoint for real-time communication
@app.websocket("/ws/{game_code}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_code: str, player_id: str):
    """WebSocket endpoint for real-time game communication."""
    game_code = game_code.upper()
    
    await connection_manager.connect(websocket, game_code, player_id)
    
    try:
        # Get database session
        db_gen = get_db()
        db = next(db_gen)
        
        try:
            # Verify player exists in game
            player = db.query(Player).filter(Player.id == player_id).first()
            if not player or player.game.code != game_code:
                await websocket.close(code=4003, reason="Player not found in game")
                return
            
            # Mark player as connected
            player.is_connected = True
            player.last_activity = datetime.utcnow()
            db.commit()
            
            # Send current game state
            game = player.game
            await websocket.send_json({
                "type": "game_state",
                "game": game.to_dict()
            })
            
            # Handle WebSocket messages
            while True:
                data = await websocket.receive_json()
                
                await handle_websocket_message(db, websocket, game_code, player_id, data)
                
        finally:
            db.close()
            
    except WebSocketDisconnect:
        logger.info(f"Player {player_id} disconnected from game {game_code}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Mark player as disconnected
        db_gen = get_db()
        db = next(db_gen)
        try:
            player = db.query(Player).filter(Player.id == player_id).first()
            if player:
                player.is_connected = False
                db.commit()
        except Exception as e:
            logger.error(f"Error marking player as disconnected: {e}")
        finally:
            db.close()
        
        connection_manager.disconnect(game_code, player_id)

async def handle_websocket_message(db: Session, websocket: WebSocket, game_code: str, player_id: str, data: dict):
    """Handle incoming WebSocket messages."""
    try:
        message_type = data.get("type")
        
        if message_type == "solution_submitted":
            # Handle solution submission
            solution = data.get("solution", [])
            
            success, message, result = room_service.submit_solution(
                db=db,
                game_code=game_code,
                player_id=player_id,
                solution=solution
            )
            
            # Send response to player
            await websocket.send_json({
                "type": "solution_response",
                "success": success,
                "message": message,
                "is_correct": result.is_correct if result else False,
                "is_winner": result.is_winner if result else False,
                "points_awarded": result.points_awarded if result else 0
            })
            
            if success and result:
                # Broadcast to all players in game
                game = room_service.get_game_status(db, game_code)
                player = db.query(Player).filter(Player.id == player_id).first()
                
                await connection_manager.broadcast_to_game(
                    game_code,
                    {
                        "type": "player_answered",
                        "player_id": player_id,
                        "username": player.username if player else "Unknown",
                        "is_correct": result.is_correct,
                        "is_winner": result.is_winner,
                        "time_taken": result.time_taken,
                        "game": game.to_dict() if game else None
                    },
                    exclude=player_id
                )
                
                # If round ended, broadcast updated game state
                if result.is_winner or game.solution_revealed:
                    await connection_manager.broadcast_to_game(
                        game_code,
                        {
                            "type": "round_ended",
                            "winner": player.username if result.is_winner else None,
                            "solution_revealed": game.solution_revealed,
                            "game": game.to_dict()
                        }
                    )
        
        elif message_type == "ready_status":
            # Handle ready status change
            is_ready = data.get("is_ready", False)
            
            success, message = room_service.set_player_ready(
                db=db,
                game_code=game_code,
                player_id=player_id,
                is_ready=is_ready
            )
            
            if success:
                # Broadcast to all players
                game = room_service.get_game_status(db, game_code)
                player = db.query(Player).filter(Player.id == player_id).first()
                
                await connection_manager.broadcast_to_game(
                    game_code,
                    {
                        "type": "player_ready_changed",
                        "player_id": player_id,
                        "username": player.username if player else "Unknown",
                        "is_ready": is_ready,
                        "game": game.to_dict() if game else None
                    }
                )
        
        elif message_type == "chat_message":
            # Handle chat message (optional feature)
            message_text = data.get("message", "")
            if message_text:
                player = db.query(Player).filter(Player.id == player_id).first()
                
                await connection_manager.broadcast_to_game(
                    game_code,
                    {
                        "type": "chat_message",
                        "player_id": player_id,
                        "username": player.username if player else "Unknown",
                        "message": message_text,
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    exclude=player_id
                )
        
        else:
            logger.warning(f"Unknown message type: {message_type}")
            
    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")
        await websocket.send_json({
            "type": "error",
            "message": "Failed to process message"
        })

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    ) 