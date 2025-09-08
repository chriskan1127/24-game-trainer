Got it — thanks for the detailed clarifications. Since you already have the single-player logic working, this spec will focus on how the multiplayer system layers on top. Below is a structured **MVP Multiplayer Design Spec** in markdown that you can use as a reference for implementation and future iterations.

---

# 24 Game — Multiplayer MVP Design Spec

## Overview

The multiplayer mode expands the existing single-player 24 game into a synchronous competitive format, inspired by Kahoot. Players join a room with a 4-character code, compete to solve 24-game problems, and earn points based on correctness and speed. At the end of all rounds, the player(s) with the highest score win.

This MVP targets up to **4 concurrent players per room**, with **FastAPI + WebSockets** as the server backend. Cross-platform support is a future goal, but MVP assumes **Kivy clients only**.

---

## Core Gameplay

* **Rules**: Standard 24 game.

  * Players must use all 4 numbers exactly once.
  * Operators: `+`, `-`, `*`, `/`.
  * No exponentiation, concatenation, factorial, etc.
  * Parentheses are unnecessary — operations consume blocks (Kivy UX).

* **Round flow**:

  1. Countdown (3s).
  2. Problem displayed.
  3. Players attempt solutions during the timer (fixed 30 seconds).
  4. Round ends:

     * Correct solution + scoreboard update displayed for 6s.
     * Show which players got it right, with speed ranking.
     * Show one canonical solution chosen by solver.
  5. Next round begins.

* **Game over**:

  * After 10 rounds (fixed), leaderboard displayed.
  * Tie = shared first place.
  * Show final scores and winner(s).

---

## Scoring System

* **Correct submission**:

  * Base: **10 points**.
  * Speed bonus: up to +5 points.

    * Formula: `bonus = ceil((time_left / question_time) * 5)`
    * Fastest possible = 15 total points.
  * Each player can only score once per round (first valid submission counts).

* **Streaks**: Not implemented in MVP (future feature).

* **Fairness**:

  * **Server timestamps** submissions to rank speed.
  * No latency compensation in MVP.

---

## Room & Match Management

* **Room creation**:

  * Host generates a 4-character alphanumeric code.
  * Fixed settings: 10 rounds, 30 seconds per round.

* **Room lifecycle**:

  * Rooms auto-delete when empty (no complex expiration logic).

* **Joining**:

  * Max players: 4.
  * Locked once host presses **begin**.

* **Reconnection**:

  * Simple rejoin: use same room code + username.
  * Score restored if rejoining during same game.
  * No complex host handoff (game continues without host if needed).

---

## Problem Generation

* **Uniqueness**:

  * No repeats within a match (by multiset equality of numbers).

* **Generation**:

  * **Pre-solved problem pool**: Server maintains 50+ validated problems with canonical solutions.
  * Each game randomly selects 10 unique problems from this pool.

* **Solutions**:

  * Canonical solution chosen using existing single-player solver’s criteria.
  * Only one valid solution displayed to players.

---

## Client–Server Responsibilities

* **Client (Kivy)**:

  * UI/UX for joining rooms, submitting answers, seeing results.
  * Local input validation (simulates single-player system).
  * Send submission events (equation + timestamp) to server.

* **Server (FastAPI + WebSockets)**:

  * Authoritative state: rooms, players, scores, problem sets.
  * Receives and timestamps submissions.
  * For MVP: accepts **client-validated submissions** (less secure, but faster and easier).
  * Updates scores and broadcasts round results.
  * Logs all submissions for debugging.

---

## Networking Model

* **Protocol**: WebSockets (JSON messages).
* **Core Events** (simplified):

  * `join_room` → { roomCode, username }
  * `start_game` → broadcast problem + timer  
  * `submit_answer` → { expression, clientSaysValid }
  * `round_complete` → { scores, canonicalSolution, nextProblem }

---

## Anti-Cheat (MVP Level)

* **Client-side validation** for submissions (reuse single-player solver).
* Server accepts results as-is.
* Minimal safeguards:

  * Submission logging.
  * Rate limit: \~10 submissions/sec per player.
  * Flag abnormal activity for review.
* Stronger anti-cheat can be added in future (server-side validation).

---

## User Experience Details

* **Pre-round countdown**: 3s.

* **Round timer**: Fixed 30 seconds.

* **Round results display**: 6s (correct solution + scoreboard).

* **Scoreboard**:

  * Visible after each round during 6s result window.
  * Shows points and per-round correctness.

* **Game over screen**:

  * Final leaderboard with winner announcement.

---

## Server Technology

* **FastAPI** backend.
* **WebSockets** for realtime communication.
* Python solver reused for:

  * Pre-generating problems.
  * Selecting canonical solution.
* Deployment target: lightweight single server for MVP, scaling later.

---

## Open Questions for Post-MVP

* Do we move solution validation fully server-side (more secure, more lag)?
* Add spectator/teacher mode?
* Cross-platform web client?
* More detailed anti-cheat (rate limits, suspicious activity flags)?

---

✅ This spec covers the MVP multiplayer layer on top of your working single-player mode.

---

Would you like me to **flesh this out with sample JSON message formats** (like a schema for `answer.submit`, `round.end`, etc.), so you have a clear contract between client and server, or keep this document more high-level?
