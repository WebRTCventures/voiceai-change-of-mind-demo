# Requirements: baseline-booking-agent

## Introduction

The smallest working voice agent for the booking scenario in `demo-brief.md`. A caller talks to it in the browser and books an appointment by day. The backend is slow on purpose, so a caller who changes their mind while the tool is running ends up with two bookings. That double booking is the expected baseline. Later specs fix it.

## Requirements

### 1. Run and connect
**User story:** As a reader, I want to clone the repo, add keys and run one command, so that I can talk to the agent in my browser.

Acceptance criteria:
1. After `uv sync` and `uv run bot.py`, the Pipecat runner serves the built-in browser client at `http://localhost:7860/client`.
2. The bot uses Pipecat (version pinned in `pyproject.toml`), `SmallWebRTCTransport` via the runner, Silero VAD, Deepgram STT and TTS, and an OpenAI LLM.
3. The OpenAI model name comes from `OPENAI_MODEL` in `.env`.
4. `.env.example` lists `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `COMMIT_AT` and `TOTAL`.

### 2. Greeting and prompt
**User story:** As a caller, I want the agent to speak first, so that I know what to say.

Acceptance criteria:
1. When the browser client is ready, the agent says "Hi, I can book your appointment. Which day works for you?".
2. The LLM system prompt is the one in the brief, unchanged.

### 3. Booking tool
**User story:** As a caller, I want to say a day and have it booked, so that I do not have to confirm.

Acceptance criteria:
1. The LLM has one tool, `book_appointment(day: str)`, defined as a Pipecat direct function with default tool options (cancelled on interruption).
2. The handler supplies `caller_id` (the session id) and `seq` (the number of user turns so far) to the backend. The LLM does not see these.
3. On success the handler returns a short result the model can narrate, `{"status": "booked", "day": <day>}`.

### 4. Fake calendar backend
**User story:** As a reader, I want a backend that behaves like a remote server, so that the failure in the post is reproducible.

Acceptance criteria:
1. `calendar_backend.book(day, caller_id, seq)` sleeps `COMMIT_AT` seconds (default 3.0), writes the appointment, then sleeps until `TOTAL` seconds (default 6.0) after the start, then returns.
2. The backend work runs inside `asyncio.shield`, so it completes even if the calling tool task is cancelled. A code comment says this models a remote server that never learns the client gave up, which is the main lesson of the demo.
3. Storage is append only. Every call adds a row `(day, caller_id, seq, committed_at)`.
4. After every write the calendar is printed to the terminal and written to `calendar.json`.
5. The storage mode is a parameter of `book`, so a later spec can add upsert without restructuring.

### 5. Expected baseline behavior
**User story:** As a reader, I want to see the double booking, so that I understand the problem later specs solve.

Acceptance criteria:
1. Saying "Book me for Friday" produces exactly one Friday row in the terminal and in `calendar.json`, about `COMMIT_AT` seconds after the tool starts.
2. Saying "actually, make it Saturday" while the tool is running leaves both a Friday and a Saturday row. This is intended and must not be fixed here.

### 6. Structure
Acceptance criteria:
1. Code lives in `bot.py` and `calendar_backend.py`, following the brief's layout.
2. `bot.py` has clearly marked places where a timeline module and a `--policy` / `--turn` flag mapping will plug in. Neither is built.
3. No automated tests are added.

## Out of scope
Timeline and latency output, `--policy` and `--turn` flags, upsert storage, README.
