# 24 Game — Multiplayer MVP Design Spec (detailed, implementable)

Below is a concrete, implementable design for the multiplayer MVP you requested. It assumes your single-player solver and Kivy frontend already exist. This spec includes: server architecture, data models/state, event/message schemas, room/round lifecycle, scoring formulas and worked examples, pre-generation algorithm for problems, edge-case handling, diagnostics/audit logging, security/session rules, deployment considerations, and a recommended folder layout for both server and Kivy client.

---

# 1 — High-level summary / goals (reminder)

* Synchronous Kahoot-like multiplayer for the 24 game (1–10 players per room).
* FastAPI backend with WebSockets for real-time events.
* Clients: Kivy app (MVP only).
* Problems: four values in 1..13, standard 24 rules (use each exactly once, ops `+ - * /`). Parentheses handled implicitly by button-driven reduction UI.
* Pre-generate all N problems at match start (no duplicates by multiset equality).
* Client-side expression validation for MVP (fast, same UX as single-player). Server timestamps used as authoritative for speed/ordering and scoring.
* Scoring: base 10, speed bonus up to +5 (fastest totals 15), streak +2 per consecutive correct. Round lasts fixed time (room setting). Results shown 6s. Countdown 3s pre-round.
* Logging of all submissions and background (optional) audit validation later.

---

# 2 — System architecture (big picture)

```
[ Kivy Client x N ]  <---- WebSockets/JSON ---->  [FastAPI WebSocket Server (uvicorn worker)]
                                     |
                                     v
                        In-memory Room Store / Redis (optional, pub/sub)
                                     |
                                     v
                      Persistent Logging DB (SQLite for MVP / Postgres later)
                                     |
                                     v
                         Background Audit Worker (optional)
```

* **MVP**: single FastAPI instance with in-memory room store (Python dict) + SQLite logging. This minimizes infra and reuses Python solver directly.
* **Scale**: switch to Redis for room state + pub/sub if you need >1 server instance; solver service can be isolated into worker processes.

---

# 3 — Server responsibilities (detailed)

* Manage rooms, players, and authoritative timers.
* Pre-generate problem set at game start using server-side call to your existing solver (to ensure solvable problems).
* Broadcast `round.start` messages with server timestamps and `round_end` ISO timestamp.
* Accept `answer.submit` messages and timestamp arrival (`server_receive_time`).
* Apply acceptance rules: ensure current round is open and player hasn't already scored this round. For MVP, server **accepts client’s validity flag** but still enforces per-round and per-player constraints.
* Compute scores using server times (see scoring section).
* Persist every submission (expression, client flags, timestamps) to DB/logs for auditing.
* Clean up inactive rooms: both (a) rooms not started within 3 minutes from creation, and (b) rooms inactive for 3 minutes.
* Handle reconnections: restore players if reconnect within game duration + 60s grace via session token.

---

# 4 — Data models & in-memory state

> All timestamps are UTC ISO8601 strings, and server uses monotonic timers internally to avoid clock drift for expiration logic.

## Room (object)

* `room_code: str` (6-char alphanumeric)
* `host_player_id: str`
* `settings: { rounds: int, time_per_round_seconds: int }`
* `players: dict[player_id -> Player]`
* `problems: list[Problem]` — pre-generated at `game.start`, length = `rounds`
* `round_index: int` — 0-based index into `problems`
* `state: enum{LOBBY, RUNNING, FINISHED}`
* `created_at: iso`
* `last_activity_at: iso`
* `timer_handle` (server-side reference to scheduled coroutine for round end)
* `room_lock` (async lock to avoid race conditions)

## Player (object)

* `player_id: str` (server-generated UUID)
* `username: str`
* `session_token: str` (opaque token returned on join for reconnections)
* `connection_id: str` (current ws connection id; null if disconnected)
* `score: int`
* `streak: int`
* `joined_at: iso`
* `last_seen_at: iso`
* `has_scored_this_round: bool`
* `disconnected_at: iso | null`

## Problem (object)

* `numbers: [int, int, int, int]` (order arbitrary; uniqueness by multiset)
* `canonical_solution: str` (single canonical expression string from single-player solver; shown after round)
* `problem_id: str` (UUID)
* `stats: { correct_count: int }` (used to compute % correct later)

## Submission (logged)

* `submission_id`
* `room_code`
* `round_index`
* `player_id`
* `expression` (string)
* `client_eval_value` (numeric) — optional per client
* `client_eval_is_valid` (bool) — what client says
* `client_timestamp` (optional ISO)
* `server_receive_time` (ISO)
* `accepted` (bool)
* `reason` (string; logged on rejection)

---

# 5 — Message/event formats (JSON) — full schemas & examples

All messages are JSON. `type` field indicates message type. Timestamps ISO strings.

> NOTE: These are the canonical messages for WebSocket. Use a small wrapper object:
> `{ "type": "event.type", "payload": { ... } }`

---

## 5.1 — Client → Server (requests)

### `room.create`

Client: host creates a room (could be REST POST; WebSocket also possible).
Payload:

```json
{
  "type":"room.create",
  "payload":{
    "username":"Alice",
    "settings":{
      "rounds":10,
      "time_per_round_seconds":30
    }
  }
}
```

Server response: `room.created` (see below).

---

### `room.join`

Client joins lobby using the 6-char code.

```json
{
  "type":"room.join",
  "payload":{
    "room_code":"A1B2C3",
    "username":"Bob"
  }
}
```

Server replies `room.joined` (success) or `error.room` (failure).

---

### `game.start` (host only)

Host clicks begin. Server pre-generates problems and moves room to RUNNING.

```json
{
  "type":"game.start",
  "payload":{
    "room_code":"A1B2C3"
  }
}
```

Server replies `game.started` with `problems_count` and broadcasts first countdown/round.start.

---

### `answer.submit`

Client submits an attempted expression. **MVP: client computes validity** (reuse single-player solver).
Payload:

```json
{
  "type":"answer.submit",
  "payload":{
    "room_code":"A1B2C3",
    "player_id":"player-uuid",
    "session_token":"opaque-token",
    "round_index":3,
    "expression":"((6-4)*8)+4",
    "used_numbers":[6,4,8,4],
    "client_eval_value":24,
    "client_eval_is_valid": true,
    "client_timestamp":"2025-09-07T14:23:32.123Z"
  }
}
```

Server behavior:

* Validate authentication & that room is RUNNING and `round_index` matches server `round_index`.
* Check that player hasn't already had an accepted submission this round.
* **MVP acceptance rule**: If `client_eval_is_valid===true` and `used_numbers` multiset equals current problem numbers multiset, accept. Otherwise reject.
* Record `server_receive_time` (ISO), compute `time_left_seconds = round_end - server_receive_time` and compute scoring. Respond with `answer.ack` (accepted/rejected).

Server response examples:

**Accepted ack**

```json
{
  "type":"answer.ack",
  "payload":{
    "submission_id":"sub-xxx",
    "accepted":true,
    "server_receive_time":"2025-09-07T14:23:34.345Z",
    "time_left_seconds":21.65
  }
}
```

**Rejected ack**

```json
{
  "type":"answer.ack",
  "payload":{
    "accepted":false,
    "reason":"round_closed"   // or "not_your_round", "invalid_used_numbers", "already_scored"
  }
}
```

> Logging note: store the raw `expression` & `client_eval_*` for audits.

---

## 5.2 — Server → Client (broadcasts)

### `room.created`

Sent to host after `room.create` success:

```json
{
  "type":"room.created",
  "payload":{
    "room_code":"A1B2C3",
    "host_player_id":"player-uuid",
    "session_token":"opaque-token",
    "settings": { "rounds":10, "time_per_round_seconds":30 }
  }
}
```

### `room.joined`

Sent to joining player (and broadcast to lobby players) after join:

```json
{
  "type":"room.joined",
  "payload":{
    "room_code":"A1B2C3",
    "player_id":"player-uuid",
    "session_token":"opaque-token",
    "players":[
      {"player_id":"p1","username":"Alice"},
      {"player_id":"p2","username":"Bob"}
    ],
    "state":"LOBBY"
  }
}
```

### `countdown.start` (3s before each round)

Broadcast before each round.

```json
{
  "type":"countdown.start",
  "payload":{
    "round_index":0,
    "countdown_seconds":3,
    "server_time":"2025-09-07T14:23:00.000Z"
  }
}
```

### `round.start`

Includes the canonical server `round_end` timestamp — clients should use this for UI countdown but server uses `server_receive_time` to determine scoring.

```json
{
  "type":"round.start",
  "payload":{
    "round_index":0,
    "problem_id":"prob-uuid",
    "numbers":[6,4,8,4],
    "time_limit_seconds":30,
    "server_time":"2025-09-07T14:23:03.000Z",
    "round_end":"2025-09-07T14:23:33.000Z"
  }
}
```

### `round.end`

Sent when the round timer expires (or server forced end). Contains scoring & canonical solution.

```json
{
  "type":"round.end",
  "payload":{
    "round_index":0,
    "problem_id":"prob-uuid",
    "canonical_solution":"((6-4)*8)+4",
    "players_correct":[
      {"player_id":"p2","username":"Bob","points_gained":15,"time_left":21.65},
      {"player_id":"p3","username":"Charlie","points_gained":12,"time_left":18.3}
    ],
    "updated_scores":[
      {"player_id":"p2","score":45,"streak":3},
      {"player_id":"p3","score":30,"streak":1}
    ]
  }
}
```

### `game.end`

Sent after last round:

```json
{
  "type":"game.end",
  "payload":{
    "leaderboard":[
      {"player_id":"p2","username":"Bob","score":120},
      {"player_id":"p3","username":"Charlie","score":98}
    ],
    "most_correct":{
      "problem_id":"prob-uuid",
      "numbers":[1,3,3,4],
      "correct_percent":0.85
    },
    "least_correct":{
      "problem_id":"prob-uuid2",
      "numbers":[13,13,13,13],
      "correct_percent":0.05
    }
  }
}
```

---

# 6 — Scoring rules, formulas & worked examples

## Formula (exact)

* `BASE = 10`
* `MAX_SPEED_BONUS = 5` (so fastest possible total for a single round is `15`)
* `streak_bonus = 2 * streak_count` (where `streak_count` is number of consecutive correct answers **before** this round)
* `speed_bonus = ceil( (time_left_seconds / round_time_seconds) * MAX_SPEED_BONUS )`
* `points_gained = BASE + speed_bonus + streak_bonus`

### Constraints

* `time_left_seconds` computed on server as `round_end - server_receive_time`. If `server_receive_time > round_end` => rejected.
* `points_gained` capped at `BASE + MAX_SPEED_BONUS + streak_bonus` (no upper cap beyond streak).
* Only the **first accepted submission per player per round** is counted; further submissions that round are ignored.

### Example

* Round time = 30s.
* Player A submits and server receives at server\_receive\_time such that time\_left = 25s.

  * speed\_bonus = ceil((25/30)\*5) = ceil(4.1666) = 5
  * streak = 0
  * points = 10 + 5 + 0 = 15
* Player B submits with time\_left = 10s and streak = 2:

  * speed\_bonus = ceil((10/30)\*5) = ceil(1.666) = 2
  * streak\_bonus = 2\*2 = 4
  * points = 10 + 2 + 4 = 16

---

# 7 — Problem generation algorithm (pre-generate N problems)

**Requirements**

* One canonical solution selected per problem from single-player solver.
* No duplicate problem multisets within game.

**Algorithm (pseudocode outline)**

1. Initialize `problems=[]`, `seen_multisets=set()`, `attempts=0`.
2. While `len(problems) < N` and `attempts < MAX_ATTEMPTS`:

   * Sample `numbers = random.choice_with_replacement(1..13, k=4)` (or choose uniformly among combinations).
   * Compute `multiset_key = tuple(sorted(numbers))`.
   * If `multiset_key` in `seen_multisets`: `attempts +=1`, continue.
   * Use your single-player solver (server-side) to try to find solutions for `numbers`.
   * If solver finds at least one solution:

     * Get `canonical_solution` from your existing selection function.
     * Append `Problem{numbers, canonical_solution}` to `problems`.
     * Add `multiset_key` to `seen_multisets`.
   * `attempts += 1`
3. If not enough problems after `MAX_ATTEMPTS` (e.g., 10\*N attempts), escalate:

   * Option A: expand sampling method to exhaustive combination search (deterministic).
   * Option B: fail match creation and notify host.

**Notes**

* For small N (10–50) this is trivial. Use backing solver because not all 4-value combos are solvable.

---

# 8 — Room & timer lifecycle (detailed)

## Lobby phase

* Room created; persists for 3 minutes unless started.
* Players join until host presses `game.start`.
* After `game.start`, server pre-generates problems (block if small latency) then send `countdown.start` and the first `round.start`.

## Round phase

* `round.start` contains `round_end` (server timestamp).
* Server marks `round_open = True`.
* Accept `answer.submit` until `server_receive_time > round_end` + `GRACE_MS` (e.g., 50ms). Submissions after that rejected.
* When round\_end passes, server:

  * cancels any open timers,
  * calculates scores based on logged accepted submissions,
  * updates player `score` and `streak` fields,
  * broadcasts `round.end`,
  * sets `round_open = False`,
  * waits 6s (result display), then starts next `countdown.start` for next round.

## End phase

* After all N rounds processed, server computes most/least correct percentages (use `problem.stats.correct_count / total_players_present_for_round`) and broadcasts `game.end`.
* Room transitions to `FINISHED`. Room persists for `3 minutes` after completion for clients to view results, then deleted.

---

# 9 — Reconnect / session rules & host handoff

* When a player joins, server returns `session_token`. Client must persist token locally.
* If connection drops, client reconnects to same `room.join` with `session_token`. If token valid and `player_id` matches, restore `connection_id` and `score` and `streak`. Mark `disconnected_at = null`. If reconnect occurs after 60s grace, new player is created instead (previous identity lost).
* If host disconnects mid-game:

  * Auto-assign host to earliest-joined player (`joined_at`) who is connected.
  * Continue game normally.
* If host disconnects in lobby before `game.start`, room remains for 3 minutes; earliest-joined becomes host.

---

# 10 — Edge cases & mitigations

1. **Client lies (claims valid but used wrong numbers)**

   * MVP: server trusts `client_eval_is_valid`. But we store every submission to DB. Later, background audit worker may re-run solver against suspicious submissions and flag/penalize.
   * Option for quick mitigation: server performs cheap check that `used_numbers` multiset equals current problem's numbers multiset — this is inexpensive and recommended. (If you want full trust-break prevention later, run full parse/validation server-side.)

2. **High-latency users**

   * Server uses server\_receive\_time for all scoring. No latency compensation in MVP.

3. **Duplicate fast submissions**

   * Accept only first accepted submission per player per round; further accepted submissions ignored.

4. **Two players submitting at same ms**

   * Time precision: use server timestamps with milliseconds. If exact tie in time\_left after rounding, treat speed\_bonus tied. For deterministic tie-break in ranking displays, sort by `server_receive_time`, then `player_id` lexical.

5. **All players disconnected**

   * If room has 0 connected players for 3 minutes, garbage-collect room and log as aborted.

6. **Problem pre-generation fails to find N problems**

   * Notify host with error, and allow options: lower rounds, attempt exhaustive generation, or cancel.

7. **Cheating via multiple devices/rapid submissions**

   * MVP: no strong mitigation. Implement rate-limit soft constraint (client-side only) and log bursts. For next iteration, server-side limits and server validation should be added.

8. **Clock drift on client**

   * Clients should display time using server-provided `round_end`. Optionally send `server_time` in `round.start` to help clients estimate network latency.

---

# 11 — Persistence & logging (for debugging & audit)

* **MVP DB**: SQLite with tables:

  * `rooms` (room\_code, settings, state, created\_at)
  * `players` (player\_id, username, session\_token)
  * `matches` (room\_code, started\_at, ended\_at)
  * `rounds` (match\_id, round\_index, problem\_id, round\_end)
  * `submissions` (submission\_id, round\_id, player\_id, expression, client\_eval\_is\_valid, client\_eval\_value, client\_ts, server\_receive\_time, accepted, reason)
* Log retention: keep logs for N days for early testing (e.g., 30 days), then archive.

---

# 12 — Security & auth (MVP)

* Minimal auth: server generates `session_token` per join. Token must be supplied on reconnect & for `answer.submit`.
* Do not rely on username for auth.
* Validate session token on interaction.
* Avoid exposing other players' session tokens.
* Use HTTPS/WSS in production.

---

# 13 — Tests & QA scenarios (must-have tests)

* **Functional**: host creates room → 3 players join → host starts → N rounds play normally → `game.end` leaderboard correct.
* **Scoring**: test scoring formula across various time\_left and streak combos.
* **Race**: 10 players submit simultaneously; ensure only one accepted submission per player and correctness of computed bonuses.
* **Reconnect**: disconnect & reconnect within 60s; verify score/streak restoration.
* **Room expiration**: create, do not start → verify deleted after 3m; finish game → persists 3m then cleanup.
* **Audit**: submissions get logged; simulate modified clients and verify logs contain evidence for later audits.

---

# 14 — Implementation specifics — FastAPI & WebSocket patterns

### Process model (recommended)

* Run FastAPI with `uvicorn` single process for MVP.
* Use `asyncio`-based WebSocket handlers.
* Each room has an `asyncio.Lock()` to serialize state updates.
* Use `asyncio.create_task()` for scheduled round end tasks; store handle in `timer_handle` so you can cancel on early termination.

### Timers & clocks

* When broadcasting `round.start`, compute `round_end = now_utc + time_limit_seconds` using server monotonic + epoch time.
* When a submission arrives, compute `server_receive_time = now_utc` and compare to `round_end`.
* Use small grace `GRACE_MS = 50`ms to avoid rejecting submissions due to negligible network jitter.

### Logging & audit

* Log structured JSON lines (one per submission) to disk and into DB.
* Background worker can parse logs and re-run server-side solver for flagged submissions. Keep audit results separate.

---

# 15 — Folder layout (recommended)

## Server

```
server/
├─ app/
│  ├─ main.py                # FastAPI app + startup
│  ├─ ws_router.py           # WebSocket connection & message routing
│  ├─ rooms.py               # Room management (Room, Player classes)
│  ├─ scheduler.py           # timer & background task helpers
│  ├─ solver_adapter.py      # adapter to single-player solver (pre-generation + canonical solution)
│  ├─ scoring.py             # scoring calculation functions
│  ├─ storage/
│  │  ├─ memory_store.py     # in-memory store for MVP
│  │  ├─ redis_store.py      # optional Redis-backed store (future)
│  ├─ models.py              # pydantic message schemas for validation
│  ├─ persistence/
│  │  ├─ db.py               # sqlite wrapper and ORM models (or SQLAlchemy)
│  │  └─ logger.py           # structured submission logs
│  ├─ config.py              # env / config values
│  └─ utils.py               # misc utilities (time, multiset helpers)
├─ tests/
│  ├─ test_room_lifecycle.py
│  ├─ test_scoring.py
│  └─ ...
├─ requirements.txt
├─ Dockerfile
└─ README.md
```

## Client (Kivy)

```
client-kivy/
├─ app.py                    # Kivy app bootstrap
├─ ui/
│  ├─ main.kv
│  ├─ lobby.kv
│  ├─ game.kv
│  └─ results.kv
├─ screens/
│  ├─ lobby_screen.py
│  ├─ game_screen.py
│  └─ results_screen.py
├─ network/
│  └─ ws_client.py           # WebSocket message send/recv & reconnection logic
├─ logic/
│  ├─ solver.py              # reuse single-player solver for local validation
│  ├─ game_state.py          # local UI state, local scoring preview
│  └─ input_handler.py       # button click -> expression building
├─ assets/
└─ README.md
```

---

# 16 — Operational notes / deployment checklist

* Use `uvicorn app.main:app --host 0.0.0.0 --port 80` behind a reverse proxy (nginx).
* Use `--workers 1` for MVP. For scaling, add Redis and multiple Uvicorn workers with sticky sessions or use Redis pub/sub for room events.
* Use TLS (WSS) in production.
* Monitor logs, memory usage (rooms in memory), and DB size. Because rooms live briefly, memory churn should be small.

---

# 17 — Future improvements (post-MVP)

* Move to Redis store + pub/sub for multi-server scaling.
* Server-side authoritative validation of expressions (fractions) to prevent cheating.
* Spectator / teacher mode and web client.
* More sophisticated anti-cheat and rate-limiting (server-side).
* Realtime analytics dashboard for rooms & matches.
* Leaderboard persistence across matches & player accounts.

---

# 18 — Appendix: example sequences (message flow)

## Normal round flow (quick)

1. Host issues `game.start` (REST/WS).
2. Server pre-generates problems, returns `game.started`.
3. Server broadcasts `countdown.start` (3s).
4. Server broadcasts `round.start` (with `round_end`).
5. Clients allow player to interact. They perform local validation using single-player solver; when ready they send `answer.submit`. Multiple submissions allowed but server accepts only first accepted one per player per round.
6. Server receives submissions, stores them, `answer.ack` to submitter.
7. When `round_end` reached, server computes points for all accepted submissions (using server timestamps), updates players, and broadcasts `round.end`.
8. Wait 6 seconds; repeat next round.
9. After final `round.end`, compute stats and broadcast `game.end`.

---

# 19 — Final notes & action items for your repo

* Add `solver_adapter.py` to import your working single-player solver. Use it for pre-generation and canonical solution extraction.
* Implement `models.py` (Pydantic) using JSON schemas above so WS messages are validated.
* Implement `rooms.py` with `asyncio.Lock()` per room.
* Implement `ws_router.py` to parse events and call room APIs.
* Add logging to `persistence/logger.py` for submission auditing.
* In Kivy client `ws_client.py` implement reconnection with saved `session_token`.
* Add tests per folder layout.

---

If you want, I can:

* produce the **complete Pydantic schemas** for all messages (copy-paste ready),
* produce the **SQL CREATE TABLE** statements for the persistence tables,
* or create a **detailed sequence diagram** (textual or mermaid) of message flow between client and server.

Which of those would be most useful next?
