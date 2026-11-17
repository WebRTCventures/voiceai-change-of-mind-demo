# Design: baseline-booking-agent

## Verified against Pipecat 1.16.0

Pinned in `pyproject.toml` as `pipecat-ai[webrtc,deepgram,openai,silero,runner]==1.16.0`. Every API below was checked in the installed package, and the structure follows the current docs quickstart (`docs.pipecat.ai/pipecat/get-started/quickstart`).

| Used | Where verified |
|---|---|
| `PipelineWorker`, `PipelineParams` from `pipecat.pipeline.worker` | `PipelineTask` and `PipelineRunner` are deprecated aliases since 1.3.0 |
| `WorkerRunner` from `pipecat.workers.runner`, `add_workers()` then `run()` | `workers/runner.py` |
| `worker.rtvi.event_handler("on_client_ready")` for the greeting | `PipelineWorker` enables RTVI by default (`pipeline/worker.py`) |
| `create_transport(runner_args, {"webrtc": ...})`, `main()` from `pipecat.runner.run` | `runner/utils.py`, `runner/run.py` |
| `DeepgramSTTService(api_key=)`, `DeepgramTTSService(api_key=)` (default voice `aura-2-helena-en`) | `services/deepgram/` |
| `OpenAILLMService(settings=OpenAILLMService.Settings(model=, system_instruction=))` | `services/openai/llm.py` |
| `LLMContext(tools=[book_appointment])` auto-registers a direct function with default options | `LLMService._sync_registered_tool_handlers`; schema from signature and docstring checked |
| `LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())`, default stop strategy is Smart Turn v3 | `turns/user_turn_strategies.py` docstring |
| `on_user_turn_stopped` handler `(aggregator, strategy, message)` | `llm_response_universal.py` |
| Session id: `runner_args.webrtc_connection.pc_id` | `transports/smallwebrtc/connection.py` |

Differences from the brief and the quickstart repo:
- The brief mentions `@tool_options`. It is not needed: default options are what we want, and the decorator is only for overrides.
- The `pipecat-quickstart` GitHub repo still shows `PipelineTask`/`PipelineRunner` and `on_client_connected` for the greeting. The docs and 1.16.0 use `PipelineWorker`/`WorkerRunner` and `on_client_ready`, so we follow those.
- The docs quickstart uses Cartesia TTS and `OpenAIResponsesLLMService`. We use Deepgram TTS (per the brief) and `OpenAILLMService` (Chat Completions).
- `pyproject.toml` has no direct `python-dotenv` dependency. It comes with the `runner` extra, and `bot.py` imports it as the quickstart does.

## Components

### `bot.py`
- `run_bot(transport, runner_args)` builds the pipeline: `transport.input() -> stt -> user_aggregator -> llm -> tts -> transport.output() -> assistant_aggregator`.
- `book_appointment(params, day)` is a closure inside `run_bot`, so it can see `session_id` and the `user_turns` counter. Pipecat extracts the tool schema from its signature and docstring.
- `user_turns` increments in the `on_user_turn_stopped` handler (S0 to S1). The first "Friday" turn gives `seq=1`, the "Saturday" turn gives `seq=2`.
- Greeting: on `on_client_ready`, a `developer` message tells the LLM to say the greeting text exactly, then `LLMRunFrame` is queued. The greeting is then in the context.
- Plug-in points, marked with `PLUG-IN POINT` comments: the flag mapping (near the top) and the timeline (before `PipelineWorker` is created).

### `calendar_backend.py`
- `book(day, caller_id, seq, mode="append")` creates the work as a task and `await asyncio.shield(work)`. Cancelling the caller raises `CancelledError` at the shield only. The task keeps running and writes the row.
- `_book` reads `COMMIT_AT` and `TOTAL` from the environment at call time, sleeps `COMMIT_AT`, writes, then sleeps the remaining `TOTAL - elapsed`.
- `_write(..., mode)` appends in `"append"` mode and raises for unknown modes. The upsert branch goes there.
- `_show()` prints the calendar and rewrites `calendar.json` after each write.

## Expected baseline flow

1. "Book me for Friday": tool starts, Friday row at about 3 s, tool returns at about 6 s.
2. "Actually, make it Saturday" during those 6 s: the user turn interrupts the tool call. The handler gets `CancelledError` (the brief says the context then records the call as cancelled; not checked here), but the shielded task still writes Friday at 3 s. The LLM calls the tool again with Saturday, and Saturday is written 3 s later. Result: Friday and Saturday rows.

## Shortcuts

| Shortcut | Production approach |
|---|---|
| In-process fake backend with `asyncio.shield` standing in for a remote API | Real HTTP API. Treat a cancelled request as "outcome unknown" and reconcile by reading state back |
| Fixed 3 s commit and 6 s total so a human can hit the window | Real latency varies. Measure the window and log stale writes |
| No confirmation before booking | Draft then commit: hold the slot, confirm, then make the irreversible write |
| `seq` is a per-session count of stopped user turns, incremented in an event handler. Event handlers run as separate tasks, so ordering against the LLM call is not guaranteed in theory. In practice the LLM takes far longer than the increment | Pass an explicit idempotency key and version from the turn that produced the call |
| `caller_id` is the WebRTC `pc_id` | Authenticated caller identity |
| Calendar kept in a module-level list, file rewritten synchronously on each write, no locking | Persistent store with transactions |
| One caller, state lost on restart | Persistent store, many sessions |
| `day` is a free string; the model is trusted to pass Monday to Saturday | Validate against an enum and reject bad input |
| Greeting is produced by the LLM from a "say exactly" instruction | Fixed `TTSSpeakFrame`, or a pre-generated audio clip |
| Default Silero and Smart Turn settings | Tune VAD, interruption strategies and backchannel filtering per deployment |
| Model default `gpt-4.1` if `OPENAI_MODEL` is unset | Require explicit config |

## Findings for later specs

- The runner's `main()` calls a strict `argparse` `parse_args()` (`runner/run.py`). `--policy` and `--turn` will be rejected unless they are removed from `sys.argv` before `main()` runs. The flag mapping spec must handle this.
- In the Kiro sandbox the runner failed to bind the IPv6 loopback, so the browser client was not reached there. Passing the runner's `--host` option with an IPv4 address is a possible workaround, untested. Not expected on a normal machine.
