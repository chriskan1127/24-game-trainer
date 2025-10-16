# 24-Game Multiplayer Server Architecture Documentation

## Overview

This document provides a comprehensive analysis of the 24-Game multiplayer server implementation. The server is built using FastAPI with WebSocket support to enable real-time multiplayer 24-game competitions following a Kahoot-like synchronous gameplay model.

## High-Level Architecture

The server follows a service-oriented architecture with clear separation of concerns:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   WebSocket     │    │   FastAPI       │    │   Service       │
│   Connections   │◄──►│   Main App      │◄──►│   Layer         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Service Components                            │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│ Room Manager    │ Game State Mgr  │ Player Manager  │ Timer Svc │
├─────────────────┼─────────────────┼─────────────────┼───────────┤
│ Problem Pool    │ Submission      │ Message         │           │
│ Service         │ Processor       │ Broadcaster     │           │
└─────────────────┴─────────────────┴─────────────────┴───────────┘
```

---

## File-by-File Analysis

### 1. main.py - Server Entry Point and WebSocket Handler

**Purpose**: Serves as the main application entry point, coordinates all services, and handles WebSocket connections.

**Key Components**:
- FastAPI application setup with CORS middleware
- Global service instance management
- WebSocket endpoint for real-time communication
- HTTP endpoints for health checks and statistics

**Critical Functions**:

#### `startup_event()`
- **Purpose**: Initialize all services in dependency order during server startup
- **Implementation**: Creates instances of all service classes and establishes cross-service dependencies
- **Dependencies**: Sets up the service dependency chain: ProblemPoolService → MessageBroadcaster → RoomManager → PlayerManager → TimerService → SubmissionProcessor → GameStateManager

#### `websocket_endpoint(websocket, room_code, player_id)`
- **Purpose**: Handle WebSocket connections for individual players
- **Implementation**: Accepts connections, manages connection lifecycle, routes incoming messages
- **Connection Management**: Tracks active connections in global dictionaries mapping connection IDs to WebSockets and player IDs to connection IDs

#### `handle_websocket_message(websocket, connection_id, player_id, message)`
- **Purpose**: Parse and route incoming WebSocket messages to appropriate handlers
- **Implementation**: JSON parsing, message type routing, error handling
- **Message Types**: room.create, room.join, game.start, answer.submit

#### `handle_room_create(websocket, player_id, payload)`
- **Purpose**: Process room creation requests from hosts
- **Implementation**: Validates username, calls room manager to create room, sends success response

#### `handle_room_join(websocket, player_id, payload)`
- **Purpose**: Process room join requests from players
- **Implementation**: Validates inputs, handles both new joins and reconnections, broadcasts player joined event

#### `handle_game_start(websocket, player_id, payload)`
- **Purpose**: Process game start requests from hosts
- **Implementation**: Validates host permissions, delegates to game state manager

#### `handle_answer_submit(websocket, player_id, payload)`
- **Purpose**: Process answer submissions from players
- **Implementation**: Validates submission data, delegates to submission processor, sends acknowledgment

#### `handle_player_disconnect(player_id, room_code)`
- **Purpose**: Clean up when players disconnect
- **Implementation**: Marks player as disconnected, broadcasts player left event
       
---

### 2. game_state_manager.py - Game Flow Controller

**Purpose**: Controls the overall game flow, round progression, and state transitions. Acts as the central coordinator for game timing and phase management.

**Key Responsibilities**:
- Game lifecycle management (start, rounds, end)
- Round phase transitions (countdown → active → results)
- Timer coordination and callbacks
- Score calculation and broadcasting

**Critical Functions**:

#### `start_game(room_code, host_player_id, session_token)`
- **Purpose**: Initiate a multiplayer game session
- **Implementation**: Validates host permissions, checks minimum players (2), transitions room to RUNNING state, resets player scores, starts first round
- **Business Logic**: Enforces game start rules and initializes game state

#### `start_round(room_code)`
- **Purpose**: Begin a new round with countdown phase
- **Implementation**: Validates round index, resets scoring tracking, schedules countdown timer, broadcasts countdown start
- **Flow Control**: Manages progression from one round to the next

#### `handle_countdown_complete(room_code)`
- **Purpose**: Transition from countdown to active play phase
- **Implementation**: Updates round state to ACTIVE, calculates round end time, broadcasts round start with problem, schedules round timer
- **Timing**: Establishes authoritative server timing for the round

#### `handle_round_timeout(room_code)`
- **Purpose**: Handle automatic round ending when time expires
- **Implementation**: Delegates to end_round() method
- **Flow Control**: Ensures rounds end on time regardless of player activity

#### `end_round(room_code)`
- **Purpose**: Conclude active round and display results
- **Implementation**: Transitions to RESULTS phase, calculates player scores, broadcasts round end with leaderboard, schedules results timer
- **Scoring**: Compiles and broadcasts round results and updated scores

#### `handle_results_complete(room_code)`
- **Purpose**: Transition from results display to next round or game end
- **Implementation**: Increments round index, checks for game completion, either starts next round or ends game
- **Flow Control**: Manages overall game progression

#### `end_game(room_code)`
- **Purpose**: Conclude the entire game and show final results
- **Implementation**: Sets room to FINISHED state, cancels timers, generates final leaderboard, broadcasts game end
- **Cleanup**: Ensures proper resource cleanup and final score reporting

#### `force_end_game(room_code, reason)`
- **Purpose**: Emergency game termination for admin/cleanup purposes
- **Implementation**: Cancels all timers, sets finished state, cleans up resources
- **Admin Function**: Provides server admin capability to force-end problematic games

---

### 3. room_manager.py - Room Lifecycle and Player Management

**Purpose**: Manages the creation, joining, and lifecycle of game rooms. Handles player membership and authentication.

**Key Responsibilities**:
- Room creation and unique code generation
- Player joining and session token management
- Room state tracking and validation
- Host transfer and player removal

**Critical Functions**:

#### `generate_room_code()`
- **Purpose**: Create unique 4-character alphanumeric room codes
- **Implementation**: Uses random selection with collision detection
- **Security**: Ensures uniqueness across all active rooms

#### `generate_session_token()`
- **Purpose**: Create secure session tokens for player authentication
- **Implementation**: Uses UUID4 for cryptographically secure tokens
- **Authentication**: Provides session-based auth without requiring user accounts

#### `create_room(host_username, host_player_id)`
- **Purpose**: Create a new game room with specified host
- **Implementation**: Generates room code and session token, creates host player, generates problems via problem pool service, returns creation result
- **Business Logic**: Establishes host privileges and room ownership

#### `join_room(room_code, username, player_id, session_token)`
- **Purpose**: Add a player to an existing room or handle reconnection
- **Implementation**: Validates room exists and has capacity, handles reconnection with existing tokens, prevents username conflicts, creates or updates player record
- **Reconnection Logic**: Supports seamless reconnection using session tokens

#### `validate_session_token(room_code, player_id, session_token)`
- **Purpose**: Verify player authentication for room actions
- **Implementation**: Cross-references session token with player record in room
- **Security**: Prevents unauthorized actions by validating session tokens

#### `is_host(room_code, player_id)`
- **Purpose**: Check if a player has host privileges in a room
- **Implementation**: Compares player ID with room's host player ID
- **Authorization**: Enables host-only actions like starting games

#### `remove_player(room_code, player_id)`
- **Purpose**: Remove a player from a room and handle cleanup
- **Implementation**: Removes player and session token, handles empty room cleanup, transfers host privileges if needed
- **Host Transfer**: Automatically assigns new host when current host leaves

#### `cleanup_inactive_rooms(max_age_hours)`
- **Purpose**: Remove stale rooms to prevent memory leaks
- **Implementation**: Identifies rooms inactive beyond threshold, removes rooms and associated session tokens
- **Resource Management**: Prevents server memory buildup from abandoned rooms

---

### 4. player_manager.py - Player State and Scoring

**Purpose**: Manages player state, scoring calculations, and performance tracking. Handles the business logic for scoring and leaderboards.

**Key Responsibilities**:
- Score calculation with speed bonuses
- Round-based scoring tracking
- Leaderboard generation
- Player statistics and performance metrics

**Critical Functions**:

#### `calculate_score(time_left, time_limit)`
- **Purpose**: Calculate points awarded for correct answers based on speed
- **Implementation**: Base 10 points + speed bonus (0-5 points based on time remaining), uses ceiling function for bonus calculation
- **Business Logic**: Implements the speed-bonus scoring system per design specification
- **Returns**: Tuple of (base_points, speed_bonus)

#### `add_score_to_player(player, base_points, speed_bonus)`
- **Purpose**: Apply calculated score to a player's total and update streak
- **Implementation**: Adds total points to player score, increments streak for correct answers, resets streak on incorrect answers
- **State Management**: Maintains both total score and consecutive correct streak

#### `mark_player_scored_this_round(room_code, player_id)`
- **Purpose**: Track which players have already scored in the current round
- **Implementation**: Maintains room-specific sets of player IDs who have scored
- **Business Logic**: Prevents multiple scoring attempts per player per round

#### `has_player_scored_this_round(room_code, player_id)`
- **Purpose**: Check if a player has already scored in the current round
- **Implementation**: Queries room-specific scoring sets
- **Validation**: Used by submission processor to enforce one-score-per-round rule

#### `reset_round_scoring(room_code)`
- **Purpose**: Clear round scoring tracking when starting a new round
- **Implementation**: Clears the set of players who have scored for the specified room
- **State Management**: Ensures clean state between rounds

#### `get_leaderboard(players)`
- **Purpose**: Generate sorted leaderboard from player scores
- **Implementation**: Creates LeaderboardEntry objects, sorts by score (descending) then username (ascending) for tie-breaking
- **UI Support**: Provides data structure for client leaderboard displays

#### `get_score_updates(players)`
- **Purpose**: Generate current score updates for all players
- **Implementation**: Creates PlayerScoreUpdate objects with current scores and streaks
- **Broadcasting**: Used for round-end score update broadcasts

#### `validate_player_in_room(room_code, player_id, session_token, room_manager)`
- **Purpose**: Verify player belongs to room with valid session
- **Implementation**: Cross-validates player existence in room and session token
- **Security**: Prevents cross-room actions and unauthorized submissions

---

### 5. submission_processor.py - Answer Validation and Scoring

**Purpose**: Processes and validates player answer submissions. Handles the core business logic for accepting/rejecting answers and awarding points.

**Key Responsibilities**:
- Answer submission validation
- Timing-based rejection
- Score calculation and application
- Submission history tracking

**Critical Functions**:

#### `process_submission(room_code, player_id, session_token, round_index, expression, used_numbers, client_eval_value, client_eval_is_valid, client_timestamp, room_manager)`
- **Purpose**: Core submission processing with comprehensive validation
- **Implementation**: Creates submission record, validates session token, checks room state and round timing, validates round index, prevents duplicate scoring, calculates time remaining, validates solution, calculates and awards score
- **Business Logic**: Implements all submission acceptance rules per design specification
- **Returns**: SubmissionRecord with acceptance status and details

#### `_calculate_time_remaining(round_state)`
- **Purpose**: Calculate seconds remaining in the current active round
- **Implementation**: Computes difference between current time and round end time
- **Timing**: Provides authoritative server-side timing for submissions

#### `_validate_solution_server_side(used_numbers, problem_numbers)`
- **Purpose**: Basic server-side validation of number usage
- **Implementation**: Verifies used numbers match problem numbers as multisets, optionally uses solver for additional validation
- **Security**: Provides basic anti-cheat protection (MVP trusts client, but this adds a safety layer)

#### `get_submission_stats(room_code)`
- **Purpose**: Generate statistics about submissions for analysis
- **Implementation**: Calculates acceptance rates, rejection reasons, average time remaining
- **Analytics**: Provides insights into game performance and player behavior

#### `clear_submission_history(room_code)`
- **Purpose**: Clean up submission history for memory management
- **Implementation**: Removes submission records for specified room or all rooms
- **Resource Management**: Prevents memory buildup from submission history

---

### 6. problem_pool_service.py - Problem Generation

**Purpose**: Generates validated 24-game problems on-demand for each game session. Ensures all problems are solvable and unique within a game.

**Key Responsibilities**:
- On-demand problem generation
- Solution validation using the existing solver
- Problem deduplication within games
- Canonical solution formatting

**Critical Functions**:

#### `initialize()`
- **Purpose**: Initialize the service and validate solver functionality
- **Implementation**: Tests solver with known problems to ensure it's working correctly
- **Validation**: Confirms the underlying solver is functional before game start

#### `generate_problems_for_game(count)`
- **Purpose**: Generate a set of unique, solvable problems for a single game
- **Implementation**: Randomly generates number combinations (1-13 range), validates each problem has solutions using solver, prevents duplicates within the game using multiset tracking, formats canonical solutions for display
- **Business Logic**: Ensures each game has unique, solvable problems per design requirements
- **Performance**: Uses retry logic with maximum attempt limits to prevent infinite loops

#### `generate_single_problem()`
- **Purpose**: Generate one validated problem (for testing or special cases)
- **Implementation**: Simplified version of batch generation for single problem
- **Utility**: Useful for testing and debugging

#### `_get_best_solution(solutions)`
- **Purpose**: Select the most appropriate solution from multiple options
- **Implementation**: Prefers solutions without negative intermediate results, falls back to last solution if all have negatives
- **UX**: Ensures displayed solutions are user-friendly and easy to understand

#### `_format_solution(solution_steps)`
- **Purpose**: Convert solver output into human-readable solution text
- **Implementation**: Parses step-by-step solution format, formats with proper mathematical symbols (× for *, ÷ for /)
- **Display**: Creates user-friendly solution displays for round-end broadcasts

#### `validate_problem(numbers)`
- **Purpose**: Check if a set of numbers can form 24
- **Implementation**: Uses solver to validate problem solvability
- **Utility**: Provides validation without full solution generation

---

### 7. message_broadcaster.py - WebSocket Communication

**Purpose**: Handles broadcasting messages to WebSocket connections. Manages the communication layer between game logic and connected clients.

**Key Responsibilities**:
- Room-wide message broadcasting
- Individual player messaging
- Connection management integration
- Broadcast statistics and monitoring

**Critical Functions**:

#### `set_connection_manager(active_connections, player_connections)`
- **Purpose**: Establish references to connection management data structures
- **Implementation**: Stores references to the main.py connection dictionaries
- **Dependency Injection**: Allows the broadcaster to access connection information

#### `broadcast_to_room(room_code, message, room_manager)`
- **Purpose**: Send a message to all players in a specific room
- **Implementation**: Gets room player list, looks up connection IDs for each player, sends message to all connected players, tracks success/failure rates
- **Reliability**: Handles connection failures gracefully and provides delivery statistics

#### `broadcast_to_room_except(room_code, message, room_manager, exclude_player_id)`
- **Purpose**: Broadcast to all room players except one (e.g., don't echo back to sender)
- **Implementation**: Similar to broadcast_to_room but skips the excluded player
- **Use Case**: Prevents echoing messages back to the player who triggered them

#### `send_to_player(player_id, message)`
- **Purpose**: Send a message to a specific individual player
- **Implementation**: Looks up player's connection ID, sends message to their WebSocket
- **Direct Messaging**: Enables targeted communication for player-specific events

#### `send_to_players(player_ids, message)`
- **Purpose**: Send a message to multiple specific players
- **Implementation**: Iterates through player list, sends to each connected player
- **Batch Messaging**: Efficient for sending to subsets of players

#### `get_connected_players_in_room(room_code, room_manager)`
- **Purpose**: Determine which players in a room are currently connected
- **Implementation**: Cross-references room player list with active connections
- **Status Tracking**: Useful for determining who will receive broadcasts

---

### 8. timer_service.py - Precise Game Timing

**Purpose**: Provides precise timing for game phases and events. Manages all time-based game progression using asyncio tasks.

**Key Responsibilities**:
- Countdown timers for round preparation
- Round duration timers for active gameplay
- Results display timers
- Timer cleanup and cancellation

**Critical Functions**:

#### `schedule_countdown(room_code, countdown_seconds)`
- **Purpose**: Schedule a countdown timer before each round starts
- **Implementation**: Creates asyncio task with specified duration, calls game state manager when complete, handles cancellation gracefully
- **Flow Control**: Provides the transition from round end to next round start
- **Returns**: Timer ID for potential cancellation

#### `schedule_round_timer(room_code, round_duration)`
- **Purpose**: Schedule the main round timer for active gameplay
- **Implementation**: Creates asyncio task for round duration, triggers round timeout in game state manager
- **Timing**: Provides authoritative round ending regardless of player activity
- **Business Logic**: Ensures rounds end on time per game rules

#### `schedule_results_timer(room_code, results_duration)`
- **Purpose**: Schedule timer for results display phase
- **Implementation**: Creates asyncio task for results display period, triggers transition to next round or game end
- **UX**: Ensures players have time to see round results before continuing

#### `schedule_custom_timer(name, duration, callback)`
- **Purpose**: Schedule arbitrary timers with custom callbacks
- **Implementation**: Creates asyncio task with custom callback execution, handles both sync and async callbacks
- **Extensibility**: Allows for future custom timing needs

#### `cancel_timer(timer_id)`
- **Purpose**: Cancel a specific timer by its ID
- **Implementation**: Cancels asyncio task and removes from tracking
- **Control**: Enables manual timer cancellation when needed

#### `cancel_room_timers(room_code)`
- **Purpose**: Cancel all timers associated with a specific room
- **Implementation**: Finds all timers matching room code pattern, cancels each one
- **Cleanup**: Essential for proper room cleanup when games end or are force-ended

#### `cleanup()`
- **Purpose**: Cancel all active timers during server shutdown
- **Implementation**: Cancels all tracked asyncio tasks, waits for graceful completion
- **Shutdown**: Ensures clean server shutdown without hanging tasks

---

## Service Interactions and Data Flow

### Game Start Sequence
1. **main.py** receives `game.start` WebSocket message
2. **game_state_manager.py** validates host permissions and starts game
3. **player_manager.py** resets all player scores
4. **game_state_manager.py** calls `start_round()`
5. **timer_service.py** schedules countdown timer
6. **message_broadcaster.py** sends countdown message to all players

### Round Progression
1. **timer_service.py** countdown expires, calls game state manager
2. **game_state_manager.py** transitions to active phase
3. **problem_pool_service.py** provides current problem
4. **message_broadcaster.py** broadcasts round start with problem
5. **timer_service.py** schedules round timer

### Answer Submission
1. **main.py** receives `answer.submit` WebSocket message
2. **submission_processor.py** validates submission and timing
3. **player_manager.py** calculates and applies score
4. **main.py** sends acknowledgment back to player

### Round End
1. **timer_service.py** round timer expires
2. **game_state_manager.py** calculates round results
3. **player_manager.py** provides score updates and leaderboard
4. **message_broadcaster.py** broadcasts round end results
5. **timer_service.py** schedules results display timer

## Key Design Patterns

### Service-Oriented Architecture
- Each service has a single, well-defined responsibility
- Services communicate through clearly defined interfaces
- Dependencies are injected at startup for loose coupling

### Event-Driven Communication
- WebSocket messages trigger state changes
- Timer expiration drives phase transitions
- State changes trigger broadcasts to all relevant players

### State Management
- Room state is centralized in RoomManager
- Player state is managed by PlayerManager
- Game flow state is controlled by GameStateManager

### Error Handling and Resilience
- Comprehensive validation at all entry points
- Graceful handling of disconnections and network issues
- Resource cleanup on errors and shutdowns

## Security Considerations

### Authentication
- Session token-based authentication without user accounts
- Session tokens validated for all player actions
- Host permissions enforced for game control actions

### Input Validation
- All WebSocket messages validated against Pydantic schemas
- Number ranges and expression lengths limited
- Round indices and timing validated

### Resource Management
- Room cleanup prevents memory leaks
- Timer cleanup prevents resource buildup
- Connection tracking prevents orphaned WebSockets

This architecture provides a robust, scalable foundation for multiplayer 24-game competitions with clear separation of concerns and comprehensive error handling.