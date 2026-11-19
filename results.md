# Results

Single live runs of this demo, done by hand by the repo owner. Every number comes from a terminal timeline of this repo; nothing is taken from vendor documentation. Each run is described in full in the spec named in its row (`.kiro/specs/<spec>/tasks.md` and `design.md`). These are single runs, not rates: they show what happened, not how often.

## Setup

| Item | Value | Source |
|---|---|---|
| Pipecat | 1.16.0 (`pipecat-ai[deepgram,openai,runner,silero,webrtc]==1.16.0`) | `pyproject.toml`, `uv.lock`, Pipecat's startup line |
| LLM | OpenAI `gpt-4.1` | Named in the 2026-11-19 logs. For the 2026-11-18 runs the logs say only "OpenAI"; `gpt-4.1` was the default in both `.env.example` and `bot.py` |
| STT | Deepgram `nova-3-general` (Pipecat 1.16.0 default; `bot.py` sets no model) | `pipecat/services/deepgram/stt.py` |
| TTS | Deepgram voice `aura-2-helena-en` (Pipecat 1.16.0 default; `bot.py` sets no voice) | `pipecat/services/deepgram/tts.py` |
| VAD | Silero, defaults (`start_secs=0.2`, `stop_secs=0.2`) | `bot.py`, `pipecat/audio/vad/vad_analyzer.py` |
| `--turn smart` | `TurnAnalyzerUserTurnStopStrategy` with Smart Turn v3 (`smart-turn-v3.2-cpu.onnx`, bundled, CPU) | Pipecat 1.16.0 default |
| `--turn fast` | `SpeechTimeoutUserTurnStopStrategy`, `TURN_FAST_TIMEOUT=0.4` (0.2 in the tuning runs marked below) | `bot.py`, `.env.example` |
| Tool timing | `COMMIT_AT=3.0`, `TOTAL=6.0` | `.env.example`; the timelines show the commit at +3.00 s and the result at +6.00 s |
| Transport | SmallWebRTC, Pipecat runner's browser client | `bot.py` |
| Machine | Linux, Nix dev shell, Python 3.11.18 | Pipecat's startup line in the `llm-cancel` logs |
| Runs logged | 2026-11-18 (policies, timeline) and 2026-11-19 (turn modes, `llm-cancel`) | git history |

## Policies, S2 main script

`--turn smart`. "Book me for Friday.", then the correction about 2 s into the tool call.

| Policy | Spec, check | Calendar | Agent said | Verdict | `tool_cancel_latency` |
|---|---|---|---|---|---|
| `cancel` (before policies existed) | `timeline-and-session-dump`, D | Friday, Saturday | | `MISMATCH: 2 bookings (Friday, Saturday)` | 201 ms |
| `deaf` | `interruption-policies`, D | Friday | "Your appointment is booked for Friday." | `OK: 1 booking, Friday  <- expected for deaf` | none (muted, no interruption) |
| `cancel` | `interruption-policies`, E | Friday, Saturday | "Your appointment is booked for Saturday." | `MISMATCH: 2 bookings (Friday, Saturday)` | 202 ms |
| `safe` | `interruption-policies`, F | Saturday (replaced Friday) | "Your appointment is booked for Saturday." | `OK: 1 booking, Saturday` | 201 ms |
| `llm-cancel` run 1 | `llm-cancel-policy`, D | Saturday (replaced Friday) | "Your appointment is booked for Saturday." | `OK: 1 booking, Saturday` | none (async tool keeps running) |
| `llm-cancel` run 2 | `llm-cancel-policy`, E | Saturday (replaced Friday) | "Your appointment is booked for Friday, and now I'll book you for Saturday instead." | `OK: 1 booking, Saturday` | none |
| `llm-cancel` run 3 | `llm-cancel-policy`, F | Saturday (replaced Friday) | "Your appointment is booked for Saturday." | `OK: 1 booking, Saturday` | none |

- `deaf`: the correction's transcript arrived 3.1 s into the mute and 2.9 s before the unmute, and was dropped.
- `safe`: one earlier run is not counted. The LLM took 2.2 s to answer "Book me for Friday.", so the correction landed before any tool call (S1) and no Friday call was made.

### `llm-cancel` timing

Seconds after `TOOL book_appointment(day=Friday) started`. The Friday write is at 3.00 s and the Friday result at 6.00 s in every run.

| Run | Correction speech starts | Last correction turn closes | Model's cancel | Cancel result | Saturday tool starts |
|---|---|---|---|---|---|
| 1 | 0.52 s | 3.05 s | 4.15 s | cancelled | 8.40 s |
| 2 | 1.98 s | 5.18 s | 7.32 s and 8.08 s | refused twice, Friday had returned at 6.00 s (`LATE`) | 8.93 s and 9.57 s |
| 3 | 2.16 s | 4.22 s | 5.54 s | cancelled | 6.22 s |

- The cancel always came after the Friday write: 1.15 s after it in run 1 and 2.54 s in run 3.
- From the last correction turn closing to the model's cancel: 1.10 s (run 1) and 1.32 s (run 3).
- Run 2: a second reply, "You're now booked for Saturday. Your Friday appointment was also booked earlier; let me know if you want to cancel that.", was never spoken. The Deepgram TTS websocket closed with a keepalive ping timeout, and Pipecat logged that the audio context produced no audio and left the text out of the context.

## Turn modes, S0 script

`turn-detection-modes`, checks D and E. `--policy cancel`, the recording `s0.m4a` ("Book me for Friday, ummm... actually Saturday"). VAD-visible pause: the correction's `VAD user started speaking` minus the previous `VAD user stopped speaking`.

| Mode | Run | Turn closed during the pause? | Friday tool before the correction? | VAD-visible pause | Verdict |
|---|---|---|---|---|---|
| `fast`, 0.2 s | 3 | yes, inside a 0.22 s dip between "Friday" and "ummm" | no (the "ummm" interrupted the LLM, S1) | 2.40 s (after the "ummm") | `OK: 1 booking, Saturday` |
| `fast`, 0.4 s | 4 | yes, 0.40 s after the VAD stop | yes, 1.70 s before | 3.14 s | `MISMATCH: 2 bookings (Friday, Saturday)` |
| `fast`, 0.4 s | 5 | yes | yes, 0.88 s before | 2.22 s | `MISMATCH: 2 bookings (Friday, Saturday)` |
| `fast`, 0.4 s | 6 | yes | yes, 0.59 s before | 2.32 s | `MISMATCH: 2 bookings (Friday, Saturday)` |
| `smart` | S1 | no | no | 2.32 s | `MISMATCH: 2 bookings (Friday, Saturday)` (the model booked Friday, then Saturday, one after the other) |
| `smart` | S2 | no | no | 2.36 s | `OK: 1 booking, Saturday` |
| `smart` | S3 | no | no | 2.26 s | `OK: 1 booking, Saturday` |

- `fast` runs 1 and 2 are not listed: they used the unedited recording and only showed that the wiring works.
- `fast` run 4: `tool_cancel_latency=202ms`. Runs 5 and 6 do not have it logged.
- `smart`: in all three runs the turn closed 0.150 s after the correction's VAD stop with only "Book me for Friday.", and "Actually, Saturday." arrived as a second user message.

## LLM latency: turn close to tool call

The time from `TURN user turn stopped` to `TOOL book_appointment(...) started`. It decides whether a correction lands in S1 or S2.

| Run | Seconds |
|---|---|
| `cancel` (`interruption-policies` E), Saturday call | 0.85 |
| `safe` (`interruption-policies` F), Saturday call | 0.64 |
| `fast` runs 4, 5, 6, Friday call | 1.05, 0.94, 1.33 |
| `llm-cancel` runs 1, 2, 3, Friday call | 1.01, 0.85, 0.73 |
| `safe`, run not counted | no tool call; first token still missing after 2.2 s |

## `tool_cancel_latency`

From caller speech start (VAD onset, back-dated by `start_secs`) to the tool call being cancelled.

| Run | Value |
|---|---|
| `timeline-and-session-dump` D | 201 ms |
| `interruption-policies` E (`cancel`) | 202 ms |
| `interruption-policies` F (`safe`) | 201 ms |
| `turn-detection-modes` run 4 (`fast`) | 202 ms |

## `yield_latency`, S4

From caller speech start to `BotStoppedSpeakingFrame` on the server. Audio already buffered in the browser can play slightly longer.

| Run | `yield_latency` | Committed text | Stops at the interruption? |
|---|---|---|---|
| `timeline-and-session-dump` F | 202 ms | "Your appointment is booked for Friday." (`interrupted=True`) | Not shown. The interruption came about 1.5 s into a short sentence, and the whole sentence was committed |

Unverified: the demo brief's claim that Pipecat commits only the words actually spoken for an interrupted assistant turn. No run interrupted early enough to show it, so the post should not make that claim.
