"""Fake in-process calendar backend for the "change of mind" demo.

Stands in for a remote scheduling API. `book()` is slow on purpose: it commits
the appointment COMMIT_AT seconds after it starts and only returns at TOTAL
seconds, so a human has time to change their mind while the tool is running.
"""

import asyncio
import json
import os
import time
from datetime import datetime

CALENDAR_FILE = "calendar.json"

_calendar: list[dict] = []
# Optional callbacks the timeline sets:
#   on_commit(row, replaced)  after every write. `replaced` is the row an upsert
#                             overwrote, or None.
#   on_reject(day, seq, why)  when upsert mode refuses a stale write.
on_commit = None
on_reject = None
# Strong references to in-flight backend tasks. The event loop only keeps weak
# references, so a shielded task nobody awaits anymore could be garbage collected.
_inflight: set[asyncio.Task] = set()


async def book(day: str, caller_id: str, seq: int, mode: str = "append") -> None:
    """Book `day` for `caller_id`. `seq` is the caller's user-turn number.

    `mode` is the storage mode, chosen by the policy in bot.py:
      "append": every write adds a row (the naive backend).
      "upsert": one held row per caller, replaced on each write. A write whose
                seq is lower than the held seq is rejected as stale.
    """
    work = asyncio.ensure_future(_book(day, caller_id, seq, mode))
    _inflight.add(work)
    work.add_done_callback(_inflight.discard)
    # asyncio.shield: if our caller (the Pipecat tool task) is cancelled, the
    # CancelledError stops at this await and `work` keeps running to completion.
    # This models a remote server that never learns the client gave up: the HTTP
    # request was already sent, so the write still happens. This is the main
    # lesson of the demo.
    await asyncio.shield(work)


async def _book(day: str, caller_id: str, seq: int, mode: str) -> None:
    # Read at call time so values from .env are picked up whenever it is loaded.
    commit_at = float(os.getenv("COMMIT_AT", "3.0"))
    total = float(os.getenv("TOTAL", "6.0"))

    start = time.monotonic()
    await asyncio.sleep(commit_at)
    _write(day, caller_id, seq, mode)
    await asyncio.sleep(max(0.0, total - (time.monotonic() - start)))


def _write(day: str, caller_id: str, seq: int, mode: str) -> None:
    row = {
        "day": day,
        "caller_id": caller_id,
        "seq": seq,
        "committed_at": datetime.now().isoformat(timespec="milliseconds"),
    }
    replaced = None
    if mode == "append":
        _calendar.append(row)
    elif mode == "upsert":
        held = next((i for i, r in enumerate(_calendar) if r["caller_id"] == caller_id), None)
        if held is None:
            _calendar.append(row)
        elif seq < _calendar[held]["seq"]:
            # Seq guard: a write from an older turn must not overwrite a newer one.
            if on_reject:
                on_reject(day, seq, f"stale, held seq={_calendar[held]['seq']}")
            return
        else:
            replaced, _calendar[held] = _calendar[held], row
    else:
        raise ValueError(f"unknown storage mode: {mode!r}")
    if on_commit:
        on_commit(row, replaced)
    _show()


def rows_for(caller_id: str) -> list[dict]:
    """What the backend holds for this caller right now."""
    return [r for r in _calendar if r["caller_id"] == caller_id]


def _show() -> None:
    """Print the calendar to the terminal and save it to calendar.json."""
    print(f"\nCALENDAR ({len(_calendar)} row{'s' if len(_calendar) != 1 else ''})")
    for r in _calendar:
        print(f"  {r['day']:<10} caller={r['caller_id']} seq={r['seq']} at {r['committed_at']}")
    print(flush=True)
    with open(CALENDAR_FILE, "w") as f:
        json.dump(_calendar, f, indent=2)
