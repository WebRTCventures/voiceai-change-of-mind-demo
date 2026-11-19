# Tasks: llm-cancel-policy

No automated tests. Verification is manual.

## Implementation

- [x] 1. Verify `tool_options`, `cancellable_by_llm`, the generated cancel tool's name, what is sent to the model, and how late async results enter the context, against Pipecat 1.16.0; record in `design.md` (requirement 4)
- [x] 2. `bot.py`: `tool` column in `POLICIES`, `llm-cancel` row, `tool_options(book_appointment, **...)` in the context, tool options in `describe()` (requirement 1)
- [x] 3. `timeline.py`: async calls tracked from `FunctionCallInProgressFrame`, `keeps running` on `INTERRUPT`, `model called cancel_...`, `CANCELLED by the model`, cancel result, `LATE` on deferred results, short async-tool messages in the dump, verdict ignores cancelled calls (requirements 2, 3)
- [x] 4. `README.md`: `llm-cancel` in the run line and a `--policy` section
- [x] 5. `design.md`: purpose, verified facts, differences from the brief, outcome table, shortcuts

## Manual checks

Done without API keys:
- [x] A. `uv run bot.py --policy bogus` is rejected and lists `llm-cancel`. `--policy llm-cancel --host 127.0.0.1` prints `STARTUP  policy=llm-cancel  (user mute: none; tool: cancel_on_interruption=False, cancellable_by_llm=True; storage: upsert)` and the server starts. `--policy safe` prints `tool: default`
- [x] B. Registration probe: with the `llm-cancel` options the service registers `book_appointment` (async, cancellable) and `cancel_book_appointment`, sends both to OpenAI, and appends the two async-tool blocks to the system prompt. With `{}`, only `book_appointment` and the prompt unchanged
- [x] C. Offline harness `llm_cancel_offline.py` in this directory (real service, aggregators, timeline, backend; model choices scripted). Run from the repo root: `uv run python .kiro/specs/llm-cancel-policy/llm_cancel_offline.py <rebook|cancel-only|cancel+rebook|question> [llm-cancel|cancel|safe]`. Output in `design.md`: `rebook` gives `LATE` Friday result and `OK: 1 booking, Saturday`; `cancel-only` gives `CANCELLED by the model` and `MISMATCH: 1 booking (Friday), the model cancelled every booking call`; `cancel+rebook` in one response gives `refused: 2 book_appointment calls are running`; `question` gives `OK: 1 booking, Friday`. `cancel` and `safe` keep their verdicts

Needs keys and a microphone (run these yourself). **Not run by the agent that wrote this spec: no `OPENAI_API_KEY`, `DEEPGRAM_API_KEY` or microphone in its sandbox.**

Main script, `uv run bot.py --policy llm-cancel`: "Book me for Friday", wait for the `TOOL book_appointment(day=Friday) started` line, then about 2 s later "Actually, wait, make it Saturday." Then stay quiet until the agent has finished talking (at least 10 s after the correction, so the late Friday result and the Saturday result both arrive), and disconnect. A run where no Friday call starts before the correction is an S1 case and does not count (see `interruption-policies/design.md`).

For each run, note: what the model did (cancelled the Friday call, re-booked without cancelling, asked a question, something else), whether a `LATE` line appeared and what the agent said after it, the calendar, and the verdict line.

- [x] D. Run 1: the model cancelled Friday, then booked Saturday. `OK: 1 booking, Saturday`
- [x] E. Run 2: the cancel came after Friday had finished and was refused twice. The model booked Saturday twice and said Friday was booked. `OK: 1 booking, Saturday`, but what the agent said was wrong
- [x] F. Run 3: the model cancelled Friday, then booked Saturday. `OK: 1 booking, Saturday`
- [x] G. Screenshot for the post, taken by the repo owner from run 2: timeline lines only (+23.932 to +64.553 and the verdict), Pipecat's log hidden (the Deepgram TTS warnings are log lines, not timeline lines), and the empty `assistant turn stopped ""` lines, `CALENDAR` blocks and the second VAD pair left out. Run 3 is the clean contrast. The image file is not in the repo

## Results

Live runs by the repo owner, 2026-11-19: Pipecat 1.16.0, `gpt-4.1`, Deepgram, SmallWebRTC, `--turn smart`, main script. Times are seconds into the Friday tool call (`TOOL book_appointment(day=Friday) started` = 0). Friday commits at 3.0 and would return at 6.0.

| Run | What the model did | `LATE` result | What the agent said | Calendar | Verdict |
|---|---|---|---|---|---|
| 1 | **Cancelled the Friday call** (at 4.15 s, with `tool_call_id`), then booked Saturday in a second response | none, Friday was cancelled before it returned | "Your appointment is booked for Saturday." | Saturday seq=3 (replaced Friday seq=1) | `OK: 1 booking, Saturday` |
| 2 | **Tried to cancel too late, then re-booked twice.** Friday returned at 6.0 s, before the model replied. The model then called `cancel_book_appointment` twice with Friday's id, and both were refused (`no book_appointment call is running`). Then it called `book_appointment(Saturday)` twice | Friday at 6.0 s, injected as a developer message (dump agrees) | "Your appointment is booked for Friday, and now I'll book you for Saturday instead." A second reply, "You're now booked for Saturday. Your Friday appointment was also booked earlier; let me know if you want to cancel that.", was lost to a Deepgram TTS error and never spoken | Saturday seq=3 (replaced Friday, then replaced itself) | `OK: 1 booking, Saturday`. **The verdict is misleading**: the backend is right, but the agent told the caller Friday was booked, and the model believes there are two bookings |
| 3 | **Cancelled the Friday call** (at 5.54 s, with `tool_call_id`), then booked Saturday 0.7 s later | none | "Your appointment is booked for Saturday." | Saturday seq=3 (replaced Friday seq=1) | `OK: 1 booking, Saturday` |

**Overall: mixed.** The backend ended with exactly one booking, on Saturday, in 3 of 3 runs. The caller heard only Saturday in 2 of 3 runs. In run 2 the caller was told Friday was booked.

Per-run notes:

- **Run 1.** The correction started 0.52 s into the tool and was split into two turns ("Actually, wait." / "Make it Saturday."), so seq is 3. The last turn closed at 3.05 s, the Friday commit had landed at 3.00 s, and the model's cancel came at 4.15 s, 1.1 s after the turn closed. So the cancel stopped Friday's result but not its write. The Friday row was then replaced by the upsert. Saturday's call started 4.2 s after the cancel result. That gap is not explained by this log (`LOG_LEVEL=WARNING` hides the LLM requests); in run 3 the same step took 0.7 s.
- **Run 2.** The correction started at 1.98 s, but the caller spoke slowly and the last turn ("Make it Saturday.") only closed at 5.18 s. Friday returned at 6.00 s, before any model response, so it went in as a `LATE` developer message, and the cancel tool had nothing left to cancel. The paired actions (two refused cancels 0.76 s apart, two Saturday calls 0.64 s apart) look like two inference chains running one after the other: one from the user turn and one from the late Friday result, each continued by its refusal (`run_llm=True`). That is a reading of the timings and is not confirmed. `LOG_LEVEL=DEBUG` would show the LLM requests. Both Saturday writes had seq=3, and an equal seq replaces, so the calendar kept one row. With `append` storage this run would have left two Saturday rows next to Friday's. The spoken reply came after both Saturday results, and it still described Friday as booked.
- **Run 3.** The correction started at 2.16 s, split into "Actually," / "Saturday." (seq 3). The Friday commit landed at 3.00 s and the cancel came at 5.54 s, so again the write had already happened. The run was clean.
- **All runs:** the Friday write landed before the model could cancel, 1.15 s and 2.54 s before the cancel in runs 1 and 3. In every run the upsert, not the cancel, is what left one row. This matches `design.md`, difference 5.
- **Not seen:** a cancel and a re-book in the same response (difference 6), a cancel with no arguments (the model passed `tool_call_id` every time, although only one call was running), a question to the caller, and a cancel without re-booking.
- **Context order.** In runs 1 and 3 the dump puts the developer `CANCELLED` message before the assistant's `cancel_book_appointment` call. `FunctionCallCancelFrame` is a `SystemFrame` and `FunctionCallInProgressFrame` is a `ControlFrame`, so the aggregator handles the cancel first. The model still booked Saturday next, so the order did no visible harm here.
