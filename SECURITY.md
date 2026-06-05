# Security Policy

## Supported versions

This project is actively developed; security fixes target the latest `main`.

## Reporting a vulnerability

**Please do not report security issues in public GitHub issues.**

Report privately via GitHub's **[Report a vulnerability](https://github.com/Shehan-Wences/CallAgent/security/advisories/new)** (the repo's *Security → Advisories* tab). If you can't use that, contact the maintainer directly.

Please include:

- A description of the issue and its impact
- Steps to reproduce (a proof-of-concept if possible)
- The affected version / commit
- Any suggested remediation

We aim to acknowledge reports within a few days and will keep you posted on the fix.

## Scope & known considerations

CallAgent is built to run **locally or behind your own tunnel** for development and demos. A few things are intentionally **not** hardened for public deployment — please don't report these as vulnerabilities unless you've found an exploit beyond the documented behavior:

- **`/call` is unauthenticated** — it will place a Twilio call to any number it's given. Don't expose it publicly without adding authentication.
- **`/twilio-stream` does not yet validate Twilio request signatures.** Add signature verification before any production use.
- Secrets (`OPENAI_API_KEY`, Twilio credentials) live in `.env`, which is gitignored — never commit them.

If you deploy this for real, add authentication on `/call`, Twilio signature validation on `/twilio-stream`, and put it behind HTTPS with proper access controls.

## Responsible disclosure

We appreciate good-faith research. Please give us reasonable time to address an issue before public disclosure, and avoid accessing or modifying data that isn't yours while testing.
