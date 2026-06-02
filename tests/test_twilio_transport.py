import base64
import json
import pytest
from sales_agent.twilio_transport import TwilioMediaStreamTransport, read_stream_start


class FakeTwilioWS:
    def __init__(self, incoming_texts):
        self._incoming = list(incoming_texts)
        self.sent_text = []
        self.closed = False
    async def receive_text(self):
        if not self._incoming:
            from starlette.websockets import WebSocketDisconnect
            raise WebSocketDisconnect(code=1000)
        return self._incoming.pop(0)
    async def send_text(self, text):
        self.sent_text.append(text)
    async def close(self):
        self.closed = True


class FakeMonitor:
    def __init__(self):
        self.events = []
        self.interrupted = False
    async def send_event(self, event):
        self.events.append(event)
    async def notify_interrupted(self):
        self.interrupted = True


def _media(payload_bytes):
    return json.dumps({"event": "media",
                       "media": {"payload": base64.b64encode(payload_bytes).decode()}})


async def test_read_stream_start_returns_sid_and_params():
    ws = FakeTwilioWS([
        json.dumps({"event": "connected"}),
        json.dumps({"event": "start", "start": {
            "streamSid": "MZ123",
            "customParameters": {"call_id": "abc", "campaign": "checklinx.md", "lead_name": "Jo"},
        }}),
    ])
    sid, params = await read_stream_start(ws)
    assert sid == "MZ123"
    assert params == {"call_id": "abc", "campaign": "checklinx.md", "lead_name": "Jo"}


async def test_recv_audio_decodes_media_then_none_on_stop():
    ws = FakeTwilioWS([_media(b"\xff\xfe"), json.dumps({"event": "mark"}),
                       json.dumps({"event": "stop"})])
    t = TwilioMediaStreamTransport(ws, stream_sid="MZ1")
    assert await t.recv_audio() == b"\xff\xfe"   # mark is skipped after this returns next call
    assert await t.recv_audio() is None          # 'mark' skipped, then 'stop' -> None


async def test_recv_audio_none_on_disconnect():
    ws = FakeTwilioWS([])
    t = TwilioMediaStreamTransport(ws, stream_sid="MZ1")
    assert await t.recv_audio() is None


async def test_send_audio_emits_media_with_stream_sid():
    ws = FakeTwilioWS([])
    t = TwilioMediaStreamTransport(ws, stream_sid="MZ9")
    await t.send_audio(b"\x01\x02\x03")
    msg = json.loads(ws.sent_text[0])
    assert msg["event"] == "media"
    assert msg["streamSid"] == "MZ9"
    assert base64.b64decode(msg["media"]["payload"]) == b"\x01\x02\x03"


async def test_notify_interrupted_clears_twilio_and_monitor():
    ws = FakeTwilioWS([])
    mon = FakeMonitor()
    t = TwilioMediaStreamTransport(ws, stream_sid="MZ9", monitor=mon)
    await t.notify_interrupted()
    assert json.loads(ws.sent_text[0]) == {"event": "clear", "streamSid": "MZ9"}
    assert mon.interrupted is True


async def test_send_event_forwards_to_monitor_only():
    ws = FakeTwilioWS([])
    mon = FakeMonitor()
    t = TwilioMediaStreamTransport(ws, stream_sid="MZ9", monitor=mon)
    await t.send_event({"type": "transcript", "role": "user", "text": "hi"})
    assert mon.events == [{"type": "transcript", "role": "user", "text": "hi"}]
    assert ws.sent_text == []   # transcripts never go to the phone


async def test_send_event_noop_without_monitor():
    ws = FakeTwilioWS([])
    t = TwilioMediaStreamTransport(ws, stream_sid="MZ9")
    await t.send_event({"type": "transcript"})   # must not raise
    assert ws.sent_text == []


async def test_close_idempotent():
    ws = FakeTwilioWS([])
    t = TwilioMediaStreamTransport(ws, stream_sid="MZ9")
    await t.close()
    await t.close()
    assert ws.closed is True
