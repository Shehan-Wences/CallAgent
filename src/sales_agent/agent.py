from __future__ import annotations
import asyncio
from typing import Awaitable, Callable
from agents.realtime import RealtimeAgent, RealtimeRunner

GREETING_TRIGGER = (
    "The call has just connected. Greet the person now by delivering your "
    "opening line, then continue the conversation naturally."
)

SessionFactory = Callable[[str, str, str, list], Awaitable[object]]

async def default_session_factory(instructions: str, voice: str, model: str, tools: list):
    agent = RealtimeAgent(name="sales_agent", instructions=instructions, tools=tools)
    runner = RealtimeRunner(
        starting_agent=agent,
        config={
            "model_settings": {
                "model_name": model,
                "instructions": instructions,
                "audio": {
                    "input": {
                        "format": "pcm16",
                        "turn_detection": {"type": "semantic_vad", "interrupt_response": True},
                    },
                    "output": {"format": "pcm16", "voice": voice},
                },
            }
        },
    )
    return await runner.run()

class RealtimeSalesAgent:
    def __init__(self, instructions: str, voice: str, model: str, tools: list,
                 session_factory: SessionFactory = default_session_factory):
        self._instructions = instructions
        self._voice = voice
        self._model = model
        self._tools = tools
        self._session_factory = session_factory

    async def run(self, transport) -> None:
        session = await self._session_factory(
            self._instructions, self._voice, self._model, self._tools)
        async with session:
            await session.send_message(GREETING_TRIGGER)
            up = asyncio.create_task(self._pump_uplink(transport, session))
            down = asyncio.create_task(self._pump_downlink(session, transport))
            try:
                await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in (up, down):
                    task.cancel()
                await transport.close()

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
