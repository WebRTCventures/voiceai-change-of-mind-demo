# Results

Numbers measured by running the demo by hand, following `.kiro/specs/release-checks/runbook.md`. Every value here comes from a terminal timeline of this repo. Nothing is taken from vendor documentation.

Empty cells have not been measured yet.

## Setup

Fixed by the code and the pinned package:

| Item | Value | Source |
|---|---|---|
| Pipecat | 1.16.0 (`pipecat-ai[deepgram,openai,runner,silero,webrtc]==1.16.0`) | `pyproject.toml`, `uv.lock` |
| Transport | SmallWebRTC, Pipecat runner's browser client at `http://localhost:7860/client` | `bot.py` |
| STT | Deepgram, `nova-3-general` (Pipecat 1.16.0 default; `bot.py` sets no model) | `pipecat/services/deepgram/stt.py` |
| TTS | Deepgram, voice `aura-2-helena-en` (Pipecat 1.16.0 default; `bot.py` sets no voice) | `pipecat/services/deepgram/tts.py` |
| VAD | Silero, defaults (`start_secs=0.2`, `stop_secs=0.2`) | `bot.py`, `pipecat/audio/vad/vad_analyzer.py` |
| `--turn smart` | `TurnAnalyzerUserTurnStopStrategy` with Smart Turn v3 (`smart-turn-v3.2-cpu.onnx`, bundled, CPU) | Pipecat 1.16.0 default |
| `--turn fast` | `SpeechTimeoutUserTurnStopStrategy`, `user_speech_timeout=TURN_FAST_TIMEOUT` | `bot.py` |

From `.env` and the test machine (fill in from the runs):

| Item | Value |
|---|---|
| `OPENAI_MODEL` | `gpt-4.1` for the `llm-cancel` runs (as recorded in `llm-cancel-policy/tasks.md`; the terminal log does not print it) |
| `COMMIT_AT` / `TOTAL` | 3.0 / 6.0 for the `llm-cancel` runs (Friday commit at +3.00 s and result at +6.00 s in the timelines) |
| `TURN_FAST_TIMEOUT` | |
| Python | 3.11.18 (Pipecat's startup line) |
| uv | |
| OS | Linux, Nix dev shell |
| Browser | |
| Microphone, headphones or speakers | |
| S0 input (live voice or recording) | |
| Date of the runs | |

## Fresh clone

| Result | Notes |
|---|---|
| | |

## Outcome hit rate per policy

S2 main script, `--turn smart`, default tool duration. A run counts only if the Friday tool started before the correction (runbook, counting rule).

| Policy | Expected outcome | Reproduced | Invalid runs (S1) | Notes |
|---|---|---|---|---|
| `deaf` | 1 row, Friday, correction muted | / 5 | | |
| `cancel` | 2 rows, Friday and Saturday, Friday `CANCELLED` in context | / 5 | | |
| `safe` | 1 row, Saturday | / 5 | | |
| `llm-cancel` (optional) | 1 row, Saturday; agent says only Saturday | calendar 3 / 3, speech 2 / 3 (2 runs to go) | 0 | Run 2: the agent said Friday was booked. Details below |

### `llm-cancel` runs

2026-11-19, branch `spec/llm-cancel-policy`. Its `bot.py`, `timeline.py`, `calendar_backend.py`, `.env.example` and `uv.lock` are identical to `main`. These are the same three runs as in `.kiro/specs/llm-cancel-policy/tasks.md`. Times are seconds after `TOOL book_appointment(day=Friday) started`. The Friday write is at 3.00 s and the Friday result at 6.00 s in every run.

| Run | Correction speech starts | Last correction turn closes | Model's cancel | Cancel result | Saturday tool starts | Agent said | Calendar |
|---|---|---|---|---|---|---|---|
| 1 | 0.52 s | 3.05 s | 4.15 s | cancelled | 8.40 s | "Your appointment is booked for Saturday." | Saturday |
| 2 | 1.98 s | 5.18 s | 7.32 s and 8.08 s | refused twice, Friday had returned at 6.00 s (`LATE`) | 8.93 s and 9.57 s | "Your appointment is booked for Friday, and now I'll book you for Saturday instead." | Saturday |
| 3 | 2.16 s | 4.22 s | 5.54 s | cancelled | 6.22 s | "Your appointment is booked for Saturday." | Saturday |

- The cancel always came after the Friday write: 1.15 s after it in run 1 and 2.54 s after it in run 3.
- From the last correction turn closing to the model's cancel: 1.10 s (run 1) and 1.32 s (run 3).
- From the turn "Book me for Friday." closing to the Friday tool starting: 1.01, 0.85 and 0.73 s.
- Run 2: a second reply, "You're now booked for Saturday. Your Friday appointment was also booked earlier; let me know if you want to cancel that.", was never spoken. The Deepgram TTS websocket closed with a keepalive ping timeout, and Pipecat logged that the audio context produced no audio and left the text out of the context.

## S0 hit rate per turn mode

S0 script, `--policy cancel`, 10 attempts per mode, all counted. Hit definitions are in the runbook, check 5.

| Turn mode | Hits | VAD-visible pause (min to max) | Notes on misses |
|---|---|---|---|
| `fast` | / 10 | | |
| `smart` | / 10 | | |

## `tool_cancel_latency`

From caller speech start to the tool call being cancelled (S2). Taken from the `INTERRUPT` lines of the `cancel`, `safe` and `--turn fast` runs.

| n | Min | Median | Max | Values (ms) |
|---|---|---|---|---|
| | | | | |

## `yield_latency`

From caller speech start to `BotStoppedSpeakingFrame` on the server (S4). Audio already buffered in the browser can play slightly longer, which this number does not include.

| n | Min | Median | Max | Values (ms) |
|---|---|---|---|---|
| | | | | |

Committed text after the interruption (S4):

| Run | Committed text | Last word heard | Stops at the interruption? |
|---|---|---|---|
| | | | |
