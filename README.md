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
(flagship, best quality). See `docs/superpowers/specs/` for the cost model.

## Local dev (no Docker)

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                      # run the test suite
OPENAI_API_KEY=sk-... python -m sales_agent serve --campaign campaigns/acmecrm.md
```

## Architecture

- `campaign.py` — load a hybrid YAML+Markdown campaign file.
- `instructions.py` — compile a campaign into the agent's system prompt.
- `booking.py` / `tools.py` — `book_slot` and `log_outcome` tools writing to a JSON store.
- `transport.py` — `AudioTransport` interface; `BrowserWebSocketTransport` for Phase 1.
- `agent.py` — `RealtimeSalesAgent` bridges the browser audio to the OpenAI Realtime session.
- `server.py` / `__main__.py` — FastAPI server + `serve` CLI.
- `static/index.html` — browser call console (mic capture + playback).

Phase 2 (telephony) swaps `BrowserWebSocketTransport` for a Twilio transport
behind the same interface.
