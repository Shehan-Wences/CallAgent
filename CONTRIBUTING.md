# Contributing to CallAgent

Thanks for your interest in contributing! 🎉 This project welcomes pull requests — bug fixes, new features, more campaign examples, docs improvements, all of it.

> **Heads up:** every pull request is **reviewed by the maintainer** and must **pass CI** before it can be merged. Direct pushes to `main` are disabled. So please open a PR, even for small changes.

## Ways to contribute

- 🐛 **Report a bug** or 💡 **request a feature** — open an [issue](https://github.com/Shehan-Wences/CallAgent/issues).
- 🔧 **Fix or build something** — open a pull request (see below).
- 📝 **Add a campaign example** — drop a new `campaigns/*.md` that shows off a different product/industry.
- 📖 **Improve the docs** — typos, clearer explanations, better examples.

## Development setup

Requires **Python 3.12** and (optionally) Docker.

```bash
git clone git@github.com:<your-username>/CallAgent.git
cd CallAgent
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                       # should be all green
```

You do **not** need an OpenAI or Twilio account to run the tests — external services are mocked. You only need real keys to actually place calls.

## Pull request process

1. **Fork** the repo and create a branch from `main`:
   `git checkout -b feat/short-description` (or `fix/...`, `docs/...`).
2. **Make your change.** Keep it focused — one logical change per PR.
3. **Add or update tests.** New behavior should come with tests; `pytest` must pass.
4. **Keep secrets out.** Never commit `.env`, API keys, tokens, phone numbers, or real campaign content you don't want public. `.env` is gitignored.
5. **Open the PR** against `main`. Fill in the template (what changed, how you tested it).
6. **CI runs automatically** — make sure it's green. The maintainer (@Shehan-Wences) will be auto-requested for review.
7. **Address review feedback**, then the maintainer merges. 🚀

## Code style

- Follow the patterns already in the codebase — small, focused files, clear names.
- Each unit should be testable in isolation (see how transports/agents are tested with fakes).
- Prefer pure functions where practical; inject dependencies (clocks, factories) so tests stay deterministic.
- Run `pytest -q` before pushing.

## Reporting security issues

Found something sensitive (a way to abuse the `/call` endpoint, a leaked secret, etc.)? Please **don't** open a public issue — contact the maintainer directly so it can be handled responsibly.

By contributing, you agree your contributions are licensed under the project's [MIT License](LICENSE).
