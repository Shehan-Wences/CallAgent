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

## Phone calls (Twilio outbound)

Initiate a real outbound phone call from the UI; the agent talks over the phone
while the **transcript still streams to your screen**.

You need a Twilio account, a Twilio number to call from, and a public URL Twilio
can reach (Twilio can't reach `localhost`). For local testing, tunnel it:

```bash
ngrok http 8000        # copy the host, e.g. abc123.ngrok-free.app
```

Put the values in `.env` (see `.env.example`):

```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
PUBLIC_HOST=abc123.ngrok-free.app
```

Then `docker compose up`, open http://localhost:8000, pick a campaign, enter the
prospect's number in **E.164** (e.g. `+61412345678`), and click **Call phone
(Twilio)**. Audio rides the phone; transcript + status appear on screen.

How it works: the browser opens a `/monitor` WebSocket (transcript/status only),
`POST /call` originates the call via Twilio with a `<Stream>` pointed at
`/twilio-stream`, and that stream bridges the phone's μ-law audio to OpenAI
Realtime. Per-minute Twilio cost is on top of the model cost (~$0.018/min US).

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
- `transport.py` — `AudioTransport` interface; `BrowserWebSocketTransport` (browser mic).
- `twilio_transport.py` — `TwilioMediaStreamTransport` (phone audio over Twilio Media Streams).
- `agent.py` — `RealtimeSalesAgent` bridges either transport to the OpenAI Realtime session.
- `server.py` / `__main__.py` — FastAPI server (`/session` browser, `/monitor` + `/call` + `/twilio-stream` phone) + `serve` CLI.
- `static/index.html` — call console: browser call (mic) or phone call (Twilio), with live transcript.

Both transports implement the same `AudioTransport` interface, so the agent
brain is identical whether the call is in the browser or over the phone.
