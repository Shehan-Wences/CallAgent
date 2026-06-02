from __future__ import annotations
import base64
import json
from starlette.websockets import WebSocketDisconnect


async def read_stream_start(ws) -> tuple[str, dict]:
    """Consume Twilio Media Stream frames until the 'start' event.

    Returns (stream_sid, custom_parameters). Twilio sends 'connected' then
    'start' (which carries the streamSid and any <Parameter> values) before any
    audio, so reading up front means the streamSid is known before the agent
    produces its first (greeting) audio.
    """
    while True:
        msg = json.loads(await ws.receive_text())
        if msg.get("event") == "start":
            start = msg["start"]
            return start["streamSid"], (start.get("customParameters") or {})


class TwilioMediaStreamTransport:
    """AudioTransport over a Twilio Media Streams WebSocket (g711 μ-law, 8 kHz).

    Twilio frames are JSON; audio is base64 μ-law in 'media' events. OpenAI
    Realtime speaks g711_ulaw natively, so audio passes through with only
    base64 decode/encode — no resampling.

    Transcript/status events have no place on a phone call, so they are
    forwarded to an optional browser ``monitor`` (anything with async
    ``send_event`` / ``notify_interrupted``) for on-screen display.
    """

    def __init__(self, ws, stream_sid: str, monitor=None):
        self._ws = ws
        self._stream_sid = stream_sid
        self._monitor = monitor
        self._closed = False

    async def recv_audio(self) -> bytes | None:
        while True:
            try:
                raw = await self._ws.receive_text()
            except WebSocketDisconnect:
                return None
            msg = json.loads(raw)
            event = msg.get("event")
            if event == "media":
                return base64.b64decode(msg["media"]["payload"])
            if event == "stop":
                return None
            # connected / mark / dtmf / etc. — ignore and keep reading.

    async def send_audio(self, audio: bytes) -> None:
        await self._ws.send_text(json.dumps({
            "event": "media",
            "streamSid": self._stream_sid,
            "media": {"payload": base64.b64encode(audio).decode("ascii")},
        }))

    async def send_event(self, event: dict) -> None:
        if self._monitor is not None:
            await self._monitor.send_event(event)

    async def notify_interrupted(self) -> None:
        # Flush Twilio's queued audio so barge-in actually cuts the agent off.
        await self._ws.send_text(json.dumps({"event": "clear", "streamSid": self._stream_sid}))
        if self._monitor is not None:
            await self._monitor.notify_interrupted()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._ws.close()
        except RuntimeError:
            pass
