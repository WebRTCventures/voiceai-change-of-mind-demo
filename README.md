# Change-of-mind voice agent

Companion demo for a post about turn detection, barge-in and tool calling. A caller books an appointment, then changes their mind while the agent is still writing the booking. The agent is built with Pipecat. The scenario and the agent states (S0 to S4) are in `.kiro/steering/demo-brief.md`.

## Run

```
cp .env.example .env     # add DEEPGRAM_API_KEY and OPENAI_API_KEY
uv sync
uv run bot.py [--policy deaf|cancel|safe] [--turn smart|fast]
```

Open http://localhost:7860/client. The terminal prints a timeline, and a dump when you disconnect.

## Flags

| Flag | Values | What it changes |
|---|---|---|
| `--policy` | `deaf`, `cancel` (default), `safe` | What happens when the caller speaks while the booking tool runs |
| `--turn` | `smart` (default), `fast` | What decides that the caller has finished talking |

### `--turn`

- `smart`: Pipecat's default stop strategy, Smart Turn v3. An audio model listens after each pause and judges whether the sentence is finished, so "Book me for Friday, ummm..." can stay open.
- `fast`: a speech-timeout stop strategy. The turn closes `TURN_FAST_TIMEOUT` seconds (`.env`, default 0.2) after the caller goes quiet, whatever they sounded like.

The timeline names the strategy that closed each turn, for example `user turn stopped (SpeechTimeout)` or `(TurnAnalyzer)`.

**Smart Turn model weights.** The model ships inside the `pipecat-ai` package (`smart-turn-v3.2-cpu.onnx`, about 8.7 MB, installed by `uv sync`). Nothing downloads on first run, and it runs on the CPU. Silero VAD is bundled the same way.

## Output

The terminal shows the timeline (`+12.345  TURN ...`) and the session dump. Pipecat's own debug log is hidden once a session starts. Set `LOG_LEVEL=DEBUG` in `.env` to see it (LLM requests, STT and TTS connections). The uvicorn request lines and the few lines logged while the browser connects come from the runner and stay.
