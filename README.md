# codex-telegram-remote

Control Codex from Telegram through Hermes.

`codex-telegram-remote` is a Hermes plugin that exposes a `/codex` Telegram command. It can list and read Codex threads, start or resume work, steer a running turn, relay approval requests to Telegram, and send completion summaries back to the same chat.

This repo is for people who already run Hermes with a Telegram bot and want phone-based control over Codex.

## What It Does

- Starts a local `codex app-server` process when needed.
- Connects to the Codex app-server over a Unix socket and websocket.
- Registers a Hermes `/codex` command.
- Routes Codex approvals back to Telegram with approve, deny, cancel, session, and always options.
- Stores only local runtime routing state under `.state/`, which is ignored by git.

## Requirements

- macOS or Linux with Python 3.11+.
- Hermes with Telegram bot support already configured.
- Codex CLI installed and available as `codex`.
- Codex CLI support for `codex app-server`.
- Hermes runtime modules available to plugins:
  - `gateway.session_context`
  - `tools.send_message_tool`

## Quick Install

Clone this repo into your Hermes plugins directory:

```bash
cd /path/to/hermes/plugins
git clone https://github.com/vinzlercodes/codex-telegram-remote.git
```

Restart Hermes so it loads the plugin. Then send this in Telegram:

```text
/codex status
```

If Hermes and Codex are wired correctly, you should see socket, active thread, active turn, and pending approval state.

## Commands

```text
/codex list [query]
/codex thread <thread-id-or-title> [all|N]
/codex workspaces
/codex limits
/codex new <absolute-cwd> :: <prompt>
/codex resume <thread-id-or-title> :: <prompt>
/codex steer <text>
/codex status
/codex approve <approval-id>
/codex session <approval-id>
/codex always <approval-id>
/codex deny <approval-id> [alternate instructions]
/codex cancel <approval-id>
```

Example:

```text
/codex new /Users/me/projects/app :: Run tests and fix the failing auth case
```

When Codex requests approval, the plugin sends a Telegram message like:

```text
Codex approval A1
Thread: Fix auth tests
CWD: /Users/me/projects/app

Reply:
/codex approve A1
/codex session A1
/codex always A1
/codex deny A1 [alternate instructions]
/codex cancel A1
```

## Configuration

By default, the plugin uses:

```text
.state/codex-app-server.sock
```

Override that socket with:

```bash
export CODEX_REMOTE_APP_SERVER_SOCKET=/absolute/path/to/codex-app-server.sock
```

## Documentation

- [Install guide](docs/INSTALL.md)
- [Command reference](docs/COMMANDS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Development

Run tests:

```bash
pytest -q
```

This repo intentionally does not commit `.state/`, sockets, caches, or IDE files.

## Security

This plugin can approve local Codex actions from Telegram. Treat Telegram account access and bot access as privileged. Review approval messages carefully before using `/codex always`.

Report security issues privately; see [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).

