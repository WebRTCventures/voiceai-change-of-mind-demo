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
| `OPENAI_MODEL` | |
| `COMMIT_AT` / `TOTAL` | |
| `TURN_FAST_TIMEOUT` | |
| Python | |
| uv | |
| OS | |
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
| `llm-cancel` (optional) | 1 row, Saturday; agent says only Saturday | calendar / 5, speech / 5 | | |

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
