"""Change-of-mind voice agent: books an appointment through one slow tool.

Run:  uv run bot.py   then open http://localhost:7860/client
"""

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
from pipecat.workers.runner import WorkerRunner

import calendar_backend

SYSTEM_PROMPT = """You book appointments for a clinic. Appointments are by day only (Monday to Saturday).
As soon as the caller names a day, call book_appointment with that day. Do not ask for confirmation.
If the caller changes the day, call book_appointment again with the new day.
Keep replies to one short sentence."""

GREETING = "Hi, I can book your appointment. Which day works for you?"

# --- PLUG-IN POINT (later spec): --policy / --turn flags ----------------------
# A small mapping from flag value to settings will go here (e.g. tool options,
# user mute strategies, turn stop strategy). One pipeline, no forks. Note: the
# runner's main() uses a strict argparse, so custom flags need handling before
# main() is called.
# ------------------------------------------------------------------------------


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    session_id = runner_args.webrtc_connection.pc_id  # SmallWebRTC connection id
    user_turns = 0  # incremented when a user turn is confirmed (S0 -> S1)

    # Direct function: Pipecat builds the tool schema from the signature and
    # docstring. Default tool options, so the call is cancelled on interruption.
    async def book_appointment(params: FunctionCallParams, day: str):
        """Book an appointment on a day of the week.

        Args:
            day: The day of the appointment, Monday to Saturday.
        """
        await calendar_backend.book(day, caller_id=session_id, seq=user_turns)
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
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
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

    # --- PLUG-IN POINT (later spec): timeline -----------------------------------
    # Pass timeline observers to PipelineWorker(observers=[...]) and register the
    # timeline's aggregator event handlers here. Dump the timeline on disconnect.
    # -----------------------------------------------------------------------------
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True))

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

    main()
