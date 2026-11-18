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

**Answer: dropped, when it arrives while the user is muted (confirmed in a live run, below).** Pipecat does not buffer it. A transcript that arrives after the mute ends is a normal transcript and is delivered.

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

**Live result (check D), Pipecat 1.16.0, Deepgram, OpenAI, SmallWebRTC, run by the repo owner:** dropped, confirmed.

```
 +13.417  TOOL       book_appointment(day=Friday) started  seq=1
 +13.418  MUTE       user mute started
 +16.419  BACKEND    COMMIT Friday seq=1
 +16.510  MUTE       transcript while muted "Actually, make it Saturday."
 +19.419  TOOL       book_appointment seq=1 result {"status": "booked", "day": "Friday"}
 +19.420  MUTE       user mute stopped
 +20.533  BOT        bot started speaking
 +22.500  BOT        assistant turn stopped interrupted=False "Your appointment is booked for Friday."
OK: 1 booking, Friday  <- expected for deaf: the correction was muted
```

- The final transcript arrived 3.1 s into the mute and 2.9 s before unmute. No `VAD`, `TURN` or `INTERRUPT` line followed it, not during the mute and not after `user mute stopped`. The context holds no user message with the correction (dump: 6 messages, the last user message is "Book me for Friday.").
- The model's reply after the tool result was "Your appointment is booked for Friday.", so the caller heard Friday confirmed after asking for Saturday.
- Mute started 1 ms after the `TOOL ... started` line and stopped 1 ms after the result, as the source says.
- The late-delivery case (below) did not occur because the correction was well inside the window. Check G, which times speech to end right at the unmute, is still open.

**If it were delivered late.** This happens for speech whose transcript arrives after `user mute stopped`, for example a correction that ends just as the tool returns, because Deepgram's final transcript trails the end of speech. Then the order is: tool result Friday, `user mute stopped`, the late transcript starts a turn. The LLM may already be generating the Friday confirmation (S3), so the late turn interrupts it (`INTERRUPT` with a `yield_latency` if the bot has started speaking), and the model sees "make it Saturday" after a completed Friday booking. It calls `book_appointment(Saturday)`. With `append` storage that gives Friday and Saturday: 2 bookings, `MISMATCH`, the same row count as `cancel`. The difference from `cancel` is that the model knows Friday was booked (the tool result is `booked`, not `CANCELLED`), so it can say "I changed it to Saturday", although the Friday row remains. With the main script's timing (correction about 2 to 4 s into a 6 s tool) the correction is fully inside the mute window, so the late case does not occur. Check G tries it live.

## Live result: `cancel` (check E)

Pipecat 1.16.0, Deepgram, OpenAI, SmallWebRTC, run by the repo owner. Matches the table.

```
 +9.619  TOOL       book_appointment(day=Friday) started  seq=1
+11.340  VAD        user started speaking
+11.340  TURN       user turn started (VAD)
+11.341  INTERRUPT  interruption  tool_cancel_latency=202ms
+11.341  TOOL       book_appointment seq=1 CANCELLED
+12.619  BACKEND    COMMIT Friday seq=1 (tool was already cancelled)
+13.149  TURN       user turn stopped (TurnAnalyzer) "Actually, make it Saturday."
+13.997  TOOL       book_appointment(day=Saturday) started  seq=2
+16.997  BACKEND    COMMIT Saturday seq=2
+19.998  TOOL       book_appointment seq=2 result {"status": "booked", "day": "Saturday"}
+22.773  BOT        assistant turn stopped interrupted=False "Your appointment is booked for Saturday."
MISMATCH: 2 bookings (Friday, Saturday)
```

- The interruption cancelled the tool 202 ms after the caller started speaking, 1.7 s after the tool began. The shielded Friday write still landed 1.3 s after the cancel.
- The dump's context holds `tool id=call_ipc3... CANCELLED` for Friday, and the next LLM request (visible in the debug log) sent that same `CANCELLED` string back to the model.
- The model then called `book_appointment(Saturday)` once and did not call Friday again. It said "Your appointment is booked for Saturday." while the calendar holds two rows. The caller hears a clean confirmation and the backend has a stray Friday booking. That is the failure this policy shows.
- "The model believes Friday was never booked" is inferred from the `CANCELLED` content and from the model not retrying Friday. The log does not show the model's reasoning.
- The Friday commit came before the correction's user turn stopped (+12.619 against +13.149), so the Saturday write started after Friday had already landed. With `safe` the same timing gives a replace, not a reject.

## First `safe` run: correction landed in S1, so the policy was not exercised

Same setup as the other live runs. This run does not count as check F.

```
+12.196  TURN       user turn stopped (TurnAnalyzer) "Book me for Friday."
+14.400  VAD        user started speaking
+14.400  INTERRUPT  interruption
+14.400  TURN       user turn started (VAD)
+16.425  TURN       user turn stopped (TurnAnalyzer) "Actually, make it Saturday."
+17.269  TOOL       book_appointment(day=Saturday) started  seq=2
+20.269  BACKEND    COMMIT Saturday seq=2
OK: 1 booking, Saturday
```

- There is no `TOOL book_appointment(day=Friday) started` line, no Friday commit and no `CANCELLED` entry. The model never emitted a Friday call.
- The LLM request for "Book me for Friday." went out at +12.196 and was still waiting for its first token when the caller spoke at +14.400 (the logged `OpenAILLMService TTFB: 2.205s`; in the `cancel` and `deaf` runs it was 0.7 to 1.1 s). So the correction landed in S1 (turn confirmed, LLM generating, no tool call yet), not in S2.
- The interruption cancelled the in-flight LLM request. The INTERRUPT line has no latency numbers, because no tool was running and the bot was not speaking. The context then holds two consecutive user messages ("Book me for Friday.", "Actually, make it Saturday.") and the model made one call, Saturday.
- The `OK` verdict is true, but the upsert and the seq guard did nothing. The backend saw one write. The run shows that an S1 interruption is harmless, which is a different case from the one this policy fixes.
- The correction came from a recording, timed from the end of the first sentence, so it started 2.62 s after the first VAD stop here and 2.56 s in the `cancel` run. The difference was LLM latency, not the recording. In this session the greeting took 2.388 s to first token and the final reply 2.322 s, against 0.7 to 1.1 s in the `deaf` and `cancel` sessions. The 2.205 s TTFB logged for the Friday request is the elapsed time at the interruption (it prints in the same millisecond), so no first token had arrived.
- The same S1 window exists under `cancel` and `deaf` (deaf only mutes after `FunctionCallsStartedFrame`, see Differences, item 2). A slow LLM turns the main script into an S1 case in any policy.

To exercise `safe`, the correction must start after the `TOOL book_appointment(day=Friday) started` line prints. The reliable way to reproduce the main script is to wait for that line before speaking, then speak about 2 s later. Check F in `tasks.md` says so.

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

Live: check D (`deaf`) and check E (`cancel`), see the results above.

Done offline, no API keys (see `tasks.md` checks A to C):
- Flag parsing, startup line, server start with `--host 127.0.0.1`.
- Real user aggregator with the mute strategy (output above).
- Backend and dump for the three policies with shortened timings and a hand-driven interruption: deaf `OK: 1 booking, Friday  <- expected for deaf`, cancel `MISMATCH: 2 bookings (Friday, Saturday)`, safe `OK: 1 booking, Saturday`, and the stale reject.

Not verified:
- A valid live session for `safe` (check F). The first attempt landed in S1 (see above). `deaf` (check D) and `cancel` (check E) were run live.
- The late-delivery case in `deaf` (check G).
- That the model "believes Friday was never booked" in `cancel`. The dump shows the recorded `CANCELLED` tool message. What the model infers from it is model-dependent (same caveat as `timeline-and-session-dump`).
