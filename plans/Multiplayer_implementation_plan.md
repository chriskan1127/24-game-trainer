# 24-Game Multiplayer Implementation Plan

## Executive Summary

This document breaks down the implementation of the 24-game multiplayer system into atomic, independently buildable components. The system architecture leverages FastAPI + WebSockets for the server and adapts the existing Kivy single-player client for multiplayer functionality.

## System Architecture Overview

The multiplayer system consists of **8 server-side components**, **7 client-side components**, and **3 shared components** that work together to provide synchronized competitive gameplay for up to 4 players per room.

---

## Atomic System Components

### 🌐 Server-Side Components

#### 1. **WebSocket Server (FastAPI)**
**Purpose**: Handle real-time WebSocket connections and route messages  
**Dependencies**: FastAPI, WebSockets, Pydantic schemas  
**Key Responsibilities**:
- Accept WebSocket connections from clients
- Parse incoming JSON messages into Pydantic models
- Route messages to appropriate service handlers
- Manage connection lifecycle (connect/disconnect/error handling)
- Send responses back to clients

**API Contract**: 
- Accepts: `IncomingWSMessage` union (room.create, room.join, game.start, answer.submit)
- Sends: `OutgoingWSMessage` union (room.created, round.start, answer.ack, etc.)

#### 2. **Room Manager**
**Purpose**: Create, manage, and destroy game rooms  
**Dependencies**: Pydantic Room model, Problem Pool Service  
**Key Responsibilities**:
- Generate unique 4-character room codes
- Handle room creation with host assignment
- Manage player joining (max 4 players, duplicate username checks)
- Track room states (LOBBY → RUNNING → FINISHED)
- Initialize games with 10 pre-selected problems
- Handle room cleanup when empty

**Data Structures**:
- `rooms: Dict[RoomCode, Room]` - Active rooms registry
- Room state transitions and validation rules
- Host privileges and room locking mechanism

#### 3. **Game State Manager**
**Purpose**: Control game flow, round progression, and timing  
**Dependencies**: Timer Service, Message Broadcaster, Room Manager  
**Key Responsibilities**:
- Start games when host triggers (validate room has players)
- Manage round phases: COUNTDOWN (3s) → ACTIVE (30s) → RESULTS (6s)  
- Track current round index (0-9 for 10 rounds)
- Coordinate transitions between rounds
- Determine game end conditions and trigger final scoring

**State Transitions**:
```
LOBBY → [host starts] → COUNTDOWN → ACTIVE → RESULTS → COUNTDOWN (next) → ... → FINISHED
```

#### 4. **Player Manager**
**Purpose**: Handle player authentication, scoring, and session management  
**Dependencies**: Room Manager  
**Key Responsibilities**:
- Generate and validate session tokens for players
- Track player scores and streaks within rooms
- Handle player reconnection using room code + username
- Maintain player state (connected/disconnected/last_seen)
- Calculate final leaderboards and rankings

**Player Lifecycle**:
- Join → Authenticate → Play → Disconnect/Reconnect → Leave
- Score tracking: base points (10) + speed bonus (0-5) per correct submission
- One submission per player per round limitation

#### 5. **Problem Pool Service**
**Purpose**: Generate working 24-game problems on-demand for each game  
**Dependencies**: 24-Game Solver (lib/solve_24.py)  
**Key Responsibilities**:
- Generate 10 unique, solvable problems per game dynamically
- Ensure no duplicate problems within a single game (by number multiset)
- Provide problem metadata (numbers, problem_id, canonical solution)
- Use existing solver to validate each generated problem has a solution

**Problem Generation Strategy**:
- Generate problems on-demand when rooms are created
- For each game, iteratively generate working problems until 10 unique ones found
- Deduplication is per-game (not global) to maximize variety across games
- Use single-player solver's "best" solution logic for canonical solutions

#### 6. **Submission Processor**
**Purpose**: Validate and score player answer submissions  
**Dependencies**: Player Manager, 24-Game Solver  
**Key Responsibilities**:
- Receive player submissions with client validation results
- Apply server timestamps for authoritative speed ranking
- Calculate speed bonuses based on time remaining
- Enforce one-submission-per-player-per-round rule
- Log all submissions for debugging and anti-cheat analysis
- Update player scores in real-time

**Scoring Algorithm**:
```python
base_points = 10 if correct else 0
speed_bonus = ceil((time_left / 30.0) * 5) if correct else 0
total_points = base_points + speed_bonus
```

#### 7. **Message Broadcaster**
**Purpose**: Send synchronized messages to all players in a room  
**Dependencies**: WebSocket Server  
**Key Responsibilities**:
- Broadcast round start messages with problems to all room players
- Send countdown notifications simultaneously
- Distribute round results and score updates
- Handle player join/leave notifications
- Manage error message distribution

**Broadcasting Patterns**:
- Room-wide broadcasts (countdown, round start/end)
- Individual acknowledgments (answer.ack)
- Selective broadcasts (player.joined excludes the joining player)

#### 8. **Timer Service**
**Purpose**: Provide precise timing for round phases  
**Dependencies**: asyncio event loop  
**Key Responsibilities**:
- Schedule countdown timers (3 seconds)
- Track active round duration (30 seconds)
- Manage results display timing (6 seconds)
- Trigger phase transitions in Game State Manager
- Handle timer cancellation for game interruptions

**Timing Precision**:
- Use asyncio.create_task for precise scheduling
- Server timestamp all timing events for client synchronization
- Handle timer cleanup on game end or disconnections

---

### 📱 Client-Side Components

#### 1. **WebSocket Client**
**Purpose**: Manage WebSocket connection and communication with server  
**Dependencies**: websockets library, asyncio  
**Key Responsibilities**:
- Establish and maintain WebSocket connection to server
- Send Pydantic message objects as JSON
- Receive and parse server messages
- Handle connection errors, reconnection logic
- Provide async interface for UI components

**Connection Management**:
- Automatic reconnection with exponential backoff
- Connection state tracking (connecting/connected/disconnected)
- Message queuing during disconnection periods

#### 2. **Multiplayer Game UI**
**Purpose**: New Kivy screens for multiplayer-specific interactions  
**Dependencies**: Kivy framework, existing COLORS palette  
**Key Responsibilities**:
- Room creation screen (generate code, wait for players)
- Room joining screen (enter code, enter username)
- Waiting lobby screen (show connected players, host start button)
- Player list display with real-time updates
- Connection status indicators

**New Screens**:
- `RoomCreateScreen` - Host creates room, shows room code
- `RoomJoinScreen` - Players enter room code and username
- `LobbyScreen` - Pre-game waiting area with player list
- Screen transitions based on WebSocket message events

#### 3. **Synchronized Game Screen**
**Purpose**: Adapt existing Solve24Game for multiplayer with server synchronization  
**Dependencies**: Existing single-player game components, Message Handler  
**Key Responsibilities**:
- Display server-provided problems (not randomly generated)
- Show countdown timer synchronized with server
- Handle round phase transitions (countdown → active → results)
- Display other players' scores and progress
- Disable local timer, use server-driven timing only

**Key Adaptations**:
```python
# Replace local problem generation with server problems
def set_server_problem(self, numbers: List[int]):
    self.number1.adjust_value(numbers[0])
    # ... set all numbers from server

# Replace local timer with server countdown
def handle_countdown_start(self, countdown_seconds: int, server_time: datetime):
    # Sync with server time, show countdown UI
```

#### 4. **Message Handler**
**Purpose**: Process incoming WebSocket messages and update UI  
**Dependencies**: Pydantic schemas, all UI components  
**Key Responsibilities**:
- Parse incoming server messages by type
- Route messages to appropriate UI components
- Update game state based on server messages
- Handle error messages with user-friendly display
- Coordinate UI transitions based on game flow

**Message Routing**:
```python
async def handle_message(self, message: OutgoingWSMessage):
    if message.type == "round.start":
        self.game_screen.handle_round_start(message.payload)
    elif message.type == "round.end":
        self.scoreboard.show_results(message.payload)
    # ... handle all message types
```

#### 5. **Submission Manager**
**Purpose**: Handle answer submissions with timing and validation  
**Dependencies**: WebSocket Client, 24-Game Solver  
**Key Responsibilities**:
- Validate submissions using existing single-player solver
- Add client timestamps to submissions
- Enforce one-submission-per-round limit
- Queue submissions during network issues
- Provide immediate feedback while awaiting server acknowledgment

**Submission Flow**:
1. Player completes answer → local validation
2. If valid → send to server with timestamp
3. Show "submitting..." feedback
4. Receive server ack → update UI accordingly

#### 6. **Scoreboard UI**
**Purpose**: Display round results and final standings  
**Dependencies**: Kivy widgets, COLORS palette  
**Key Responsibilities**:
- Show round results screen (6 seconds)
- Display who got the answer correct with speed rankings
- Show canonical solution for the round
- Display updated scores and leaderboard
- Final game results with winner announcement

**Scoreboard Features**:
- Real-time score updates during results phase
- Speed bonus visualization (time left → bonus points)
- Player ranking with score breakdown
- Canonical solution display with clear formatting

#### 7. **Reconnection Manager**
**Purpose**: Handle disconnections and seamless rejoin  
**Dependencies**: WebSocket Client, local storage for session data  
**Key Responsibilities**:
- Detect connection loss and attempt reconnection
- Store room code, username, and session token locally
- Automatically rejoin room on reconnect
- Restore game state from server on successful rejoin
- Handle host disconnection scenarios

**Reconnection Strategy**:
- Store essential session data in local storage
- Retry connection with exponential backoff
- Send stored session token on reconnect for state restoration
- Update UI based on current game state received from server

---

### 🔗 Shared Components

#### 1. **Message Protocol (Pydantic Schemas)**
**Purpose**: Type-safe contract between client and server  
**Status**: Already implemented in `pydantic_schemas.py`  
**Key Features**:
- Complete WebSocket message definitions
- Validation and serialization for all data structures
- Room, Player, Problem, and Submission models
- Error handling and response types

#### 2. **24-Game Solver**
**Purpose**: Validate problems and find canonical solutions  
**Status**: Already implemented in `lib/solve_24.py`  
**Usage**:
- Server: Generate problem pool, validate solutions
- Client: Local submission validation for immediate feedback
- Shared logic ensures consistency between client/server validation

#### 3. **Game Configuration**
**Purpose**: Fixed settings and constants for MVP  
**Implementation**: Constants module  
**Settings**:
```python
MVP_SETTINGS = {
    "rounds": 10,
    "time_per_round_seconds": 30,
    "countdown_seconds": 3,
    "results_display_seconds": 6,
    "max_players_per_room": 4,
    "base_points": 10,
    "max_speed_bonus": 5
}
```

---

## Component Interactions & Data Flow

### 🚀 Game Start Flow
```
1. Client (Room UI) → WebSocket Client → WebSocket Server → Room Manager
2. Room Manager ← Problem Pool Service (10 problems selected)
3. Room Manager → Message Broadcaster → All Clients (room.joined)
4. Host starts → Game State Manager → Timer Service (start countdown)
5. Timer Service → Message Broadcaster → All Clients (countdown.start)
```

### ⚡ Round Execution Flow
```
1. Timer Service (countdown ends) → Game State Manager → Message Broadcaster
2. All Clients receive (round.start) with problem
3. Players solve → Submission Manager → WebSocket Client → Submission Processor
4. Submission Processor → Player Manager (update scores) → Message Broadcaster
5. Timer Service (round ends) → Game State Manager → Message Broadcaster (round.end)
6. All Clients display results (6s) → next round or game end
```

### 🔄 Critical Data Synchronization Points
1. **Room State**: Room Manager ↔ All connected clients
2. **Round Timing**: Timer Service ↔ Game State Manager ↔ All clients  
3. **Scoring**: Submission Processor ↔ Player Manager ↔ All clients
4. **Problem Distribution**: Problem Pool Service → Game State Manager → All clients
5. **Player Management**: Player Manager ↔ Room Manager ↔ All clients

---

## Implementation Priority & Dependencies

### Phase 1: Core Infrastructure
1. **WebSocket Server** (no dependencies)
2. **Message Protocol Integration** (use existing pydantic_schemas.py)
3. **Room Manager** (depends on WebSocket Server)
4. **Player Manager** (depends on Room Manager)

### Phase 2: Game Logic
5. **Problem Pool Service** (depends on 24-Game Solver)  
6. **Game State Manager** (depends on Room Manager, Player Manager)
7. **Timer Service** (depends on Game State Manager)
8. **Submission Processor** (depends on Player Manager, 24-Game Solver)
9. **Message Broadcaster** (depends on WebSocket Server)

### Phase 3: Client Adaptation  
10. **WebSocket Client** (no dependencies)
11. **Message Handler** (depends on WebSocket Client)
12. **Multiplayer Game UI** (depends on Message Handler)
13. **Synchronized Game Screen** (depends on existing game, Message Handler)
14. **Submission Manager** (depends on WebSocket Client)
15. **Scoreboard UI** (depends on Message Handler)
16. **Reconnection Manager** (depends on WebSocket Client)

---

## Testing Strategy

### Unit Testing
- Each component with isolated tests
- Mock dependencies for independent testing
- Pydantic schema validation tests
- Timer precision and game flow tests

### Integration Testing
- Client-server message flow
- Multi-player room scenarios
- Timing synchronization tests
- Reconnection and error recovery

### Load Testing
- Multiple concurrent rooms
- Network latency simulation
- Connection drop/recovery scenarios
- Performance under concurrent load

---

## Risk Mitigation

### High-Risk Components
1. **Timer Service**: Precise timing is critical for fairness
2. **WebSocket Connection Management**: Network issues can break synchronization
3. **Game State Manager**: Complex state transitions need careful testing
4. **Submission Processor**: Race conditions in submission handling

### Mitigation Strategies
- Comprehensive integration tests for timing-critical components
- Robust error handling and graceful degradation
- Detailed logging for debugging multiplayer issues
- Client-side validation as backup for network issues

---

## Success Metrics

### Technical Metrics
- Sub-100ms message round-trip time
- 99% message delivery success rate
- Support for 4 concurrent players per room
- Successful synchronization across all clients

### User Experience Metrics
- Seamless room joining and game start
- Fair and accurate scoring
- Intuitive multiplayer UI/UX
- Reliable reconnection experience

---

This implementation plan provides a clear roadmap for building the multiplayer 24-game system as atomic, independently testable components with well-defined interactions and data flows.