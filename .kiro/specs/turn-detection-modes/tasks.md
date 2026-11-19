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

Needs keys and a microphone. **Not run: the agent session that wrote this spec had no `DEEPGRAM_API_KEY`, `OPENAI_API_KEY` or microphone.** Run these yourself with the S0 script: "Book me for Friday, ummm...", pause about 2 s (see the finding in the tuning log: 1 s is too short), "actually Saturday". Use `--policy cancel` (default) so the failure is visible in the dump.

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

- Runs 1 and 2, `fast`, timeout 0.2 s, **not counted**: they used a recording ("Recorder - 20261119-0946(1).m4a", 6.98 s). `silencedetect` at -25 dB: "Book me for Friday" 0.95 to 2.30 s, a 0.39 s dip, "ummm" 2.70 to 3.84 s, a 1.59 s pause, "actually Saturday" 5.43 to 6.36 s. In run 2 the correction started 4.5 s after the first speech, as in the file, so the file played whole. But the VAD produced one segment of 1.24 s (just "Book me for Friday") and no event for "ummm", so with the default Silero settings "ummm" counts as silence. The bot heard about 3.1 to 3.5 s of silence instead of 1.6 s. That is past Smart Turn's 3 s fallback, so `smart` would also close the turn, and the two modes cannot be told apart. "ummm" is also not in the transcript ("Book me for Friday."), which `design.md` expected. Both runs showed the right order for `fast`, which proves the wiring only.

  | Run | VAD stop to turn close | Turn close to `TOOL started` | `TOOL started` to correction `VAD` start | Notes |
  |---|---|---|---|---|
  | 1 | n/a | 0.81 s | 0.70 s | VAD did not fire for the first sentence. The turn started from the transcript (`Transcription`) and closed 2.4 s later, so `TURN_FAST_TIMEOUT` was not what closed it |
  | 2 | 0.20 s | 1.06 s | 2.24 s | VAD fired normally. The turn closed exactly `TURN_FAST_TIMEOUT` after the VAD stop |

- **Finding from runs 1 and 2: the S0 pause must be longer than 1 s.** The turn closes 0.2 s after the VAD stop, then the LLM takes 0.8 to 1.06 s to emit the tool call. The correction must start after both, so at least about 1.3 s after `VAD user stopped speaking` (about 1.5 s after the caller stops, since VAD reports the stop 0.2 s late). With the brief's 1 s pause the correction starts while the LLM is still generating (S1) and no Friday call happens. Fix the recording, not the VAD: raise the volume of the "ummm" segment (2.70 to 3.84 s) until the VAD reports it, for example `-af "volume=enable='between(t,2.7,3.84)':volume=4"`. Then the silence the bot hears should be about 1.6 s. Check it on the timeline: `VAD user stopped speaking` to the correction's `VAD user started speaking`, minus 0.2 s. A pause of about 2 s is the target, so lengthen the file's pause a little if the 1.6 s run misses. `smart` still holds the turn open then: its silence fallback is 3 s (`SmartTurnParams.stop_secs`).
