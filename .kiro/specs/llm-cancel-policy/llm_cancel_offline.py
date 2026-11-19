"""Offline check C for --policy llm-cancel. No API keys, no microphone.

Real Pipecat pieces: the LLM service's function-call machinery and cancel tool,
the context aggregators, plus the demo's Timeline and backend. Only the model's
choices are scripted. The caller's two sentences are fed as transcripts.

Run from the repo root:
    uv run python .kiro/specs/llm-cancel-policy/llm_cancel_offline.py <variant> [policy]

variant: what the scripted model does with "make it Saturday"
    rebook         book_appointment(Saturday), no cancel
    cancel-only    cancel_book_appointment(), no new booking
    cancel+rebook  both calls in one response (they run in parallel)
    question       a reply, no tool call
policy:  llm-cancel (default), cancel or safe. deaf is not covered (no mute strategy here)

Uses Pipecat internals pinned to 1.16.0: it overrides OpenAILLMService._process_context
and uses pipecat.tests.utils.run_test. A Pipecat upgrade may break this script.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")

from pipecat.adapters.llm.schemas.direct_function import tool_options
from pipecat.frames.frames import FunctionCallFromLLM, LLMTextFrame, TranscriptionFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.pipeline.pipeline import Pipeline
from pipecat.tests.utils import SleepFrame, run_test

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root
import bot  # loads .env with override=True, so the short timings are set after this
import calendar_backend
from timeline import Timeline

# Shorter than the live 3 s / 6 s. As in the live runs, the Friday write lands
# before the model can cancel; the Friday result arrives after the correction.
os.environ["COMMIT_AT"] = "0.6"
os.environ["TOTAL"] = "1.6"

VARIANT = sys.argv[1] if len(sys.argv) > 1 else "cancel+rebook"
POLICY = sys.argv[2] if len(sys.argv) > 2 else "llm-cancel"


class ScriptedLLM(OpenAILLMService):
    """The real service with the OpenAI request replaced by a script."""

    async def _process_context(self, context):
        msgs = [m for m in context.get_messages() if isinstance(m, dict)]
        last = msgs[-1]
        users = [m["content"] for m in msgs if m["role"] == "user"]
        call = lambda name, **a: FunctionCallFromLLM(name, f"call_{uuid.uuid4().hex[:6]}", a, context)
        if last["role"] == "user" and "Friday" in last["content"]:
            await self.run_function_calls([call("book_appointment", day="Friday")])
        elif last["role"] == "user" and "Saturday" in last["content"]:
            if VARIANT == "cancel+rebook":
                await self.run_function_calls(
                    [call("cancel_book_appointment"), call("book_appointment", day="Saturday")]
                )
            elif VARIANT == "rebook":
                await self.run_function_calls([call("book_appointment", day="Saturday")])
            elif VARIANT == "cancel-only":
                await self.run_function_calls([call("cancel_book_appointment")])
            elif VARIANT == "question":
                await self.push_frame(LLMTextFrame("Do you want Saturday instead of Friday?"))
        else:
            await self.push_frame(LLMTextFrame(f"Reply after {last['role']} message."))


async def main():
    seq = 0
    session = "offline"

    async def book_appointment(params: FunctionCallParams, day: str):
        """Book an appointment on a day of the week.

        Args:
            day: The day of the appointment, Monday to Saturday.
        """
        await calendar_backend.book(day, caller_id=session, seq=seq, mode=bot.POLICIES[POLICY]["storage"])
        await params.result_callback({"status": "booked", "day": day})

    print(bot.describe(POLICY))
    llm = ScriptedLLM(api_key="x", settings=OpenAILLMService.Settings(model="scripted"))
    context = LLMContext(tools=[tool_options(book_appointment, **bot.POLICIES[POLICY]["tool"])])
    user, assistant = LLMContextAggregatorPair(context)
    timeline = Timeline()
    timeline.attach(user, assistant)
    calendar_backend.on_commit = timeline.commit
    calendar_backend.on_reject = timeline.reject

    @user.event_handler("on_user_turn_stopped")
    async def _(agg, strategy, message):
        nonlocal seq
        seq += 1

    t = lambda text: TranscriptionFrame(text=text, user_id="u", timestamp="0")
    await run_test(
        Pipeline([user, llm, assistant]),
        frames_to_send=[
            t("Book me for Friday."),
            SleepFrame(sleep=0.8),  # turn closes, tool starts; correction ~0.3 s into the tool
            t("Actually, wait, make it Saturday."),
            SleepFrame(sleep=3.0),
        ],
        observers=[timeline],
    )
    timeline.dump(context, calendar_backend.rows_for(session), POLICY, bot.POLICIES[POLICY]["storage"], "n/a")


asyncio.run(main())
