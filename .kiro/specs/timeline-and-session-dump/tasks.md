# Tasks: timeline-and-session-dump

No automated tests. Verification is manual.

## Implementation

- [x] 1. Verify Pipecat 1.16.0 event names, handler signatures and frame classes; record them in `design.md`
- [x] 2. `timeline.py`: `Timeline` observer, aggregator handlers, INTERRUPT numbers, commit and reject hooks (requirements 1, 2, 3.2, 3.3)
- [x] 3. `calendar_backend.py`: `on_commit` callback called from `_write` (requirement 3.1)
- [x] 4. `timeline.py`: `dump(context)` with calendar, context and verdict (requirement 4)
- [x] 5. `bot.py`: create the `Timeline`, attach it, pass it as an observer, set `on_commit`, call `dump` on disconnect
- [x] 6. Confirm or correct the brief's claim about the recorded text of a cancelled call in `design.md`

## Manual checks

Done without API keys:
- [x] A. `bot.py` imports, and the timeline attaches to real aggregators and a `PipelineWorker`
- [x] B. Frames fed to the observer in the double-booking order print the expected lines and a `MISMATCH` verdict

Needs keys and a microphone (run these yourself):
- [x] C. `uv run bot.py`, connect. After the greeting the timeline shows VAD, TURN and BOT lines
- [x] D. Double booking: "Book me for Friday", wait 2 s, "Actually, wait, make it Saturday". In order: Friday TOOL started, VAD user started speaking, INTERRUPT with `tool_cancel_latency`, TOOL CANCELLED, BACKEND COMMIT Friday with `(tool was already cancelled)`, a second TOOL started for Saturday, its COMMIT
- [x] E. (same session as D) Disconnect. The dump shows two calendar rows, the Friday call with a recorded `CANCELLED` result, and a `MISMATCH` verdict
- [x] F. Let a booking finish, then interrupt "You're all set for...". The INTERRUPT line shows `yield_latency`, and the BOT line shows `interrupted=True` with the words that were spoken
