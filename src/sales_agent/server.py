from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Callable
from uuid import uuid4
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.websockets import WebSocketDisconnect
from .campaign import Campaign, load_campaign, CampaignError
from .instructions import build_instructions
from .booking import BookingStore
from .tools import build_tools
from .agent import RealtimeSalesAgent
from .transport import BrowserWebSocketTransport
from .twilio_transport import TwilioMediaStreamTransport, read_stream_start

_STATIC = Path(__file__).parent / "static"


def _build_agent(campaign: Campaign, model: str, lead_name: str, audio_format: str) -> RealtimeSalesAgent:
    instructions = build_instructions(campaign, lead_name)
    store = BookingStore(os.environ.get("BOOKINGS_PATH", "bookings.json"))
    tools = build_tools(store)
    return RealtimeSalesAgent(
        instructions=instructions,
        voice=campaign.persona.get("voice", "marin"),
        model=model,
        tools=tools,
        audio_format=audio_format,
    )


def default_agent_factory(campaign: Campaign, model: str, lead_name: str) -> RealtimeSalesAgent:
    """Browser call: pcm16 @ 24 kHz."""
    return _build_agent(campaign, model, lead_name, audio_format="pcm16")


def default_twilio_agent_factory(campaign: Campaign, model: str, lead_name: str) -> RealtimeSalesAgent:
    """Phone call: g711 μ-law @ 8 kHz to match Twilio Media Streams."""
    return _build_agent(campaign, model, lead_name, audio_format="g711_ulaw")


def default_twilio_client_factory(account_sid: str, auth_token: str):
    from twilio.rest import Client  # imported lazily so tests can inject a fake
    return Client(account_sid, auth_token)


def _build_twiml(public_host: str, call_id: str, campaign: str, lead_name: str) -> str:
    from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
    response = VoiceResponse()
    connect = Connect()
    scheme = "ws" if public_host.startswith("localhost") or public_host.startswith("127.") else "wss"
    stream = Stream(url=f"{scheme}://{public_host}/twilio-stream")
    stream.parameter(name="call_id", value=call_id or "")
    stream.parameter(name="campaign", value=campaign or "")
    stream.parameter(name="lead_name", value=lead_name or "there")
    connect.append(stream)
    response.append(connect)
    return str(response)


def _safe_name(filename: str) -> str:
    name = Path(filename).name
    if not name.endswith(".md") or name.startswith("."):
        raise CampaignError("Campaign file name must be a plain '*.md' file.")
    return name


def list_campaigns(campaigns_dir: str | Path) -> list[dict]:
    directory = Path(campaigns_dir)
    if not directory.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(directory.glob("*.md")):
        entry = {"file": path.name, "product": None, "valid": True}
        try:
            entry["product"] = load_campaign(path).product.get("name")
        except CampaignError as exc:
            entry["valid"] = False
            entry["error"] = str(exc)
        out.append(entry)
    return out


def save_campaign(campaigns_dir: str | Path, filename: str, content: str) -> Campaign:
    directory = Path(campaigns_dir)
    directory.mkdir(parents=True, exist_ok=True)
    name = _safe_name(filename)
    tmp = directory / f".{name}.upload"
    tmp.write_text(content)
    try:
        campaign = load_campaign(tmp)
    except CampaignError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(directory / name)
    return campaign


def create_app(campaign: Campaign, model: str,
               agent_factory: Callable[..., RealtimeSalesAgent] = default_agent_factory,
               campaigns_dir: str | Path = "campaigns",
               default_campaign_file: str | None = None,
               twilio_agent_factory: Callable[..., RealtimeSalesAgent] = default_twilio_agent_factory,
               twilio_client_factory: Callable[..., object] = default_twilio_client_factory) -> FastAPI:
    app = FastAPI()
    campaigns_dir = Path(campaigns_dir)
    monitors: dict[str, BrowserWebSocketTransport] = {}   # call_id -> browser monitor channel

    def _resolve_campaign(requested: str | None) -> Campaign:
        if not requested:
            return campaign
        try:
            return load_campaign(campaigns_dir / _safe_name(requested))
        except CampaignError:
            return campaign

    @app.get("/")
    async def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/campaigns")
    async def campaigns():
        return {"default": default_campaign_file, "campaigns": list_campaigns(campaigns_dir)}

    @app.post("/campaigns")
    async def upload_campaign(request: Request):
        filename = request.query_params.get("file", "")
        content = (await request.body()).decode("utf-8", errors="replace")
        try:
            saved = save_campaign(campaigns_dir, filename, content)
        except CampaignError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
        return {"ok": True, "file": _safe_name(filename), "product": saved.product.get("name")}

    # ---- Browser call (mic in the browser) ---------------------------------
    @app.websocket("/session")
    async def session(ws: WebSocket):
        await ws.accept()
        lead_name = ws.query_params.get("lead_name") or "there"
        chosen = _resolve_campaign(ws.query_params.get("campaign"))
        transport = BrowserWebSocketTransport(ws)
        agent = agent_factory(chosen, model, lead_name)
        await agent.run(transport)

    # ---- Phone call (Twilio) : monitor + initiate + media bridge -----------
    @app.websocket("/monitor")
    async def monitor(ws: WebSocket):
        """Browser observer: receives transcript + status for a phone call."""
        await ws.accept()
        call_id = uuid4().hex
        monitors[call_id] = BrowserWebSocketTransport(ws)
        await ws.send_text(json.dumps({"type": "call_id", "call_id": call_id}))
        try:
            while True:
                await ws.receive_text()   # keepalive; ignore inbound, detect close
        except WebSocketDisconnect:
            pass
        finally:
            monitors.pop(call_id, None)

    @app.post("/call")
    async def call(request: Request):
        data = await request.json()
        phone = data.get("phone")
        call_id = data.get("call_id")
        campaign_file = data.get("campaign") or ""
        lead_name = data.get("lead_name") or "there"

        creds = {
            "TWILIO_ACCOUNT_SID": os.environ.get("TWILIO_ACCOUNT_SID"),
            "TWILIO_AUTH_TOKEN": os.environ.get("TWILIO_AUTH_TOKEN"),
            "TWILIO_FROM_NUMBER": os.environ.get("TWILIO_FROM_NUMBER"),
            "PUBLIC_HOST": os.environ.get("PUBLIC_HOST"),
        }
        missing = [k for k, v in creds.items() if not v]
        if missing:
            return JSONResponse(status_code=400, content={
                "ok": False, "error": "Missing config: " + ", ".join(missing)})
        if not phone:
            return JSONResponse(status_code=400, content={"ok": False, "error": "phone is required"})

        twiml = _build_twiml(creds["PUBLIC_HOST"], call_id, campaign_file, lead_name)
        try:
            client = twilio_client_factory(creds["TWILIO_ACCOUNT_SID"], creds["TWILIO_AUTH_TOKEN"])
            created = client.calls.create(to=phone, from_=creds["TWILIO_FROM_NUMBER"], twiml=twiml)
        except Exception as exc:  # network / auth / invalid number
            return JSONResponse(status_code=502, content={"ok": False, "error": str(exc)})

        mon = monitors.get(call_id)
        if mon is not None:
            await mon.send_event({"type": "status", "status": "dialing", "phone": phone})
        return {"ok": True, "call_sid": getattr(created, "sid", None)}

    @app.websocket("/twilio-stream")
    async def twilio_stream(ws: WebSocket):
        await ws.accept()
        stream_sid, params = await read_stream_start(ws)
        call_id = params.get("call_id")
        lead_name = params.get("lead_name") or "there"
        chosen = _resolve_campaign(params.get("campaign"))
        mon = monitors.get(call_id) if call_id else None
        if mon is not None:
            await mon.send_event({"type": "status", "status": "connected"})
        transport = TwilioMediaStreamTransport(ws, stream_sid=stream_sid, monitor=mon)
        agent = twilio_agent_factory(chosen, model, lead_name)
        try:
            await agent.run(transport)
        finally:
            if mon is not None:
                await mon.send_event({"type": "status", "status": "ended"})

    return app
