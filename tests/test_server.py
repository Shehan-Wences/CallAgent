import textwrap
from fastapi.testclient import TestClient
from sales_agent.campaign import Campaign
from sales_agent.server import create_app

def _campaign():
    return Campaign(
        product={"name": "AcmeCRM"},
        persona={"name": "Alex", "voice": "marin"},
        goal={"type": "book_follow_up"},
        opening_line="Hi {name}",
    )

VALID_MD = textwrap.dedent("""\
    ---
    product:
      name: "Widget"
    persona:
      name: "Sam"
      voice: "cedar"
    goal:
      type: book_follow_up
    opening_line: "Hi {name}, it's Sam."
    ---
    ## Pitch
    Widgets are great.
    """)

class StubAgent:
    """Stands in for RealtimeSalesAgent: echoes a frame then closes."""
    def __init__(self, *a, **k): pass
    async def run(self, transport):
        await transport.send_audio(b"HELLO_AUDIO")
        await transport.close()

def test_index_served():
    app = create_app(_campaign(), "gpt-realtime-mini", agent_factory=lambda *a, **k: StubAgent())
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Start call" in r.text

def test_session_ws_runs_agent_and_streams_audio():
    captured = {}
    def factory(campaign, model, lead_name):
        captured["lead_name"] = lead_name
        return StubAgent()
    app = create_app(_campaign(), "gpt-realtime-mini", agent_factory=factory)
    client = TestClient(app)
    with client.websocket_connect("/session?lead_name=Dana") as ws:
        data = ws.receive_bytes()
        assert data == b"HELLO_AUDIO"
    assert captured["lead_name"] == "Dana"

def _app_with_dir(tmp_path, **kw):
    return create_app(_campaign(), "gpt-realtime-mini",
                      agent_factory=lambda *a, **k: StubAgent(),
                      campaigns_dir=tmp_path, **kw)

def test_list_campaigns_reports_product_and_validity(tmp_path):
    (tmp_path / "widget.md").write_text(VALID_MD)
    (tmp_path / "broken.md").write_text("no front matter")
    app = _app_with_dir(tmp_path, default_campaign_file="widget.md")
    client = TestClient(app)
    body = client.get("/campaigns").json()
    assert body["default"] == "widget.md"
    by_file = {c["file"]: c for c in body["campaigns"]}
    assert by_file["widget.md"] == {"file": "widget.md", "product": "Widget", "valid": True}
    assert by_file["broken.md"]["valid"] is False
    assert "error" in by_file["broken.md"]

def test_upload_valid_campaign_saves_and_lists(tmp_path):
    app = _app_with_dir(tmp_path)
    client = TestClient(app)
    r = client.post("/campaigns?file=new.md", content=VALID_MD)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "file": "new.md", "product": "Widget"}
    assert (tmp_path / "new.md").exists()
    files = [c["file"] for c in client.get("/campaigns").json()["campaigns"]]
    assert "new.md" in files

def test_upload_invalid_campaign_rejected_and_not_saved(tmp_path):
    app = _app_with_dir(tmp_path)
    client = TestClient(app)
    r = client.post("/campaigns?file=bad.md", content="not a campaign")
    assert r.status_code == 400
    assert r.json()["ok"] is False
    assert not (tmp_path / "bad.md").exists()

def test_upload_rejects_unsafe_filename(tmp_path):
    app = _app_with_dir(tmp_path)
    client = TestClient(app)
    r = client.post("/campaigns?file=../escape.md", content=VALID_MD)
    # path components are stripped to a safe basename; the escape path must not be written
    assert not (tmp_path.parent / "escape.md").exists()
    assert r.status_code in (200, 400)

def test_session_uses_selected_campaign(tmp_path):
    (tmp_path / "widget.md").write_text(VALID_MD)
    captured = {}
    def factory(campaign, model, lead_name):
        captured["product"] = campaign.product.get("name")
        return StubAgent()
    app = create_app(_campaign(), "gpt-realtime-mini", agent_factory=factory,
                     campaigns_dir=tmp_path)
    client = TestClient(app)
    with client.websocket_connect("/session?campaign=widget.md") as ws:
        ws.receive_bytes()
    assert captured["product"] == "Widget"   # used the selected campaign, not the default AcmeCRM

def test_session_falls_back_to_default_for_unknown_campaign(tmp_path):
    captured = {}
    def factory(campaign, model, lead_name):
        captured["product"] = campaign.product.get("name")
        return StubAgent()
    app = create_app(_campaign(), "gpt-realtime-mini", agent_factory=factory,
                     campaigns_dir=tmp_path)
    client = TestClient(app)
    with client.websocket_connect("/session?campaign=missing.md") as ws:
        ws.receive_bytes()
    assert captured["product"] == "AcmeCRM"   # fell back to the default campaign
