"""Change-of-mind voice agent: books an appointment through one slow tool.

Run:  uv run bot.py [--policy deaf|cancel|safe]   then open http://localhost:7860/client
"""

import argparse
import os

from dotenv import load_dotenv
from loguru import logger

load_dotenv(override=True)

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.turns.user_mute import FunctionCallUserMuteStrategy
from pipecat.workers.runner import WorkerRunner

import calendar_backend
from timeline import Timeline

SYSTEM_PROMPT = """You book appointments for a clinic. Appointments are by day only (Monday to Saturday).
As soon as the caller names a day, call book_appointment with that day. Do not ask for confirmation.
If the caller changes the day, call book_appointment again with the new day.
Keep replies to one short sentence."""

GREETING = "Hi, I can book your appointment. Which day works for you?"

# --- Interruption policies ----------------------------------------------------
# One pipeline. A policy is only a user mute setting plus a backend storage mode.
#   deaf:   user input is muted while a tool runs, so the correction is never heard
#   cancel: Pipecat default. The interruption cancels the tool, but the backend
#           write is shielded and still lands, and the storage just appends
#   safe:   same as cancel, but the backend keeps one row per caller and rejects
#           a write from an older turn (seq guard)
POLICIES = {
    # name      user mute strategies (classes, one instance per session)   storage
    "deaf":   {"mute": [FunctionCallUserMuteStrategy], "storage": "append"},
    "cancel": {"mute": [],                             "storage": "append"},
    "safe":   {"mute": [],                             "storage": "upsert"},
}
DEFAULT_POLICY = "cancel"


def describe(policy: str) -> str:
    cfg = POLICIES[policy]
    mute = ", ".join(c.__name__ for c in cfg["mute"]) or "none"
    return f"policy={policy}  (user mute: {mute}; storage: {cfg['storage']})"


def policy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Change-of-mind voice agent")
    parser.add_argument("--policy", choices=POLICIES, default=DEFAULT_POLICY)
    return parser
# ------------------------------------------------------------------------------


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    session_id = runner_args.webrtc_connection.pc_id  # SmallWebRTC connection id
    policy = runner_args.cli_args.policy
    storage = POLICIES[policy]["storage"]
    print(f"\nSESSION START  {describe(policy)}", flush=True)
    user_turns = 0  # incremented when a user turn is confirmed (S0 -> S1)

    # Direct function: Pipecat builds the tool schema from the signature and
    # docstring. Default tool options, so the call is cancelled on interruption
    # (every policy; deaf avoids the interruption by muting the user instead).
    async def book_appointment(params: FunctionCallParams, day: str):
        """Book an appointment on a day of the week.

        Args:
            day: The day of the appointment, Monday to Saturday.
        """
        await calendar_backend.book(day, caller_id=session_id, seq=user_turns, mode=storage)
        await params.result_callback({"status": "booked", "day": day})

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    tts = DeepgramTTSService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            system_instruction=SYSTEM_PROMPT,
        ),
    )

    # Tools passed in the context are registered with the LLM automatically.
    context = LLMContext(tools=[book_appointment])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            user_mute_strategies=[m() for m in POLICIES[policy]["mute"]],
        ),
    )

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message):
        nonlocal user_turns
        user_turns += 1

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    # Timeline: aggregator events plus a small observer; the backend reports commits.
    timeline = Timeline()
    timeline.attach(user_aggregator, assistant_aggregator)
    calendar_backend.on_commit = timeline.commit
    calendar_backend.on_reject = timeline.reject
    worker = PipelineWorker(
        pipeline, params=PipelineParams(enable_metrics=True), observers=[timeline]
    )

    # The agent greets first, once the browser client is ready.
    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        context.add_message(
            {"role": "developer", "content": f'Greet the caller by saying exactly: "{GREETING}"'}
        )
        await worker.queue_frames([LLMRunFrame()])

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        timeline.dump(context, calendar_backend.rows_for(session_id), policy, storage)
        await runner.cancel()

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Entry point called by the Pipecat runner for each browser session."""
    transport_params = {
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    parser = policy_parser()
    print(f"STARTUP  {describe(parser.parse_known_args()[0].policy)}", flush=True)
    main(parser)  # the runner adds its own flags to our parser
