import asyncio
from types import SimpleNamespace
from sales_agent.agent import RealtimeSalesAgent

class FakeSession:
    def __init__(self, events):
        self._events = list(events)
        self.sent_audio = []
        self.messages = []
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    def __aiter__(self):
        async def gen():
            for e in self._events:
                yield e
        return gen()
    async def send_audio(self, audio): self.sent_audio.append(audio)
    async def send_message(self, msg): self.messages.append(msg)

class FakeTransport:
    def __init__(self, incoming):
        self._incoming = list(incoming)
        self.sent = []
        self.events = []
        self.interrupted = False
        self.closed = False
    async def recv_audio(self):
        return self._incoming.pop(0) if self._incoming else None
    async def send_audio(self, audio): self.sent.append(audio)
    async def send_event(self, event): self.events.append(event)
    async def notify_interrupted(self): self.interrupted = True
    async def close(self): self.closed = True

def _raw_event(model_data):
    return SimpleNamespace(type="raw_model_event", data=model_data)

def _audio_event(data):
    return SimpleNamespace(type="audio", audio=SimpleNamespace(data=data))

def _agent(session):
    async def factory(instructions, voice, model, tools, audio_format="pcm16"):
        return session
    return RealtimeSalesAgent("instr", "marin", "gpt-realtime-mini", [],
                             session_factory=factory)

async def test_downlink_forwards_audio_and_interrupt():
    session = FakeSession([_audio_event(b"OUT"),
                          SimpleNamespace(type="audio_interrupted")])
    transport = FakeTransport([])
    await _agent(session)._pump_downlink(session, transport)
    assert transport.sent == [b"OUT"]
    assert transport.interrupted is True

async def test_downlink_forwards_assistant_and_user_transcripts():
    assistant = SimpleNamespace(type="transcript_delta", item_id="a1", delta="Hello", response_id="r1")
    user = SimpleNamespace(type="input_audio_transcription_completed", item_id="u1", transcript="Hi there")
    session = FakeSession([_raw_event(assistant), _raw_event(user)])
    transport = FakeTransport([])
    await _agent(session)._pump_downlink(session, transport)
    assert transport.events == [
        {"type": "transcript", "role": "assistant", "item_id": "a1", "delta": "Hello", "final": False},
        {"type": "transcript", "role": "user", "item_id": "u1", "text": "Hi there", "final": True},
    ]

async def test_downlink_ignores_other_raw_model_events():
    other = SimpleNamespace(type="some_other_event")
    session = FakeSession([_raw_event(other)])
    transport = FakeTransport([])
    await _agent(session)._pump_downlink(session, transport)
    assert transport.events == []

async def test_uplink_forwards_frames_until_none():
    session = FakeSession([])
    transport = FakeTransport([b"IN1", b"IN2", None])
    await _agent(session)._pump_uplink(transport, session)
    assert session.sent_audio == [b"IN1", b"IN2"]

async def test_run_sends_greeting_and_closes_transport():
    session = FakeSession([_audio_event(b"OUT")])
    transport = FakeTransport([None])
    await _agent(session).run(transport)
    assert len(session.messages) == 1
    assert transport.closed is True

class ExplodingSession(FakeSession):
    def __aiter__(self):
        async def gen():
            raise RuntimeError("session blew up")
            yield  # pragma: no cover  (makes this an async generator)
        return gen()

async def test_run_reraises_downlink_error():
    import pytest
    session = ExplodingSession([])
    transport = FakeTransport([None])
    with pytest.raises(RuntimeError, match="session blew up"):
        await _agent(session).run(transport)
    assert transport.closed is True
