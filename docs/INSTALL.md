# Install Guide

This guide assumes Hermes already runs with a Telegram bot.

## 1. Verify Prerequisites

Check Codex is available:

```bash
codex --version
```

Check Codex app-server support:

```bash
codex app-server --help
```

Check Python:

```bash
python3 --version
```

Use Python 3.11 or newer.

## 2. Clone Into Hermes Plugins

From your Hermes plugins directory:

```bash
git clone https://github.com/vinzlercodes/codex-telegram-remote.git
```

The cloned directory should contain:

```text
__init__.py
plugin.yaml
codex_remote/
```

## 3. Test The Checkout

```bash
cd codex-telegram-remote
pytest -q
```

Expected:

```text
9 passed
```

## 4. Restart Hermes

Restart Hermes so it reloads plugins. The exact command depends on your Hermes install.

## 5. Verify From Telegram

Send:

```text
/codex status
```

Expected response includes:

```text
Socket:
Active thread:
Active turn:
Pending approvals:
```

## 6. Start A Codex Turn

Send:

```text
/codex new /absolute/path/to/workspace :: Summarize this repo
```

Use an absolute workspace path. Relative paths are rejected.

## Optional Socket Override

By default, runtime socket and state live under `.state/`.

```bash
export CODEX_REMOTE_APP_SERVER_SOCKET=/absolute/path/to/codex-app-server.sock
```

Set this in the environment that starts Hermes.

