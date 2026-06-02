import json
import textwrap
from fastapi.testclient import TestClient
from sales_agent.campaign import Campaign
from sales_agent.server import create_app, _build_twiml

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


# ---- Twilio outbound phone calls --------------------------------------------

class FakeCall:
    sid = "CA123"

class FakeCalls:
    def __init__(self):
        self.created = None
    def create(self, to, from_, twiml):
        self.created = {"to": to, "from_": from_, "twiml": twiml}
        return FakeCall()

class FakeTwilioClient:
    def __init__(self):
        self.calls = FakeCalls()

class StubTwilioAgent:
    def __init__(self, *a, **k):
        pass
    async def run(self, transport):
        await transport.send_event({"type": "transcript", "role": "assistant",
                                    "item_id": "a", "delta": "Hi", "final": False})

def test_build_twiml_has_stream_and_params():
    xml = _build_twiml("example.ngrok.io", "cid1", "checklinx.md", "Jo")
    assert "wss://example.ngrok.io/twilio-stream" in xml
    assert 'name="call_id" value="cid1"' in xml
    assert 'name="campaign" value="checklinx.md"' in xml
    assert 'name="lead_name" value="Jo"' in xml

def test_monitor_returns_call_id():
    client = TestClient(create_app(_campaign(), "gpt-realtime-mini"))
    with client.websocket_connect("/monitor") as ws:
        msg = json.loads(ws.receive_text())
    assert msg["type"] == "call_id" and msg["call_id"]

def test_call_missing_creds_returns_400(monkeypatch):
    for k in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "PUBLIC_HOST"]:
        monkeypatch.delenv(k, raising=False)
    client = TestClient(create_app(_campaign(), "gpt-realtime-mini"))
    r = client.post("/call", json={"phone": "+15551234567"})
    assert r.status_code == 400
    assert "Missing config" in r.json()["error"]

def test_call_initiates_with_mocked_twilio(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550000000")
    monkeypatch.setenv("PUBLIC_HOST", "example.ngrok.io")
    fake = FakeTwilioClient()
    app = create_app(_campaign(), "gpt-realtime-mini",
                     twilio_client_factory=lambda sid, tok: fake)
    client = TestClient(app)
    r = client.post("/call", json={"phone": "+15551234567", "campaign": "",
                                   "lead_name": "Jo", "call_id": "x"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["call_sid"] == "CA123"
    assert fake.calls.created["to"] == "+15551234567"
    assert fake.calls.created["from_"] == "+15550000000"
    assert "/twilio-stream" in fake.calls.created["twiml"]

def test_twilio_stream_bridges_and_forwards_to_monitor():
    app = create_app(_campaign(), "gpt-realtime-mini",
                     twilio_agent_factory=lambda *a, **k: StubTwilioAgent())
    client = TestClient(app)
    with client.websocket_connect("/monitor") as mon:
        cid = json.loads(mon.receive_text())["call_id"]
        with client.websocket_connect("/twilio-stream") as tw:
            tw.send_text(json.dumps({"event": "start", "start": {
                "streamSid": "MZ1",
                "customParameters": {"call_id": cid, "campaign": "", "lead_name": "Jo"},
            }}))
            seen = [json.loads(mon.receive_text()) for _ in range(3)]
    pairs = [(e.get("type"), e.get("status")) for e in seen]
    assert ("status", "connected") in pairs
    assert any(e.get("type") == "transcript" for e in seen)
    assert ("status", "ended") in pairs
