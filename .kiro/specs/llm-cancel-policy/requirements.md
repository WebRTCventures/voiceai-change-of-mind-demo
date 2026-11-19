# Requirements: llm-cancel-policy

## Introduction

Adds a fourth value to the `--policy` flag: `llm-cancel`, the "let the model decide" option. The scenario, agent states (S0 to S4) and principles are in `.kiro/steering/demo-brief.md`. The `deaf`, `cancel` and `safe` policies, the append and upsert storage modes and the seq guard already exist (spec `interruption-policies`).

Main script: the caller asks for Friday, the tool runs about 6 s, and about 2 s in the caller says "Actually, wait, make it Saturday."

## Requirements

### 1. The `llm-cancel` policy
**User story:** As a reader, I want a policy where the model, not the framework, decides what to do with the running Friday call, so that I can see how that choice plays out.

Acceptance criteria:
1. `uv run bot.py --policy llm-cancel` selects it. The other policies and the default (`cancel`) are unchanged.
2. It is one new row in the `POLICIES` mapping in `bot.py`. The only new column is per-policy tool options for `book_appointment`; the existing rows get empty options (Pipecat defaults).
3. `llm-cancel` sets `cancel_on_interruption=False` and `cancellable_by_llm=True` on `book_appointment`. The call keeps running through the interruption, and Pipecat advertises a cancel tool for it to the model.
4. Storage is `upsert` with the seq guard, as in `safe`.
5. No pipeline fork: same pipeline, prompt, tool function and backend for every policy.
6. The startup and session-start lines show the tool options.

### 2. Timeline
**User story:** As a reader, I want to see what the model did, so that I can tell a cancel from a re-book from a question.

Acceptance criteria:
1. When the model calls the cancel tool, a `TOOL` line says so (`model called cancel_book_appointment(...)`), followed by the outcome (the call it cancelled, or Pipecat's refusal).
2. A call cancelled by the model is marked `CANCELLED by the model`, so it is not confused with the interruption cancel of `cancel` and `safe`.
3. When an async tool result arrives after the conversation has moved on, so that Pipecat injects it into the context as a new message, the `TOOL ... result` line is marked `LATE`.
4. The `INTERRUPT` line says when the interruption left an async call running.
5. The dump shows Pipecat's async-tool messages in a short form (status and result, no long description), so it fits a screenshot.

### 3. Verdict
Acceptance criteria:
1. The dump's verdict compares the calendar with the model's last `book_appointment` call that was not cancelled. A call the model cancelled does not count as wanted, even though its shielded write may have landed.
2. If the model cancelled every booking call, an empty calendar is `OK` and any row is `MISMATCH`.
3. Verdicts of the existing policies on the main script stay the same.

### 4. Pipecat facts checked against the installed version
Acceptance criteria:
1. `design.md` records, from the installed Pipecat 1.16.0, the name of the generated cancel tool, what is sent to the model, and how and when a late async result enters the context.
2. Any difference from the brief is stated in `design.md`.

### 5. Done when
The repo owner runs the main script 3 times with `--policy llm-cancel`. `tasks.md` records for each run what the model did (cancelled the Friday call, re-booked without cancelling, asked a question, or something else), what the agent said, and the verdict. A mixed result is acceptable as long as it is recorded.

### 6. Constraints
1. Principles from the brief: simplicity over production readiness, no automated tests, no pipeline forks, readable output.
2. New shortcuts are listed in `design.md` with their production approach.
