# Change-of-mind voice agent

Companion demo for a post about turn detection, barge-in and tool calling. A caller books an appointment, then changes their mind while the agent is still writing the booking. The agent is built with Pipecat and runs in your browser. You talk to it, and the terminal prints a timeline of what the agent heard, decided and wrote.

The scenario comes from a production failure described by Krishna Tyagi (Cisco) at IIT RTC 2026. The caller asked for Friday and said "wait, actually Saturday" while the agent was busy scheduling. The agent booked Friday anyway and talked over the caller.

The code is three files, meant to be read in one sitting:

| File | What it holds |
|---|---|
| `bot.py` | The pipeline, the prompt, the `book_appointment` tool, and the `--policy` and `--turn` tables |
| `calendar_backend.py` | A fake slow backend. The write is shielded, so it lands even when the tool call is cancelled |
| `timeline.py` | The terminal timeline, the latency numbers and the end-of-session dump |

## Agent states

The same words from the caller mean different things depending on what the agent is doing. The code, the timeline and this README use these names:

| State | Meaning |
|---|---|
| S0 | User turn not confirmed yet (for example a pause after "Friday, ummm...") |
| S1 | Turn confirmed, LLM generating, no tool call yet |
| S2 | Tool running, agent silent. Nothing is playing, so only the tool can be interrupted |
| S3 | Tool finished, LLM generating the reply. The result is already committed |
| S4 | Agent speaking the confirmation. Classic barge-in |

The demo is about S2. S0 (turn detection) and S4 (barge-in) are the secondary cases.

## Prerequisites

- Python 3.11 or later.
- [uv](https://docs.astral.sh/uv/). It installs the pinned dependencies (Pipecat 1.16.0).
- A Deepgram API key (speech-to-text and text-to-speech) and an OpenAI API key (the LLM).
- A browser with a microphone. Headphones help: the browser's echo cancellation is all that stops the agent from hearing itself.

No Daily or LiveKit account is needed. The audio goes over WebRTC straight from your browser to the bot on your machine. Silero VAD and the Smart Turn v3 model ship inside the `pipecat-ai` package and run on the CPU, so nothing downloads on first run and no GPU is needed.

A Nix flake (`flake.nix`, `.envrc`) is included for NixOS users. Everyone else can ignore it.

## Setup

```
git clone https://github.com/WebRTCventures/voiceai-change-of-mind-demo.git
cd voiceai-change-of-mind-demo
cp .env.example .env      # fill in DEEPGRAM_API_KEY and OPENAI_API_KEY
uv sync
```

## Run

```
uv run bot.py [--policy deaf|cancel|safe|llm-cancel] [--turn smart|fast]
```

Open http://localhost:7860/client and click **Connect**. The agent greets you: "Hi, I can book your appointment. Which day works for you?" Click **Disconnect** to end the session. The terminal then prints the session dump. Click **Connect** again for a new session; you do not need to restart the bot.

The first lines show what you started:

```
STARTUP  policy=cancel  (user mute: none; tool: default; storage: append)
         turn=smart (stop strategy: TurnAnalyzer, Smart Turn v3)
```

### `--policy`: what happens when the caller speaks while the tool runs

| Command | Policy |
|---|---|
| `uv run bot.py --policy deaf` | The caller is muted while the tool runs, so the correction is never heard |
| `uv run bot.py --policy cancel` (or no flag) | Pipecat's default. The interruption cancels the tool call, but the backend write still lands, and the backend appends every write |
| `uv run bot.py --policy safe` | Like `cancel`, and the backend keeps one booking per caller. A write from an older turn is rejected (upsert with a turn-number guard) |
| `uv run bot.py --policy llm-cancel` | The model decides. The tool call keeps running through the interruption, and Pipecat gives the model a `cancel_book_appointment` tool. Storage as `safe` |

### `--turn`: what decides the caller has finished talking

| Command | Turn mode |
|---|---|
| `uv run bot.py --turn smart` (or no flag) | Pipecat's default stop strategy. After each pause, the Smart Turn v3 audio model judges whether the sentence is finished, so "Book me for Friday, ummm..." can stay open |
| `uv run bot.py --turn fast` | A speech-timeout stop strategy. The turn closes `TURN_FAST_TIMEOUT` seconds (default 0.4) after the caller goes quiet, whatever they sounded like |

The flags combine, for example `uv run bot.py --policy safe --turn fast`.

### Settings in `.env`

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_MODEL` | `gpt-4.1` | The LLM |
| `COMMIT_AT` | `3.0` | Seconds after the tool starts until the booking is written |
| `TOTAL` | `6.0` | Seconds after the tool starts until the tool returns |
| `TURN_FAST_TIMEOUT` | `0.4` | `--turn fast` only: seconds of silence before the turn closes |
| `LOG_LEVEL` | `WARNING` | Pipecat's own log. `DEBUG` shows LLM requests and STT and TTS connections. The timeline prints at any level |

The tool is slow on purpose (6 s) so that a human has time to change their mind while it runs.

## The scripts

### S2, main script: correction while the tool runs

1. Say "Book me for Friday."
2. Watch the terminal for `TOOL  book_appointment(day=Friday) started`.
3. About 2 s later, say "Actually, wait, make it Saturday."
4. Stay quiet until the agent has finished talking, then disconnect.

Goal: exactly one appointment, on Saturday, and the agent says so.

Wait for the `TOOL` line before you speak. If you speak while the LLM is still generating (S1), no Friday call ever starts and the run tests nothing. A slow LLM response (about 2 s instead of the usual 0.7 to 1.1 s) makes this happen even with good timing.

### S0: correction before the turn is confirmed

1. Say "Book me for Friday, ummm..." with no gap between "Friday" and "ummm".
2. Stay silent for about 2 s.
3. Say "actually Saturday".

Run it with `--policy cancel` so a double booking shows in the dump. Compare `--turn fast` and `--turn smart`.

The brief this demo was built from suggested a 1 s pause. In the live runs 1 s was too short. The `fast` turn closes about 0.6 s after you go quiet (0.2 s VAD plus the 0.4 s timeout), and the LLM takes another 0.8 to 1.3 s to call the tool. A correction inside that time lands in S1, not S2. Keep "ummm" attached to "Friday": a gap of more than 0.2 s between them lets the VAD end the segment on "Book me for Friday", which sounds complete, and then both modes behave the same.

### S4: barge-in on the confirmation

1. Say "Book me for Friday." and let the booking finish.
2. When the agent starts the confirmation ("Your appointment is booked for Friday."), interrupt it within the first second, for example with "Actually, make it Saturday."

Run it with `--policy safe`, so that a re-booking leaves one row. The confirmation is a short sentence, so a late interruption finds it already finished.

## Expected outcome per policy (S2 main script)

| Policy | Calendar | What the agent says | Verdict line in the dump |
|---|---|---|---|
| `deaf` | 1 row, Friday | Friday | `OK: 1 booking, Friday  <- expected for deaf: the correction was muted` |
| `cancel` | 2 rows, Friday and Saturday | Saturday | `MISMATCH: 2 bookings (Friday, Saturday)` |
| `safe` | 1 row, Saturday (Friday replaced) | Saturday | `OK: 1 booking, Saturday` |
| `llm-cancel` | 1 row, Saturday (Friday replaced) | Depends on the model. Saturday in 2 of 3 live runs; in the third the agent also said Friday was booked | `OK: 1 booking, Saturday` |

The verdict compares the calendar with the last booking the model asked for and did not cancel. It cannot know what the caller wanted. In `deaf` the model never hears the correction, so `OK` there means the failure is complete. In `llm-cancel` an `OK` can sit next to a reply that told the caller the wrong day.

For S0 with `--policy cancel`:

| Turn mode | What happens | Verdict |
|---|---|---|
| `fast` | The turn closes during the pause, the Friday tool starts, the correction interrupts it | `MISMATCH: 2 bookings (Friday, Saturday)` |
| `smart` | The turn stays open through the pause, so no Friday tool call starts before the correction | `OK: 1 booking, Saturday` in 2 of 3 live runs. In the third the model booked Friday, then Saturday |

`smart` makes the race rarer for a caller who trails off. It does not remove it: a complete "Book me for Friday." followed by a correction 2 s later is S2 in either mode.

Measured hit rates are in [results.md](results.md).

## What to look for in the timeline

Each line is `seconds since session start`, a category, and the event. All excerpts below are copied from live runs on Pipecat 1.16.0 with Deepgram, `gpt-4.1` and the browser client. Some lines in between are left out.

Two latency numbers appear on `INTERRUPT` lines, both measured from when the caller started speaking:
- `tool_cancel_latency`: until the tool call is cancelled (S2).
- `yield_latency`: until the bot stops speaking (S4). It is measured on the server, so audio already buffered in the browser can play a little longer.

### `deaf`

```
 +13.417  TOOL       book_appointment(day=Friday) started  seq=1
 +13.418  MUTE       user mute started
 +16.419  BACKEND    COMMIT Friday seq=1
 +16.510  MUTE       transcript while muted "Actually, make it Saturday."
 +19.419  TOOL       book_appointment seq=1 result {"status": "booked", "day": "Friday"}
 +19.420  MUTE       user mute stopped
 +20.533  BOT        bot started speaking
 +22.500  BOT        assistant turn stopped interrupted=False "Your appointment is booked for Friday."
OK: 1 booking, Friday  <- expected for deaf: the correction was muted
```

- `user mute started` follows the `TOOL ... started` line, and `user mute stopped` follows the result.
- The correction shows only as `MUTE  transcript while muted`. Speech-to-text still runs, but Pipecat drops the transcript before it reaches the LLM. There is no `VAD`, `TURN` or `INTERRUPT` line for it, and the context has no user message for it.
- The agent confirms Friday after the caller asked for Saturday.

### `cancel`

```
  +9.619  TOOL       book_appointment(day=Friday) started  seq=1
 +11.340  VAD        user started speaking
 +11.340  TURN       user turn started (VAD)
 +11.341  INTERRUPT  interruption  tool_cancel_latency=202ms
 +11.341  TOOL       book_appointment seq=1 CANCELLED
 +12.619  BACKEND    COMMIT Friday seq=1 (tool was already cancelled)
 +13.149  TURN       user turn stopped (TurnAnalyzer) "Actually, make it Saturday."
 +13.997  TOOL       book_appointment(day=Saturday) started  seq=2
 +16.997  BACKEND    COMMIT Saturday seq=2
 +19.998  TOOL       book_appointment seq=2 result {"status": "booked", "day": "Saturday"}
 +22.773  BOT        assistant turn stopped interrupted=False "Your appointment is booked for Saturday."
MISMATCH: 2 bookings (Friday, Saturday)
```

- Pipecat interrupts in S2 although nothing is playing, and cancels the tool call (`CANCELLED`, with `tool_cancel_latency`).
- `COMMIT Friday ... (tool was already cancelled)`: the backend write was already on its way and lands anyway. This is the main lesson of the demo.
- In the dump, the Friday call's tool message reads `CANCELLED`. That is what the model sees, so it books Saturday and says "Saturday", while the calendar holds both days.

### `safe`

```
+10.153  TOOL       book_appointment(day=Friday) started  seq=1
+11.650  VAD        user started speaking
+11.650  TURN       user turn started (VAD)
+11.651  INTERRUPT  interruption  tool_cancel_latency=201ms
+11.651  TOOL       book_appointment seq=1 CANCELLED
+13.154  BACKEND    COMMIT Friday seq=1 (tool was already cancelled)
+13.422  TURN       user turn stopped (TurnAnalyzer) "Actually,"
+13.625  TURN       user turn stopped (TurnAnalyzer) "it Saturday."
+14.264  TOOL       book_appointment(day=Saturday) started  seq=3
+17.265  BACKEND    COMMIT Saturday seq=3 (replaced Friday seq=1)
+23.129  BOT        assistant turn stopped interrupted=False "Your appointment is booked for Saturday."
CALENDAR (1 row)
  Saturday   seq=3
OK: 1 booking, Saturday
```

- Up to the Friday commit it is the same as `cancel`. The fix is in the backend.
- `COMMIT Saturday ... (replaced Friday seq=1)`: one row per caller, newest turn wins.
- `seq` is the user-turn number. Here one spoken correction was split into two turns, so Saturday got seq=3. The guard only needs `seq` to go up.
- `BACKEND REJECT <day> seq=<n> (stale, held seq=<n>)` would mean an older write arrived after a newer one and was refused. With the fixed 6 s tool, Friday always lands first, so the main script shows a replace, not a reject.

### `llm-cancel`

No live timeline excerpt is recorded in this repo yet. The lines to look for:

- `INTERRUPT  interruption  (book_appointment seq=1 keeps running)`: the interruption does not cancel the async tool call.
- `TOOL  model called cancel_book_appointment(...)`, then `book_appointment seq=1 CANCELLED by the model` and `cancel_book_appointment cancelled <id>`, or `cancel_book_appointment refused: ...` when nothing is left to cancel.
- `... result {...}  LATE: caller spoke since, injected as a developer message`: the Friday result arrived after the correction. Pipecat tells the model to pass it on, so the agent may announce Friday.

In the three live runs the Friday write landed before the model's cancel every time (the commit is at 3 s, the cancel came at 4.15 s and 5.54 s). The one-row calendar comes from the upsert storage, not from the cancel.

### `--turn fast` (S0 script)

```
 +10.135  VAD        user stopped speaking
 +10.535  TURN       user turn stopped (SpeechTimeout) "Book me for Friday."
 +11.580  TOOL       book_appointment(day=Friday) started  seq=1
 +13.277  VAD        user started speaking
 +13.278  INTERRUPT  interruption  tool_cancel_latency=202ms
 +13.278  TOOL       book_appointment seq=1 CANCELLED
```

- `user turn stopped (SpeechTimeout)` comes exactly `TURN_FAST_TIMEOUT` (0.4 s) after `VAD user stopped speaking`.
- The Friday tool starts before the correction's `VAD user started speaking`. From here on it is the S2 race, and the policy decides the outcome.
- "ummm" is missing from the transcript. Deepgram drops the filler, which is why only an audio model can hear that the sentence is unfinished.

### `--turn smart` (S0 script)

```
 +10.859  VAD        user stopped speaking
 +13.120  VAD        user started speaking
 +13.819  VAD        user stopped speaking
 +13.969  TURN       user turn stopped (TurnAnalyzer) "Book me for Friday."
 +14.000  INTERRUPT  interruption
 +14.000  TURN       user turn started (Transcription)
 +14.150  TURN       user turn stopped (TurnAnalyzer) "Actually, Saturday."
 +16.028  TOOL       book_appointment(day=Saturday) started  seq=2
```

- No `user turn stopped` line between the first `VAD user stopped speaking` and the correction's `VAD user started speaking`, 2.26 s later. Smart Turn judged "Book me for Friday, ummm" unfinished.
- No Friday tool call starts before the correction.
- The correction still arrives as a second user message: the first turn closes with only "Book me for Friday." 0.15 s after the VAD stop, and "Actually, Saturday." starts a new turn. The model sees both messages. In 2 of 3 live runs it booked only Saturday. In the third it booked Friday and then Saturday, one after the other.

### S4: barge-in

No live timeline excerpt is recorded in this repo yet. The lines to look for:

- `INTERRUPT  interruption  yield_latency=<n>ms`, followed by `BOT  bot stopped speaking`. In one earlier live run `yield_latency` was 202 ms.
- `BOT  assistant turn stopped interrupted=True "..."`. Pipecat should commit only the words that were actually spoken. In that earlier run the interruption came about 1.5 s into a short sentence and the whole sentence was committed, so interrupt early to see the text cut off.

## Output

The terminal shows the timeline and, on disconnect, the session dump: policy, turn mode, the calendar rows for this session, every context message the model saw, and the verdict. Each write also prints the whole calendar and saves it to `calendar.json`.

Pipecat's own log is hidden once a session starts. Set `LOG_LEVEL=DEBUG` in `.env` to see it. The uvicorn request lines and the few lines logged while the browser connects come from the runner and stay.

## Shortcuts and their production approach

This is teaching code. Each shortcut below makes the demo easier to build or read.

| Shortcut | Production approach |
|---|---|
| Fake in-process backend with `asyncio.shield` standing in for a remote API | Real HTTP API. Treat a cancelled request as "outcome unknown" and reconcile by reading state back |
| Tool duration fixed at about 6 s so a human can hit the window | Real latency varies. Measure the window and log stale writes |
| No confirmation step before booking | Draft then commit: hold the slot, confirm with the caller, then make the irreversible write |
| Upsert keyed by session id, turn counter as `seq` | Business-level idempotency key plus a server-side version or `If-Match` precondition |
| Agent silent during the tool | Contextual filler speech or an async tool, which moves the race from S2 to S4 |
| Browser WebRTC with the browser's echo cancellation | Telephony adds gateway and jitter-buffer delay plus echo that can make the agent interrupt itself |
| One caller, state lost on restart | Persistent store, many sessions |
| Default Silero and Smart Turn settings | Tune VAD, interruption strategies and backchannel filtering per deployment |

The design notes for each part, including what was verified against Pipecat 1.16.0 and the full live-run logs, are in `.kiro/specs/`.
