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
