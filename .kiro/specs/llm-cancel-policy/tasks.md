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
- [x] C. Offline harness (real service, aggregators, timeline, backend; model choices scripted), output in `design.md`: `rebook` gives `LATE` Friday result and `OK: 1 booking, Saturday`; `cancel-only` gives `CANCELLED by the model` and `MISMATCH: 1 booking (Friday), the model cancelled every booking call`; `cancel+rebook` in one response gives `refused: 2 book_appointment calls are running`; `question` gives `OK: 1 booking, Friday`. `cancel` and `safe` keep their verdicts

Needs keys and a microphone (run these yourself). **Not run by the agent that wrote this spec: no `OPENAI_API_KEY`, `DEEPGRAM_API_KEY` or microphone in its sandbox.**

Main script, `uv run bot.py --policy llm-cancel`: "Book me for Friday", wait for the `TOOL book_appointment(day=Friday) started` line, then about 2 s later "Actually, wait, make it Saturday." Then stay quiet until the agent has finished talking (at least 10 s after the correction, so the late Friday result and the Saturday result both arrive), and disconnect. A run where no Friday call starts before the correction is an S1 case and does not count (see `interruption-policies/design.md`).

For each run, note: what the model did (cancelled the Friday call, re-booked without cancelling, asked a question, something else), whether a `LATE` line appeared and what the agent said after it, the calendar, and the verdict line.

- [ ] D. Run 1
- [ ] E. Run 2
- [ ] F. Run 3

## Results (to be filled in from the live runs)

| Run | What the model did | `LATE` result | What the agent said | Calendar | Verdict |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
