# pydantic_schemas.py
from __future__ import annotations
from typing import Dict, List, Optional, Literal, Union, Any
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field, validator, root_validator, constr, conint, PositiveInt


# ---------------------------
# Helper validators / types
# ---------------------------

RoomCode = constr(pattern=r'^[A-Z0-9]{4}$')  # 4 uppercase alphanumeric characters
Username = constr(min_length=1, max_length=32)
ExpressionStr = constr(min_length=1, max_length=512)


def ensure_tzaware(dt: datetime) -> datetime:
    """Ensure a datetime has tzinfo. If naive, interpret as UTC (or raise)."""
    if dt.tzinfo is None:
        # To be strict: raise ValueError
        # But for robustness, we convert naive -> UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------
# Domain models
# ---------------------------

class RoomSettings(BaseModel):
    """
    Room configuration set by the host before start.
    - rounds: number of rounds in the match (1..100)
    - time_per_round_seconds: fixed seconds per round (5..300)
    """
    rounds: conint(ge=1, le=100) = Field(..., description="Number of rounds in the match")
    time_per_round_seconds: conint(ge=5, le=300) = Field(..., description="Seconds per round")

    model_config = {
        "json_schema_extra": {
            "example": {"rounds": 10, "time_per_round_seconds": 30}
        }
    }


class MVPRoomSettings(BaseModel):
    """
    Fixed MVP room settings: 10 rounds, 30 seconds per round, 3 second countdown, 6 second results.
    """
    rounds: Literal[10] = Field(10, description="Fixed 10 rounds for MVP")
    time_per_round_seconds: Literal[30] = Field(30, description="Fixed 30 seconds per round for MVP")
    countdown_seconds: Literal[3] = Field(3, description="Fixed 3 second countdown before each round")
    results_display_seconds: Literal[6] = Field(6, description="Fixed 6 seconds to display round results")

    model_config = {
        "json_schema_extra": {
            "example": {
                "rounds": 10,
                "time_per_round_seconds": 30,
                "countdown_seconds": 3,
                "results_display_seconds": 6
            }
        }
    }


class PlayerPublic(BaseModel):
    """Public player info used in broadcasts."""
    player_id: UUID
    username: Username
    score: int = 0
    streak: int = 0

    model_config = {"from_attributes": True}


class PlayerInternal(PlayerPublic):
    """Server-side player representation (includes session token & connection meta)."""
    session_token: str
    connection_id: Optional[str] = None
    joined_at: datetime
    last_seen_at: Optional[datetime] = None
    has_scored_this_round: bool = False
    disconnected_at: Optional[datetime] = None

    # validate datetimes are timezone-aware
    _tz_joined = validator('joined_at', allow_reuse=True)(ensure_tzaware)
    _tz_last_seen = validator('last_seen_at', allow_reuse=True)(lambda v: ensure_tzaware(v) if v is not None else None)
    _tz_disconnected = validator('disconnected_at', allow_reuse=True)(lambda v: ensure_tzaware(v) if v is not None else None)


class ProblemStats(BaseModel):
    correct_count: int = 0


class Problem(BaseModel):
    problem_id: UUID = Field(default_factory=uuid4)
    numbers: List[conint(ge=1, le=13)] = Field(..., description="Four numbers in range 1..13 (order arbitrary)")
    canonical_solution: Optional[ExpressionStr] = Field(None, description="Canonical solution string chosen by solver")
    stats: ProblemStats = Field(default_factory=ProblemStats)

    @validator('numbers')
    def numbers_must_be_len4(cls, v):
        if len(v) != 4:
            raise ValueError("numbers must be a list of exactly 4 integers in 1..13")
        return v


class RoomState(str):
    LOBBY = "LOBBY"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"


class RoundPhase(str):
    COUNTDOWN = "COUNTDOWN"
    ACTIVE = "ACTIVE"
    RESULTS = "RESULTS"


class RoundState(BaseModel):
    """Tracks the current round timing state."""
    phase: Literal[RoundPhase.COUNTDOWN, RoundPhase.ACTIVE, RoundPhase.RESULTS]
    phase_start_time: datetime
    phase_end_time: datetime
    round_start_time: Optional[datetime] = None
    round_end_time: Optional[datetime] = None

    _tz_phase_start = validator('phase_start_time', allow_reuse=True)(ensure_tzaware)
    _tz_phase_end = validator('phase_end_time', allow_reuse=True)(ensure_tzaware)
    _tz_round_start = validator('round_start_time', allow_reuse=True)(lambda v: ensure_tzaware(v) if v is not None else None)
    _tz_round_end = validator('round_end_time', allow_reuse=True)(lambda v: ensure_tzaware(v) if v is not None else None)


class Room(BaseModel):
    room_code: RoomCode
    host_player_id: UUID
    settings: MVPRoomSettings = Field(default_factory=MVPRoomSettings)
    players: Dict[UUID, PlayerInternal] = Field(default_factory=dict)
    problems: List[Problem] = Field(default_factory=list)
    round_index: int = 0  # 0-based index into problems when running
    state: Literal[RoomState.LOBBY, RoomState.RUNNING, RoomState.FINISHED] = RoomState.LOBBY
    current_round_state: Optional[RoundState] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _tz_created = validator('created_at', allow_reuse=True)(ensure_tzaware)
    _tz_last_activity = validator('last_activity_at', allow_reuse=True)(ensure_tzaware)

    @validator('players', pre=True)
    def ensure_players_is_dict(cls, v):
        return v or {}

    @validator('players')
    def max_four_players(cls, v):
        if len(v) > 4:
            raise ValueError("Room cannot have more than 4 players")
        return v


# ---------------------------
# Submission & logging
# ---------------------------

class SubmissionRecord(BaseModel):
    submission_id: UUID = Field(default_factory=uuid4)
    room_code: RoomCode
    round_index: conint(ge=0)
    player_id: UUID
    expression: ExpressionStr
    used_numbers: List[conint(ge=1, le=13)]
    client_eval_value: Optional[float] = None
    client_eval_is_valid: bool = False
    client_timestamp: Optional[datetime] = None
    server_receive_time: Optional[datetime] = None
    accepted: bool = False
    reason: Optional[str] = None
    time_left_at_submission: Optional[float] = Field(None, description="Seconds remaining when submitted")
    speed_bonus_awarded: Optional[int] = Field(None, description="Speed bonus points awarded (0-5)")
    points_awarded: Optional[int] = Field(None, description="Total points awarded for this submission")

    @validator('used_numbers')
    def used_numbers_len4(cls, v):
        if len(v) != 4:
            raise ValueError("used_numbers must be a list of exactly 4 integers")
        return v

    _tz_client_ts = validator('client_timestamp', allow_reuse=True)(lambda v: ensure_tzaware(v) if v is not None else None)
    _tz_server_recv = validator('server_receive_time', allow_reuse=True)(lambda v: ensure_tzaware(v) if v is not None else None)


# ---------------------------
# Scoring related models (for broadcasts)
# ---------------------------

class PlayerScored(BaseModel):
    player_id: UUID
    username: Username
    points_gained: int
    base_points: int = Field(10, description="Base 10 points for correct answer")
    speed_bonus: int = Field(0, description="Speed bonus 0-5 points based on time remaining")
    time_left: float = Field(..., description="Seconds remaining when answer submitted")
    time_submitted: datetime = Field(..., description="Server timestamp when answer was submitted")
    submission_rank: int = Field(..., description="1-based rank among correct submissions this round")

    _tz_time_submitted = validator('time_submitted', allow_reuse=True)(ensure_tzaware)

    @validator('points_gained')
    def points_gained_equals_base_plus_bonus(cls, v, values):
        base = values.get('base_points', 10)
        bonus = values.get('speed_bonus', 0)
        if v != base + bonus:
            raise ValueError("points_gained must equal base_points + speed_bonus")
        return v

class PlayerScoreUpdate(BaseModel):
    player_id: UUID
    score: int
    streak: int


class LeaderboardEntry(BaseModel):
    player_id: UUID
    username: Username
    score: int


class ProblemPercentEntry(BaseModel):
    problem_id: UUID
    numbers: List[int]
    correct_percent: float = Field(..., ge=0.0, le=1.0)


# ---------------------------
# WebSocket message payloads
# (envelope: {"type": "...", "payload": {...}} )
# ---------------------------

# --- CLIENT -> SERVER payloads ---


class RoomCreatePayload(BaseModel):
    username: Username
    settings: MVPRoomSettings = Field(default_factory=MVPRoomSettings)


class RoomJoinPayload(BaseModel):
    room_code: RoomCode
    username: Username
    # optional: client may include previously stored session token when reconnecting
    session_token: Optional[str] = None


class GameStartPayload(BaseModel):
    room_code: RoomCode
    # host must include session token for auth
    session_token: str


class AnswerSubmitPayload(BaseModel):
    room_code: RoomCode
    player_id: UUID
    session_token: str
    round_index: conint(ge=0)
    expression: ExpressionStr
    used_numbers: List[conint(ge=1, le=13)]
    client_eval_value: Optional[float] = None
    client_eval_is_valid: bool
    client_timestamp: Optional[datetime] = None

    @validator('used_numbers')
    def used_numbers_len4(cls, v):
        if len(v) != 4:
            raise ValueError("used_numbers must contain exactly 4 integers")
        return v

    _tz_client_ts = validator('client_timestamp', allow_reuse=True)(lambda v: ensure_tzaware(v) if v is not None else None)


class RoomCreateMessage(BaseModel):
    type: Literal["room.create"]
    payload: RoomCreatePayload


class RoomJoinMessage(BaseModel):
    type: Literal["room.join"]
    payload: RoomJoinPayload


class GameStartMessage(BaseModel):
    type: Literal["game.start"]
    payload: GameStartPayload


class AnswerSubmitMessage(BaseModel):
    type: Literal["answer.submit"]
    payload: AnswerSubmitPayload


# Union of all incoming message types (for parsing)
IncomingWSMessage = Union[
    RoomCreateMessage,
    RoomJoinMessage,
    GameStartMessage,
    AnswerSubmitMessage
]


# --- SERVER -> CLIENT payloads ---


class RoomCreatedPayload(BaseModel):
    room_code: RoomCode
    host_player_id: UUID
    session_token: str
    settings: MVPRoomSettings


class RoomCreatedMessage(BaseModel):
    type: Literal["room.created"]
    payload: RoomCreatedPayload


class RoomJoinedPayload(BaseModel):
    room_code: RoomCode
    player_id: UUID
    session_token: str
    players: List[PlayerPublic]
    state: Literal[RoomState.LOBBY, RoomState.RUNNING, RoomState.FINISHED]


class RoomJoinedMessage(BaseModel):
    type: Literal["room.joined"]
    payload: RoomJoinedPayload


class CountdownStartPayload(BaseModel):
    round_index: conint(ge=0)
    countdown_seconds: conint(ge=1)
    server_time: datetime

    _tz_server_time = validator('server_time', allow_reuse=True)(ensure_tzaware)


class CountdownStartMessage(BaseModel):
    type: Literal["countdown.start"]
    payload: CountdownStartPayload


class RoundStartPayload(BaseModel):
    round_index: conint(ge=0)
    problem_id: UUID
    numbers: List[conint(ge=1, le=13)]
    time_limit_seconds: conint(ge=5)
    server_time: datetime
    round_end: datetime

    @validator('numbers')
    def numbers_len4(cls, v):
        if len(v) != 4:
            raise ValueError("numbers must have exactly 4 values")
        return v

    _tz_server_time = validator('server_time', allow_reuse=True)(ensure_tzaware)
    _tz_round_end = validator('round_end', allow_reuse=True)(ensure_tzaware)


class RoundStartMessage(BaseModel):
    type: Literal["round.start"]
    payload: RoundStartPayload


class AnswerAckPayload(BaseModel):
    submission_id: Optional[UUID] = None
    accepted: bool
    server_receive_time: Optional[datetime] = None
    time_left_seconds: Optional[float] = None
    reason: Optional[str] = None

    _tz_server_recv = validator('server_receive_time', allow_reuse=True)(lambda v: ensure_tzaware(v) if v is not None else None)


class AnswerAckMessage(BaseModel):
    type: Literal["answer.ack"]
    payload: AnswerAckPayload


class RoundEndPayload(BaseModel):
    round_index: conint(ge=0)
    problem_id: UUID
    canonical_solution: Optional[ExpressionStr]
    players_correct: List[PlayerScored] = Field(default_factory=list)
    updated_scores: List[PlayerScoreUpdate] = Field(default_factory=list)


class RoundEndMessage(BaseModel):
    type: Literal["round.end"]
    payload: RoundEndPayload


class GameEndPayload(BaseModel):
    leaderboard: List[LeaderboardEntry]
    most_correct: Optional[ProblemPercentEntry] = None
    least_correct: Optional[ProblemPercentEntry] = None


class GameEndMessage(BaseModel):
    type: Literal["game.end"]
    payload: GameEndPayload


class PlayerJoinedPayload(BaseModel):
    player: PlayerPublic
    total_players: conint(ge=1, le=4)


class PlayerJoinedMessage(BaseModel):
    type: Literal["player.joined"]
    payload: PlayerJoinedPayload


class PlayerLeftPayload(BaseModel):
    player_id: UUID
    username: Username
    total_players: conint(ge=0, le=4)


class PlayerLeftMessage(BaseModel):
    type: Literal["player.left"]
    payload: PlayerLeftPayload


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorMessage(BaseModel):
    type: Literal["error"]
    payload: ErrorPayload


# Union of outgoing message types
OutgoingWSMessage = Union[
    RoomCreatedMessage,
    RoomJoinedMessage,
    CountdownStartMessage,
    RoundStartMessage,
    AnswerAckMessage,
    RoundEndMessage,
    GameEndMessage,
    PlayerJoinedMessage,
    PlayerLeftMessage,
    ErrorMessage,
]


# ---------------------------
# Extra helpers / schemas used by server internals
# ---------------------------

class CreateRoomResult(BaseModel):
    room_code: RoomCode
    host_player_id: UUID
    host_session_token: str
    created_at: datetime

    _tz_created = validator('created_at', allow_reuse=True)(ensure_tzaware)


class JoinRoomResult(BaseModel):
    room_code: RoomCode
    player_id: UUID
    session_token: str
    players: List[PlayerPublic]
    state: str


# ---------------------------
# Example usage hints (not executed)
# ---------------------------
# - On WebSocket receive: parse into IncomingWSMessage union; e.g.:
#     msg = json.loads(ws_text)
#     # then decide which model to validate by msg['type'] or use discriminated union logic
# - On server send: instantiate the appropriate Message class and .json() it.
# ---------------------------
