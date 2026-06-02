import pytest
from sales_agent.transport import BrowserWebSocketTransport

class FakeWS:
    """Minimal stand-in for a Starlette WebSocket."""
    def __init__(self, incoming):
        self._incoming = list(incoming)
        self.sent_bytes = []
        self.sent_text = []
        self.closed = False
    async def receive_bytes(self):
        if not self._incoming:
            from starlette.websockets import WebSocketDisconnect
            raise WebSocketDisconnect(code=1000)
        return self._incoming.pop(0)
    async def send_bytes(self, data):
        self.sent_bytes.append(data)
    async def send_text(self, text):
        self.sent_text.append(text)
    async def close(self):
        self.closed = True

async def test_recv_audio_returns_frames_then_none_on_disconnect():
    ws = FakeWS([b"A", b"B"])
    t = BrowserWebSocketTransport(ws)
    assert await t.recv_audio() == b"A"
    assert await t.recv_audio() == b"B"
    assert await t.recv_audio() is None

async def test_send_audio_forwards_bytes():
    ws = FakeWS([])
    t = BrowserWebSocketTransport(ws)
    await t.send_audio(b"OUT")
    assert ws.sent_bytes == [b"OUT"]

async def test_notify_interrupted_sends_control_text():
    ws = FakeWS([])
    t = BrowserWebSocketTransport(ws)
    await t.notify_interrupted()
    assert any("interrupted" in m for m in ws.sent_text)

async def test_close_closes_ws_once():
    ws = FakeWS([])
    t = BrowserWebSocketTransport(ws)
    await t.close()
    await t.close()
    assert ws.closed is True
