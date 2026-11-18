# Tasks: turn-detection-modes

No automated tests. Verification is manual.

## Implementation

- [x] 1. Verify `SpeechTimeoutUserTurnStopStrategy`, `UserTurnStrategies`, the default stop strategy and where the Smart Turn weights live against Pipecat 1.16.0; record in `design.md`
- [x] 2. `bot.py`: `TURNS` dict, `--turn` flag through the same parser as `--policy`, `turn_strategies()` passed as `user_turn_strategies`, `TURN_FAST_TIMEOUT` read per session, startup and session-start print (requirements 1, 2, 3.1, 4.1)
- [x] 3. `timeline.py`: `TURN MODE` line in the dump, `no strategy` label when no stop strategy closed the turn (requirements 4.2, 4.3)
- [x] 4. `.env.example`: `TURN_FAST_TIMEOUT=0.2` with a comment (requirement 3.2)
- [x] 5. `README.md`: run instructions, the two flags, the Smart Turn weights note (requirement from the brief: weights bundled, no download)
- [x] 6. `design.md`: default confirmation, weights, differences from the brief, alternatives, shortcuts (requirement 6.4, 6.5)

## Manual checks

Done without API keys:
- [x] A. `uv run bot.py --turn bogus` is rejected with a usage message. The startup block prints `turn=smart ...` with no flag, `turn=fast (... user_speech_timeout=0.35s)` with `--turn fast` and `TURN_FAST_TIMEOUT=0.35`, and works next to `--policy safe`. (The runner's `main` was stubbed for this check, so no server started.)
- [x] B. Real user aggregator with the strategies from `bot.turn_strategies`, fed synthetic frames: `fast` closes the turn `TURN_FAST_TIMEOUT` after the VAD stop line and prints `(SpeechTimeout)`; `smart` builds `TurnAnalyzerUserTurnStopStrategy` (`turn_strategies("smart")` is `None`). Output in `design.md`
- [x] C. The default Smart Turn model loads from the installed package (`.../smart_turn/data/smart-turn-v3.2-cpu.onnx`), no download

Needs keys and a microphone. **Not run: the agent session that wrote this spec had no `DEEPGRAM_API_KEY`, `OPENAI_API_KEY` or microphone.** Run these yourself with the S0 script: "Book me for Friday, ummm...", pause about 1 s, "actually Saturday". Use `--policy cancel` (default) so the failure is visible in the dump.

- [ ] D. `--turn fast`, tune `TURN_FAST_TIMEOUT` (start at 0.2) until the order below shows on 3 consecutive runs:
  ```
  VAD   user stopped speaking
  TURN  user turn stopped (SpeechTimeout) "..."
  TOOL  book_appointment(day=Friday) started
  VAD   user started speaking      <- the correction
  ```
  After each miss, read the gap between `TURN user turn stopped` and `TOOL ... started`. If it is about 0.7 to 1.1 s, the LLM is the limit and the timeout cannot fix it: lengthen the pause (1.5 s or more) or change `OPENAI_MODEL`, and write that down. If the turn closes late, lower the timeout (no effect below about 0.15 s). Record the final value and set it in `.env.example`
- [ ] E. `--turn smart`, 1 or 2 runs: no `TURN user turn stopped` between the first `VAD user stopped speaking` and the correction's `VAD user started speaking`, and one `book_appointment(day=Saturday)` only. Dump: `OK: 1 booking, Saturday`
- [ ] F. Screenshot the `smart` and `fast` timelines for the post

## Results (to be filled in from the live runs)

Final `TURN_FAST_TIMEOUT`: _not tuned yet, shipped default 0.2 s_

Tuning log, one line per run: timeout, whether the order was right, gap from `VAD user stopped speaking` to `TURN user turn stopped`, gap from `TURN user turn stopped` to `TOOL ... started`.

- _empty_

Check the transcript on the `TURN user turn stopped` line. If it includes "ummm", the filler-word assumption in `design.md` is wrong. Update that paragraph.
