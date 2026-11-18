# Tasks: interruption-policies

No automated tests. Verification is manual.

## Implementation

- [x] 1. Verify `FunctionCallUserMuteStrategy`, `LLMUserAggregatorParams.user_mute_strategies` and the runner's custom-flag support against Pipecat 1.16.0; record in `design.md`
- [x] 2. `calendar_backend.py`: `upsert` mode, seq guard, `on_reject` callback, `on_commit(row, replaced)`, `rows_for(caller_id)` (requirement 3)
- [x] 3. `bot.py`: `POLICIES` dict, `--policy` flag through `main(parser)`, mute strategies and storage mode from the policy, startup and session-start print (requirements 1, 4.1)
- [x] 4. `timeline.py`: policy line, backend-state calendar and `expected for deaf` note in the dump, `REJECT` and `replaced` on BACKEND lines, `MUTE` line for transcripts while muted (requirements 3.4, 4, 5.1)
- [x] 5. `design.md`: shortcuts table, deaf finding from source and from the offline check (requirements 5.2, 7.3)

## Manual checks

Done without API keys:
- [x] A. `uv run bot.py --policy bogus` is rejected. `--policy safe --host 127.0.0.1` prints `STARTUP policy=safe ...` and the server starts
- [x] B. Real user aggregator with `FunctionCallUserMuteStrategy`, fed frames in the Friday order: the transcript while muted prints a `MUTE` line, no `TURN` lines, nothing added to the context. Without the strategy the same transcript starts a turn
- [x] C. Backend and dump driven by hand in the three policies, with shortened timings: `deaf` gives `OK ... expected for deaf`, `cancel` gives `MISMATCH: 2 bookings (Friday, Saturday)`, `safe` gives `OK: 1 booking, Saturday` with `(replaced Friday seq=1)`. A Saturday write followed by a Friday write is rejected as stale

Needs keys and a microphone (run these yourself, one session per policy, main script: "Book me for Friday", then about 2 s later "Actually, wait, make it Saturday"):
- [x] D. `--policy deaf`: `MUTE user mute started`, then `MUTE transcript while muted "..."`, no INTERRUPT line, `user mute stopped` when the tool returns, no `TURN` line for the correction, the agent confirms Friday. Dump: `OK: 1 booking, Friday  <- expected for deaf`. Result recorded in `design.md`
- [x] E. `--policy cancel` (or no flag): INTERRUPT, TOOL CANCELLED, Friday COMMIT `(tool was already cancelled)`, Saturday COMMIT. Dump: 2 rows, `CANCELLED` in the context, `MISMATCH`. Result recorded in `design.md`
- [x] F. `--policy safe` (speak the correction only after the `TOOL book_appointment(day=Friday) started` line prints; a first run spoke it during LLM generation, S1, and never made a Friday call, see `design.md`; second run passed): Friday COMMIT, then Saturday COMMIT `(replaced Friday seq=1)`. Dump: 1 row, Saturday, `OK: 1 booking, Saturday`
- [~] G. (skipped by the repo owner: it costs live model calls and adds little. The late-delivery case stays unobserved, `design.md` describes it from the source.) `--policy deaf`, speak the correction so it ends right after the tool returns (about 5 s into the tool). If a `TURN` line follows `user mute stopped`, the late-delivery case happens; note the outcome in `design.md`
