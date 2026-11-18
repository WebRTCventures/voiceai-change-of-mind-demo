# Design: interruption-policies

## Verified against Pipecat 1.16.0

Checked in the installed package (`.venv/lib/python3.11/site-packages/pipecat`), not from the brief.

| Used | Where verified |
|---|---|
| `from pipecat.turns.user_mute import FunctionCallUserMuteStrategy`. Constructor takes no arguments. It keeps a set of in-flight `tool_call_id`s and reports "muted" while the set is non-empty. `FunctionCallsStartedFrame` adds ids, `FunctionCallResultFrame` and `FunctionCallCancelFrame` remove them | `turns/user_mute/__init__.py`, `function_call_user_mute_strategy.py` |
| `LLMUserAggregatorParams(vad_analyzer=..., user_mute_strategies=[...])`. `user_mute_strategies` is a `list[BaseUserMuteStrategy]`, default empty list. `LLMContextAggregatorPair(context, user_params=...)` passes it to the user aggregator | `llm_response_universal.py` `LLMUserAggregatorParams` (~137 to 200) |
| Strategy instances hold state and `setup`/`cleanup` run per aggregator, so the policy table stores classes and `run_bot` creates a new instance per session | `llm_response_universal.py` `setup`/`cleanup` (~870 to 900), `function_call_user_mute_strategy.py` |
| The user aggregator receives the function call frames because the LLM service uses `broadcast_frame(FunctionCallsStartedFrame, ...)` and `_broadcast_function_call_cancelled` (upstream copies reach the aggregator that sits before the LLM) | `services/llm_service.py` ~1892, ~2410 |
| Mute is evaluated in `LLMUserAggregator.process_frame` before anything else (`_maybe_mute_frame`). While muted these frames are dropped there: `InterruptionFrame`, VAD and user-speaking frames, `InputAudioRawFrame`, `InterimTranscriptionFrame`, `TranscriptionFrame`, `EagerTranscriptionFrame` | `llm_response_universal.py` `_maybe_mute_frame` (~1342 to 1390) |
| Mute events: `on_user_mute_started` / `on_user_mute_stopped`, already used by `timeline.py` | `llm_response_universal.py` `_maybe_mute_frame` |
| Custom flags: `pipecat.runner.run.main(parser=None)` accepts a caller's `argparse.ArgumentParser`, adds the runner flags to it and exposes the result as `runner_args.cli_args`. It is set on the `SmallWebRTCRunnerArguments` for both WebRTC entry points | `runner/run.py` `main` (~1878 to 1925), `cli_args` assignments at ~1145 and ~1345, `runner/types.py` |
| `TranscriptionFrame(text, user_id, timestamp)` | `frames/frames.py`, used by the offline check |

## Differences from the brief and from earlier specs

1. **The `--policy` flag needs no `sys.argv` trick.** `baseline-booking-agent/design.md` ("Findings for later specs") says the runner's strict `argparse` rejects custom flags unless they are removed from `sys.argv`. In 1.16.0 `main()` takes an optional parser, so `bot.py` passes its own parser with `--policy` and the runner adds its flags to it. The brief's `--turn` flag can use the same parser later. `--policy` is also parsed once before `main()` (with `parse_known_args`) only to print the startup line.
2. **The brief's mute claim is confirmed**, with one detail: mute starts at `FunctionCallsStartedFrame`, which the LLM service emits when it starts the tool call. Speech during S1 (LLM generating, no tool call yet) is not muted, so a correction spoken in that window still interrupts. The main script does not hit it, because the correction comes about 2 s into S2.
3. **Mute drops frames in the user aggregator, not before STT.** `stt` is upstream of the aggregator in our pipeline, so Deepgram still receives the audio and still produces transcripts while the user is muted. Those transcripts are then discarded at the aggregator. Nothing in the timeline would show that without the new `MUTE transcript while muted` line.

## Policies as configuration

```python
POLICIES = {
    # name      user mute strategies (classes, one instance per session)   storage
    "deaf":   {"mute": [FunctionCallUserMuteStrategy], "storage": "append"},
    "cancel": {"mute": [],                             "storage": "append"},
    "safe":   {"mute": [],                             "storage": "upsert"},
}
```

`run_bot` reads `runner_args.cli_args.policy`, then:
- passes `user_mute_strategies=[m() for m in POLICIES[policy]["mute"]]` to `LLMUserAggregatorParams`,
- passes `mode=POLICIES[policy]["storage"]` to `calendar_backend.book()` in the tool.

The pipeline, tool and prompt are the same for every policy. `cancel` and `safe` need no Pipecat setting: the tool keeps the default `cancel_on_interruption=True` and the interruption comes from Pipecat's default start strategies. `deaf` works by removing the interruption altogether.

## Backend

`calendar_backend.py` keeps `book(day, caller_id, seq, mode)`.

- `append`: unchanged.
- `upsert`: find the row with the same `caller_id`. None: append. Held `seq` greater than the write's `seq`: call `on_reject(day, seq, "stale, held seq=<n>")` and return, nothing changes. Otherwise replace the row in place and call `on_commit(row, replaced)`.
- The check and the replacement have no `await` between them, so they cannot interleave with another write in the single event loop.
- `rows_for(caller_id)` returns the rows the backend holds for a caller. `bot.py` hands them to the dump, so in upsert mode the dump shows the final state, not the two commits.
- `on_commit` now takes `(row, replaced)`. `on_reject` is new and `bot.py` sets it to `timeline.reject`, the hook `timeline-and-session-dump` already defined.

When does the guard fire? With one tool, `COMMIT_AT` and `TOTAL` apply to both calls, and Friday's call starts first, so the Friday write always lands before Saturday's. The main script therefore shows a replace (`COMMIT Saturday seq=2 (replaced Friday seq=1)`), not a reject. The guard matters when a slow older write overtakes a newer one (varying real latency). It was exercised by driving the backend by hand, Saturday seq=2 then Friday seq=1 (check C). To see a reject live, raise `COMMIT_AT` so Friday's commit lands after Saturday's, which needs a caller who is quick and a tool whose latency varies. The demo does not stage that.

## Timeline and dump changes

- `Timeline.commit(row, replaced=None)` prints `(replaced <day> seq=<n>)` for an upsert. It no longer stores commits.
- `Timeline.reject` prints `BACKEND  REJECT <day> seq=<n> (stale, held seq=<n>)`.
- `Timeline` tracks `muted` from the mute events. A `TranscriptionFrame` seen while muted prints `MUTE  transcript while muted "<text>"`. The aggregator drops it. The line only records that the transcript arrived.
- `dump(context, rows, policy, storage)`:
  - first line after the header: `POLICY <name> (storage: <mode>)`,
  - `CALENDAR` lists `rows` (what the backend holds for this caller),
  - verdict unchanged, with `  <- expected for deaf: the correction was muted` appended to an `OK` verdict when the policy is `deaf`. The note is there because the verdict compares the calendar to the model's last `book_appointment` call. In deaf mode the model never hears the correction, so Friday always matches and the verdict cannot catch the failure.
- Startup line printed by `__main__`: `STARTUP  policy=<name>  (user mute: <classes or none>; storage: <mode>)`. The same text prints as `SESSION START` when a browser connects.

## Question: is muted speech dropped or delivered after unmute?

**Answer: dropped, when it arrives while the user is muted.** Pipecat does not buffer it. A transcript that arrives after the mute ends is a normal transcript and is delivered.

Evidence:
- Source: `_maybe_mute_frame` returns before the frame is handled, so a muted `TranscriptionFrame` is never aggregated and never starts a user turn. The same holds for audio, so the VAD, which runs inside the aggregator, sees no speech either. In deaf mode the timeline shows no `VAD`, `TURN` or `INTERRUPT` line for the correction.
- Offline check B (real user aggregator and `FunctionCallUserMuteStrategy`, synthetic frames, not a live session). Frames: tool call started, a transcript "Actually, wait, make it Saturday.", tool result.

  ```
  --- muted=True
    +0.003  TOOL       book_appointment(day=Friday) started  seq=0
    +0.004  MUTE       user mute started
    +0.204  MUTE       transcript while muted "Actually, wait, make it Saturday."
    +0.705  TOOL       book_appointment seq=0 result {"status": "booked"}
    +0.706  MUTE       user mute stopped
  user messages in context: []
  --- muted=False
    +0.002  TOOL       book_appointment(day=Friday) started  seq=0
    +0.204  TURN       user turn started (Transcription)
    +0.205  TURN       user turn stopped (TurnAnalyzer) "Actually, wait, make it Saturday."
    +0.705  INTERRUPT  interruption  tool_cancel_latency=n/a
    +0.705  TOOL       book_appointment seq=0 result {"status": "booked"}
  user messages in context: [{'role': 'user', 'content': 'Actually, wait, make it Saturday.'}]
  ```

  With mute, the transcript is seen on the timeline, produces no turn, and the context has no user message after the tool result. Without mute, the same transcript starts a turn and interrupts.

**Live result (check D):** not run yet. Fill in from a real session: whether a `TURN` line appears between `user mute stopped` and the end of the session.

**If it were delivered late.** This happens for speech whose transcript arrives after `user mute stopped`, for example a correction that ends just as the tool returns, because Deepgram's final transcript trails the end of speech. Then the order is: tool result Friday, `user mute stopped`, the late transcript starts a turn. The LLM may already be generating the Friday confirmation (S3), so the late turn interrupts it (`INTERRUPT` with a `yield_latency` if the bot has started speaking), and the model sees "make it Saturday" after a completed Friday booking. It calls `book_appointment(Saturday)`. With `append` storage that gives Friday and Saturday: 2 bookings, `MISMATCH`, the same row count as `cancel`. The difference from `cancel` is that the model knows Friday was booked (the tool result is `booked`, not `CANCELLED`), so it can say "I changed it to Saturday", although the Friday row remains. With the main script's timing (correction about 2 to 4 s into a 6 s tool) the correction is fully inside the mute window, so the late case does not occur. Check G tries it live.

## Shortcuts

| Shortcut | Production approach |
|---|---|
| Upsert keyed by `caller_id`, which is the WebRTC session id (`pc_id`) | A business-level idempotency key (for example caller plus slot or booking intent), so a reconnect keeps the same appointment |
| The turn counter (`user_turns`, count of stopped user turns) is the `seq` for the guard | A server-side version or `If-Match` precondition. The server decides what is stale from a version it issued, not from a number the client increments |
| Seq guard compares only `seq`, with equal `seq` allowed to replace | Compare on the version and return a conflict the client must resolve |
| Dump reads the backend's rows for the session id | Read the booking back from the real API |
| The `deaf` note in the dump is a string comparison on the policy name | The verdict compares against what the caller confirmed, so it fails on its own when a correction was lost |
| `FunctionCallUserMuteStrategy` mutes all user speech during the tool, so a correction cannot get through even though the user is the one who wants to change it | Mute only the speech that cannot matter (echo, backchannel) and let the correction through to an interrupt policy that reconciles state |
| Policy table lives in `bot.py` and holds classes, instances are made per session | A config object per deployment with tool options and turn settings |
| `--policy` parsed twice (once to print the startup line, once by the runner) | One parse in a custom entry point that starts the runner programmatically |
| The reject path is not reachable with the main script's timing (see Backend) | Real latency varies, so log and alert on rejected stale writes |

## Verification status

Done offline, no API keys (see `tasks.md` checks A to C):
- Flag parsing, startup line, server start with `--host 127.0.0.1`.
- Real user aggregator with the mute strategy (output above).
- Backend and dump for the three policies with shortened timings and a hand-driven interruption: deaf `OK: 1 booking, Friday  <- expected for deaf`, cancel `MISMATCH: 2 bookings (Friday, Saturday)`, safe `OK: 1 booking, Saturday`, and the stale reject.

Not verified:
- A live session for any policy. The brief's table outcomes depend on the model calling `book_appointment` again with Saturday (cancel, safe) and on the correction landing inside the mute window (deaf). Checks D to G in `tasks.md` need Deepgram and OpenAI keys and a microphone.
- That the model "believes Friday was never booked" in `cancel`. The dump shows the recorded `CANCELLED` tool message. What the model infers from it is model-dependent (same caveat as `timeline-and-session-dump`).
