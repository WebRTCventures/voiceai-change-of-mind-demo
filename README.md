# Change-of-mind voice agent

Companion demo for a blog post about turn detection, barge-in and tool calling. A caller books an appointment, then changes their mind while the agent is still writing the booking. Built with Pipecat.

## Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- A Deepgram API key and an OpenAI API key
- A browser with a microphone (headphones recommended)

## Setup

```
git clone https://github.com/WebRTCventures/voiceai-change-of-mind-demo.git
cd voiceai-change-of-mind-demo
cp .env.example .env      # fill in DEEPGRAM_API_KEY and OPENAI_API_KEY
uv sync
```

## Run

```
uv run bot.py [--policy deaf|cancel|safe|llm-cancel] [--turn smart|fast]
```

Defaults: `--policy cancel`, `--turn smart`.

Open http://localhost:7860/client and click **Connect**. The agent greets you. Click **Disconnect** to end the session; the terminal prints the timeline as you talk and a session dump at the end.

## What to say

**Main script** (try each `--policy`):
1. "Book me for Friday."
2. Wait for `TOOL  book_appointment(day=Friday) started` in the terminal.
3. About 2 s later: "Actually, wait, make it Saturday."
4. Stay quiet until the agent finishes, then disconnect.

**Turn detection** (`--policy cancel`, compare `--turn fast` and `--turn smart`): "Book me for Friday, ummm..." with no gap before "ummm", about 2 s of silence, then "actually Saturday".

**Barge-in** (`--policy safe`): "Book me for Friday." When the agent starts the confirmation, interrupt it right away.

## Settings

Optional, in `.env`: `OPENAI_MODEL`, the tool timing (`COMMIT_AT`, `TOTAL`), `TURN_FAST_TIMEOUT`, and `LOG_LEVEL=DEBUG` to show Pipecat's own log. Each is described in `.env.example`.
