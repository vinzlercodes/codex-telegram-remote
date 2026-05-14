# Contributing

Thanks for improving `codex-telegram-remote`.

## Development Setup

Use Python 3.11 or newer.

```bash
pytest -q
```

The plugin is designed to run from a Hermes plugin checkout. Keep runtime behavior compatible with Hermes command loading through the root `__init__.py`.

## Pull Requests

- Keep the `/codex` command stable unless the change is clearly documented.
- Add or update tests for command parsing, approval mapping, formatting, and state behavior.
- Do not commit `.state/`, sockets, `__pycache__/`, `.pytest_cache/`, or IDE metadata.
- Avoid storing Telegram chat IDs, Codex thread IDs, or local workspace paths in committed fixtures unless they are fake examples.

## Documentation

Update docs when changing commands, install steps, required Hermes integrations, or approval behavior.

