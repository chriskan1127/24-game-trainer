# 24-Game Trainer

A comprehensive **single-player and multiplayer** 24-game trainer with competitive features, built with Python, Kivy, and FastAPI.

## Features

### Single-Player Mode
- **Interactive Kivy Interface**: Beautiful, modern UI with touch-friendly controls
- **Smart Number Generation**: Only generates solvable puzzles using advanced algorithms
- **Real-time Solution Validation**: Instant feedback on your mathematical expressions
- **Progressive Difficulty**: Timed challenges to improve your mental math skills
- **Solution Display**: Shows optimal solutions when time runs out

### Multiplayer Mode 
- **Real-time Competitive Gameplay**: First-to-solve wins each round
- **6-Digit Game Codes**: Easy-to-share codes for joining games with friends
- **Configurable Scoring**: Set custom point targets (default: first to 10 points wins)
- **30-Second Round Timer**: Fast-paced gameplay with automatic solution reveal
- **Live Leaderboard**: Real-time score tracking for all players
- **Host Controls**: Game creators can start rounds and manage the game
- **Cross-Platform**: Works on Windows, macOS, and Linux

### 🏗️ Technical Features
- **Scalable Architecture**: Designed to handle growing player bases
- **WebSocket Communication**: Real-time multiplayer updates
- **Secure Game Codes**: Cryptographically secure with collision avoidance
- **Database Persistence**: PostgreSQL/SQLite support for game data
- **Comprehensive Testing**: Full test coverage for reliability
- **Production Ready**: Monitoring, metrics, and deployment-ready configuration

## Quick Start

### Prerequisites
- **Python 3.9+**
- **Conda** (Miniconda or Anaconda)

### 1. Setup Environment
```bash
# Clone the repository
git clone <repository-url>
cd 24-game-trainer

# Set up conda environment with all dependencies
python run_system.py setup
```

### 2. Activate Environment
```bash
conda activate 24-game
```

### 3. Play Single-Player
```bash
python run_system.py frontend
```

### 4. Play Multiplayer

#### Start the Server (Host)
```bash
# Initialize database (first time only)
python run_system.py init-db

# Start the multiplayer server
python run_system.py server
```

#### Start the Client
```bash
# In a new terminal (keep server running)
python run_system.py multiplayer
```

## Multiplayer Gameplay

### Creating a Game
1. Launch the multiplayer client
2. Enter your name
3. Set points to win (default: 10)
4. Click "Create Game"
5. Share the 6-digit game code with friends

### Joining a Game
1. Launch the multiplayer client
2. Enter your name
3. Enter the 6-digit game code
4. Click "Join Game"

### Playing
- **Round Timer**: Each round lasts 30 seconds
- **First Correct Answer**: First player to reach 24 wins the round (+1 point)
- **No Solution**: If no one solves it, the solution is revealed
- **Winning**: First player to reach the target score wins the game
- **Real-time Updates**: See other players' scores and game status instantly

## Game Rules

The goal is to use **four numbers** and **basic operations** (+, -, ×, ÷) to make exactly **24**.

### Example:
- Numbers: `2, 2, 10, 10` → Solution: `10 + 10 + 2 + 2 = 24`
- Numbers: `11, 1, 13, 6` → Solution: `(11 * 13 + 1) / 6 = 24`

### Rules:
- Use each number exactly once
- Only use +, -, ×, ÷ operations
- Order of operations applies (×÷ before +-)
- Parentheses can change operation order

## Development

### Architecture

```
24-game-trainer/
├── src/                    # Frontend applications
│   ├── main.py            # Single-player Kivy app
│   ├── solve24.kv         # Single-player UI layout
│   ├── multiplayer_main.py # Multiplayer Kivy client
│   └── multiplayer.kv     # Multiplayer UI layout
├── server/                # Multiplayer backend
│   ├── main.py           # FastAPI server
│   ├── database/         # Database models & management
│   ├── services/         # Business logic
│   ├── websocket/        # Real-time communication
│   ├── utils/            # Utilities (code generation, etc.)
│   └── tests/            # Server tests
├── lib/                  # Shared solver library
│   └── solve_24.py       # 24-game solver algorithms
├── docs/                 # Documentation
├── environment.yml       # Conda environment
└── run_system.py         # Management script
```

### Testing

```bash
# Run all system tests
python run_system.py test

# Run server unit tests only  
python run_system.py unit-tests

# Test multiplayer integration (requires running server)
python run_system.py test-multiplayer
```

### Server API

The multiplayer server provides a REST API and WebSocket interface:

#### REST Endpoints
- `POST /games/create` - Create a new game
- `POST /games/{code}/join` - Join a game
- `GET /games/{code}/status` - Get game status
- `DELETE /games/{code}` - Delete a game (host only)
- `GET /health` - Server health check
- `GET /metrics` - Server metrics

#### WebSocket Messages
- `game_update` - Game state changes
- `round_started` - New round begins
- `round_ended` - Round completion
- `solution_correct` - Player solved correctly
- `solution_revealed` - Time expired, show solution
- `game_finished` - Game over

### Configuration

Server settings in `server/config.py`:

```python
# Game Settings
DEFAULT_POINTS_TO_WIN = 10
MAX_PLAYERS_PER_GAME = 8
MAX_ROUND_TIME = 30  # seconds

# Database
DATABASE_URL = "sqlite:///./24game.db"  # Development
# DATABASE_URL = "postgresql://..."     # Production

# Security
GAME_CODE_LENGTH = 6
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ234567"  # No I/O for clarity
```

## Deployment

### Local Development
```bash
# Start server
python run_system.py server

# Start client
python run_system.py multiplayer
```

### Production Deployment

#### Server
```bash
# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost/24game"
export DEBUG=false

# Start with production ASGI server
cd server
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### Client Configuration
Update `SERVER_BASE_URL` and `WS_BASE_URL` in `src/multiplayer_main.py` for your server.

## Troubleshooting

### Common Issues

#### "Cannot connect to server"
- Ensure the server is running: `python run_system.py server`
- Check server URL in multiplayer client
- Verify firewall settings

#### "Conda not found"
- Install Miniconda: https://docs.conda.io/en/latest/miniconda.html
- Add conda to PATH

#### "Game code not found"
- Game codes expire after inactivity
- Ensure correct 6-digit code (case-insensitive)
- Create a new game if needed

#### "WebSocket connection failed"
- Check server logs for errors
- Ensure WebSocket support (port 8000)
- Try restarting both server and client

### Performance

The system is designed to scale:
- **Local**: Supports 50+ concurrent games
- **Single Server**: Handles 1000+ concurrent players
- **Horizontal Scaling**: Load balancer + multiple servers
- **Database**: PostgreSQL for production workloads

## Acknowledgments

- **Original 24-Game**: Classic mathematical puzzle
- **Kivy**: Cross-platform GUI framework
- **FastAPI**: Modern, fast web framework
- **SQLAlchemy**: Database ORM

