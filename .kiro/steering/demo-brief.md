# Demo Brief: "Change of Mind" Voice Agent

## Purpose
This repo is the companion demo for a blog post about three voice AI concepts: **turn detection**, **barge-in** (the user interrupting the agent), and **tool calling**. Readers clone it, run it, talk to it, and read the code. The code is teaching material first.

## The scenario
A caller books an appointment, then changes their mind while the agent is still writing the booking. It is based on a real production failure described by Krishna Tyagi (Cisco) at IIT RTC 2026: the caller asked for Friday, said "wait, actually Saturday" while the agent was busy scheduling, and the agent booked Friday anyway and talked over the caller.

Main script:
    Agent: "Hi, I can book your appointment. Which day works for you?"
    User:  "Book me for Friday."
    Agent: [calls book_appointment(day="Friday"), silent while the backend works, about 6 s]
    User:  (about 2 s later) "Actually, wait, make it Saturday."
    Goal:  exactly one appointment, on Saturday, and the agent says so.

The tool takes only `day` (Monday to Saturday). No time, no name, so the LLM never needs a follow-up question before calling it.

## Agent states
The same user speech means different things depending on what the agent is doing. Use these names in code comments, logs and docs:

| State | Meaning |
|---|---|
| S0 | User turn not confirmed yet (e.g. a pause after "Friday, ummm...") |
| S1 | Turn confirmed, LLM generating, no tool call emitted yet |
| S2 | Tool running, agent silent. Nothing is playing, so "interrupt the speech" has nothing to interrupt. Only the tool is in flight. |
| S3 | Tool finished, LLM generating the reply. The result is already committed. |
| S4 | Agent speaking the confirmation. Classic barge-in. |

The demo focuses on S2, with S0 (turn detection) and S4 (classic barge-in) as secondary cases:
- S0 script: "Book me for Friday, ummm...", pause about 1 s, "actually Saturday".
- S4 script: let a booking finish, then interrupt "You're all set for Friday...".

## Stack
- Pipecat (Python 3.11+), managed with `uv`. Pin the version in `pyproject.toml`.
- `SmallWebRTCTransport` with the Pipecat runner's built-in browser client at `http://localhost:7860/client`. No Daily or LiveKit account, no custom frontend.
- Silero VAD (Pipecat default). Smart Turn v3 as the default turn stop strategy.
- Deepgram for STT and TTS. OpenAI for the LLM, model name from `.env`.
- Two API keys total: `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`.

Run command:
    uv sync
    uv run bot.py [--policy ...] [--turn ...]

## Repository layout (target)
    README.md
    pyproject.toml
    .env.example          # DEEPGRAM_API_KEY, OPENAI_API_KEY, OPENAI_MODEL, COMMIT_AT, TOTAL, ...
    bot.py                # pipeline, prompt, --policy and --turn flags (~150 lines target)
    calendar_backend.py   # fake backend: shielded commit, append/upsert, seq guard (~60 lines)
    timeline.py           # timeline, latency numbers, end-of-session dump (~120 lines)
Three Python files. A reader should be able to read all of it in one sitting.

## System prompt
    You book appointments for a clinic. Appointments are by day only (Monday to Saturday).
    As soon as the caller names a day, call book_appointment with that day. Do not ask for confirmation.
    If the caller changes the day, call book_appointment again with the new day.
    Keep replies to one short sentence.

## Principles
- **Simplicity over production readiness.** Take shortcuts that make the demo easier to build and read, and list each one in the spec's design.md with its production approach.
- **Verify Pipecat APIs against the installed version.** Pipecat changes quickly. Every class name, import, event name and parameter in a design must be checked against the installed package (source or docs for that version), not taken from memory or from this brief. If something below turns out wrong, say so in design.md and follow the installed version.
- **No automated tests.** Verification is manual: run the bot, talk, read the timeline. tasks.md lists the manual checks.
- **No pipeline forks.** Policies and turn modes are configuration. One pipeline, a small mapping from flag value to settings.
- **Readable output.** Timeline lines and the end-of-session dump will appear as screenshots in the post. Keep them short and consistent.

## Known shortcuts and their production approach
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

## Framework facts from the research (verify each against the installed version)
These come from Pipecat docs and from reading Pipecat's `main` branch in November 2026. Treat them as hypotheses to confirm.
- **Interruptions cover the tool-running state.** When a user turn starts and interruptions are enabled, Pipecat interrupts unless the bot is waiting for the user, meaning while it is thinking, speaking, or running a function call. So in S2 the user's speech triggers an interruption even though no audio is playing. (Seen in `llm_response_universal.py`, `_on_user_turn_started`.)
- **Sync tools are cancelled on interruption by default.** The LLM service cancels registered functions with `cancel_on_interruption=True` (`LLMService._handle_interruptions`). The handler receives `asyncio.CancelledError`. Work the handler started outside its own task (or inside `asyncio.shield`) is not cancelled.
- **Context bookkeeping for tool calls.** When a call starts, the context gets an assistant tool-call message plus a tool message whose content is `"IN_PROGRESS"`. On result it is replaced with the result. On cancel of a sync call it becomes `"CANCELLED"`. So after a cancel, the model believes the call did not happen, even if the backend committed.
- **`@tool_options`** on a direct-function tool supports `cancel_on_interruption` (default True; False makes the call async), `timeout_secs`, and `cancellable_by_llm` (only works with `cancel_on_interruption=False`; Pipecat then advertises a `cancel_<tool_name>` tool to the model).
- **User mute strategies** are set through `LLMUserAggregatorParams`. `FunctionCallUserMuteStrategy` mutes user input from `FunctionCallsStartedFrame` until all calls finish (`FunctionCallResultFrame`) or are cancelled (`FunctionCallCancelFrame`).
- **Turn events** on the context aggregators: `on_user_turn_started` (with the start strategy), `on_user_turn_stopped` (with the stop strategy and transcript), `on_user_mute_started` / `on_user_mute_stopped`, `on_assistant_turn_stopped` (with the assistant text and an `interrupted` flag). Only words actually spoken are committed for an interrupted assistant turn.
- **Turn detection.** Silero VAD defaults: `start_secs=0.2`, `stop_secs=0.2`. Pipecat recommends leaving VAD `stop_secs` alone and tuning waiting in the stop strategy. The default stop strategy uses Smart Turn v3 (an audio model that runs after VAD detects silence and predicts whether the utterance is complete). A speech-timeout stop strategy (`SpeechTimeoutUserTurnStopStrategy`, `user_speech_timeout`, default 0.6 s) is the simpler alternative.
- **Observers.** Pipecat ships a debug log observer, a turn tracking observer and a user-bot latency observer. They are useful references for a custom timeline.
