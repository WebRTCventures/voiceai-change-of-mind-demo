# Requirements: interruption-policies

## Introduction

Adds a `--policy` flag to `bot.py`. A policy pairs a Pipecat configuration with a backend storage mode, so one pipeline can reproduce the failure, show Pipecat's default behavior, and show a fix. The scenario, agent states (S0 to S4) and principles are in `.kiro/steering/demo-brief.md`. The baseline agent and the timeline already exist (`bot.py`, `calendar_backend.py`, `timeline.py`).

Main script: the caller asks for Friday, the tool runs about 6 s, and about 2 s in the caller says "Actually, wait, make it Saturday."

## Requirements

### 1. The `--policy` flag
**User story:** As a reader, I want to pick a policy on the command line, so that I can run the same script three ways.

Acceptance criteria:
1. `uv run bot.py --policy <deaf|cancel|safe>`. The default is `cancel`. Any other value is rejected with a usage message.
2. The runner's own flags (`--host`, `--port`, ...) keep working next to `--policy`.
3. The policy mapping is one small dict in `bot.py`, readable in a blog screenshot. No pipeline fork per policy: the pipeline is built once and the policy only supplies user mute strategies and a storage mode.
4. The storage mode comes from the policy. There is no separate storage flag.
5. `--turn` and an `llm-cancel` policy are out of scope.

### 2. Policies
| Policy | Pipecat configuration | Storage | Expected outcome of the main script |
|---|---|---|---|
| `deaf` | `FunctionCallUserMuteStrategy`: user input muted while a function call runs | append | The correction is lost. 1 booking, Friday. The agent confirms Friday. Reproduces the Tyagi failure. |
| `cancel` (default) | Pipecat default: sync tool, `cancel_on_interruption=True` | append | The interruption cancels the tool and the context records it as cancelled. The model books Saturday, but the shielded Friday write still lands. 2 bookings, and the model believes Friday was never booked. |
| `safe` | Same as `cancel` | upsert with seq guard | Friday is written, then replaced by Saturday. 1 booking, Saturday. |

### 3. Backend storage modes
**User story:** As a reader, I want the fix to be visible in the backend, so that I can see why the race no longer double books.

Acceptance criteria:
1. `append` (existing): every write adds a row.
2. `upsert`: one held appointment per `caller_id`. Each write replaces the caller's row.
3. Seq guard, upsert mode only: a write whose `seq` is lower than the held `seq` is rejected as stale. The backend reports it through a reject callback, and the timeline prints a `BACKEND` `REJECT` line. A write with an equal or higher `seq` replaces the row.
4. The BACKEND commit line says what an upsert replaced, for example `COMMIT Saturday seq=2 (replaced Friday seq=1)`.
5. The storage mode is a parameter of `book()` (already there). `calendar_backend.py` does not know about policies.

### 4. Policy shown in the output
Acceptance criteria:
1. The active policy and storage mode print when the server starts and when a session starts.
2. The end-of-session dump prints them as its first line.
3. The dump's calendar is what the backend holds for this caller at the end of the session. In upsert mode that is the replaced state, not the history of writes.
4. In `deaf` mode, an `OK` verdict carries the note `expected for deaf`, because the verdict only compares the calendar with what the model asked for, and the model never heard the correction.

### 5. Muted speech is visible on the timeline
Acceptance criteria:
1. A transcript that reaches the user aggregator while the user is muted prints a `MUTE` line with the text. A later `TURN` line would show that it was delivered after unmute instead.
2. `design.md` records, from the timeline, whether muted speech in `deaf` mode is dropped or delivered after unmute, and how a late delivery would change the outcome.

### 6. Done when
With the main script, each policy ends as in the table and the verdict line says:
- `deaf`: `OK: 1 booking, Friday  <- expected for deaf: ...` although the caller asked for Saturday.
- `cancel`: `MISMATCH: 2 bookings (Friday, Saturday)`.
- `safe`: `OK: 1 booking, Saturday`.

### 7. Constraints
1. Principles from the brief: simplicity over production readiness, no automated tests, no pipeline forks, readable output.
2. Every Pipecat name is checked against the installed 1.16.0 (see `design.md`).
3. New shortcuts are listed in `design.md` with their production approach.
