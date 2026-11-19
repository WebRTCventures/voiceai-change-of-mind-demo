# Tasks: turn-detection-modes

No automated tests. Verification is manual.

## Implementation

- [x] 1. Verify `SpeechTimeoutUserTurnStopStrategy`, `UserTurnStrategies`, the default stop strategy and where the Smart Turn weights live against Pipecat 1.16.0; record in `design.md`
- [x] 2. `bot.py`: `TURNS` dict, `--turn` flag through the same parser as `--policy`, `turn_strategies()` passed as `user_turn_strategies`, `TURN_FAST_TIMEOUT` read per session, startup and session-start print (requirements 1, 2, 3.1, 4.1)
- [x] 3. `timeline.py`: `TURN MODE` line in the dump, `no strategy` label when no stop strategy closed the turn (requirements 4.2, 4.3)
- [x] 4. `.env.example`: `TURN_FAST_TIMEOUT` with a comment, 0.4 after tuning (requirement 3.2)
- [x] 5. `README.md`: run instructions, the two flags, the Smart Turn weights note (requirement from the brief: weights bundled, no download)
- [x] 6. `design.md`: default confirmation, weights, differences from the brief, alternatives, shortcuts (requirement 6.4, 6.5)

## Manual checks

Done without API keys:
- [x] A. `uv run bot.py --turn bogus` is rejected with a usage message. The startup block prints `turn=smart ...` with no flag, `turn=fast (... user_speech_timeout=0.35s)` with `--turn fast` and `TURN_FAST_TIMEOUT=0.35`, and works next to `--policy safe`. (The runner's `main` was stubbed for this check, so no server started.)
- [x] B. Real user aggregator with the strategies from `bot.turn_strategies`, fed synthetic frames: `fast` closes the turn `TURN_FAST_TIMEOUT` after the VAD stop line and prints `(SpeechTimeout)`; `smart` builds `TurnAnalyzerUserTurnStopStrategy` (`turn_strategies("smart")` is `None`). Output in `design.md`
- [x] C. The default Smart Turn model loads from the installed package (`.../smart_turn/data/smart-turn-v3.2-cpu.onnx`), no download

Needs keys and a microphone. **Not run: the agent session that wrote this spec had no `DEEPGRAM_API_KEY`, `OPENAI_API_KEY` or microphone.** Run these yourself with the S0 script: "Book me for Friday, ummm...", pause about 2 s (see the finding in the tuning log: 1 s is too short), "actually Saturday". Use `--policy cancel` (default) so the failure is visible in the dump.

- [x] D. `--turn fast`, tune `TURN_FAST_TIMEOUT` (start at 0.2) until the order below shows on 3 consecutive runs:
  ```
  VAD   user stopped speaking
  TURN  user turn stopped (SpeechTimeout) "..."
  TOOL  book_appointment(day=Friday) started
  VAD   user started speaking      <- the correction
  ```
  After each miss, read the gap between `TURN user turn stopped` and `TOOL ... started`. If it is about 0.7 to 1.1 s, the LLM is the limit and the timeout cannot fix it: lengthen the pause (1.5 s or more) or change `OPENAI_MODEL`, and write that down. If the turn closes late, lower the timeout (no effect below about 0.15 s). Record the final value and set it in `.env.example`
- [x] E. `--turn smart`, 1 or 2 runs: no `TURN user turn stopped` between the first `VAD user stopped speaking` and the correction's `VAD user started speaking`, and one `book_appointment(day=Saturday)` only. Dump: `OK: 1 booking, Saturday`
- [x] F. Screenshot the `smart` and `fast` timelines for the post. Taken by the repo owner from `smart` run S3 and `fast` run 6 (0.4 s). The image files are not in the repo

## Results (to be filled in from the live runs)

Final `TURN_FAST_TIMEOUT`: **0.4 s** (runs 4 to 6, three consecutive hits; 0.2 s missed in run 3). Set in `.env.example` and as the code default.

Tuning log, one line per run: timeout, whether the order was right, gap from `VAD user stopped speaking` to `TURN user turn stopped`, gap from `TURN user turn stopped` to `TOOL ... started`.

- Runs 1 and 2, `fast`, timeout 0.2 s, **not counted**: they used a recording ("Recorder - 20261119-0946(1).m4a", 6.98 s). Both showed the right order for `fast`, which proves the wiring only, not the S0 case. `ffmpeg silencedetect` at -25 dB: "Book me for Friday" 0.95 to 2.30 s, a 0.39 s dip, "ummm" 2.70 to 3.84 s, a 1.59 s pause, "actually Saturday" 5.43 to 6.36 s. The "ummm" is as loud as "Friday" (mean -18.3 dB against -15.7 dB). "ummm" is not in the transcript ("Book me for Friday."), as `design.md` expected.

  What the demo's Silero VAD makes of the file (`vad_file.py`, default parameters, offline):

  | VAD segment | Speaking | Back to quiet |
  |---|---|---|
  | "Book me for Friday" | 1.09 s | 2.46 s |
  | "ummm" | 2.85 s | 3.20 s |
  | "actually Saturday" | 5.57 s | 6.56 s |

  The VAD hears only the first ~0.35 s of the "ummm" (confidence 0.82 to 0.98 until 3.04 s, then 0.43 and falling although the sound runs to 3.84 s). It is a separate segment because the dip before it (0.39 s) is longer than `stop_secs` (0.2 s). Live, run 2 showed no VAD event for the "ummm" at all. One non-speech chunk in the starting state resets the start (`VADAnalyzer._run_analyzer`), so a 0.35 s sound only just over the 0.7 threshold can miss live (browser noise suppression, echo cancellation and Opus all change the audio; not confirmed). So this "ummm" is detected offline and missed live: unreliable.

  | Run | VAD stop to turn close | Turn close to `TOOL started` | `TOOL started` to correction `VAD` start | Notes |
  |---|---|---|---|---|
  | 1 | n/a | 0.81 s | 0.70 s | VAD did not fire for the first sentence. The turn started from the transcript (`Transcription`) and closed 2.4 s later, so `TURN_FAST_TIMEOUT` was not what closed it |
  | 2 | 0.20 s | 1.06 s | 2.24 s | VAD fired normally. The turn closed exactly `TURN_FAST_TIMEOUT` after the VAD stop |
  | 3 | 0.20 s | no Friday call | n/a | miss in S1, see run 3 below |
  | 4 | 0.40 s | 1.05 s | 1.70 s | **hit**, `TURN_FAST_TIMEOUT=0.4`, `s0.m4a` |
  | 5 | 0.40 s | 0.94 s | 0.88 s | **hit** |
  | 6 | 0.40 s | 1.33 s | 0.59 s | **hit**. The VAD split "Friday" and "ummm" by 0.24 s (`9.976` to `10.216`), which would have closed the turn at 0.2 s as in run 3, and 0.4 s bridged it |

- Run 3, `fast`, 0.2 s, `s0.m4a`: **miss (S1), not counted.** The live VAD did not keep "Friday, ummm" as one segment, although offline it does. It saw `9.535-9.732`, `9.913-10.553` and `10.772-11.295`. The gap between the second and third (10.553 to 10.772, 0.22 s) is longer than the turn's 0.2 s timeout, so `TURN user turn stopped (SpeechTimeout) "Book me for Friday."` fired at +10.753. The "ummm" `VAD user started speaking` came 19 ms later (+10.772) and interrupted the LLM before it emitted a tool call, so `book_appointment(Friday)` never started. The turn that the "ummm" opened had no transcript (Deepgram drops the filler), so `SpeechTimeout` could not close it, and it stayed open until "Actually, Saturday." (+14.675). Result: two consecutive user messages, one `book_appointment(Saturday)`, `OK: 1 booking, Saturday`. The VAD-visible silence after the "ummm" was 2.4 s (+11.295 to +13.695), as intended. The strategy did what it is configured to do: it closed 0.20 s after a VAD stop. The timeout is shorter than a dip the live audio contains.
- Next: `TURN_FAST_TIMEOUT=0.4` in `.env`. A start of "ummm" within 0.4 s of the previous stop cancels the pending close (the strategy discards its timers on every VAD start), so the dip is bridged. The turn then closes at about +11.7 (0.4 s after the "ummm" stop at +11.295), the tool starts about 0.8 to 1.1 s later, and the correction's `VAD` start at +13.7 comes after it. Predicted margin about 0.9 s. Leave `.env.example` at 0.2 until a live run confirms the value.
- Run 4, `fast`, `TURN_FAST_TIMEOUT=0.4`, `s0.m4a`: **hit (1 of 3 consecutive).** `VAD user stopped speaking` +10.135, `TURN user turn stopped (SpeechTimeout) "Book me for Friday."` +10.535 (0.40 s later), `TOOL book_appointment(day=Friday) started` +11.580 (1.05 s later), correction `VAD user started speaking` +13.277 (1.70 s after the tool started). The interruption cancelled the tool (`tool_cancel_latency=202ms`), the Friday write landed anyway, then Saturday: `MISMATCH: 2 bookings (Friday, Saturday)`, as `cancel` is expected to. The live VAD saw one segment of 1.24 s, which is "Book me for Friday" only, with no event for the "ummm" (it did see it in run 3). So the VAD-visible silence before the correction was 3.14 s here, not the 1.8 to 2.4 s the file gives when the "ummm" is detected. Whether the VAD sees the "ummm" varies from run to run.
- Runs 5 and 6, `fast`, `TURN_FAST_TIMEOUT=0.4`: **hits (3 of 3 consecutive).** Run 5: one VAD segment of 1.56 s, stop +13.593, turn closed +13.995, `TOOL Friday started` +14.933, correction `VAD` start +15.812. Run 6: two VAD segments (+8.937 to +9.976 and +10.216 to +10.776, a 0.24 s gap), turn closed +11.177 (0.40 s after the last stop), tool +12.511, correction +13.096. Both ended `MISMATCH: 2 bookings (Friday, Saturday)`, as `cancel` should. The margin between `TOOL Friday started` and the correction was 1.70, 0.88 and 0.59 s in runs 4 to 6, and it shrinks with LLM latency (turn close to tool start: 1.05, 0.94, 1.33 s). A slow response (about 2.3 s, seen once earlier) would miss. 0.4 s is the tuned value.
- `smart`, runs S1 to S3 (`s0.m4a`, `--policy cancel`): **the turn stayed open in 3 of 3; a single `book_appointment(Saturday)` in 2 of 3.** VAD-visible silence before the correction: 2.32, 2.36 and 2.26 s, so the 3 s fallback never fired and the model itself held the turn open. Each run closed the turn exactly 0.150 s after the correction's VAD stop with only "Book me for Friday." (the STT safety net, see `design.md`, "Live results"), then a new turn with "Actually, Saturday." started 0.03 to 0.27 s later. S1 ended `MISMATCH: 2 bookings (Friday, Saturday)`: the LLM called Friday, got its result, then called Saturday, sequentially, with no overlap. S2 and S3 ended `OK: 1 booking, Saturday`. The earlier risk (fallback at 3 s) did not occur.

- **Finding from runs 1 and 2: the S0 recording needs two changes, and the second matters for `smart`.**
  1. The pause after the caller stops must be about 2 s as the VAD sees it. The turn closes 0.2 s after the VAD stop, then the LLM takes 0.8 to 1.06 s to emit the tool call, so the correction must start at least about 1.3 s after `VAD user stopped speaking`. With 1 s the correction starts while the LLM is still generating (S1) and no Friday call happens. In this file the VAD-visible silence is 2.2 s after the "ummm" (3.20 to 5.41 s) and 3.1 s after "Friday" (2.30 to 5.41 s).
  2. There must be no VAD-visible gap between "Friday" and "ummm". The 0.39 s dip splits them, so the VAD stops after "Book me for Friday", which is a complete sentence. `smart` analyzes the audio at every VAD stop, so it can close the turn right there, before "ummm" starts, and then `fast` and `smart` look the same. Close the dip to under 0.2 s so the VAD sees one segment ending in the "ummm":
     ```
     ffmpeg -i "Recorder - 20261119-0946(1).m4a" -filter_complex "[0:a]atrim=0:2.34,asetpts=PTS-STARTPTS[a];[0:a]atrim=2.66,asetpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=0:a=1" s0.m4a
     ```
     This removes 0.31 s of the dip and keeps the rest. Check the result with `vad_file.py`: there should be no `QUIET` state between "Friday" and "ummm", and about 2 s of silence before the last segment.
  Result of the cut (`s0.m4a`, `vad_file.py`, offline): one VAD segment from 1.09 s to 3.30 s (the dip is 0.07 s, no `QUIET` between "Friday" and "ummm", and the "ummm" keeps confidence 0.88 to 0.99 from 2.37 to 2.98 s), then 1.79 s of silence until the correction starts (5.09 s, `SPEAKING` at 5.25 s). Prediction for `fast` at 0.2 s: the turn closes about 3.5 s into the file, the tool starts about 4.3 to 4.6 s, the correction's `VAD` start comes at 5.25 s. Margin 0.7 to 0.95 s. A slow LLM response (about 2.3 s, seen once) would miss. Live check: one `VAD user started speaking` and one `stopped` about 2.2 s apart before the tool starts. Two segments mean the live audio lost the "ummm" again.
  Do not change VAD parameters. Read the final pause off the timeline: `VAD user stopped speaking` to the correction's `VAD user started speaking`, minus 0.2 s.
