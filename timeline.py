"""Timeline: one terminal line per event, latency numbers, end-of-session dump.

Turn, mute and assistant-turn events come from the context aggregators. A small
observer (this class) adds what they do not carry: VAD, interruption, bot
speaking and function call frames. States S2 and S4 are from the demo brief.
"""

import json
import re
import time

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    FunctionCallCancelFrame,
    FunctionCallResultFrame,
    FunctionCallsStartedFrame,
    InterruptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver
from pipecat.processors.frame_processor import FrameDirection


_FLUSHES = (
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
    BotStartedSpeakingFrame,
    FunctionCallsStartedFrame,
    FunctionCallResultFrame,
)


def _name(strategy) -> str:
    return re.sub(r"UserTurn(Start|Stop)Strategy$", "", type(strategy).__name__)


class Timeline(BaseObserver):
    def __init__(self):
        super().__init__(observe_every_push=False)  # each frame once, at its first push
        self.t0 = time.monotonic()
        self.turns = 0  # stopped user turns, same count as bot.py's seq
        self.speech_start = None  # when the current user speech began
        self.bot_speaking = False  # S4
        self.running = {}  # tool_call_id -> (name, seq); non-empty means S2
        self.cancelled_seqs = set()
        self.last_day = None  # day of the last book_appointment call the model made
        self.pending = None  # INTERRUPT line waiting for its latency numbers
        self.commits = []  # rows reported by the backend

    def now(self) -> float:
        return time.monotonic() - self.t0

    def log(self, category: str, message: str):
        print(f"{self.now():+8.3f}  {category:<9}  {message}", flush=True)

    # --- aggregator events ---------------------------------------------------
    def attach(self, user, assistant):
        @user.event_handler("on_user_turn_started")
        async def _(agg, strategy):
            self.log("TURN", f"user turn started ({_name(strategy)})")

        @user.event_handler("on_user_turn_stopped")
        async def _(agg, strategy, message):
            self.turns += 1
            self.log("TURN", f'user turn stopped ({_name(strategy)}) "{message.content}"')

        @user.event_handler("on_user_mute_started")
        async def _(agg):
            self.log("MUTE", "user mute started")

        @user.event_handler("on_user_mute_stopped")
        async def _(agg):
            self.log("MUTE", "user mute stopped")

        @assistant.event_handler("on_assistant_turn_stopped")
        async def _(agg, message):
            self.log("BOT", f'assistant turn stopped interrupted={message.interrupted} "{message.content}"')

    # --- backend hooks (calendar_backend.on_commit = timeline.commit) ----------
    def commit(self, row: dict):
        self.commits.append(row)
        late = " (tool was already cancelled)" if row["seq"] in self.cancelled_seqs else ""
        self.log("BACKEND", f"COMMIT {row['day']} seq={row['seq']}{late}")

    def reject(self, day: str, seq: int, reason: str):
        """Hook for a later spec: the backend refuses a stale write."""
        self.log("BACKEND", f"REJECT {day} seq={seq} ({reason})")

    # --- observer: frames the aggregator events do not cover -------------------
    async def on_push_frame(self, data):
        f = data.frame
        if data.direction != FrameDirection.DOWNSTREAM:
            return  # frames are often sent both ways as separate copies, read the downstream one
        # Any other event line means the pending INTERRUPT line will not get its numbers.
        if isinstance(f, _FLUSHES):
            self._flush()
        if isinstance(f, VADUserStartedSpeakingFrame):
            # The VAD confirms speech start_secs after it began, so back-date the onset.
            self.speech_start = self.now() - f.start_secs
            self.log("VAD", "user started speaking")
        elif isinstance(f, VADUserStoppedSpeakingFrame):
            self.log("VAD", "user stopped speaking")
        elif isinstance(f, InterruptionFrame):
            self._flush()
            waits = {"tool_cancel_latency": bool(self.running), "yield_latency": self.bot_speaking}
            self.pending = {k: None for k, on in waits.items() if on and self.speech_start is not None}
            if not self.pending:
                self._flush()
        elif isinstance(f, BotStartedSpeakingFrame):
            self.bot_speaking = True
            self.log("BOT", "bot started speaking")
        elif isinstance(f, BotStoppedSpeakingFrame):
            self.bot_speaking = False
            self._resolve("yield_latency")
            self.log("BOT", "bot stopped speaking")
        elif isinstance(f, FunctionCallsStartedFrame):
            for c in f.function_calls:
                self.running[c.tool_call_id] = (c.function_name, self.turns)
                if c.function_name == "book_appointment":
                    self.last_day = c.arguments.get("day")
                args = ", ".join(f"{k}={v}" for k, v in c.arguments.items())
                self.log("TOOL", f"{c.function_name}({args}) started  seq={self.turns}")
        elif isinstance(f, FunctionCallCancelFrame):
            name, seq = self.running.pop(f.tool_call_id, (f.function_name, "?"))
            self.cancelled_seqs.add(seq)
            self._resolve("tool_cancel_latency")
            self.log("TOOL", f"{name} seq={seq} CANCELLED")
        elif isinstance(f, FunctionCallResultFrame):
            name, seq = self.running.pop(f.tool_call_id, (f.function_name, "?"))
            self.log("TOOL", f"{name} seq={seq} result {json.dumps(f.result)}")

    def _resolve(self, key: str):
        """Fill in one latency (ms since user speech start); print once all are known."""
        if self.pending and self.pending.get(key, 0) is None:
            self.pending[key] = (self.now() - self.speech_start) * 1000
            if None not in self.pending.values():
                self._flush()

    def _flush(self):
        if self.pending is None:
            return
        nums = "".join(f"  {k}={'n/a' if v is None else f'{v:.0f}ms'}" for k, v in self.pending.items())
        self.pending = None
        self.log("INTERRUPT", f"interruption{nums}")

    # --- end of session ---------------------------------------------------------
    def dump(self, context):
        rows, msgs = self.commits, context.get_messages()
        print(f"\n=== SESSION DUMP ===\nCALENDAR ({len(rows)} row{'s' * (len(rows) != 1)})")
        for r in rows:
            print(f"  {r['day']:<10} seq={r['seq']} at {r['committed_at']}")
        print(f"CONTEXT ({len(msgs)} messages)")
        for m in (m for m in msgs if isinstance(m, dict)):
            calls = "; ".join(
                f"{c['function']['name']}({c['function']['arguments']}) id={c['id']}"
                for c in m.get("tool_calls", [])
            )
            tool_id = f"id={m['tool_call_id']} " if m["role"] == "tool" else ""
            print(f"  {m['role']:<9} {tool_id}{calls or m.get('content')}")
        days = [r["day"] for r in rows]
        if len(days) == 1 and days[0].lower() == str(self.last_day).lower():
            print(f"OK: 1 booking, {days[0]}")
        else:
            print(f"MISMATCH: {len(days)} bookings ({', '.join(days) or 'none'})")
