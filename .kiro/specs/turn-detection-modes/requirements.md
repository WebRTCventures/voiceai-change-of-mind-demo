# Requirements: turn-detection-modes

## Introduction

Adds a `--turn` flag to `bot.py`. A turn mode picks the user turn **stop strategy**, the component that decides the caller has finished talking. It is the S0 section of the post: the same sentence can be closed too early or held open, and the timeline shows which stop strategy made the call. The scenario, agent states (S0 to S4) and principles are in `.kiro/steering/demo-brief.md`. The agent, the timeline and the `--policy` flag already exist (`bot.py`, `timeline.py`, `calendar_backend.py`).

S0 script: "Book me for Friday, ummm...", a pause of about 1 s, then "actually Saturday".

## Requirements

### 1. The `--turn` flag
**User story:** As a reader, I want to pick a turn detection mode on the command line, so that I can run the S0 script with a quick detector and with a smart one.

Acceptance criteria:
1. `uv run bot.py --turn <smart|fast>`. The default is `smart`. Any other value is rejected with a usage message.
2. `--turn` works next to `--policy` and the runner's own flags (`--host`, `--port`, ...).
3. The mapping is one small dict in `bot.py`. No pipeline fork: the pipeline is built once and the mode only supplies the stop strategies passed in `LLMUserAggregatorParams`.
4. Only the stop strategy changes. VAD parameters stay at their defaults and so do the start strategies.

### 2. Modes
| Mode | Stop strategy | Behavior |
|---|---|---|
| `smart` (default) | Pipecat's default stop strategy (Smart Turn v3), left unset so Pipecat applies it | After each VAD pause, an audio model judges whether the utterance is complete. An incomplete one stays open until the caller resumes or a silence fallback ends it. |
| `fast` | `SpeechTimeoutUserTurnStopStrategy` with `user_speech_timeout` from `TURN_FAST_TIMEOUT` | The turn closes a fixed time after the caller goes quiet, once a transcript has arrived. |

### 3. Configuration
Acceptance criteria:
1. `TURN_FAST_TIMEOUT` is read from `.env`, in seconds. Default `0.4` when unset (the tuned value, see `tasks.md`).
2. `.env.example` lists `TURN_FAST_TIMEOUT` with a comment.
3. The final tuned value is recorded in `tasks.md` (the shipped default in `.env.example` is that value).

### 4. Turn mode shown in the output
Acceptance criteria:
1. The active mode, its stop strategy and (for `fast`) the timeout print when the server starts and when a session starts.
2. The end-of-session dump prints the mode on its own line, after the policy line.
3. Every `TURN ... user turn stopped` line names the stop strategy that closed the turn (`SpeechTimeout` or `TurnAnalyzer`). A turn closed without a strategy (Pipecat's `user_turn_stop_timeout`, or the session ending) reads `no strategy`, not a Python type name.

### 5. Done when
With the S0 script:
- `--turn fast`: the timeline shows `TURN user turn stopped (SpeechTimeout)` during the pause, and `TOOL book_appointment(day=Friday) started` before the correction's `VAD user started speaking`.
- `--turn smart`: the turn usually stays open through the pause, and a single `book_appointment(day=Saturday)` runs.
- `TURN_FAST_TIMEOUT` is tuned until the `fast` case gives the order above on 3 consecutive runs. The final value and the tuning log are in `tasks.md`.

### 6. Constraints
1. Principles from the brief: simplicity over production readiness, no automated tests, no pipeline forks, readable output.
2. Configuration only. No change to `SileroVADAnalyzer` parameters. Waiting is tuned in the stop strategy.
3. Every Pipecat name is checked against the installed 1.16.0 (see `design.md`).
4. Out of scope: eager or speculative end of turn, LLM-based turn completeness, third-party interruption models. `design.md` mentions them as alternatives for the post, nothing more.
5. New shortcuts are listed in `design.md` with their production approach.
