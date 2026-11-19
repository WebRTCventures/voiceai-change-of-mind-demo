"""Timeline: one terminal line per event, latency numbers, end-of-session dump.

Turn, mute and assistant-turn events come from the context aggregators. A small
observer (this class) adds what they do not carry: VAD, interruption, bot
speaking and function call frames, including the model calling Pipecat's
cancel_<tool> tool and an async result that arrives after the caller spoke
(llm-cancel). States S2 and S4 are from the demo brief.
"""

import json
import re
import time

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    FunctionCallCancelFrame,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
    FunctionCallsStartedFrame,
    InterruptionFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver
from pipecat.processors.aggregators import async_tool_messages
from pipecat.processors.frame_processor import FrameDirection
from pipecat.utils.async_tool_cancellation import CANCEL_TOOL_PREFIX


_FLUSHES = (
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
    BotStartedSpeakingFrame,
    FunctionCallsStartedFrame,
    FunctionCallResultFrame,
)


def _name(strategy) -> str:
    if strategy is None:
        return "no strategy"  # closed by user_turn_stop_timeout (5 s) or by the session ending
    return re.sub(r"UserTurn(Start|Stop)Strategy$", "", type(strategy).__name__)


class Timeline(BaseObserver):
    def __init__(self):
        super().__init__(observe_every_push=False)  # each frame once, at its first push
        self.t0 = time.monotonic()
        self.turns = 0  # stopped user turns, same count as bot.py's seq
        self.speech_start = None  # when the current user speech began
        self.bot_speaking = False  # S4
        self.running = {}  # tool_call_id -> (name, seq); non-empty means S2
        self.async_ids = set()  # running calls with cancel_on_interruption=False (llm-cancel)
        self.cancelled_seqs = set()
        self.cancelled_ids = set()
        self.calls = []  # (tool_call_id, day) of every book_appointment call the model made
        self.model_cancelling = False  # the model's cancel_<tool> call is running
        self.pending = None  # INTERRUPT line waiting for its latency numbers
        self.kept = []  # async calls the pending interruption left running
        self.muted = False  # user mute is on (deaf policy)

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
            self.speech_start = None  # the next interruption must not reuse this turn's VAD onset
            self.log("TURN", f'user turn stopped ({_name(strategy)}) "{message.content}"')

        @user.event_handler("on_user_mute_started")
        async def _(agg):
            self.muted = True
            self.log("MUTE", "user mute started")

        @user.event_handler("on_user_mute_stopped")
        async def _(agg):
            self.muted = False
            self.log("MUTE", "user mute stopped")

        @assistant.event_handler("on_assistant_turn_stopped")
        async def _(agg, message):
            self.log("BOT", f'assistant turn stopped interrupted={message.interrupted} "{message.content}"')

    # --- backend hooks (calendar_backend.on_commit = timeline.commit) ----------
    def commit(self, row: dict, replaced: dict | None = None):
        late = " (tool was already cancelled)" if row["seq"] in self.cancelled_seqs else ""
        over = f" (replaced {replaced['day']} seq={replaced['seq']})" if replaced else ""
        self.log("BACKEND", f"COMMIT {row['day']} seq={row['seq']}{over}{late}")

    def reject(self, day: str, seq: int, reason: str):
        """The backend refused a stale write (upsert mode, seq guard)."""
        self.log("BACKEND", f"REJECT {day} seq={seq} ({reason})")

    # --- observer: frames the aggregator events do not cover -------------------
    async def on_push_frame(self, data):
        f = data.frame
        if data.direction != FrameDirection.DOWNSTREAM:
            return  # frames are often sent both ways as separate copies, read the downstream one
        # Any other event line means the pending INTERRUPT line will not get its numbers.
        if isinstance(f, _FLUSHES):
            self._flush()
        if isinstance(f, TranscriptionFrame) and self.muted:
            # STT is upstream of the user aggregator, so it still transcribes. The
            # aggregator ignores the frame while muted; a TURN line after "user
            # mute stopped" would mean it was delivered late instead.
            self.log("MUTE", f'transcript while muted "{f.text}"')
        if isinstance(f, VADUserStartedSpeakingFrame):
            # The VAD confirms speech start_secs after it began, so back-date the onset.
            self.speech_start = self.now() - f.start_secs
            self.log("VAD", "user started speaking")
        elif isinstance(f, VADUserStoppedSpeakingFrame):
            self.log("VAD", "user stopped speaking")
        elif isinstance(f, InterruptionFrame):
            self._flush()
            # An interruption cancels only sync calls. Async ones (llm-cancel) keep running.
            sync = any(i not in self.async_ids for i in self.running)
            self.kept = [f"{n} seq={s}" for i, (n, s) in self.running.items() if i in self.async_ids]
            waits = {"tool_cancel_latency": sync, "yield_latency": self.bot_speaking}
            self.pending = {k: None for k, on in waits.items() if on}
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
                    self.calls.append((c.tool_call_id, c.arguments.get("day")))
                args = ", ".join(f"{k}={v}" for k, v in c.arguments.items())
                self.log("TOOL", f"{c.function_name}({args}) started  seq={self.turns}")
        elif isinstance(f, FunctionCallInProgressFrame):
            if f.function_name.startswith(CANCEL_TOOL_PREFIX):
                # Pipecat leaves its built-in cancel tool out of FunctionCallsStartedFrame,
                # so this frame is the first sign that the model called it.
                self._flush()
                self.model_cancelling = True
                args = ", ".join(f"{k}={v}" for k, v in f.arguments.items())
                self.log("TOOL", f"model called {f.function_name}({args})")
            elif not f.cancel_on_interruption:
                self.async_ids.add(f.tool_call_id)
        elif isinstance(f, FunctionCallCancelFrame):
            name, seq = self.running.pop(f.tool_call_id, (f.function_name, "?"))
            self.cancelled_seqs.add(seq)
            self.cancelled_ids.add(f.tool_call_id)
            self._resolve("tool_cancel_latency")
            by = " by the model" if self.model_cancelling else ""
            self.log("TOOL", f"{name} seq={seq} CANCELLED{by}")
        elif isinstance(f, FunctionCallResultFrame):
            if f.function_name.startswith(CANCEL_TOOL_PREFIX):
                self.model_cancelling = False
                r = f.result if isinstance(f.result, dict) else {}
                # A refusal's reason lists the running calls after a colon; the dump has it in full.
                why = str(r.get("reason", f.result)).split(":")[0]
                done = f"cancelled {r['cancelled']}" if r.get("cancelled") else f"refused: {why}"
                self.log("TOOL", f"{f.function_name} {done}")
                return
            name, seq = self.running.pop(f.tool_call_id, (f.function_name, "?"))
            # Pipecat's rule for an async call: if a user message came after the call
            # started, the result goes in as a new developer message instead of
            # replacing the tool placeholder. A stopped user turn is that user message.
            late = ""
            if f.tool_call_id in self.async_ids and seq != "?" and self.turns > seq:
                late = "  LATE: caller spoke since, injected as a developer message"
            self.log("TOOL", f"{name} seq={seq} result {json.dumps(f.result)}{late}")

    def _resolve(self, key: str):
        """Fill in one latency (ms since user speech start); print once all are known."""
        if self.pending and self.pending.get(key, 0) is None:
            # n/a: the turn was started by a transcript, VAD never saw this speech
            ms = None if self.speech_start is None else (self.now() - self.speech_start) * 1000
            self.pending[key] = "n/a" if ms is None else f"{ms:.0f}ms"
            if None not in self.pending.values():
                self._flush()

    def _flush(self):
        if self.pending is None:
            return
        nums = "".join(f"  {k}={v or 'n/a'}" for k, v in self.pending.items())
        if self.kept:
            nums += f"  ({', '.join(self.kept)} keeps running)"
        self.pending = None
        self.kept = []
        self.log("INTERRUPT", f"interruption{nums}")

    # --- end of session ---------------------------------------------------------
    def dump(self, context, rows, policy: str, storage: str, turn: str):
        """`rows` is what the backend holds for this caller (see rows_for)."""
        msgs = context.get_messages()
        print(f"\n=== SESSION DUMP ===\nPOLICY {policy} (storage: {storage})\nTURN MODE {turn}\nCALENDAR ({len(rows)} row{'s' * (len(rows) != 1)})")
        for r in rows:
            print(f"  {r['day']:<10} seq={r['seq']} at {r['committed_at']}")
        print(f"CONTEXT ({len(msgs)} messages)")
        for m in (m for m in msgs if isinstance(m, dict)):
            calls = "; ".join(
                f"{c['function']['name']}({c['function']['arguments']}) id={c['id']}"
                for c in m.get("tool_calls", [])
            )
            tool_id = f"id={m['tool_call_id']} " if m["role"] == "tool" else ""
            print(f"  {m['role']:<9} {tool_id}{calls or _short(m)}")
        # What the model last asked for and did not cancel. The cancelled call's
        # write is shielded and can still land, so a cancel does not empty the calendar.
        wanted = [day for i, day in self.calls if i not in self.cancelled_ids]
        days = [r["day"] for r in rows]
        if not wanted and self.calls:
            ok = not days
            n = f"{len(days)} booking{'s' * (len(days) != 1)}"
            print(f"{'OK' if ok else 'MISMATCH'}: {n} ({', '.join(days) or 'none'}), "
                  "the model cancelled every booking call")
        elif len(days) == 1 and days[0].lower() == str(wanted[-1] if wanted else None).lower():
            # The verdict only knows what the model asked for. In deaf mode the
            # caller's correction never reached the model, so OK proves nothing.
            note = "  <- expected for deaf: the correction was muted" if policy == "deaf" else ""
            print(f"OK: 1 booking, {days[0]}{note}")
        else:
            print(f"MISMATCH: {len(days)} bookings ({', '.join(days) or 'none'})")


def _short(m: dict) -> str:
    """Message content for the dump. Async-tool messages drop their long description."""
    p = async_tool_messages.parse_message(m)
    if p is None:
        return str(m.get("content"))
    who = "" if m["role"] == "tool" else f" id={p.tool_call_id}"  # tool lines print the id already
    return f"async_tool {p.status}{who}" + (f" {p.result}" if p.result else "")
