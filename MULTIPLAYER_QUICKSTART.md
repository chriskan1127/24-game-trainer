# Multiplayer 24-Game Quick Start Guide

This guide will help you quickly test the new multiplayer functionality.

## Quick Setup (5 minutes)

### 1. Environment Setup
```bash
# Set up environment
python run_system.py setup

# Activate environment  
conda activate 24-game
```

### 2. Initialize Database
```bash
# Initialize database (first time only)
python run_system.py init-db
```

### 3. Test the System
```bash
# Run comprehensive tests
python run_system.py test
```

## Testing Multiplayer

### Option A: Run Demo Script (Automated)

```bash
# Terminal 1: Start server
python run_system.py server

# Terminal 2: Run demo (in new terminal)
python demo_multiplayer.py
```

The demo script will:
- Test server connection
- Create a game with "Alice_Host" 
- Join game with "Bob_Player"
- Show game status and player list
- Connect both players via WebSocket
- Start a competitive round
- Simulate solution submissions
- Display real-time game events

### Option B: Manual Testing with GUI

```bash
# Terminal 1: Start server
python run_system.py server

# Terminal 2: Start first client (Host)
python run_system.py multiplayer

# Terminal 3: Start second client (Player)  
python run_system.py multiplayer
```

#### In the GUI:
1. **Host Client**: 
   - Enter name (e.g., "Alice")
   - Click "Create Game"
   - Note the 6-digit game code
   - Wait for players to join

2. **Player Client**:
   - Enter name (e.g., "Bob")  
   - Enter the game code from step 1
   - Click "Join Game"

3. **Start Playing**:
   - Host clicks "Start Game"
   - Both players see the same 4 numbers
   - First to make 24 wins the round
   - First to target score (default: 10) wins the game

### Option C: API Testing Only

```bash
# Terminal 1: Start server
python run_system.py server

# Terminal 2: Test multiplayer integration
python run_system.py test-multiplayer
```

## What to Expect

### ✅ Working Features
- **6-digit game codes** (e.g., "ABC123")
- **Real-time player joining/leaving**
- **Live score updates**
- **30-second round timer**
- **First-correct-answer scoring**
- **Automatic solution reveal on timeout**
- **Configurable win conditions**
- **Cross-platform support**

### 🎮 Gameplay Flow
1. **Lobby Phase**: Players join, see each other, host starts game
2. **Round Phase**: All players see same numbers, race to solve
3. **Scoring Phase**: First correct answer gets +1 point
4. **Next Round**: Continues until someone reaches target score
5. **Game Over**: Winner announced, option to start new game

### 📊 Real-time Features
- **Player list updates** when someone joins/leaves
- **Score tracking** updates immediately after each round
- **Round timer** counts down for all players
- **Solution reveal** if no one solves in time
- **Game state sync** across all connected clients

## Troubleshooting

### "Cannot connect to server"
```bash
# Make sure server is running
python run_system.py server

# Check server is healthy  
curl http://localhost:8000/health
```

### "Game code not found"
- Game codes expire after inactivity
- Double-check the 6-character code
- Create a new game if needed

### "WebSocket connection failed"
- Restart the server
- Check firewall settings (port 8000)
- Try connecting clients one at a time

### GUI Issues
```bash
# Update environment
python run_system.py update

# Test Kivy installation
python -c "import kivy; print('Kivy OK')"
```

## Architecture Overview

```
┌─────────────────┐    HTTP/WS     ┌─────────────────┐
│  Kivy Client 1  │◄──────────────►│                 │
│   (Host)        │                │  FastAPI Server │
└─────────────────┘                │   + WebSocket   │
                                   │   + Database    │
┌─────────────────┐    HTTP/WS     │                 │
│  Kivy Client 2  │◄──────────────►│                 │
│   (Player)      │                └─────────────────┘
└─────────────────┘
```

### Key Components
- **FastAPI Server**: REST API + WebSocket handling
- **SQLite Database**: Game state and results storage  
- **Kivy Clients**: Cross-platform GUI applications
- **WebSocket Manager**: Real-time communication
- **Game Logic**: Round management and scoring

## Next Steps

Once multiplayer is working:

1. **Scale Testing**: Try with 4-8 players simultaneously
2. **Network Testing**: Test over local network (update SERVER_BASE_URL)
3. **Production Deploy**: Use PostgreSQL and production ASGI server
4. **Customization**: Modify game rules, UI themes, scoring systems

## Support

If you encounter issues:

1. **Check server logs** in the terminal running the server
2. **Run system tests**: `python run_system.py test`
3. **Verify environment**: `conda list` should show all dependencies
4. **Test single-player**: `python run_system.py frontend` should work

The multiplayer system is designed to be robust and handle edge cases gracefully. Happy gaming! 🎮 