# 24-Game Multiplayer Server

A FastAPI + WebSocket server for multiplayer 24-game competitions, built as the backend for the 24-Game Trainer application.

## Overview

This server enables real-time multiplayer 24-game competitions with up to 4 players per room. It features:

- **Room-based gameplay** with 4-character room codes
- **Real-time WebSocket communication** for synchronized gameplay
- **Pre-validated problem pool** of 100+ solvable 24-game puzzles
- **Scoring system** with base points + speed bonuses
- **Complete game state management** with countdown, active, and results phases
- **Session-based authentication** with reconnection support

## Architecture

The server is built using a modular service architecture:

- **Main Server** (`main.py`) - FastAPI application with WebSocket endpoints
- **Room Manager** (`room_manager.py`) - Handles room creation, joining, and lifecycle
- **Game State Manager** (`game_state_manager.py`) - Controls game flow and round progression
- **Player Manager** (`player_manager.py`) - Manages player scoring and session tracking
- **Problem Pool Service** (`problem_pool_service.py`) - Maintains pre-validated 24-game problems
- **Submission Processor** (`submission_processor.py`) - Validates and scores player submissions
- **Message Broadcaster** (`message_broadcaster.py`) - Handles WebSocket message distribution
- **Timer Service** (`timer_service.py`) - Provides precise timing for game phases

## Game Flow

1. **Lobby Phase**: Host creates room, players join using room code
2. **Game Start**: Host starts game (requires ≥2 players)
3. **Countdown Phase**: 3-second countdown before each round
4. **Active Phase**: 30 seconds for players to solve the problem
5. **Results Phase**: 6 seconds showing round results and scores
6. **Game End**: After 10 rounds, final leaderboard is displayed

## Installation & Setup

### Requirements

- Python 3.8+
- Dependencies listed in `requirements.txt`

### Installation

1. Navigate to the server directory:
```bash
cd server
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start the server:
```bash
python main.py
```

The server will start on `http://localhost:8000`

## API Endpoints

### HTTP Endpoints

- `GET /health` - Health check endpoint
- `GET /stats` - Server statistics (active connections, rooms, players)

### WebSocket Endpoint

- `WS /ws/{room_code}/{player_id}` - Main WebSocket connection for gameplay

## WebSocket Message Protocol

### Client → Server Messages

#### Room Creation
```json
{
  "type": "room.create",
  "payload": {
    "username": "PlayerName"
  }
}
```

#### Room Joining
```json
{
  "type": "room.join",
  "payload": {
    "room_code": "ABCD",
    "username": "PlayerName",
    "session_token": "optional-for-reconnection"
  }
}
```

#### Game Start (Host Only)
```json
{
  "type": "game.start",
  "payload": {
    "room_code": "ABCD",
    "session_token": "host-session-token"
  }
}
```

#### Answer Submission
```json
{
  "type": "answer.submit",
  "payload": {
    "room_code": "ABCD",
    "player_id": "uuid",
    "session_token": "player-session-token",
    "round_index": 0,
    "expression": "player solution",
    "used_numbers": [1, 2, 3, 4],
    "client_eval_value": 24.0,
    "client_eval_is_valid": true,
    "client_timestamp": "2024-01-01T00:00:00Z"
  }
}
```

### Server → Client Messages

#### Room Created
```json
{
  "type": "room.created",
  "payload": {
    "room_code": "ABCD",
    "host_player_id": "uuid",
    "session_token": "session-token",
    "settings": {...}
  }
}
```

#### Countdown Start
```json
{
  "type": "countdown.start",
  "payload": {
    "round_index": 0,
    "countdown_seconds": 3,
    "server_time": "2024-01-01T00:00:00Z"
  }
}
```

#### Round Start
```json
{
  "type": "round.start",
  "payload": {
    "round_index": 0,
    "problem_id": "uuid",
    "numbers": [1, 2, 3, 4],
    "time_limit_seconds": 30,
    "server_time": "2024-01-01T00:00:00Z",
    "round_end": "2024-01-01T00:00:30Z"
  }
}
```

#### Round End
```json
{
  "type": "round.end",
  "payload": {
    "round_index": 0,
    "problem_id": "uuid",
    "canonical_solution": "Solution steps...",
    "players_correct": [...],
    "updated_scores": [...]
  }
}
```

## Testing

### Unit Tests
```bash
cd ../tests
python test_server.py
```

### Integration Tests
```bash
cd ../tests
python test_integration.py
```

## Configuration

### MVP Settings (Fixed)
- **Rounds**: 10 per game
- **Time per Round**: 30 seconds
- **Countdown**: 3 seconds
- **Results Display**: 6 seconds
- **Max Players**: 4 per room
- **Base Points**: 10 for correct answers
- **Speed Bonus**: 0-5 points based on time remaining

### Scoring Formula
```python
base_points = 10  # Fixed for correct answers
speed_bonus = ceil((time_left / 30.0) * 5)  # 0-5 based on time remaining
total_points = base_points + speed_bonus
```

## Development

### Adding New Features

1. **New Message Types**: Add to `pydantic_schemas.py`
2. **New Endpoints**: Add to `main.py`
3. **New Game Logic**: Extend `game_state_manager.py`
4. **New Tests**: Add to `tests/` directory

### Debugging

- Server logs provide detailed information about all operations
- Use `/stats` endpoint to monitor server state
- WebSocket connection issues are logged with context
- All player submissions are logged for analysis

## Production Considerations

### Security
- Add authentication beyond session tokens
- Implement rate limiting on submissions
- Add server-side solution validation
- Use HTTPS/WSS in production

### Scaling
- Add Redis for room state persistence
- Implement horizontal scaling with load balancers
- Add database for player statistics
- Use message queues for reliable delivery

### Monitoring
- Add metrics collection (Prometheus)
- Implement health checks with dependencies
- Add structured logging
- Monitor WebSocket connection counts

## License

This server is part of the 24-Game Trainer project.