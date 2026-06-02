# Voice Sales Agent — Phase 1 Design

**Date:** 2026-06-02
**Status:** Approved (design), pending implementation plan

## Summary

A realtime voice agent that holds a persuasive sales conversation about a
configurable product and drives toward **booking a follow-up**. Phase 1 builds
the *agent that talks* — native speech-to-speech via the OpenAI Realtime API,
tested locally through mic/speaker. It is **not** wired to a phone line; the
telephony layer (Twilio) is a later phase and plugs into an isolated transport
seam.

The agent is retargeted to a new product by editing a single hybrid config file
(YAML front-matter + Markdown body). No code changes needed to sell something
else.

## Goals (Phase 1)

- Natural, low-latency, persuasive voice conversation about one product.
- Fully driven by a per-product **campaign** config file.
- Objective: book a follow-up (callback/demo) via a `book_slot` tool.
- Record how each call ends via a `log_outcome` tool.
- Honest by default: discloses it's an AI if asked, never invents claims.

## Non-Goals (Phase 1)

- No phone/telephony integration (no Twilio yet).
- No real calendar/CRM sync — bookings persist to a local JSON file.
- No multi-language support (English only for now).
- No config UI — the YAML/Markdown file is edited by hand.

## Decisions

| Decision | Choice |
|---|---|
| Audio scope | Full realtime speech-to-speech |
| Stack | OpenAI Realtime API via the OpenAI **Agents SDK** (`RealtimeAgent`), Python |
| Config format | Hybrid: YAML front-matter + Markdown body |
| Call goal | Book a follow-up (`book_slot`), plus `log_outcome` |
| Disclosure | Disclose if asked; stay strictly truthful (guardrails in config) |
| Transport | Isolated behind an interface; `LocalMicTransport` for Phase 1 |

## Architecture

```
campaigns/*.md  ──►  CampaignLoader  ──►  Campaign (validated)
                                              │
                                              ▼
                                       InstructionBuilder  ──►  system prompt
                                              │
                                              ▼
          ┌─────────────────  RealtimeSalesAgent  ─────────────────┐
          │   (OpenAI RealtimeAgent: instructions + tools + VAD)   │
          └───────┬───────────────────────────────────┬───────────┘
                  │ audio in/out                       │ tool calls
                  ▼                                     ▼
          AudioTransport (interface)            Tools: book_slot, log_outcome
          └─ LocalMicTransport (Phase 1)               │
          └─ TwilioTransport (Phase 2, later)          ▼
                                              BookingStore (JSON file)
```

**Separation principle:** the *brain* (campaign → instructions → conversation +
tools) knows nothing about *where* audio comes from. Phase 2 replaces
`LocalMicTransport` with a Twilio media-stream transport without touching the
brain.

## Components

Each component has one job, a clear interface, and known dependencies.

- **CampaignLoader** — reads a `.md` file, splits YAML front-matter from the
  Markdown body, validates required fields, returns a `Campaign`. Fails loudly
  with the exact missing field named. *Depends on:* a YAML parser.
- **Campaign** — plain data object: structured fields (persona, goal, product,
  guardrails, disclosure, opening_line) + prose body (pitch, benefits,
  objections).
- **InstructionBuilder** — pure function `Campaign → str`. Assembles the system
  prompt: persona, goal, disclosure rule, guardrails, product knowledge,
  objection guidance. No I/O. *Depends on:* nothing — trivially testable.
- **RealtimeSalesAgent** — wraps OpenAI `RealtimeAgent`/session: applies
  instructions, registers tools, runs the conversation loop, speaks the
  opening line. *Depends on:* OpenAI Agents SDK, an AudioTransport, the tools.
- **AudioTransport** (interface) — streams audio in/out. `LocalMicTransport`
  (sounddevice mic + speaker) is the Phase 1 implementation and the seam Phase
  2 plugs into.
- **Tools** — `book_slot` and `log_outcome`, writing through **BookingStore**.
- **BookingStore** — thin wrapper over an append-only JSON file. Isolated so a
  real DB/calendar can replace it later. *Timestamps are passed in by the tool
  layer* (the store does no clock access itself), keeping it deterministic and
  testable.
- **CLI** — `python -m sales_agent run --campaign campaigns/widget.md
  [--lead-name NAME]`.

## Campaign config file

Hybrid format. Example `campaigns/widget.md`:

```markdown
---
product:
  name: "AcmeCRM"
  one_liner: "A CRM that sets itself up in 10 minutes."
  price: "$29/user/month, 14-day free trial"
persona:
  name: "Alex"
  role: "sales rep at Acme"
  tone: "warm, concise, never pushy"
goal:
  type: book_follow_up
  success: "a callback or demo is booked via book_slot"
disclosure: if_asked            # if_asked | upfront
guardrails:
  - "Never invent features, pricing, or claims not in this file."
  - "Never promise specific ROI numbers."
  - "If the person asks to stop or says not interested twice, thank them and end politely."
opening_line: "Hi, am I speaking with {name}? I'm Alex from Acme — do you have 30 seconds?"
---

## Pitch
AcmeCRM replaces spreadsheets... (the core value story in prose)

## Key benefits
- 10-minute setup, no IT needed
- ...

## Objection handling
- **"Too expensive"** → emphasize the 14-day free trial and time saved...
- **"We already use X"** → ask what's frustrating about X, position the switch...
- **"Send me an email"** → offer to book a 10-min call instead; that's the goal.
```

**Required fields** (loader fails clearly if missing): `product.name`,
`persona.name`, `goal.type`, `opening_line`. All other fields have sensible
defaults. The Markdown body is optional but recommended — it is injected
wholesale as product knowledge.

`{name}` is a placeholder filled from per-call context. Phase 1 supplies it via
a `--lead-name` flag (default: "there").

## Tools

- **`book_slot(lead_name, contact, preferred_time, notes)`** — captures a
  follow-up. Appends a record to `bookings.json`. Returns a confirmation string
  the agent reads back aloud.
- **`log_outcome(status, notes)`** — `status ∈ {booked, interested,
  not_interested, callback_requested, no_answer}`. Records how the call ended.
  The agent is instructed to always call this before ending.

## Data flow (one call)

1. CLI loads campaign → InstructionBuilder → system prompt.
2. RealtimeSalesAgent starts a Realtime session with instructions + tools;
   speaks the `opening_line`.
3. LocalMicTransport streams mic audio up; server VAD detects turns; the agent
   responds with audio.
4. When the lead agrees, the agent calls `book_slot` → BookingStore writes the
   record → the agent confirms aloud.
5. The agent calls `log_outcome` → the session ends.

## Error handling

- Missing/invalid campaign field → exit **before** connecting, naming the exact
  field.
- Missing `OPENAI_API_KEY` → clear startup error.
- WebSocket drop mid-call → log, attempt one reconnect; otherwise end
  gracefully and `log_outcome("no_answer")`.
- Tool failure (e.g. disk write error) → tool returns an error string; the
  agent apologizes and offers to follow up, and does not crash.

## Testing strategy

TDD for the brain; manual testing for live audio.

- **CampaignLoader** — valid file parses correctly; each missing required field
  raises a clear, specific error; defaults are applied.
- **InstructionBuilder** — pure function: assert persona, goal, guardrails, and
  disclosure text all appear in the output; `disclosure: upfront` vs `if_asked`
  produce different prompts.
- **Tools / BookingStore** — `book_slot` and `log_outcome` write correct
  records to a temp store; bad inputs are handled.
- **Realtime/audio layer** — manually tested by talking to it. Not
  unit-tested (live audio). It is isolated precisely so everything around it is
  testable.

## Future phases (context, not in scope now)

- **Phase 2:** Twilio telephony transport (real outbound calls) behind the
  existing `AudioTransport` seam.
- Later: real calendar/CRM integration replacing `BookingStore`; a config UI
  over the structured front-matter; multi-language; analytics over outcomes.
