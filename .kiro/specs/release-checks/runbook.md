# Runbook: release checks

Manual checks before publishing. They need a voice and a microphone, so the repo owner runs them. The numbers go into `results.md` at the repo root.

Total: about 41 sessions (1 fresh clone, 5 × 3 policies, 20 S0 attempts, 5 S4), plus 5 optional `llm-cancel` runs. Checks 2 to 4 are the first runs of check 7, not extra sessions. Roughly 1 to 1.5 minutes each.

## Before you start

- Use the same machine, browser, microphone and network for every check, and write them down (`results.md`, Setup).
- Leave `.env` at the defaults from `.env.example` (`OPENAI_MODEL=gpt-4.1`, `COMMIT_AT=3.0`, `TOTAL=6.0`, `TURN_FAST_TIMEOUT=0.4`, `LOG_LEVEL=WARNING`). Check 7 is about the default tool duration.
- One session = **Connect**, script, stay quiet until the agent has finished talking, **Disconnect**, read the dump. Click **Connect** again for the next session. Restart `uv run bot.py` only when you change flags.
- Do not tune anything between attempts of the same check. If something has to change, start that check again and note why.

### Counting rule for the policy checks (2, 3, 4, 7)

A main-script run only tests the policy if `TOOL book_appointment(day=Friday) started` prints **before** the correction's `VAD user started speaking`. If it does not (you spoke while the LLM was still generating, S1), mark the run **invalid**, note it, and do another run. Invalid runs do not count towards the 5, but report how many there were.

The S0 attempts (check 5) have no such rule. Timing is what that check measures, so all 10 attempts count.

### What to send back

For every session, one line in this form (copy it from the terminal; the timestamps are enough):

```
check, run, valid?, verdict line, INTERRUPT line(s), anything odd
```

Also paste the **full timeline** of:
- one clean S4 run (check 6), and
- one clean `llm-cancel` run, if you do the optional runs in check 7.

The README has no live excerpt for those two yet. Pasted timelines become its excerpts.

## 1. Fresh clone to working conversation

Purpose: the README alone is enough to get a reader talking to the agent.

1. In a new empty directory, follow the README's Setup section word for word:
   ```
   git clone https://github.com/WebRTCventures/voiceai-change-of-mind-demo.git
   cd voiceai-change-of-mind-demo
   cp .env.example .env      # fill in the two keys, nothing else
   uv sync
   uv run bot.py
   ```
2. Open http://localhost:7860/client, click **Connect**, allow the microphone.
3. Say "Book me for Friday." Wait for the confirmation. **Disconnect**.
4. Click **Connect** again and check that a new `SESSION START` line prints and the agent greets you again (the README says no restart is needed between sessions). **Disconnect**.

Pass:
- The startup lines read `STARTUP  policy=cancel  (user mute: none; tool: default; storage: append)` and `turn=smart (stop strategy: TurnAnalyzer, Smart Turn v3)`.
- The agent greets first with "Hi, I can book your appointment. Which day works for you?"
- `BACKEND COMMIT Friday seq=1` about 3 s after `TOOL book_appointment(day=Friday) started`, and a spoken confirmation about 3 s after that.
- The dump ends with `OK: 1 booking, Friday`.
- The second Connect starts a new session without a restart.

Record: OS, Python version (`python3 --version`), uv version (`uv --version`), browser and version, the Pipecat version from the first log line (`Pipecat 1.16.0`), and any step that failed or needed something the README does not mention.

## 2. `deaf`: one Friday booking, correction visible during the mute

```
uv run bot.py --policy deaf
```

Main script: "Book me for Friday." Wait for `TOOL book_appointment(day=Friday) started`. About 2 s later: "Actually, wait, make it Saturday." Finish the sentence well before the tool returns (6 s after it started). Stay quiet until the agent has spoken.

Pass:
- `MUTE  user mute started` right after the `TOOL ... started` line.
- `MUTE  transcript while muted "..."` with your correction, **between** `user mute started` and `user mute stopped`. This is the correction being visible during the mute window.
- No `VAD`, `TURN` or `INTERRUPT` line for the correction, during the mute or after `user mute stopped`.
- The agent confirms Friday.
- Dump: `CALENDAR (1 row)` with Friday, and `OK: 1 booking, Friday  <- expected for deaf: the correction was muted`.

This is run 1 of 5 for `deaf` in check 7.

## 3. `cancel`: two bookings, cancelled Friday call in the context dump

```
uv run bot.py --policy cancel
```

Main script, as in check 2.

Pass:
- `INTERRUPT  interruption  tool_cancel_latency=<n>ms`, then `TOOL  book_appointment seq=1 CANCELLED`.
- `BACKEND  COMMIT Friday seq=1 (tool was already cancelled)`.
- `TOOL  book_appointment(day=Saturday) started`, then `BACKEND  COMMIT Saturday ...`.
- Dump: `CALENDAR (2 rows)`, Friday and Saturday.
- Dump, `CONTEXT` section: an `assistant` line with `book_appointment(...Friday...) id=call_...` (the arguments are printed as the model sent them), followed by a `tool      id=<same id> CANCELLED` line. This is the cancelled Friday call.
- Verdict: `MISMATCH: 2 bookings (Friday, Saturday)`.

Record the `tool_cancel_latency` value. This is run 1 of 5 for `cancel` in check 7.

## 4. `safe`: one Saturday booking

```
uv run bot.py --policy safe
```

Main script, as in check 2.

Pass:
- `INTERRUPT ... tool_cancel_latency=<n>ms` and `CANCELLED`, as in `cancel`.
- `BACKEND  COMMIT Saturday seq=<n> (replaced Friday seq=1)`.
- Dump: `CALENDAR (1 row)`, Saturday, and `OK: 1 booking, Saturday`.
- The agent says Saturday.

A `BACKEND REJECT` line is not expected with the default timing. If one appears, paste the timeline.

Record the `tool_cancel_latency` value. This is run 1 of 5 for `safe` in check 7.

## 5. `--turn fast` vs `--turn smart` on the S0 script, 10 attempts each

```
uv run bot.py --policy cancel --turn fast
uv run bot.py --policy cancel --turn smart
```

S0 script: "Book me for Friday, ummm..." with no gap between "Friday" and "ummm", then about 2 s of silence, then "actually Saturday". One attempt per session. Alternate the modes in blocks if you like (for example 5 fast, 5 smart, 5 fast, 5 smart), but keep the same voice and pacing.

Use a live voice or a recording, and say which in `results.md`. The earlier tuning used a recording (`s0.m4a`, not in the repo). A recording keeps the pause the same each time; a live voice is what a reader will do.

A hit means the mode did what the post says it does:

| Mode | Hit |
|---|---|
| `fast` | A `TURN  user turn stopped (SpeechTimeout)` line closes the first sentence during the pause, **and** `TOOL book_appointment(day=Friday) started` prints before the correction's `VAD user started speaking` |
| `smart` | No `TURN  user turn stopped` line between the last `VAD user stopped speaking` before the pause and the correction's `VAD user started speaking`, **and** no Friday tool call starts before the correction |

For each attempt, record:
- hit or miss,
- the pause as the VAD saw it: the correction's `VAD user started speaking` time minus the previous `VAD user stopped speaking` time,
- how many `VAD user started speaking` lines came before the pause (2 or more means the VAD split "Friday" and "ummm"),
- the verdict line,
- for a miss, which condition failed.

Every `fast` hit also produces a `tool_cancel_latency`; record it.

## 6. S4: `yield_latency` and the committed text stops at the interruption

```
uv run bot.py --policy safe
```

`safe` so a re-booking leaves one row. 5 runs.

1. Say "Book me for Friday." and stay silent through the tool call.
2. When you hear the confirmation start (`BOT  bot started speaking`), interrupt within about half a second: "Actually, make it Saturday." Earlier runs interrupted about 1.5 s in, and the short sentence was already finished.

Pass:
- `INTERRUPT  interruption  yield_latency=<n>ms` before `BOT  bot stopped speaking`.
- `BOT  assistant turn stopped interrupted=True "<text>"` where `<text>` ends where you cut in: it is shorter than the full confirmation, it matches the words you heard, and it does not end with the words you did not hear.

Record per run: `yield_latency`, the committed text, and the last word you heard. If the committed text is the full sentence although you cut in early, note it as a fail: the README states the opposite, and one of the two has to change.

Paste the full timeline of one clean run.

## 7. Each policy outcome reproduces at least 4 times out of 5

Default tool duration (`COMMIT_AT=3.0`, `TOTAL=6.0`), `--turn smart`, main script. 5 valid runs per policy; runs 1 of checks 2, 3 and 4 count as the first.

| Policy | The run reproduces the outcome when |
|---|---|
| `deaf` | Calendar 1 row, Friday; verdict `OK: 1 booking, Friday  <- expected for deaf...`; a `MUTE transcript while muted` line for the correction |
| `cancel` | Calendar 2 rows, Friday and Saturday; verdict `MISMATCH: 2 bookings (Friday, Saturday)`; a `CANCELLED` tool message for Friday in the dump |
| `safe` | Calendar 1 row, Saturday; verdict `OK: 1 booking, Saturday`; a `(replaced Friday seq=1)` commit |

Pass: 4 or more of 5 valid runs per policy.

Optional, `llm-cancel` (5 runs, `uv run bot.py --policy llm-cancel`). The outcome depends on the model by design, so it is not held to the 4 of 5 bar. Record two things per run: the calendar (1 row, Saturday?) and what the agent said (only Saturday, or Friday too?). Also note whether `model called cancel_book_appointment` and a `LATE` line appeared.

Record every `tool_cancel_latency` from the `cancel` and `safe` runs.
