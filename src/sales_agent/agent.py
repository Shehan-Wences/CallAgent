from __future__ import annotations
import asyncio
import os
from typing import Awaitable, Callable
from agents.realtime import RealtimeAgent, RealtimeRunner

GREETING_TRIGGER = (
    "The call has just connected. Greet the person now by delivering your "
    "opening line, then continue the conversation naturally."
)

SessionFactory = Callable[[str, str, str, list], Awaitable[object]]


def _turn_detection() -> dict:
    """Voice-activity detection tuned to avoid interrupting on slight sounds.

    Server VAD with a raised threshold + longer trailing silence is far less
    twitchy than the default. Tunable at runtime via env without a rebuild:
      VAD_THRESHOLD   (0.0-1.0, higher = needs louder speech to trigger; default 0.6)
      VAD_SILENCE_MS  (ms of silence before the caller's turn ends; default 800)
    """
    return {
        "type": "server_vad",
        "threshold": float(os.environ.get("VAD_THRESHOLD", "0.6")),
        "prefix_padding_ms": int(os.environ.get("VAD_PREFIX_MS", "300")),
        "silence_duration_ms": int(os.environ.get("VAD_SILENCE_MS", "800")),
        # Genuine barge-in still works; the higher threshold + browser echo
        # cancellation stop the agent from interrupting itself.
        "interrupt_response": os.environ.get("VAD_INTERRUPT", "true").lower() != "false",
    }


async def default_session_factory(instructions: str, voice: str, model: str, tools: list,
                                  audio_format: str = "pcm16"):
    # pcm16 (24 kHz) for the browser; g711_ulaw (8 kHz) for a Twilio phone leg.
    agent = RealtimeAgent(name="sales_agent", instructions=instructions, tools=tools)
    runner = RealtimeRunner(
        starting_agent=agent,
        config={
            "model_settings": {
                "model_name": model,
                "instructions": instructions,
                "audio": {
                    "input": {
                        "format": audio_format,
                        "turn_detection": _turn_detection(),
                        # Suppress background noise so it doesn't trip the VAD.
                        "noise_reduction": {"type": "near_field"},
                        # Transcribe the caller's speech so the browser can show a live transcript.
                        "transcription": {"model": "gpt-4o-mini-transcribe"},
                    },
                    "output": {"format": audio_format, "voice": voice},
                },
            }
        },
    )
    return await runner.run()

class RealtimeSalesAgent:
    def __init__(self, instructions: str, voice: str, model: str, tools: list,
                 session_factory: SessionFactory = default_session_factory,
                 audio_format: str = "pcm16"):
        self._instructions = instructions
        self._voice = voice
        self._model = model
        self._tools = tools
        self._session_factory = session_factory
        self._audio_format = audio_format

    async def run(self, transport) -> None:
        session = await self._session_factory(
            self._instructions, self._voice, self._model, self._tools,
            audio_format=self._audio_format)
        async with session:
            await session.send_message(GREETING_TRIGGER)
            up = asyncio.create_task(self._pump_uplink(transport, session))
            down = asyncio.create_task(self._pump_downlink(session, transport))
            try:
                done, pending = await asyncio.wait(
                    {up, down}, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            finally:
                await transport.close()
            for task in done:
                task.result()  # re-raise a genuine session/transport error, not swallow it

    async def _pump_uplink(self, transport, session) -> None:
        while True:
            chunk = await transport.recv_audio()
            if chunk is None:
                break
            if chunk:
                await session.send_audio(chunk)

    async def _pump_downlink(self, session, transport) -> None:
        async for event in session:
            if event.type == "audio":
                await transport.send_audio(event.audio.data)
            elif event.type == "audio_interrupted":
                await transport.notify_interrupted()
            elif event.type == "raw_model_event":
                await self._forward_transcript(event.data, transport)

    async def _forward_transcript(self, data, transport) -> None:
        """Relay transcript events to the browser as JSON for the live transcript."""
        if data.type == "transcript_delta":  # streaming agent (assistant) speech
            await transport.send_event({
                "type": "transcript", "role": "assistant",
                "item_id": data.item_id, "delta": data.delta, "final": False,
            })
        elif data.type == "input_audio_transcription_completed":  # caller (user) speech
            await transport.send_event({
                "type": "transcript", "role": "user",
                "item_id": data.item_id, "text": data.transcript, "final": True,
            })
