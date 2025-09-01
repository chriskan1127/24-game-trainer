# 24-Game Multiplayer Server

A scalable, real-time multiplayer server for the 24-game built with FastAPI, WebSockets, and SQLAlchemy.

## Features

- **Real-time Multiplayer**: WebSocket-based communication for instant game updates
- **6-Digit Game Codes**: Kahoot-style room codes for easy game joining
- **Secure Code Generation**: Cryptographically secure game codes with collision avoidance
- **Solution Validation**: Integration with Python 24-game solver for accurate validation
- **Scalable Architecture**: Designed to handle growing player base
- **Comprehensive Testing**: Unit and integration tests for reliability
- **Monitoring & Metrics**: Built-in health checks and performance monitoring

## Quick Start

### Installation

#### Option 1: Using Conda (Recommended)

From the **root directory** of the project:

1. Create and activate the conda environment:
```bash
conda env create -f environment.yml
conda activate 24-game
```

#### Option 2: Using pip

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Initialize and Start

1. Navigate to the server directory:
```bash
cd server
```

2. Initialize database:
```bash
python -c "from database.database import init_db; init_db()"
```

3. Start the server:
```bash
python start_server.py
```

The server will start on `http://localhost:8000` by default.

### Configuration

Copy `.env.example` to `.env` and modify as needed:

```bash
# Basic configuration
HOST=localhost
PORT=8000
DEBUG=true
ENVIRONMENT=development
DATABASE_URL=sqlite:///./game_server.db
```

## Testing All Systems

From the **root directory**, run the comprehensive test suite:

```bash
python test_all_systems.py
```

This will test:
- Python environment and core libraries
- Frontend dependencies (Kivy)
- Backend dependencies (FastAPI, etc.)
- Unit tests
- Code quality (linting)
- Server startup and API endpoints
- Game creation and management

## API Endpoints

### Game Management

- `POST /api/games/create` - Create a new game
- `POST /api/games/{code}/join` - Join an existing game
- `GET /api/games/{code}/status` - Get game status
- `POST /api/games/{code}/start` - Start a game (host only)
- `DELETE /api/games/{code}` - Delete a game (host only)

### System

- `GET /api/health` - Health check
- `GET /api/metrics` - Server metrics

### WebSocket

- `WS /ws/{game_code}/{player_id}` - Real-time game communication

## WebSocket Message Types

### Client to Server

```json
{
  "type": "solution_submitted",
  "solution": [...],
  "time_taken": 15
}
```

```json
{
  "type": "ready_status",
  "is_ready": true
}
```

### Server to Client

```json
{
  "type": "game_started",
  "game": {...}
}
```

```json
{
  "type": "solution_submitted",
  "player_id": "...",
  "username": "...",
  "is_correct": true,
  "time_taken": 15
}
```

## Architecture

### Core Components

- **FastAPI Application** (`main.py`): REST API and WebSocket endpoints
- **Database Models** (`database/models.py`): SQLAlchemy models for games, players, results
- **Room Service** (`services/room_service.py`): Game room management logic
- **Solver Service** (`services/solver_service.py`): Integration with 24-game solver
- **Connection Manager** (`websocket/connection_manager.py`): WebSocket connection handling
- **Code Generator** (`utils/code_generator.py`): Secure game code generation

### Database Schema

- **Games**: Store game sessions with codes, status, numbers, and configuration
- **Players**: Track players in games with scores and connection status
- **Game Results**: Store individual solution attempts and scores
- **Server Metrics**: Monitor system performance and usage

## Testing

Run the test suite:

```bash
pytest
```

Run only unit tests (exclude integration tests):

```bash
pytest -m "not integration"
```

Run with coverage:

```bash
pytest --cov=server --cov-report=html
```

## Scaling Considerations

### Phase 1: Single Server (Current Implementation)
- SQLite database for simplicity
- In-memory WebSocket connections
- Suitable for 100-1000 concurrent users

### Phase 2: Horizontal Scaling (Future)
- PostgreSQL for production database
- Redis for session management and pub/sub
- Load balancer with sticky sessions
- Suitable for 10,000+ concurrent users

### Phase 3: Microservices (Future)
- Separate game logic and connection services
- Message queue for inter-service communication
- Auto-scaling based on demand

## Code Generation Statistics

The system uses a 32-character alphabet (digits + uppercase letters, excluding I/O for clarity):
- **Total combinations**: 32^6 = 1,073,741,824
- **Safe concurrent games**: >10,000 with <1% collision probability
- **Collision handling**: Automatic retry with up to 100 attempts

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | localhost | Server host |
| `PORT` | 8000 | Server port |
| `DEBUG` | true | Debug mode |
| `DATABASE_URL` | sqlite:///./game_server.db | Database connection |
| `MAX_ACTIVE_GAMES` | 1000 | Maximum concurrent games |
| `MAX_PLAYERS_PER_GAME` | 10 | Maximum players per game |
| `DEFAULT_TIME_LIMIT` | 30 | Default game time limit (seconds) |

## Development

### Project Structure

```
server/
├── config.py              # Configuration management
├── main.py                # FastAPI application
├── start_server.py        # Development server script
├── environment.yml        # Conda environment file
├── requirements.txt       # Pip requirements file
├── database/
│   ├── database.py        # Database setup and session management
│   └── models.py          # SQLAlchemy models
├── services/
│   ├── room_service.py    # Game room management
│   └── solver_service.py  # Solution validation
├── websocket/
│   └── connection_manager.py  # WebSocket management
├── utils/
│   └── code_generator.py  # Game code generation
└── tests/
    ├── test_code_generator.py
    └── test_solver_service.py
```

### Environment Management

#### Conda Environment
```bash
# Create environment
conda env create -f environment.yml

# Activate environment
conda activate 24-game

# Update environment
conda env update -f environment.yml

# Export current environment
conda env export > environment.yml

# Remove environment
conda env remove -n 24-game
```

#### Virtual Environment (Alternative)
```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Deactivate
deactivate
```

### Adding New Features

1. **New API Endpoints**: Add to `main.py` with proper error handling
2. **Database Changes**: Update models in `database/models.py`
3. **Business Logic**: Add to appropriate service in `services/`
4. **WebSocket Messages**: Update connection manager and document message types
5. **Tests**: Add comprehensive tests for new functionality

## Monitoring

### Health Check
```bash
curl http://localhost:8000/api/health
```

### Metrics
```bash
curl http://localhost:8000/api/metrics
```

### Logs
The server provides structured logging with different levels:
- INFO: General operations
- WARNING: Recoverable issues
- ERROR: Serious problems
- DEBUG: Detailed debugging (debug mode only)

## Production Deployment

### Database Migration
For production, use PostgreSQL:

```bash
# Update DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@localhost/gamedb

# Install PostgreSQL adapter (included in environment.yml)
# conda install postgresql psycopg2

# Initialize database
python -c "from database.database import init_db; init_db()"
```

### Security Considerations
- Change `SECRET_KEY` to a secure random value
- Use HTTPS in production
- Implement rate limiting
- Monitor for abuse patterns
- Validate all user inputs

### Performance Optimization
- Use connection pooling for database
- Implement caching for frequently accessed data
- Monitor WebSocket connection limits
- Set up proper logging and monitoring

## Contributing

1. Follow the existing code style and patterns
2. Add comprehensive tests for new features
3. Update documentation for API changes
4. Ensure backward compatibility where possible

## License

[Include appropriate license information] 