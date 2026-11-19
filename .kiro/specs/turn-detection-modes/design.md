# Design: turn-detection-modes

## Why this exists

"Book me for Friday." is a complete sentence, so no turn detector should hold it open. Any mode closes that turn within a fraction of a second, and the LLM starts `book_appointment(Friday)`.

Turn detection cannot prevent the S2 race. It only changes how often it happens. The case is a caller who trails off: "Book me for Friday, ummm..." and then "actually Saturday" after about 1 s.

- A short silence timeout (`fast`) closes the turn during the pause. The LLM sees "Book me for Friday", calls the tool, and the correction arrives while the tool runs (S2). That is the failure the other specs handle.
- A model that listens to the audio (`smart`) can hear that the sentence is unfinished and keep the turn open. The correction then joins the same turn, the LLM sees one message, and a single `book_appointment(Saturday)` runs.

Smart Turn does not remove the race. It makes the race rarer for this kind of speech. A caller who says a complete "Book me for Friday." and changes their mind 2 s later still hits S2 in either mode.

## Verified against Pipecat 1.16.0

Checked in the installed package (`.venv/lib/python3.11/site-packages/pipecat`, `pipecat_ai-1.16.0.dist-info`), not from the brief.

| Used | Where verified |
|---|---|
| `from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy`. Constructor: `user_speech_timeout: float = 0.6`, `wait_for_transcript: bool = True`. **The brief's name and parameter are right.** | `turns/user_stop/__init__.py`, `speech_timeout_user_turn_stop_strategy.py` |
| `from pipecat.turns.user_turn_strategies import UserTurnStrategies`. A dataclass with `start` and `stop` lists. A list left `None` or empty is filled with the default in `__post_init__`, so `UserTurnStrategies(stop=[...])` replaces only the stop side and keeps the default start strategies (`VADUserTurnStartStrategy`, `TranscriptionUserTurnStartStrategy`) | `turns/user_turn_strategies.py` |
| `LLMUserAggregatorParams(user_turn_strategies=...)`. Default `None`. Merged with the default `UserTurnStrategiesParams` (`REPLACE` merge, `stop_mode=ALL`), so the list we pass is used on its own | `llm_response_universal.py` `LLMUserAggregatorParams` (~195), `__init__` (~749 to 770) |
| `on_user_turn_stopped(aggregator, strategy, message)`. `strategy` is the `BaseUserTurnStopStrategy` instance that decided, which `timeline.py` already prints. It is `None` when no strategy decided: the `user_turn_stop_timeout` (5 s) ended the turn, or the session ended | `llm_response_universal.py` `_on_user_turn_stopped` (~1618), `_maybe_emit_user_turn_stopped`, `user_turn_controller.py` `_user_turn_stop_timeout_task_handler` (~705) |
| Strategy instances hold state and are set up per aggregator, so the mapping stores a factory and `run_bot` creates a new instance per session (same reason as the mute strategies) | `speech_timeout_user_turn_stop_strategy.py` (`_text`, timer tasks) |
| Silero VAD defaults: `VAD_START_SECS = 0.2`, `VAD_STOP_SECS = 0.2`. We pass `SileroVADAnalyzer()` with no parameters, as before | `audio/vad/vad_analyzer.py` |
| STT p99 latency for Deepgram: `DEEPGRAM_TTFS_P99 = 0.35` s, sent as `STTMetadataFrame`. Both stop strategies use it as a safety net | `services/stt_latency.py`, `services/deepgram/stt.py` (~336) |
| Deepgram's STT does not recommend its own turn strategies (no `user_turn_strategies` override in `services/deepgram/stt.py`), so ours are not merged with a service's | `services/deepgram/stt.py`, `services/stt_service.py` `service_metadata_frame` (~750) |

## Question: is Smart Turn v3 still the default stop strategy?

**Yes, in 1.16.0.** `UserTurnStrategies` documents and implements the default stop list as `[TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3)]` (`default_user_turn_stop_strategies()` in `turns/user_turn_strategies.py`). `LLMUserAggregatorParams.user_turn_strategies` defaults to `None`, which becomes `UserTurnStrategies()` and so the default list.

For `smart`, `bot.py` passes `user_turn_strategies=None`, so Pipecat applies its own default. The code does not name `LocalSmartTurnAnalyzerV3`, and the mode follows the default if a later Pipecat changes it. The cost is that the code does not show which analyzer runs, so `describe_turn` prints `TurnAnalyzer, Smart Turn v3` as a fixed string. Check that string against the default when upgrading Pipecat.

## Question: do the model weights ship with the package or download on first run?

**They ship with the package. Nothing downloads.**

- The wheel contains `pipecat/audio/turn/smart_turn/data/smart-turn-v3.2-cpu.onnx` (8,679,182 bytes, listed in `pipecat_ai-1.16.0.dist-info/RECORD`). `uv sync` installs it.
- `LocalSmartTurnAnalyzerV3.__init__` loads it from that path when `smart_turn_model_path` is not given. The log line is `Loading Local Smart Turn v3.x model from .../smart-turn-v3.2-cpu.onnx`. Verified by building the default strategy in the installed environment.
- The only network code in `audio/turn` is `http_smart_turn.py` (a remote analyzer), which the default does not use.
- Silero VAD is bundled the same way (`audio/vad/data/silero_vad.onnx`).
- The model runs on CPU (ONNX Runtime, one thread by default), so `smart` needs no GPU and no extra key. This goes in the README.

The first session is not slower because of a download. `LocalSmartTurnAnalyzerV3()` is constructed when the aggregator is built, so the ONNX file loads at the start of each session.

## Differences from the brief

1. **The brief's class and parameter names are correct.** `SpeechTimeoutUserTurnStopStrategy` and `user_speech_timeout` exist in 1.16.0 with the default 0.6 s.
2. **The timeout is not the whole wait.** `user_speech_timeout` starts when VAD reports the stop, and VAD reports it `stop_secs` (0.2 s) after the caller actually went quiet. The strategy also runs a second timer, the STT safety net, of `ttfs_p99_latency - stop_secs` = 0.35 - 0.2 = 0.15 s. It is skipped when Deepgram sends a finalized transcript. The turn closes when both timers are done and a transcript exists. So with `TURN_FAST_TIMEOUT=0.2`, the turn closes about 0.4 s after the caller stopped, at best. When the transcript is not finalized, the close waits for the longer of the two timers, so a timeout under 0.15 s no longer shortens it.
3. **The strategy requires a transcript** (`wait_for_transcript=True`). Pipecat's Deepgram settings do not expose `filler_words`, so Deepgram's default applies, and "ummm" is left out of the transcript (confirmed in the first live runs: "Book me for Friday."). If so, the transcript for the S0 script reads "Book me for Friday" in both modes and only the audio shows the hesitation. `fast` ignores the audio. `smart` hears it. That is the contrast the post describes.

## Turn modes as configuration

```python
TURNS = {
    # name    stop strategies (new instances per session); None = Pipecat default
    "smart": lambda: None,
    "fast":  lambda: [SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=fast_timeout())],
}
```

`run_bot` reads `runner_args.cli_args.turn` and passes `user_turn_strategies=turn_strategies(turn)` to `LLMUserAggregatorParams`. `turn_strategies` returns `None` for `smart` and `UserTurnStrategies(stop=[...])` for `fast`. The pipeline, VAD, tool and prompt are the same for both. `--turn` is added to the same parser as `--policy` (the runner's `main(parser)` accepts it, see `interruption-policies/design.md`).

`fast_timeout()` reads `TURN_FAST_TIMEOUT` when a session starts (`load_dotenv(override=True)` has already run), default `0.2`. A value that is not a number fails with Python's `ValueError` when the session starts.

## Output changes

- Startup and session start print a second line: `turn=fast (stop strategy: SpeechTimeout, user_speech_timeout=0.2s)` or `turn=smart (stop strategy: TurnAnalyzer, Smart Turn v3)`.
- The dump has `TURN MODE <same text>` after the `POLICY` line. `dump()` takes a new `turn` argument.
- No new timeline line. `TURN  user turn stopped (<strategy>) "<text>"` already named the strategy from the earlier timeline spec. Names come from the class name with `UserTurnStopStrategy` stripped: `SpeechTimeout`, `TurnAnalyzer`. Added: `None` now prints `no strategy` instead of `NoneType`.
- To see how long the close took, read the two lines: `VAD user stopped speaking` and `TURN user turn stopped`. That gap is the quantity `TURN_FAST_TIMEOUT` controls.

Expected S0 timeline with `--turn fast` (shape, not a recording):

```
VAD        user started speaking
TURN       user turn started (VAD)
VAD        user stopped speaking
TURN       user turn stopped (SpeechTimeout) "Book me for Friday"
TOOL       book_appointment(day=Friday) started  seq=1
VAD        user started speaking          <- "actually Saturday", tool is already running
INTERRUPT  interruption  tool_cancel_latency=...
```

With `--turn smart` the same speech shows `VAD user stopped speaking`, then `VAD user started speaking` again with no `TURN user turn stopped` in between.

## Offline check of the wiring

The real `LLMUserAggregator` with the strategies from `bot.turn_strategies`, fed synthetic frames (VAD start, finalized transcript "Book me for Friday", VAD stop with `stop_secs=0.2`). This checks wiring and the timer arithmetic, not turn detection quality. The `smart` model needs real audio, so only the live run covers it.

```
--- fast, TURN_FAST_TIMEOUT=0.2          --- fast, TURN_FAST_TIMEOUT=0.5
stop strategies: ['SpeechTimeout...']    stop strategies: ['SpeechTimeout...']
+0.304  VAD   user stopped speaking      +0.304  VAD   user stopped speaking
+0.506  TURN  user turn stopped          +0.806  TURN  user turn stopped
        (SpeechTimeout) "Book me..."             (SpeechTimeout) "Book me..."
```

The turn closes `TURN_FAST_TIMEOUT` after the VAD stop line, as the source says (the finalized transcript skips the STT safety net). For `smart`, the same check shows `stop strategies: ['TurnAnalyzerUserTurnStopStrategy']`, and `bot.turn_strategies("smart")` returns `None`. The synthetic frames carry no audio, so the turn was only closed when the session ended (`no strategy`, which is why that label exists).

## Tuning and the race window for `fast`

The caller's pause is about 1 s. For the S0 case to show `book_appointment(Friday)` before "actually Saturday", this must finish inside the pause:

`VAD stop (0.2 s after speech ends) + TURN_FAST_TIMEOUT (+ STT wait if not finalized) + LLM time to first tool call`

The first two terms total about 0.4 to 0.55 s with the default. The LLM term for `gpt-4.1` in the earlier live runs (`interruption-policies/design.md`) was 0.7 to 1.1 s in most sessions (the `cancel` run: turn closed at +13.149, tool started at +13.997, 0.85 s later) and 2.3 s in a slow one. So the total is about 1.1 to 1.7 s normally, which is longer than a 1 s pause. When that happens the correction starts while the LLM is still generating (S1), the tool call never starts, and the run does not count (same as the first `safe` run). `TURN_FAST_TIMEOUT` can only shorten the first two terms. The VAD term is fixed, and the timeout cannot go below 0, so the most it can save over the default is 0.2 s. The first two live runs measured it: the turn closed 0.20 s after the VAD stop and the tool started 0.81 and 1.06 s after that (`tasks.md`), so the correction has to start at least about 1.3 s after the VAD stop. If the live runs show the LLM term is the problem, the options are a longer pause in the script (about 1.5 to 2 s) or a faster `OPENAI_MODEL` in `.env`, not VAD changes. The tuning log is in `tasks.md`.

## Alternatives for the post (not built)

- **Eager or speculative end of turn.** Start the LLM on a likely end of turn and discard the answer if the caller keeps talking. Pipecat 1.16.0 has `EagerUserTurnStrategies` and `EagerUserTurnStopStrategy`. They move the cost of waiting from latency to wasted LLM calls.
- **LLM-based turn completeness.** Ask the LLM whether the turn is complete. Pipecat 1.16.0 has `FilterIncompleteUserTurnStrategies`, which adds `LLMTurnCompletionUserTurnStopStrategy` (the model prefixes each reply with a completeness marker).
- **Third-party models.** For example Krisp VIVA (`KrispVivaTurn`) in Pipecat's turn analyzers, or a hosted model behind `HttpSmartTurnAnalyzer`.

These are named from the installed package for the post to mention. None is used, configured or tested here.

## Shortcuts

| Shortcut | Production approach |
|---|---|
| Two modes with one tuned timeout, read from `.env` | Tune per deployment and per language against recorded calls, and log how often a turn was reopened after it closed |
| `smart` passes `None` to use Pipecat's default, and the startup text "Smart Turn v3" is a fixed string | Construct the analyzer explicitly and print its class, so a changed default is visible |
| Smart Turn runs on CPU, one thread, bundled model, defaults for `SmartTurnParams` (3 s silence fallback) | Choose the fallback silence per use case, and pin and evaluate the model version |
| The 1 s pause in the S0 script is an assumption about the caller | Measure real pause lengths from calls (callers pause longer on numbers and addresses) |
| `fast_timeout()` is read per session and accepts any float | Validate the range at startup |
| `--turn` parsed twice (startup line, then the runner), like `--policy` | One parse in a custom entry point that starts the runner programmatically |
| The mode only affects when the turn closes. A caller who resumes after the turn closed still interrupts the tool and the policy decides what happens next | Combine turn detection with the interruption policy and the backend guard from `interruption-policies` |
