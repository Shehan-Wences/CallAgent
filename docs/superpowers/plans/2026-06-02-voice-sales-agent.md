# Voice Sales Agent (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Docker-runnable realtime voice sales agent you talk to in your browser — it pitches a configurable product (from a hybrid Markdown campaign file) and books a follow-up via tool calls.

**Architecture:** A FastAPI server in a container runs the "brain" (campaign → instructions → OpenAI Realtime session + tools) and bridges audio to the browser over a WebSocket. The browser captures the mic and plays the agent's voice. The OpenAI integration sits behind injectable factories so every component around the live audio is unit-testable. Audio transport is isolated behind an `AudioTransport` interface so Phase 2 (Twilio) plugs in without touching the brain.

**Tech Stack:** Python 3.12, `openai-agents` (Realtime), FastAPI + uvicorn, PyYAML, pytest + pytest-asyncio. Vanilla JS browser client. Docker + docker-compose.

**Spec:** `docs/superpowers/specs/2026-06-02-voice-sales-agent-design.md`

---

## File Structure

```
CallAgent/
├── pyproject.toml                 # deps, package discovery (src layout), pytest config
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── README.md
├── campaigns/
│   └── acmecrm.md                 # sample campaign (hybrid YAML + Markdown)
├── src/sales_agent/
│   ├── __init__.py
│   ├── campaign.py                # Campaign dataclass + load_campaign()
│   ├── instructions.py            # build_instructions() — pure function
│   ├── booking.py                 # BookingStore (append-only JSON)
│   ├── tools.py                   # record_booking/record_outcome + build_tools()
│   ├── transport.py               # AudioTransport protocol + BrowserWebSocketTransport
│   ├── agent.py                   # RealtimeSalesAgent + default_session_factory
│   ├── server.py                  # create_app() + default_agent_factory()
│   ├── __main__.py                # `python -m sales_agent serve`
│   └── static/
│       └── index.html             # browser "call console" (HTML + JS)
└── tests/
    ├── test_campaign.py
    ├── test_instructions.py
    ├── test_booking.py
    ├── test_tools.py
    ├── test_transport.py
    ├── test_agent.py
    └── test_server.py
```

**Responsibility boundaries:** `campaign`/`instructions`/`booking`/`tools` are pure brain (no I/O beyond the booking file, no network) and fully unit-tested. `transport`/`agent`/`server` are plumbing tested with fakes/mocks. `static/index.html` and the live OpenAI round-trip are manually tested.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/sales_agent/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
def test_package_imports():
    import sales_agent
    assert sales_agent.__name__ == "sales_agent"
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "sales_agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "openai-agents>=0.7",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 3: Create empty package files**

```bash
mkdir -p src/sales_agent/static tests campaigns
printf '"""Voice sales agent (Phase 1)."""\n' > src/sales_agent/__init__.py
: > tests/__init__.py
```

- [ ] **Step 4: Install dev deps and run the test**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
Then: `pytest tests/test_smoke.py -v`
Expected: PASS (`test_package_imports`)

- [ ] **Step 5: Create `.gitignore` additions and commit**

Append to `.gitignore` (file already exists): ensure it contains `.venv/`, `__pycache__/`, `*.pyc`, `bookings.json`, `.env`, `*.egg-info/`.

```bash
git add pyproject.toml src/sales_agent/__init__.py tests/__init__.py tests/test_smoke.py .gitignore
git commit -m "Scaffold sales_agent package and pytest setup"
```

---

## Task 2: Campaign model + loader

**Files:**
- Create: `src/sales_agent/campaign.py`
- Test: `tests/test_campaign.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_campaign.py
import textwrap
import pytest
from sales_agent.campaign import load_campaign, Campaign, CampaignError

def _write(tmp_path, text):
    p = tmp_path / "c.md"
    p.write_text(textwrap.dedent(text))
    return p

VALID = """\
    ---
    product:
      name: "AcmeCRM"
      one_liner: "A CRM that sets itself up in 10 minutes."
      price: "$29/user/month"
    persona:
      name: "Alex"
      role: "sales rep at Acme"
      tone: "warm, concise"
      voice: "cedar"
    goal:
      type: book_follow_up
      success: "a callback is booked"
    disclosure: if_asked
    guardrails:
      - "Never invent features."
    opening_line: "Hi, am I speaking with {name}?"
    ---
    ## Pitch
    AcmeCRM replaces spreadsheets.
    """

def test_loads_all_fields(tmp_path):
    c = load_campaign(_write(tmp_path, VALID))
    assert c.product["name"] == "AcmeCRM"
    assert c.persona["name"] == "Alex"
    assert c.persona["voice"] == "cedar"
    assert c.goal["type"] == "book_follow_up"
    assert c.disclosure == "if_asked"
    assert c.guardrails == ["Never invent features."]
    assert c.opening_line == "Hi, am I speaking with {name}?"
    assert "AcmeCRM replaces spreadsheets." in c.body

def test_defaults_applied(tmp_path):
    minimal = """\
        ---
        product:
          name: "Widget"
        persona:
          name: "Sam"
        goal:
          type: book_follow_up
        opening_line: "Hello {name}"
        ---
        """
    c = load_campaign(_write(tmp_path, minimal))
    assert c.persona["voice"] == "marin"      # default voice
    assert c.disclosure == "if_asked"          # default disclosure
    assert c.guardrails == []                    # default empty
    assert c.body == ""                          # no body is fine

@pytest.mark.parametrize("missing_key,doc", [
    ("product.name", '---\npersona:\n  name: "S"\ngoal:\n  type: book_follow_up\nopening_line: "hi"\n---\n'),
    ("persona.name", '---\nproduct:\n  name: "W"\ngoal:\n  type: book_follow_up\nopening_line: "hi"\n---\n'),
    ("goal.type", '---\nproduct:\n  name: "W"\npersona:\n  name: "S"\nopening_line: "hi"\n---\n'),
    ("opening_line", '---\nproduct:\n  name: "W"\npersona:\n  name: "S"\ngoal:\n  type: book_follow_up\n---\n'),
])
def test_missing_required_field_raises_named_error(tmp_path, missing_key, doc):
    p = tmp_path / "c.md"
    p.write_text(doc)
    with pytest.raises(CampaignError) as exc:
        load_campaign(p)
    assert missing_key in str(exc.value)

def test_missing_front_matter_raises(tmp_path):
    p = tmp_path / "c.md"
    p.write_text("no front matter here")
    with pytest.raises(CampaignError):
        load_campaign(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_campaign.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sales_agent.campaign'`

- [ ] **Step 3: Implement `campaign.py`**

```python
# src/sales_agent/campaign.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml

class CampaignError(ValueError):
    """Raised when a campaign file is missing or malformed."""

DEFAULT_VOICE = "marin"
DEFAULT_DISCLOSURE = "if_asked"

@dataclass
class Campaign:
    product: dict
    persona: dict
    goal: dict
    opening_line: str
    disclosure: str = DEFAULT_DISCLOSURE
    guardrails: list[str] = field(default_factory=list)
    body: str = ""

def _split_front_matter(text: str) -> tuple[str, str]:
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        raise CampaignError("Campaign file must start with a YAML front-matter block (---).")
    # Drop the leading '---' line, then split on the next '---' line.
    after = stripped.split("---", 2)
    # after == ["", "<yaml>", "<body>"]
    if len(after) < 3:
        raise CampaignError("Front-matter block is not closed with a second '---'.")
    return after[1], after[2]

def _require(data: dict, dotted: str):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node or node[part] in (None, ""):
            raise CampaignError(f"Campaign is missing required field: {dotted}")
        node = node[part]
    return node

def load_campaign(path: str | Path) -> Campaign:
    path = Path(path)
    if not path.exists():
        raise CampaignError(f"Campaign file not found: {path}")
    raw_yaml, body = _split_front_matter(path.read_text())
    data = yaml.safe_load(raw_yaml) or {}
    if not isinstance(data, dict):
        raise CampaignError("Front-matter did not parse to a mapping.")

    # Validate required fields (raises CampaignError naming the field).
    _require(data, "product.name")
    _require(data, "persona.name")
    _require(data, "goal.type")
    _require(data, "opening_line")

    persona = dict(data["persona"])
    persona.setdefault("voice", DEFAULT_VOICE)

    return Campaign(
        product=dict(data["product"]),
        persona=persona,
        goal=dict(data["goal"]),
        opening_line=str(data["opening_line"]),
        disclosure=str(data.get("disclosure", DEFAULT_DISCLOSURE)),
        guardrails=list(data.get("guardrails") or []),
        body=body.strip(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_campaign.py -v`
Expected: PASS (all cases)

- [ ] **Step 5: Commit**

```bash
git add src/sales_agent/campaign.py tests/test_campaign.py
git commit -m "Add Campaign model and loader with validation"
```

---

## Task 3: Instruction builder (pure function)

**Files:**
- Create: `src/sales_agent/instructions.py`
- Test: `tests/test_instructions.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_instructions.py
from sales_agent.campaign import Campaign
from sales_agent.instructions import build_instructions

def _campaign(**over):
    base = dict(
        product={"name": "AcmeCRM", "one_liner": "Sets itself up fast.", "price": "$29"},
        persona={"name": "Alex", "role": "rep at Acme", "tone": "warm", "voice": "marin"},
        goal={"type": "book_follow_up", "success": "callback booked"},
        opening_line="Hi {name}, it's Alex.",
        disclosure="if_asked",
        guardrails=["Never invent features."],
        body="## Pitch\nReplaces spreadsheets.",
    )
    base.update(over)
    return Campaign(**base)

def test_includes_persona_goal_guardrails_and_product():
    out = build_instructions(_campaign(), lead_name="Dana")
    assert "Alex" in out
    assert "book" in out.lower()
    assert "Never invent features." in out
    assert "AcmeCRM" in out
    assert "Replaces spreadsheets." in out      # markdown body injected
    assert "Dana" in out                          # lead name interpolated

def test_disclosure_if_asked_vs_upfront_differ():
    asked = build_instructions(_campaign(disclosure="if_asked"), lead_name="Dana")
    upfront = build_instructions(_campaign(disclosure="upfront"), lead_name="Dana")
    assert asked != upfront
    assert "if asked" in asked.lower()
    assert "state" in upfront.lower() and "ai" in upfront.lower()

def test_mentions_both_tools():
    out = build_instructions(_campaign(), lead_name="Dana")
    assert "book_slot" in out
    assert "log_outcome" in out

def test_opening_line_placeholder_filled():
    out = build_instructions(_campaign(opening_line="Hello {name}!"), lead_name="Dana")
    assert "Hello Dana!" in out
    assert "{name}" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_instructions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sales_agent.instructions'`

- [ ] **Step 3: Implement `instructions.py`**

```python
# src/sales_agent/instructions.py
from __future__ import annotations
from .campaign import Campaign

_DISCLOSURE_RULES = {
    "if_asked": (
        "You are an AI voice assistant. Do not volunteer that you are an AI, "
        "but if asked directly whether you are a bot/AI/recording, answer honestly "
        "and briefly, then continue."
    ),
    "upfront": (
        "At the very start of the call, clearly state that you are an AI assistant "
        "calling on behalf of the company before continuing."
    ),
}

def build_instructions(campaign: Campaign, lead_name: str) -> str:
    p = campaign.persona
    prod = campaign.product
    disclosure = _DISCLOSURE_RULES.get(campaign.disclosure, _DISCLOSURE_RULES["if_asked"])
    opening = campaign.opening_line.replace("{name}", lead_name)
    guardrails = "\n".join(f"- {g}" for g in campaign.guardrails) or "- (none specified)"

    return f"""\
You are {p.get('name')}, {p.get('role', 'a sales representative')}.
Tone: {p.get('tone', 'warm, concise, professional')}.

# Your goal
Drive the conversation toward this outcome: {campaign.goal.get('type')}.
Success means: {campaign.goal.get('success', 'a follow-up is booked')}.
You are speaking with a person named {lead_name}.

# Honesty & disclosure
{disclosure}
Never invent facts, features, pricing, or claims that are not supported by the
product knowledge below. If you don't know, say you'll follow up.

# Hard guardrails (never violate)
{guardrails}

# Product you are selling
Name: {prod.get('name')}
One-liner: {prod.get('one_liner', '')}
Price: {prod.get('price', 'not specified')}

# Product knowledge, pitch, and objection handling
{campaign.body or '(no additional notes provided)'}

# How to run the call
1. Open the call by saying, naturally: "{opening}"
2. Have a real, responsive conversation. Listen, handle objections using the
   guidance above, and steer toward the goal. Keep turns short and human.
3. When the person agrees to a follow-up, call the `book_slot` tool with their
   name, a contact (phone/email), the preferred time they gave, and any notes.
   Read the confirmation back to them.
4. Before the call ends — for ANY outcome — call the `log_outcome` tool with the
   final status (booked / interested / not_interested / callback_requested /
   no_answer) and a one-line note.
5. If the person asks to stop or says they're not interested twice, thank them
   warmly and end. Do not be pushy.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_instructions.py -v`
Expected: PASS (all cases)

- [ ] **Step 5: Commit**

```bash
git add src/sales_agent/instructions.py tests/test_instructions.py
git commit -m "Add pure instruction builder from campaign"
```

---

## Task 4: Booking store

**Files:**
- Create: `src/sales_agent/booking.py`
- Test: `tests/test_booking.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_booking.py
import json
from sales_agent.booking import BookingStore

def test_append_creates_file_with_list(tmp_path):
    store = BookingStore(tmp_path / "bookings.json")
    store.append({"record_type": "booking", "lead_name": "Dana"})
    data = json.loads((tmp_path / "bookings.json").read_text())
    assert data == [{"record_type": "booking", "lead_name": "Dana"}]

def test_append_is_additive(tmp_path):
    store = BookingStore(tmp_path / "bookings.json")
    store.append({"record_type": "booking", "lead_name": "Dana"})
    store.append({"record_type": "outcome", "status": "booked"})
    data = json.loads((tmp_path / "bookings.json").read_text())
    assert len(data) == 2
    assert data[1]["status"] == "booked"

def test_creates_parent_dirs(tmp_path):
    store = BookingStore(tmp_path / "nested" / "dir" / "bookings.json")
    store.append({"record_type": "outcome", "status": "no_answer"})
    assert (tmp_path / "nested" / "dir" / "bookings.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_booking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sales_agent.booking'`

- [ ] **Step 3: Implement `booking.py`**

```python
# src/sales_agent/booking.py
from __future__ import annotations
import json
from pathlib import Path

class BookingStore:
    """Append-only JSON list of booking/outcome records."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                records = json.loads(self.path.read_text())
                if not isinstance(records, list):
                    records = []
            except json.JSONDecodeError:
                records = []
        else:
            records = []
        records.append(record)
        self.path.write_text(json.dumps(records, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_booking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sales_agent/booking.py tests/test_booking.py
git commit -m "Add append-only BookingStore"
```

---

## Task 5: Tools (book_slot, log_outcome)

**Files:**
- Create: `src/sales_agent/tools.py`
- Test: `tests/test_tools.py`

Note: tool *logic* is in pure functions (`record_booking`, `record_outcome`) that are unit-tested. `build_tools()` wraps them with `@function_tool` for the agent; the wrapper itself is thin and exercised via manual/agent testing.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tools.py
import json
from sales_agent.booking import BookingStore
from sales_agent.tools import record_booking, record_outcome, build_tools

def _store(tmp_path):
    return BookingStore(tmp_path / "bookings.json")

def test_record_booking_writes_record_and_confirms(tmp_path):
    store = _store(tmp_path)
    msg = record_booking(store, lambda: "2026-06-02T10:00:00Z",
                         lead_name="Dana", contact="dana@x.com",
                         preferred_time="Tue 3pm", notes="keen")
    data = json.loads((tmp_path / "bookings.json").read_text())
    assert data[0]["record_type"] == "booking"
    assert data[0]["lead_name"] == "Dana"
    assert data[0]["preferred_time"] == "Tue 3pm"
    assert data[0]["timestamp"] == "2026-06-02T10:00:00Z"
    assert "Tue 3pm" in msg          # confirmation reads back the time

def test_record_outcome_writes_status(tmp_path):
    store = _store(tmp_path)
    record_outcome(store, lambda: "2026-06-02T10:05:00Z",
                  status="booked", notes="done")
    data = json.loads((tmp_path / "bookings.json").read_text())
    assert data[0]["record_type"] == "outcome"
    assert data[0]["status"] == "booked"
    assert data[0]["timestamp"] == "2026-06-02T10:05:00Z"

def test_build_tools_returns_two_named_tools(tmp_path):
    tools = build_tools(_store(tmp_path), lambda: "t")
    names = {t.name for t in tools}
    assert names == {"book_slot", "log_outcome"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sales_agent.tools'`

- [ ] **Step 3: Implement `tools.py`**

```python
# src/sales_agent/tools.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Callable
from agents import function_tool
from .booking import BookingStore

Clock = Callable[[], str]

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def record_booking(store: BookingStore, now: Clock, *, lead_name: str,
                  contact: str, preferred_time: str, notes: str = "") -> str:
    store.append({
        "record_type": "booking",
        "timestamp": now(),
        "lead_name": lead_name,
        "contact": contact,
        "preferred_time": preferred_time,
        "notes": notes,
    })
    return f"Booked a follow-up for {lead_name or 'the lead'} at {preferred_time}."

def record_outcome(store: BookingStore, now: Clock, *, status: str, notes: str = "") -> str:
    store.append({
        "record_type": "outcome",
        "timestamp": now(),
        "status": status,
        "notes": notes,
    })
    return "Outcome recorded."

def build_tools(store: BookingStore, now: Clock = _utc_now) -> list:
    @function_tool
    def book_slot(lead_name: str, contact: str, preferred_time: str, notes: str = "") -> str:
        """Book a follow-up call/demo. Use when the person agrees to a follow-up.

        Args:
            lead_name: The person's name.
            contact: Their phone number or email for the follow-up.
            preferred_time: The date/time they asked for, in their own words.
            notes: Any short note about what they want.
        """
        return record_booking(store, now, lead_name=lead_name, contact=contact,
                             preferred_time=preferred_time, notes=notes)

    @function_tool
    def log_outcome(status: str, notes: str = "") -> str:
        """Record how the call ended. Call this before the call ends, every time.

        Args:
            status: One of booked, interested, not_interested, callback_requested, no_answer.
            notes: One-line summary of the call outcome.
        """
        return record_outcome(store, now, status=status, notes=notes)

    return [book_slot, log_outcome]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tools.py -v`
Expected: PASS

If `t.name` fails (SDK attribute differs), inspect with `python -c "from agents import function_tool; f=function_tool(lambda x: x); print(dir(f))"` and adjust the test's name access to the actual attribute (e.g. `t.name`). Keep the assertion on the two tool names.

- [ ] **Step 5: Commit**

```bash
git add src/sales_agent/tools.py tests/test_tools.py
git commit -m "Add book_slot and log_outcome tools"
```

---

## Task 6: Audio transport (interface + browser WebSocket)

**Files:**
- Create: `src/sales_agent/transport.py`
- Test: `tests/test_transport.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transport.py
import pytest
from sales_agent.transport import BrowserWebSocketTransport

class FakeWS:
    """Minimal stand-in for a Starlette WebSocket."""
    def __init__(self, incoming):
        self._incoming = list(incoming)   # list of bytes; empty list -> disconnect
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
    assert await t.recv_audio() is None      # disconnect -> None

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
    await t.close()                          # idempotent
    assert ws.closed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_transport.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sales_agent.transport'`

- [ ] **Step 3: Implement `transport.py`**

```python
# src/sales_agent/transport.py
from __future__ import annotations
import json
from typing import Protocol, runtime_checkable
from starlette.websockets import WebSocketDisconnect

@runtime_checkable
class AudioTransport(Protocol):
    async def recv_audio(self) -> bytes | None: ...
    async def send_audio(self, audio: bytes) -> None: ...
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

    async def notify_interrupted(self) -> None:
        await self._ws.send_text(json.dumps({"type": "interrupted"}))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._ws.close()
        except RuntimeError:
            pass   # already closed by the framework
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_transport.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sales_agent/transport.py tests/test_transport.py
git commit -m "Add AudioTransport interface and browser WebSocket transport"
```

---

## Task 7: RealtimeSalesAgent (bridge brain ↔ transport ↔ OpenAI)

**Files:**
- Create: `src/sales_agent/agent.py`
- Test: `tests/test_agent.py`

The OpenAI session is created by an injectable `session_factory`, so the pump logic is tested with a fake session and fake transport. The two pump directions are separate methods for deterministic testing.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_agent.py
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
        self.interrupted = False
        self.closed = False
    async def recv_audio(self):
        return self._incoming.pop(0) if self._incoming else None
    async def send_audio(self, audio): self.sent.append(audio)
    async def notify_interrupted(self): self.interrupted = True
    async def close(self): self.closed = True

def _audio_event(data):
    return SimpleNamespace(type="audio", audio=SimpleNamespace(data=data))

def _agent(session):
    async def factory(instructions, voice, model, tools):
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

async def test_uplink_forwards_frames_until_none():
    session = FakeSession([])
    transport = FakeTransport([b"IN1", b"IN2", None])
    await _agent(session)._pump_uplink(transport, session)
    assert session.sent_audio == [b"IN1", b"IN2"]

async def test_run_sends_greeting_and_closes_transport():
    session = FakeSession([_audio_event(b"OUT")])
    transport = FakeTransport([None])
    await _agent(session).run(transport)
    assert len(session.messages) == 1            # greeting trigger sent
    assert transport.closed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sales_agent.agent'`

- [ ] **Step 3: Implement `agent.py`**

```python
# src/sales_agent/agent.py
from __future__ import annotations
import asyncio
from typing import Awaitable, Callable
from agents.realtime import RealtimeAgent, RealtimeRunner

GREETING_TRIGGER = (
    "The call has just connected. Greet the person now by delivering your "
    "opening line, then continue the conversation naturally."
)

SessionFactory = Callable[[str, str, str, list], Awaitable[object]]

async def default_session_factory(instructions: str, voice: str, model: str, tools: list):
    agent = RealtimeAgent(name="sales_agent", instructions=instructions, tools=tools)
    runner = RealtimeRunner(
        starting_agent=agent,
        config={
            "model_settings": {
                "model_name": model,
                "instructions": instructions,
                "audio": {
                    "input": {
                        "format": "pcm16",
                        "turn_detection": {"type": "semantic_vad", "interrupt_response": True},
                    },
                    "output": {"format": "pcm16", "voice": voice},
                },
            }
        },
    )
    return await runner.run()

class RealtimeSalesAgent:
    def __init__(self, instructions: str, voice: str, model: str, tools: list,
                 session_factory: SessionFactory = default_session_factory):
        self._instructions = instructions
        self._voice = voice
        self._model = model
        self._tools = tools
        self._session_factory = session_factory

    async def run(self, transport) -> None:
        session = await self._session_factory(
            self._instructions, self._voice, self._model, self._tools)
        async with session:
            await session.send_message(GREETING_TRIGGER)
            up = asyncio.create_task(self._pump_uplink(transport, session))
            down = asyncio.create_task(self._pump_downlink(session, transport))
            try:
                await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in (up, down):
                    task.cancel()
                await transport.close()

    async def _pump_uplink(self, transport, session) -> None:
        while True:
            chunk = await transport.recv_audio()
            if chunk is None:
                break
            if chunk:
                await session.send_audio(chunk)

    async def _pump_downlink(self, session, transport) -> None:
        async for event in session:
            if event.type == "audio":
                await transport.send_audio(event.audio.data)
            elif event.type == "audio_interrupted":
                await transport.notify_interrupted()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_agent.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sales_agent/agent.py tests/test_agent.py
git commit -m "Add RealtimeSalesAgent bridging transport and OpenAI session"
```

---

## Task 8: AppServer (FastAPI + WebSocket + static)

**Files:**
- Create: `src/sales_agent/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sales_agent.server'`

- [ ] **Step 3: Implement `server.py`**

```python
# src/sales_agent/server.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Callable
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from .campaign import Campaign
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

def create_app(campaign: Campaign, model: str,
               agent_factory: Callable[..., RealtimeSalesAgent] = default_agent_factory) -> FastAPI:
    app = FastAPI()

    @app.get("/")
    async def index():
        return FileResponse(_STATIC / "index.html")

    @app.websocket("/session")
    async def session(ws: WebSocket):
        await ws.accept()
        lead_name = ws.query_params.get("lead_name") or "there"
        transport = BrowserWebSocketTransport(ws)
        agent = agent_factory(campaign, model, lead_name)
        await agent.run(transport)

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Note: this task needs `static/index.html` to exist for `test_index_served`. Create a placeholder now; Task 9 fills it in:

```bash
printf '<!doctype html><title>Sales Agent</title><button id="call">Start call</button>\n' > src/sales_agent/static/index.html
```

Run: `pytest tests/test_server.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add src/sales_agent/server.py tests/test_server.py src/sales_agent/static/index.html
git commit -m "Add FastAPI AppServer with /session WebSocket"
```

---

## Task 9: Browser call console (manual-tested)

**Files:**
- Modify: `src/sales_agent/static/index.html` (replace placeholder)

No unit test (browser audio). Verified manually in Task 12.

- [ ] **Step 1: Replace `static/index.html` with the full client**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Sales Agent — Call Console</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 32rem; margin: 4rem auto; padding: 0 1rem; }
  button { font-size: 1rem; padding: 0.6rem 1.2rem; border-radius: 0.5rem; cursor: pointer; }
  #status { margin-top: 1rem; color: #555; }
  label { display: block; margin-bottom: 1rem; }
  input { font-size: 1rem; padding: 0.4rem; width: 12rem; }
</style>
</head>
<body>
  <h1>Sales Agent</h1>
  <label>Lead name: <input id="lead" value="there" /></label>
  <button id="call">Start call</button>
  <div id="status">Idle.</div>

<script>
const SAMPLE_RATE = 24000;       // OpenAI realtime pcm16 mono
let ctx, micStream, node, ws, playHead = 0, calling = false;
const statusEl = document.getElementById("status");
const btn = document.getElementById("call");

function setStatus(s) { statusEl.textContent = s; }

function floatToPCM16(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function pcm16ToFloat(int16) {
  const out = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) out[i] = int16[i] / 0x8000;
  return out;
}

function playChunk(arrayBuffer) {
  const int16 = new Int16Array(arrayBuffer);
  const float = pcm16ToFloat(int16);
  const buf = ctx.createBuffer(1, float.length, SAMPLE_RATE);
  buf.copyToChannel(float, 0);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(ctx.destination);
  const now = ctx.currentTime;
  if (playHead < now) playHead = now;
  src.start(playHead);
  playHead += buf.duration;
}

async function startCall() {
  ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
  micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const source = ctx.createMediaStreamSource(micStream);
  node = ctx.createScriptProcessor(4096, 1, 1);
  source.connect(node);
  node.connect(ctx.destination);

  const lead = encodeURIComponent(document.getElementById("lead").value || "there");
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/session?lead_name=${lead}`);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => setStatus("Connected — talk!");
  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      const msg = JSON.parse(ev.data);
      if (msg.type === "interrupted") playHead = ctx.currentTime;  // flush playback
      return;
    }
    playChunk(ev.data);
  };
  ws.onclose = () => { setStatus("Call ended."); cleanup(); };
  ws.onerror = () => setStatus("Connection error.");

  node.onaudioprocess = (e) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const pcm = floatToPCM16(e.inputBuffer.getChannelData(0));
    ws.send(pcm.buffer);
  };
}

function cleanup() {
  calling = false;
  btn.textContent = "Start call";
  if (node) { node.disconnect(); node.onaudioprocess = null; }
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  if (ctx) ctx.close();
}

btn.onclick = async () => {
  if (calling) { if (ws) ws.close(); return; }
  calling = true;
  btn.textContent = "End call";
  setStatus("Connecting…");
  try { await startCall(); }
  catch (err) { setStatus("Mic/connection failed: " + err.message); cleanup(); }
};
</script>
</body>
</html>
```

- [ ] **Step 2: Confirm the server still serves it**

Run: `pytest tests/test_server.py::test_index_served -v`
Expected: PASS (`Start call` present)

- [ ] **Step 3: Commit**

```bash
git add src/sales_agent/static/index.html
git commit -m "Add browser call console with mic capture and playback"
```

---

## Task 10: CLI entry point

**Files:**
- Create: `src/sales_agent/__main__.py`

- [ ] **Step 1: Implement `__main__.py`**

```python
# src/sales_agent/__main__.py
from __future__ import annotations
import argparse
import os
import sys
import uvicorn
from .campaign import load_campaign, CampaignError
from .server import create_app

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sales_agent")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the voice agent server")
    serve.add_argument("--campaign", default=os.environ.get("CAMPAIGN", "campaigns/acmecrm.md"))
    serve.add_argument("--model", default=os.environ.get("MODEL", "gpt-realtime-mini"))
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args(argv)

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        return 2
    try:
        campaign = load_campaign(args.campaign)
    except CampaignError as e:
        print(f"ERROR loading campaign: {e}", file=sys.stderr)
        return 2

    app = create_app(campaign, args.model)
    print(f"Serving '{campaign.product.get('name')}' on http://localhost:{args.port} "
          f"(model={args.model})")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-test argument handling (no server start)**

Run: `OPENAI_API_KEY= python -m sales_agent serve --campaign nope.md; echo "exit=$?"`
Expected: prints `ERROR: OPENAI_API_KEY is not set.` and `exit=2`

Run: `OPENAI_API_KEY=x python -m sales_agent serve --campaign nope.md; echo "exit=$?"`
Expected: prints `ERROR loading campaign: Campaign file not found: nope.md` and `exit=2`

- [ ] **Step 3: Commit**

```bash
git add src/sales_agent/__main__.py
git commit -m "Add serve CLI entry point"
```

---

## Task 11: Sample campaign + Docker packaging

**Files:**
- Create: `campaigns/acmecrm.md`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Create: `.env.example`

- [ ] **Step 1: Create the sample campaign**

```markdown
<!-- campaigns/acmecrm.md -->
---
product:
  name: "AcmeCRM"
  one_liner: "A CRM that sets itself up in 10 minutes."
  price: "$29/user/month, 14-day free trial"
persona:
  name: "Alex"
  role: "sales rep at Acme"
  tone: "warm, concise, never pushy"
  voice: "marin"
goal:
  type: book_follow_up
  success: "a callback or demo is booked via book_slot"
disclosure: if_asked
guardrails:
  - "Never invent features, pricing, or claims not in this file."
  - "Never promise specific ROI numbers."
  - "If the person asks to stop or says not interested twice, thank them and end politely."
opening_line: "Hi, am I speaking with {name}? I'm Alex from Acme — do you have 30 seconds?"
---

## Pitch
AcmeCRM replaces the spreadsheets and sticky notes most small teams use to track
deals. It imports your contacts, suggests next steps, and keeps the whole team on
the same page — without a week of setup.

## Key benefits
- 10-minute setup, no IT needed
- Automatic follow-up reminders so leads don't go cold
- Works on phone and laptop, syncs instantly

## Objection handling
- **"Too expensive"** → emphasize the 14-day free trial and the hours saved each week.
- **"We already use something"** → ask what frustrates them about it, position the easy switch/import.
- **"Send me an email"** → offer to book a quick 10-minute demo instead; that's the goal.
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 BOOKINGS_PATH=/data/bookings.json
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY campaigns ./campaigns
EXPOSE 8000
CMD ["python", "-m", "sales_agent", "serve"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  agent:
    build: .
    ports:
      - "8000:8000"
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY:?set OPENAI_API_KEY in your shell or .env}
      CAMPAIGN: campaigns/acmecrm.md
      MODEL: ${MODEL:-gpt-realtime-mini}
      BOOKINGS_PATH: /data/bookings.json
    volumes:
      - ./campaigns:/app/campaigns
      - ./data:/data
```

- [ ] **Step 4: Create `.dockerignore`**

```
.venv/
__pycache__/
*.pyc
*.egg-info/
.git/
data/
tests/
docs/
.env
```

- [ ] **Step 5: Create `.env.example`**

```
OPENAI_API_KEY=sk-replace-me
MODEL=gpt-realtime-mini
```

- [ ] **Step 6: Build the image to verify it compiles**

Run: `docker compose build`
Expected: builds successfully (pip install of `.` completes, no missing-file errors).

- [ ] **Step 7: Commit**

```bash
git add campaigns/acmecrm.md Dockerfile docker-compose.yml .dockerignore .env.example
git commit -m "Add sample campaign and Docker packaging"
```

---

## Task 12: README + full-suite + manual verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# Voice Sales Agent (Phase 1)

A realtime voice agent that pitches a configurable product and books follow-ups.
You talk to it in your browser; it runs in Docker.

## Quick start (Docker)

```bash
cp .env.example .env        # put your real OPENAI_API_KEY in .env
export OPENAI_API_KEY=sk-...   # (or rely on .env / your shell)
docker compose up --build
# open http://localhost:8000, set a lead name, click "Start call", talk
```

Bookings and call outcomes are written to `./data/bookings.json`.

## Sell a different product

Add a file under `campaigns/` (copy `acmecrm.md`), then set `CAMPAIGN` to it in
`docker-compose.yml` (or `-e CAMPAIGN=campaigns/yours.md`) and restart. No rebuild
needed — `campaigns/` is mounted.

## Models

`MODEL=gpt-realtime-mini` (default, cheap, for dev) or `MODEL=gpt-realtime`
(flagship, best quality). See the design spec for the cost model.

## Local dev (no Docker)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                      # run the test suite
OPENAI_API_KEY=sk-... python -m sales_agent serve --campaign campaigns/acmecrm.md
```
````

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: PASS — all tests across campaign, instructions, booking, tools, transport, agent, server, smoke.

- [ ] **Step 3: Manual live verification (requires a real `OPENAI_API_KEY`)**

```bash
docker compose up --build
```
Then in a browser at `http://localhost:8000`:
1. Confirm the page loads and shows "Start call".
2. Set a lead name, click "Start call", allow mic access.
3. Confirm the agent **speaks its opening line first** (greeting trigger works).
   - If it does NOT speak first, adjust the greeting mechanism in `agent.py`
     (`GREETING_TRIGGER` / `send_message`) — this is the known manual-tuning point.
4. Have a short exchange; raise an objection; agree to a follow-up.
5. Confirm the agent calls `book_slot` (you'll hear it confirm a time) and that a
   record appears in `./data/bookings.json` with `record_type: "booking"`.
6. End the call; confirm an `outcome` record is also written.

Record the result of each step. If any step fails, debug before declaring done.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Add README and verification steps"
```

---

## Self-Review Notes (author)

- **Spec coverage:** CampaignLoader (T2), InstructionBuilder (T3), BookingStore (T4),
  Tools/book_slot/log_outcome (T5), AudioTransport + BrowserWebSocketTransport (T6),
  RealtimeSalesAgent (T7), AppServer + WebSocket (T8), Browser console (T9), CLI (T10),
  Docker packaging + sample campaign (T11), cost-model model selection via `--model`/`MODEL`
  (T10/T11), disclosure if_asked/upfront (T3), guardrails (T3), prompt-caching stable prefix
  (instructions built once per call, not per turn — T3/T7). Manual audio round-trip (T12).
- **Known manual-tuning point:** the proactive greeting (`send_message` trigger) is the one
  behavior that can't be unit-tested; T12 step 3 calls it out explicitly with a fallback.
- **SDK version risk:** realtime event shape (`event.type == "audio"`, `event.audio.data`)
  and `model_settings` keys are pinned to `openai-agents>=0.7`. If a step's attribute access
  fails at runtime, verify against the installed version's `agents.realtime` and adjust the
  pump in `agent.py` only (everything else is isolated from the SDK).
