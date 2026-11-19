# Design: llm-cancel-policy

## Purpose

`llm-cancel` is the "let the model decide" option. The framework does not cancel the Friday call when the caller interrupts. It keeps running, and the model is given a tool to cancel it. What happens next depends on what the model does with the correction: cancel Friday, book Saturday on top of it, ask a question, or something else. That dependence on the model is the point the post makes about this option. The demo records each live run instead of promising one outcome.

Storage is `upsert` with the seq guard, as in `safe`, so the calendar ends with one row whatever the model does. The difference from `safe` is in what the model believes and says, not in the row count.

## Verified against Pipecat 1.16.0

Checked in the installed package (`.venv/lib/python3.11/site-packages/pipecat`) and with offline probes (see Verification), not from the brief.

| Used | Where verified |
|---|---|
| `from pipecat.adapters.llm.schemas.direct_function import tool_options`. `tool_options(fn, *, cancel_on_interruption=True, timeout_secs=None, cancellable_by_llm=False)` sets `_pipecat_*` attributes on `fn` and returns it unchanged. Called with no options it sets the defaults, the same as no decorator | `adapters/llm/schemas/direct_function.py` `tool_options` (~290) |
| A direct function in `LLMContext(tools=[...])` is registered automatically, and its options resolve "explicit argument > decorator > default" | `services/llm_service.py` `_register_direct_function`, `_resolve_tool_option` (~1398 to 1500) |
| `cancellable_by_llm=True` is ignored, with a warning, unless `cancel_on_interruption=False` | `llm_service.py` `_resolve_cancellable_by_llm` (~1460) |
| **Cancel tool name: `cancel_book_appointment`.** `CANCEL_TOOL_PREFIX = "cancel_"`, `cancel_tool_name(name)`. Schema: one optional string argument `tool_call_id`, no required arguments | `utils/async_tool_cancellation.py` (~40 to 90), `llm_service.py` `_sync_cancel_tools` (~2234) |
| The cancel tool is sent to OpenAI next to `book_appointment`. Probe output: `tools sent: ['book_appointment', 'cancel_book_appointment']` | `adapters/llm/base_llm_adapter.py` (~398, `builtin_tools` appended to the standard tools); probe below |
| Two blocks are appended to our system prompt for this policy only: `ASYNC TOOL CANCELLATION` (a cancellable tool exists) and `ASYNC TOOLS` (an async tool exists). The other policies send the prompt unchanged (probe) | `llm_service.py` `_compose_system_instruction` (~915), `async_tool_cancellation.py` `ASYNC_TOOL_CANCELLATION_INSTRUCTIONS`, `processors/aggregators/async_tool_messages.py` `ASYNC_TOOL_INSTRUCTIONS` (~110) |
| An interruption cancels only calls with `cancel_on_interruption=True`. The `InterruptionFrame` is still sent in S2 (the bot is "not waiting for the user" while a call runs), so the in-flight LLM response and TTS are interrupted, but `book_appointment` keeps running | `llm_service.py` `_handle_interruptions` (~1100), `llm_response_universal.py` `_on_user_turn_started` (~1495) |
| When an async call starts, the context gets the assistant tool-call message and a `role="tool"` placeholder whose content is JSON `{"type": "async_tool", "status": "running", ...}` with the text "This tool is still running... Do not call it again". Not `IN_PROGRESS` | `llm_response_universal.py` `_handle_function_call_in_progress` (~2209), `async_tool_messages.py` `_STARTED_DESCRIPTION` (~78) |
| No inference runs when the async call starts, so the agent is still silent in S2 unless the model wrote text along with the call | `_handle_function_call_in_progress` (no context push) |
| **How a late result enters the context.** When the result arrives, `_is_deferred` scans the context after the placeholder. If a `user` or `developer` message follows it (other calls' tool messages, assistant text and other calls' async-tool messages are skipped), the result is **appended as a new `role="developer"` message** `{"type": "async_tool", "status": "finished", "result": ...}` whose description says "You must convey this result to the user, even if the conversation has moved on". Otherwise the placeholder is overwritten in place, as for a sync call | `llm_response_universal.py` `_is_deferred` (~2686), `_handle_function_call_finished` (~2377), `async_tool_messages.py` `_FINAL_DESCRIPTION` (~122) |
| **When.** The result frame runs inference (`run_llm` defaults to on for a non-`None` result). If the bot is speaking, the context push waits until it stops; if the user is speaking, it waits for the turn | `llm_response_universal.py` `_handle_function_call_result`, `_maybe_push_context` |
| OpenAI keeps the `developer` role (`supports_developer_role` is `True` for `OpenAILLMService`), so the late result reaches the model as a developer message, not converted to `user` | `services/openai/base_llm.py` (~362), probe |
| A cancel by the model: `_cancel_tool_handler` cancels the task (the handler sees `CancelledError`), broadcasts `FunctionCallCancelFrame`, then returns `{"cancelled": <id>, "function_name": ...}` with `run_llm=True`. The context gets a `developer` message with result `"CANCELLED: this tool call was cancelled before it returned a result"` | `llm_service.py` `_cancel_tool_handler` (~2271), `_cancel_function_call_tasks`; `llm_response_universal.py` `_handle_function_call_cancel` (~2404) |
| With two `book_appointment` calls running and no `tool_call_id`, the cancel tool refuses and lists both ids (`"2 book_appointment calls are running: ..."`), again with `run_llm=True` | `_cancel_tool_handler` (~2304) |
| The cancel tool's own call is left out of `FunctionCallsStartedFrame` and `on_function_calls_started`. It still produces `FunctionCallInProgressFrame` and `FunctionCallResultFrame`, which is what the timeline reads | `llm_service.py` `user_visible_calls` (~1887), `_run_function_call` |
| `FunctionCallInProgressFrame.cancel_on_interruption` tells the timeline whether a call is async | `frames/frames.py` `FunctionCallInProgressFrame` |
| `async_tool_messages.parse_message(msg)` decodes the async-tool JSON for the dump | `async_tool_messages.py` `parse_message` |

## Differences from the brief

1. **Confirmed:** `cancellable_by_llm` needs `cancel_on_interruption=False`, and the advertised tool is `cancel_<tool_name>`, here `cancel_book_appointment`.
2. **The system prompt is not the brief's for this policy.** Pipecat appends its `ASYNC TOOL CANCELLATION` and `ASYNC TOOLS` guidance (about 300 words). Part of what the model "decides" comes from Pipecat's text, not ours. The tool options cause it, so it stays within "a mapping row plus tool options"; it is not something we add.
3. **The context bookkeeping differs from the brief's `IN_PROGRESS` / `CANCELLED`.** Those strings are for sync calls. Async calls use JSON `async_tool` messages, and a late result or a cancel arrives as a `developer` message.
4. **Two instructions pull against each other.** Our prompt says "If the caller changes the day, call book_appointment again with the new day". Pipecat's placeholder for the running Friday call says "Do not call it again". Which one the model follows is part of the outcome.
5. **Cancelling Friday does not stop the Friday write.** The cancel tool cancels the Pipecat task. The backend write is shielded (the demo's remote-API stand-in), so it lands at `COMMIT_AT` (3 s) anyway. The model can only call the cancel tool after the caller's correction ends, its turn closes, and an LLM response comes back, about 4 to 5 s into the tool with the main script. So the Friday row is normally written before the cancel, and the cancel only stops the Friday result from reaching the model. Pipecat's own `tool_options` docstring says the same: the LLM reaches the cancel tool a few seconds in at best. The one-row calendar comes from the upsert, not from the cancel.
6. **A cancel and a re-book in the same response can refuse.** The service runs a response's calls in parallel (`run_in_parallel=True`, the default), so `book_appointment(Saturday)` is already running when `cancel_book_appointment()` runs. With two calls running and no `tool_call_id`, Pipecat refuses and lists both ids, and the model gets another turn to pick one. It could cancel Friday, cancel Saturday by mistake, or move on. Seen in the offline check (variant `cancel+rebook`).

## Policy as configuration

```python
LLM_CANCELLABLE = {"cancel_on_interruption": False, "cancellable_by_llm": True}
POLICIES = {
    # name          user mute strategies (classes)          tool options      storage
    "deaf":       {"mute": [FunctionCallUserMuteStrategy], "tool": {},              "storage": "append"},
    "cancel":     {"mute": [],                             "tool": {},              "storage": "append"},
    "safe":       {"mute": [],                             "tool": {},              "storage": "upsert"},
    "llm-cancel": {"mute": [],                             "tool": LLM_CANCELLABLE, "storage": "upsert"},
}
```

`run_bot` passes `tool_options(book_appointment, **POLICIES[policy]["tool"])` in the context's tool list. With `{}` that is the Pipecat default, so `deaf`, `cancel` and `safe` behave as before. `describe()` prints the options: `policy=llm-cancel  (user mute: none; tool: cancel_on_interruption=False, cancellable_by_llm=True; storage: upsert)`, and `tool: default` for the other rows.

The pipeline, the prompt, the tool function and the backend are unchanged. `calendar_backend.py` is not touched.

## Timeline and dump changes

New or changed lines (`timeline.py`):

```
INTERRUPT  interruption  (book_appointment seq=1 keeps running)
TOOL       model called cancel_book_appointment()
TOOL       book_appointment seq=1 CANCELLED by the model
TOOL       cancel_book_appointment cancelled call_xxx
TOOL       cancel_book_appointment refused: 2 book_appointment calls are running
TOOL       book_appointment seq=1 result {"status": "booked", "day": "Friday"}  LATE: caller spoke since, injected as a developer message
```

- The observer records which running calls are async from `FunctionCallInProgressFrame.cancel_on_interruption`. An interruption only waits for `tool_cancel_latency` when a sync call is running. For async calls it notes `keeps running` instead.
- The cancel tool is recognised by `CANCEL_TOOL_PREFIX` (imported from Pipecat, not hard-coded). Its `FunctionCallInProgressFrame` prints `model called ...`. A `FunctionCallCancelFrame` that arrives while it runs is marked `by the model`. Its result prints `cancelled <id>` or `refused: <reason up to the first colon>` (the dump has the full reason).
- **`LATE` rule.** The line is marked when the call is async and a user turn has stopped since it started (`self.turns > seq`). This mirrors Pipecat's `_is_deferred` for this app: the only other message that would defer a result is a `developer` message, and the app's only one is the greeting, which comes before any call. Pipecat writes the user message to the context when the turn's inference is triggered, at about the same moment as `on_user_turn_stopped` (same millisecond in the offline check), so the two can only disagree for a result that lands in that gap. The dump shows the real outcome: a deferred result is a `developer  async_tool finished id=...` line.
- Dump: async-tool messages print as `async_tool <status> [id=...] [result]` without Pipecat's long description, for example `tool  id=call_x async_tool running` and `developer async_tool finished id=call_x {"status": "booked", "day": "Friday"}`.
- Verdict: compares the calendar with the last `book_appointment` call the model did not cancel. If the model cancelled every call: `OK: 0 bookings (none), the model cancelled every booking call`, or `MISMATCH: 1 booking (Friday), the model cancelled every booking call` when the shielded write landed. For `deaf`, `cancel` and `safe` the main script gives the same verdicts as before (in `cancel` and `safe` the cancelled call is Friday and the last uncancelled one is Saturday, as before).

## What can happen in a live run

Times from the main script: tool starts at 0, Friday commit at 3 s, Friday result at 6 s, correction starts about 2 s in.

| The model... | Calendar (upsert) | Verdict | What the caller probably hears |
|---|---|---|---|
| cancels Friday, then books Saturday (two responses) | Saturday, replacing Friday | `OK: 1 booking, Saturday` | Saturday. No Friday result arrives |
| cancels and books in one response | Saturday | `OK` | Depends on the second try after the refusal (difference 6) |
| books Saturday without cancelling | Saturday, replacing Friday | `OK: 1 booking, Saturday` | Possibly both: Friday's result arrives `LATE` at about 6 s, before Saturday's (about 10 s), and Pipecat tells the model to convey it. The agent may say Friday is booked |
| asks a question ("Saturday instead of Friday?") | Friday | `OK: 1 booking, Friday` (the model never asked for Saturday) | The question, then the late Friday result. The verdict is OK although the caller wanted Saturday; the run notes must say so |
| cancels Friday and does not re-book | Friday (shielded write) | `MISMATCH: 1 booking (Friday), the model cancelled every booking call` | That Friday was cancelled, while the backend holds it |

Not a prediction of frequency. The live runs decide.

## Verification

Offline, no API keys (`tasks.md` checks A to C). The harness used the real `OpenAILLMService` function-call machinery, the real context aggregators, `Timeline` and the backend, with `COMMIT_AT=0.6`, `TOTAL=1.6` and only the model's choices scripted. Excerpts:

Variant `rebook` (books Saturday without cancelling):
```
  +0.006  TOOL       book_appointment(day=Friday) started  seq=1
  +0.607  BACKEND    COMMIT Friday seq=1
  +0.806  INTERRUPT  interruption  (book_appointment seq=1 keeps running)
  +0.807  TURN       user turn stopped (TurnAnalyzer) "Actually, wait, make it Saturday."
  +0.807  TOOL       book_appointment(day=Saturday) started  seq=2
  +1.409  BACKEND    COMMIT Saturday seq=2 (replaced Friday seq=1)
  +1.607  TOOL       book_appointment seq=1 result {"status": "booked", "day": "Friday"}  LATE: caller spoke since, injected as a developer message
  +2.409  TOOL       book_appointment seq=2 result {"status": "booked", "day": "Saturday"}
  ...
  developer async_tool finished id=call_42e592 {"status": "booked", "day": "Friday"}
OK: 1 booking, Saturday
```
Saturday's result was not deferred although Friday's developer message came after its placeholder, because Pipecat skips other calls' async-tool messages. The timeline agreed.

Variant `cancel-only`:
```
  +0.807  TOOL       model called cancel_book_appointment()
  +0.807  TOOL       book_appointment seq=1 CANCELLED by the model
  +0.807  TOOL       cancel_book_appointment cancelled call_5cb993
  ...
  developer async_tool finished id=call_5cb993 CANCELLED: this tool call was cancelled before it returned a result
MISMATCH: 1 booking (Friday), the model cancelled every booking call
```

Variant `cancel+rebook` (both calls in one response): `cancel_book_appointment refused: 2 book_appointment calls are running`, and the Friday result then arrived `LATE`. Variant `question`: no tool call, Friday result `LATE`, `OK: 1 booking, Friday`. The same harness with `--policy cancel` and `safe` printed `MISMATCH: 2 bookings (Friday, Saturday)` and `OK: 1 booking, Saturday`, as before.

Live: three runs by the repo owner, recorded in `tasks.md`.

## Shortcuts

| Shortcut | Production approach |
|---|---|
| The model decides whether to cancel, with no check of what it decided | Decide in code. The application knows a newer booking supersedes the running one and cancels or reconciles it; the model only talks |
| Cancelling the Pipecat task stands in for cancelling the booking, and the shielded write lands anyway | A cancel endpoint on the real API, or a compensating write. Treat a cancelled request as "outcome unknown" and read the state back |
| The late Friday result is handed to the model with Pipecat's "you must convey this result" text, so the agent may announce a booking that was replaced | Filter or rewrite stale results before they reach the model (for example, drop a result whose seq is older than the held booking) |
| The `LATE` mark mirrors Pipecat's deferral rule from turn counts, not from the context | Read the outcome from the context, or from an event if Pipecat exposes one |
| Verdict compares with the model's last uncancelled call, so a model that asked a question and booked nothing new gets `OK` on Friday | Compare against what the caller confirmed |
| `tool_options` mutates the per-session tool function in place | Fine here (one function per session). With a shared module-level tool, register it with explicit options instead |
