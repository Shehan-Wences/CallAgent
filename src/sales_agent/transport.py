from __future__ import annotations
import json
from typing import Protocol, runtime_checkable
from starlette.websockets import WebSocketDisconnect

@runtime_checkable
class AudioTransport(Protocol):
    async def recv_audio(self) -> bytes | None: ...
    async def send_audio(self, audio: bytes) -> None: ...
    async def send_event(self, event: dict) -> None: ...
    async def notify_interrupted(self) -> None: ...
    async def close(self) -> None: ...

class BrowserWebSocketTransport:
    """Carries PCM16 audio frames over a browser WebSocket.

    Browser -> server: binary frames are mic audio.
    Server -> browser: binary frames are agent audio; JSON text frames are control.
    """

    def __init__(self, ws):
        self._ws = ws
        self._closed = False

    async def recv_audio(self) -> bytes | None:
        try:
            return await self._ws.receive_bytes()
        except WebSocketDisconnect:
            return None

    async def send_audio(self, audio: bytes) -> None:
        await self._ws.send_bytes(audio)

    async def send_event(self, event: dict) -> None:
        """Send a JSON control/data message (e.g. transcript) to the browser."""
        await self._ws.send_text(json.dumps(event))

    async def notify_interrupted(self) -> None:
        await self.send_event({"type": "interrupted"})

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._ws.close()
        except RuntimeError:
            pass
