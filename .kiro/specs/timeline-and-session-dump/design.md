# Design: timeline-and-session-dump

## Verified against Pipecat 1.16.0

Checked in the installed package (`.venv/lib/python3.11/site-packages/pipecat`), not from the brief.

| Used | Where verified |
|---|---|
| User aggregator events `on_user_turn_started(aggregator, strategy)`, `on_user_turn_stopped(aggregator, strategy, message)`, `on_user_mute_started(aggregator)`, `on_user_mute_stopped(aggregator)`. `message.content` is the transcript | `llm_response_universal.py` (`_register_event_handler` calls near line 733, `_call_event_handler` calls) |
| Assistant aggregator event `on_assistant_turn_stopped(aggregator, message)`. `message.content`, `message.interrupted` | `llm_response_universal.py` ~2770, `AssistantTurnStoppedMessage` |
| `BaseObserver.on_push_frame(data)` with `data.frame`, `data.direction`. `observe_every_push=False` delivers each frame once, at its first push | `observers/base_observer.py` |
| Frames: `VADUserStartedSpeakingFrame`, `VADUserStoppedSpeakingFrame`, `InterruptionFrame`, `BotStartedSpeakingFrame`, `BotStoppedSpeakingFrame`, `FunctionCallsStartedFrame` (`function_calls` with `function_name`, `tool_call_id`, `arguments`), `FunctionCallResultFrame`, `FunctionCallCancelFrame` | `frames/frames.py` |
| Many frames are sent in both directions as separate copies. The VAD frames carry no `broadcast_sibling_id` (`_queued_broadcast_frame`), so the first live run printed every VAD line twice. The observer ignores every non-DOWNSTREAM push | `llm_response_universal.py` `_queued_broadcast_frame`, `frame_processor.py` `broadcast_frame` |
| `PipelineWorker(pipeline, params=..., observers=[...])` | `pipeline/worker.py` |
| `context.get_messages()` returns the messages list (plain dicts for our messages) | `processors/aggregators/llm_context.py` |
| Strategy objects have no friendly name. Default start strategies are `VADUserTurnStartStrategy` and `TranscriptionUserTurnStartStrategy`. Default stop strategy is `TurnAnalyzerUserTurnStopStrategy` with `LocalSmartTurnAnalyzerV3` | `turns/user_turn_strategies.py` |

## Differences from the brief

1. **Pipecat already ships `SpeakingObserver` and `FunctionCallObserver`** (`pipecat.observers`). We do not use them. They are two separate observers, each with its own queue, so the INTERRUPT line and the TOOL CANCELLED line could print in either order. We need one ordered stream to print INTERRUPT first. One small observer in `timeline.py` covers the same frames.
2. **Aggregators have no VAD, interruption, bot-speaking or function-call events.** The brief's list of aggregator events is right for turns, mute and assistant turn, so the observer is needed only for the rest.
3. **Stop strategy name.** The brief's example prints `SmartTurn`. The installed class is `TurnAnalyzerUserTurnStopStrategy`, so the timeline prints `TurnAnalyzer` (class name without the `UserTurnStopStrategy` suffix). Start strategies print as `VAD` or `Transcription`.
4. **Event handlers run as separate tasks** (`BaseObject._call_event_handler` uses `create_task` unless the event is registered sync). Observers run on their own queue as well. So a TURN line and a nearby observer line can swap places by a few milliseconds. The timestamps stay correct to a few milliseconds, only the print order can differ.

## The brief's claim about the cancelled call: confirmed

The brief says the tool message is `"IN_PROGRESS"` while a sync call runs, is replaced by the result, and becomes `"CANCELLED"` on cancel. In 1.16.0:

- `LLMAssistantAggregator._handle_function_call_in_progress` adds an assistant `tool_calls` message and a `tool` message with content `"IN_PROGRESS"` (`llm_response_universal.py` ~2238).
- `_handle_function_call_cancel` calls `_update_function_call_result(..., "CANCELLED")` when `cancel_on_interruption` is true (line ~2417). The content is the literal string `CANCELLED`. A call with `cancel_on_interruption=False` is different: it adds a developer message built by `async_tool_messages.build_cancelled_message` and the tool message is left alone.
- `LLMService._handle_interruptions` cancels the handler task and broadcasts `FunctionCallCancelFrame`. The frame reaches the assistant aggregator, which is after the transport output in our pipeline.

So the context holds the assistant call message for Friday with a tool message `CANCELLED`. The part "the model believes the call did not happen" is not verified: what the model infers from `CANCELLED` depends on the model. The dump shows what is recorded, nothing more. The recorded text also depends on the aggregator receiving the cancel frame before the session ends.

## Components

### `timeline.py`
- `Timeline(BaseObserver)` is both the observer and the owner of the state. `bot.py` creates one per session.
- `attach(user_aggregator, assistant_aggregator)` registers the TURN, MUTE and assistant-turn handlers.
- `on_push_frame` prints VAD, BOT speaking, TOOL and INTERRUPT lines.
- `commit(row)` is the backend hook. `reject(day, seq, reason)` is the reject hook, defined now and not called yet.
- `dump(context)` prints calendar, context and verdict.
- State used for the numbers: `speech_start` (set on `VADUserStartedSpeakingFrame`), `bot_speaking` (S4), `running` (non-empty means S2).

### INTERRUPT line
The latency is only known after the interruption frame, when the bot stops or the tool is cancelled. So the line is held and printed when its numbers are known, just before the BOT stopped or TOOL CANCELLED line. If the interruption happens with neither (S0, S1, S3), it prints at once without numbers. If another VAD, bot-start or tool line arrives first, the line prints with `n/a` for the missing number (for example a later spec keeps the tool running). The example in the brief shows `210ms` while the INTERRUPT and CANCELLED lines are 10 ms apart. We measure to the cancel frame, so the number is the true interval and can differ by that much from the printed times.

"User speech start" is the VAD start frame's observed time minus its `start_secs` (0.2 s), because the VAD confirms speech that long after it began. Without the back-dating, `tool_cancel_latency` read 1 ms in the first live run, since the aggregator interrupts in the same instant as the VAD frame. The VAD line itself prints at the confirmation time.

The onset is cleared when a user turn stops. The second live run had a turn started by `TranscriptionUserTurnStartStrategy` with no VAD event for that speech, and the old code reused the previous utterance's onset (`tool_cancel_latency=7089ms`). Now the INTERRUPT line prints `n/a` for that case, since there is no onset to measure from.

### Backend coupling
`calendar_backend.py` gets one module variable `on_commit = None` and two lines in `_write` that call it with the stored row. `bot.py` sets `calendar_backend.on_commit = timeline.commit`. The backend does not import the timeline.

### Cancelled commit
`Timeline` records the `seq` of each cancelled tool call. A commit with that `seq` prints `(tool was already cancelled)`.

### `seq`
The TOOL line shows `seq=<number of stopped user turns>`. `Timeline` keeps its own count in its `on_user_turn_stopped` handler, the same rule as `user_turns` in `bot.py`. This duplicates one counter to avoid touching how `bot.py` computes `seq`.

### Dump
- Calendar: the rows reported through `on_commit` during this session. The backend's list is module-level and shared across sessions, so this is the session's own view. Every row is appended by `_write`, so it matches the backend.
- Context: `context.get_messages()`, one line per message. Tool calls print name, arguments and id. Tool messages print the id and the recorded content.
- Verdict: `OK: 1 booking, <day>` when there is exactly one row and its day equals the day of the last `book_appointment` call the model made (case-insensitive). Otherwise `MISMATCH: <n> bookings (<days>)`. The last call is recorded from `FunctionCallsStartedFrame`.
- `bot.py` calls `timeline.dump(context)` in `on_client_disconnected`, before `runner.cancel()`.

## Shortcuts

| Shortcut | Production approach |
|---|---|
| `print` to stdout, mixed with the backend's own CALENDAR block | Structured logs with a session id and a trace span per turn |
| `calendar_backend.on_commit` is one module-level callback, so one session at a time | Per-session event bus or the backend returns an event stream |
| Verdict and expected day come from the model's last `book_appointment` call, trusting the tool name | Compare against a business-level record of what the caller confirmed |
| `Timeline` duplicates the `seq` counter | One source of the turn number, passed to both |
| Held INTERRUPT line is flushed by the next observer line | Emit two events (interruption, then outcome) and let the reader join them |
| Dump runs only on client disconnect. A commit that lands after the dump is missing from it, but still printed live | Flush on session end after in-flight backend work settles |
| Strategy names derived from class names | Give strategies explicit labels |

## Not verified

No live run: the sandbox has no Deepgram or OpenAI keys or microphone. Checked here: `timeline.py` imports and attaches to real `LLMContextAggregatorPair` and `PipelineWorker`, and a script that feeds real Pipecat frame objects to the observer in the order of the double-booking scenario printed the expected lines, the held INTERRUPT line (`tool_cancel_latency`), a late commit flagged as after the cancel, an S4 `yield_latency`, and a `MISMATCH` verdict. The "Done when" run with the real script remains a manual check (tasks D to F).
