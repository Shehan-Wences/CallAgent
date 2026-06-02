from __future__ import annotations
import os
from pathlib import Path
from typing import Callable
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from .campaign import Campaign
from .instructions import build_instructions
from .booking import BookingStore
from .tools import build_tools
from .agent import RealtimeSalesAgent
from .transport import BrowserWebSocketTransport

_STATIC = Path(__file__).parent / "static"

def default_agent_factory(campaign: Campaign, model: str, lead_name: str) -> RealtimeSalesAgent:
    instructions = build_instructions(campaign, lead_name)
    store = BookingStore(os.environ.get("BOOKINGS_PATH", "bookings.json"))
    tools = build_tools(store)
    return RealtimeSalesAgent(
        instructions=instructions,
        voice=campaign.persona.get("voice", "marin"),
        model=model,
        tools=tools,
    )

def create_app(campaign: Campaign, model: str,
               agent_factory: Callable[..., RealtimeSalesAgent] = default_agent_factory) -> FastAPI:
    app = FastAPI()

    @app.get("/")
    async def index():
        return FileResponse(_STATIC / "index.html")

    @app.websocket("/session")
    async def session(ws: WebSocket):
        await ws.accept()
        lead_name = ws.query_params.get("lead_name") or "there"
        transport = BrowserWebSocketTransport(ws)
        agent = agent_factory(campaign, model, lead_name)
        await agent.run(transport)

    return app
