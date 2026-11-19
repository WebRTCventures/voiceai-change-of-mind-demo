# Runbook: release checks

Two manual checks before publishing. They need a voice and a microphone, so the repo owner runs them. The post describes single runs, and the single runs already logged in each spec's `tasks.md` and `design.md` are its evidence (collected in `results.md`). These two checks cover what those logs leave open. About 15 minutes.

Leave `.env` at the defaults from `.env.example`.

## 1. Fresh clone to working conversation

Purpose: the README alone gets a new reader talking to the agent.

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
4. Click **Connect** again without restarting the bot. **Disconnect**.

Pass:
- The startup lines read `STARTUP  policy=cancel  (user mute: none; tool: default; storage: append)` and `turn=smart (stop strategy: TurnAnalyzer, Smart Turn v3)`.
- The agent greets first with "Hi, I can book your appointment. Which day works for you?"
- `BACKEND COMMIT Friday seq=1` about 3 s after `TOOL book_appointment(day=Friday) started`, and a spoken confirmation about 3 s after that.
- The dump ends with `OK: 1 booking, Friday`.
- Step 4 prints a new `SESSION START` and the agent greets again. The README says no restart is needed; if this fails, that line has to go.

Send back: pass or fail per item, OS, `python3 --version`, `uv --version`, browser and version, and any step that failed or needed something the README does not mention.

## 2. S4: `yield_latency`, and the committed text stops at the interruption

```
uv run bot.py --policy safe
```

`safe` so a re-booking leaves one row.

1. Say "Book me for Friday." and stay silent through the tool call.
2. When you hear the confirmation start (`BOT  bot started speaking`), interrupt within about half a second: "Actually, make it Saturday." The earlier run interrupted about 1.5 s in, and the short sentence had already finished.
3. Stay quiet until the agent finishes, then disconnect.

Pass:
- `INTERRUPT  interruption  yield_latency=<n>ms` before `BOT  bot stopped speaking`.
- `BOT  assistant turn stopped interrupted=True "<text>"` where `<text>` ends where you cut in: shorter than the full confirmation, matching the words you heard.

The demo brief claims Pipecat commits only the words actually spoken. If `<text>` is the full sentence although you cut in early, the post must not repeat that claim. Try up to 3 runs to get an early interruption. A late one tests nothing.

Send back: the full timeline of the run, and the last word you heard.
