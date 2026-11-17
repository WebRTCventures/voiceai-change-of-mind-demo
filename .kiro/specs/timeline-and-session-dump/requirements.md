# Requirements: timeline-and-session-dump

## Introduction

Makes the double booking visible. A terminal timeline prints one line per event, the INTERRUPT line carries two derived latencies, and a dump at disconnect shows the calendar, the LLM context and a one-line verdict. Agent states S0 to S4 are defined in `demo-brief.md`. The baseline agent (`bot.py`, `calendar_backend.py`) already exists.

## Requirements

### 1. Timeline lines
**User story:** As a reader, I want one readable line per event with a time, so that I can follow the race in a screenshot.

Acceptance criteria:
1. Each line is `+<seconds since session start, 3 decimals>  <category, fixed width>  <message>`, printed to the terminal.
2. Categories and events:
   - `VAD`: user started speaking, user stopped speaking.
   - `TURN`: user turn started (start strategy name), user turn stopped (stop strategy name and transcript).
   - `MUTE`: user mute started, user mute stopped.
   - `INTERRUPT`: interruption.
   - `TOOL`: call started (name, args, seq), cancelled, result.
   - `BACKEND`: commit, reject.
   - `BOT`: bot started speaking, bot stopped speaking, assistant turn stopped (interrupted flag and committed text).
3. Events that the context aggregators emit are taken from the aggregators. A small observer covers VAD, interruption, bot speaking and function call frames.
4. `timeline.py` is the only new file. It stays around 120 lines.

### 2. Derived numbers
**User story:** As a reader, I want the cost of the interruption on the INTERRUPT line, so that I can compare S2 and S4.

Acceptance criteria:
1. `yield_latency`: user speech start to bot stopped speaking. Shown only when the bot was speaking (S4).
2. `tool_cancel_latency`: user speech start to tool cancelled. Shown only when a tool was running (S2).
3. Both are printed in milliseconds on the INTERRUPT line.

### 3. Backend reporting
**User story:** As a reader, I want to see the backend write on the timeline, so that I can see it land after the cancel.

Acceptance criteria:
1. `calendar_backend.py` reports each commit through one optional callback. This is its only change.
2. A commit whose tool call was already cancelled says `(tool was already cancelled)` on the BACKEND line.
3. `timeline.py` defines a reject hook now. A later spec connects it to the backend.

### 4. End-of-session dump
**User story:** As a reader, I want a summary when I hang up, so that I can see what the agent did versus what the model believes.

Acceptance criteria:
1. On client disconnect the dump prints the calendar rows, the LLM context messages (including tool calls and recorded tool results) and a verdict.
2. Verdict: `OK: 1 booking, <day>` or `MISMATCH: <n> bookings (<days>)`. The expected day is the day of the last `book_appointment` call the model made.

### 5. Constraints
1. Plain terminal output. No UI, no external tracing, no new flags, no automated tests.
2. Every Pipecat name is verified against the installed 1.16.0 (see `design.md`).
