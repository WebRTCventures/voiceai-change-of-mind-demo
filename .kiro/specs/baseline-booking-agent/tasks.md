# Tasks: baseline-booking-agent

No automated tests. Verification is manual.

## Implementation

- [x] 1. Project setup: `pyproject.toml` with Pipecat pinned to 1.16.0 (extras `webrtc,deepgram,openai,silero,runner`), `uv.lock`, `.gitignore`, `.env.example` (requirement 1.4)
- [x] 2. `calendar_backend.py`: shielded `book()`, append mode with a `mode` parameter, print and `calendar.json` after each write (requirement 4)
- [x] 3. `bot.py`: pipeline, system prompt, greeting on `on_client_ready` (requirements 1, 2)
- [x] 4. `bot.py`: `book_appointment(day)` direct function with default options, `caller_id` and `seq` filled by the handler (requirement 3)
- [x] 5. `bot.py`: marked plug-in points for the flag mapping and the timeline (requirement 6.2)
- [x] 6. Record verified APIs, differences from the brief and shortcuts in `design.md`

## Manual checks

Checked without API keys:
- [x] A. `import bot` succeeds on Pipecat 1.16.0, and the generated tool schema for `book_appointment` has a single `day` string parameter
- [x] B. Cancelling a `book()` call mid-way still writes the row (shield works), and `calendar.json` matches the printed calendar
- [x] C. `uv run bot.py` starts the runner and registers the bot (the sandbox could not bind the IPv6 loopback, so the browser client was not reached here)

Needs keys and a microphone (run these yourself):
- [x] D. Copy `.env.example` to `.env`, fill in keys. Run `uv sync` and `uv run bot.py`, open `http://localhost:7860/client`, click Connect. The agent greets first.
- [x] E. Say "Book me for Friday". About `COMMIT_AT` seconds later one Friday row is printed and `calendar.json` has it. The agent confirms after about `TOTAL` seconds.
- [x] F. Say "Book me for Friday", wait 2 s, say "Actually, make it Saturday". The calendar ends with a Friday and a Saturday row. Expected baseline.
- [x] G. Change `COMMIT_AT` and `TOTAL` in `.env`, restart, and confirm the timing changes.
