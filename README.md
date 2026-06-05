# 📞 CallAgent — AI Voice Sales Agent

[![CI](https://github.com/Shehan-Wences/CallAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/Shehan-Wences/CallAgent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![OpenAI Realtime](https://img.shields.io/badge/OpenAI-Realtime%20API-412991.svg)](https://platform.openai.com/docs/guides/realtime)

A realtime **AI voice agent that calls people, pitches a product, and books follow-ups** — and you can point it at any product by editing a single Markdown file. Talk to it **in your browser** or have it place a **real outbound phone call via Twilio**, with a **live transcript on screen** either way.

Built on the **OpenAI Realtime API** (native speech-to-speech), runs in **Docker**, and is configured entirely from plain-text **campaign files** — no code changes to sell something new.

---

## ✨ Features

- 🗣️ **Natural realtime voice** — speech-to-speech via the OpenAI Realtime API (warm, human delivery, configurable accent & voice).
- 📝 **Configurable per product** — a hybrid YAML + Markdown "campaign" file defines the persona, pitch, guardrails, and objection handling. Swap products without touching code.
- 📞 **Two ways to call:**
  - **Browser** — talk to the agent with your mic.
  - **Phone (Twilio)** — initiate a real outbound call from the UI; the agent talks over the phone.
- 📜 **Live transcript** — both sides of the conversation stream to the screen in real time, even on phone calls.
- 📅 **Books follow-ups** — calls `book_slot` / `log_outcome` tools and records results to a JSON store.
- 🔒 **Honest by default** — discloses it's an AI if asked, and never invents claims beyond the campaign file.
- ⬆️ **Upload campaigns in the browser** — drop in a new `.md`, it's validated and instantly selectable.
- 🐳 **One-command Docker** — `docker compose up` and open `localhost:8000`.

---

## 🚀 Quick start (Docker)

You need an [OpenAI API key](https://platform.openai.com/api-keys) with Realtime access.

```bash
git clone git@github.com:Shehan-Wences/CallAgent.git
cd CallAgent
cp .env.example .env          # then put your real OPENAI_API_KEY in .env
docker compose up --build
```

Open **http://localhost:8000**, pick a product, set a lead name, click **Start call**, and talk. Bookings and outcomes are written to `./data/bookings.json`.

> 💡 First time it's quiet? Use headphones, or see [Troubleshooting](#-troubleshooting).

---

## 📝 Sell a different product (campaigns)

A "campaign" is one Markdown file: **YAML front-matter** for the structured settings + a **Markdown body** for the pitch and objection handling. Copy the annotated template:

```bash
cp campaigns/TEMPLATE.md.example campaigns/myproduct.md
# edit it, then pick it in the UI — or upload a .md directly in the browser
```

Minimal example:

```markdown
---
product:
  name: "AcmeCRM"
  one_liner: "A CRM that sets itself up in 10 minutes."
  price: "$29/user/month, 14-day trial"
persona:
  name: "Alex"
  role: "sales rep at Acme"
  tone: "warm, concise, never pushy"
  voice: "marin"            # marin, cedar, alloy, ash, ballad, coral, echo, sage, shimmer, verse
  accent: "Australian"      # optional — steers the accent
goal:
  type: book_follow_up
disclosure: if_asked        # if_asked | upfront
guardrails:
  - "Never invent features, pricing, or claims not in this file."
opening_line: "Hi {name}, it's Alex from Acme — got a quick minute?"
---

## Pitch
The core value story, in plain conversational language.

## Key benefits
- Specific, concrete benefit
- Another one

## Objection handling
- **"Too expensive"** → emphasize the free trial and time saved.
- **"Just send me an email"** → offer a quick call instead; that's the goal.
```

**Required fields:** `product.name`, `persona.name`, `goal.type`, `opening_line`. The `## Objection handling` section is the highest-leverage part — give the agent the *angle*, not a script. See [`campaigns/TEMPLATE.md.example`](campaigns/TEMPLATE.md.example) for the fully annotated version.

---

## ☎️ Phone calls (Twilio outbound)

Initiate a real outbound call from the UI; the agent talks over the phone while the **transcript still streams to your screen**.

You need a [Twilio](https://www.twilio.com/) account, a Twilio number to call **from**, and a public URL Twilio can reach (it can't reach `localhost`). For local testing, tunnel it — e.g. [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) or [`ngrok`](https://ngrok.com/):

```bash
cloudflared tunnel --url http://localhost:8000   # copy the https host it prints
```

Add to `.env`:

```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
PUBLIC_HOST=your-tunnel-host.trycloudflare.com    # host only, no https://
```

`docker compose up`, then enter the prospect's number in **E.164** (e.g. `+61412345678`) and click **Call phone (Twilio)**.

> ⚠️ Real calls cost money (Twilio per-minute + OpenAI per-minute). And don't expose this publicly without auth — `/call` will dial any number it's given. Fine behind your own tunnel for testing.

---

## 🤖 Models & cost

| Model | Use | Audio cost (approx.) |
|---|---|---|
| `gpt-realtime-mini` | dev / bulk, cheaper, more robotic | ~$0.08–0.16 / 4-min call |
| `gpt-realtime` (flagship) | production, much warmer & more natural | ~$0.20–0.40 / 4-min call |

Set `MODEL` in `.env`. Enabling caller transcription (for the live transcript) and prompt caching are handled for you. See [`docs/superpowers/specs/`](docs/superpowers/specs/) for the full cost model.

---

## 🛠️ Local development

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                       # run the test suite
OPENAI_API_KEY=sk-... python -m sales_agent serve --campaign campaigns/acmecrm.md
```

### Architecture

```
Browser / Twilio phone  ──audio──►  AudioTransport (interface)  ──►  RealtimeSalesAgent  ──►  OpenAI Realtime API
        ▲ transcript on screen          ├─ BrowserWebSocketTransport        │ tool calls
        └────────── monitor ────────────┘─ TwilioMediaStreamTransport       ▼
                                                                     book_slot / log_outcome  ──►  bookings.json
```

| File | Responsibility |
|---|---|
| `campaign.py` | Load + validate a hybrid YAML/Markdown campaign |
| `instructions.py` | Compile a campaign into the agent's system prompt |
| `booking.py` / `tools.py` | `book_slot` / `log_outcome` tools → JSON store |
| `transport.py` | `AudioTransport` interface + browser WebSocket transport |
| `twilio_transport.py` | Twilio Media Streams transport (phone audio) |
| `agent.py` | `RealtimeSalesAgent` — bridges any transport to OpenAI Realtime |
| `server.py` / `__main__.py` | FastAPI server + `serve` CLI |
| `static/index.html` | Browser call console + live transcript |

Both transports implement the same `AudioTransport` interface, so the agent brain is identical whether the call is in the browser or over the phone.

---

## 🩹 Troubleshooting

- **Agent interrupts itself / silence:** you're likely on speakers — use **headphones**, or raise `VAD_THRESHOLD` (e.g. `0.75`) in `.env`.
- **Phone dials but silent:** the tunnel dropped or `PUBLIC_HOST` is stale — restart your tunnel and update `PUBLIC_HOST`.
- **`GET /` 404 in Docker:** rebuild (`docker compose up --build`) — the static page is packaged into the image.

---

## 🤝 Contributing

Contributions are welcome! Please read **[CONTRIBUTING.md](CONTRIBUTING.md)**. In short: fork, branch, keep the tests green, and open a PR. **Every PR is reviewed by the maintainer and must pass CI before it can be merged.**

---

## 🔒 Security

Found a vulnerability? Please report it privately — see **[SECURITY.md](SECURITY.md)**. And don't expose `/call` publicly without authentication; it will dial any number it's given.

---

## 🤖 Built with Claude

This project was designed, built, and documented with the help of [Claude](https://claude.ai) (Anthropic) — from the initial architecture and tests through the Twilio integration and these docs.

---

## 📄 License

[MIT](LICENSE) © Shehan Wences
