from __future__ import annotations
import os
from pathlib import Path
from typing import Callable
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import FileResponse, JSONResponse
from .campaign import Campaign, load_campaign, CampaignError
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


def _safe_name(filename: str) -> str:
    """Reduce an uploaded/selected name to a safe '<name>.md' basename."""
    name = Path(filename).name  # strips any path components
    if not name.endswith(".md") or name.startswith("."):
        raise CampaignError("Campaign file name must be a plain '*.md' file.")
    return name


def list_campaigns(campaigns_dir: str | Path) -> list[dict]:
    """List '*.md' campaigns in a directory with their product name and validity."""
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
    """Validate raw campaign markdown and, if valid, save it. Raises CampaignError if not."""
    directory = Path(campaigns_dir)
    directory.mkdir(parents=True, exist_ok=True)
    name = _safe_name(filename)
    tmp = directory / f".{name}.upload"
    tmp.write_text(content)
    try:
        campaign = load_campaign(tmp)  # raises CampaignError if invalid
    except CampaignError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(directory / name)  # atomic move into place only after validation
    return campaign


def create_app(campaign: Campaign, model: str,
               agent_factory: Callable[..., RealtimeSalesAgent] = default_agent_factory,
               campaigns_dir: str | Path = "campaigns",
               default_campaign_file: str | None = None) -> FastAPI:
    app = FastAPI()
    campaigns_dir = Path(campaigns_dir)

    def _resolve_campaign(requested: str | None) -> Campaign:
        """Pick the campaign for a call: the requested file if valid, else the default."""
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

    @app.websocket("/session")
    async def session(ws: WebSocket):
        await ws.accept()
        lead_name = ws.query_params.get("lead_name") or "there"
        chosen = _resolve_campaign(ws.query_params.get("campaign"))
        transport = BrowserWebSocketTransport(ws)
        agent = agent_factory(chosen, model, lead_name)
        await agent.run(transport)

    return app
