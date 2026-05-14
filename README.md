# codex-telegram-remote

Hermes-native Codex control from Telegram.

`codex-telegram-remote` is a lightweight Hermes plugin that exposes a `/codex` Telegram command. It lets you list and read Codex threads, start or resume work, steer a running turn, relay approval requests, and receive completion summaries from the same Telegram chat you already use for Hermes.

This is not another standalone Telegram bot server. It is for people who already run Hermes, already trust Hermes as their messaging gateway, and want Codex phone control without adding a second bot runtime.

## Why This Exists

There are good open-source Telegram bridges for Codex and other coding agents. Most of them are separate runtimes: they run their own Telegram bot process, manage their own sessions, and duplicate pieces of the messaging stack you already configured in Hermes.

This project takes a narrower path:

- Hermes-native: installs as a Hermes plugin and reuses Hermes Telegram routing.
- No second bot server: no extra long-polling daemon, webhook service, tunnel, or bot token manager.
- Codex app-server based: talks to Codex through `codex app-server` instead of scraping a terminal or injecting keystrokes into tmux.
- Existing Codex threads: works with Codex app-server thread APIs instead of creating an unrelated chat-only session store.
- Telegram approval routing: sends Codex approval requests back to the active Hermes Telegram chat/thread.
- Small audit surface: a compact Python plugin with local JSON state and no hosted service.

If you want a full multi-agent command center, use a broader tool. If you want Hermes to become the phone interface for Codex, this plugin is the direct fit.

## What It Does

- Starts a local `codex app-server` process when needed.
- Connects to the Codex app-server over a Unix socket and websocket.
- Registers a Hermes `/codex` command.
- Routes Codex approvals back to Telegram with approve, deny, cancel, session, and always options.
- Stores only local runtime routing state under `.state/`, which is ignored by git.

## How It Compares

| Project type | Good for | Tradeoff |
|---|---|---|
| `codex-telegram-remote` | Hermes users who want `/codex` inside existing Telegram setup | Requires Hermes; intentionally narrow |
| Standalone Codex Telegram bots | Users who want a dedicated Codex bot without Hermes | Adds another bot process and session layer |
| tmux bridges | Users who want terminal-first control over many CLI agents | Depends on terminal/tmux state, not Codex app-server APIs |
| Multi-agent gateways | Teams wanting Telegram/Discord/Slack plus many agents | Larger install and operational surface |

Known adjacent open-source projects include [OpenACP](https://github.com/Open-ACP/OpenACP), [HeyAgent](https://github.com/gergomiklos/heyagent), [TeleCodex](https://github.com/benedict2310/telecodex), [CodexClaw](https://github.com/MackDing/CodexClaw), [CCGram](https://github.com/alexei-led/ccgram), and [openclaw-codex-app-server](https://github.com/pwrdrvr/openclaw-codex-app-server). They validate the category. This repo competes by being the Hermes-native, app-server-first option.

## Requirements

- macOS or Linux with Python 3.11+.
- Hermes installed and running. Follow the original [Hermes Agent repo](https://github.com/NousResearch/hermes-agent) for the base setup.
- Hermes Telegram messaging configured according to the official [Hermes Telegram guide](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram).
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

## Expected Results

Status check:

```text
/codex status
```

Expected response:

```text
Socket: /path/to/codex-telegram-remote/.state/codex-app-server.sock
Active thread: (none)
Active turn: (none)
Pending approvals: 0
```

List recent Codex threads:

```text
/codex list
```

Expected response:

```text
Codex threads:

abc123def456  Fix auth tests
cwd: /Users/me/projects/app
updated: 2026-05-14T09:30:00Z

def456abc123  Draft release notes
cwd: /Users/me/projects/docs
updated: 2026-05-14T08:55:00Z
```

Show workspaces:

```text
/codex workspaces
```

Expected response:

```text
Codex workspaces: 2

/Users/me/projects/app
threads: 4
latest: Fix auth tests
updated: 2026-05-14T09:30:00Z

/Users/me/projects/docs
threads: 1
latest: Draft release notes
updated: 2026-05-14T08:55:00Z
```

Start a new Codex turn:

```text
/codex new /Users/me/projects/app :: Run tests and fix the failing auth case
```

Expected response:

```text
Codex turn started.
Thread: Fix auth tests
ID: abc123def456
Turn: turn789
```

Read a thread:

```text
/codex thread abc123def456 3
```

Expected response:

```text
Thread: Fix auth tests
ID: abc123def456
CWD: /Users/me/projects/app
Turns shown: 3

Turn 1: completed
User: Run tests and fix the failing auth case
Codex: Tests passed after updating the auth expiry check.
Command (completed, exit 0):
pytest -q
Output:
9 passed in 0.02s
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

Approve the request once:

```text
/codex approve A1
```

Expected response:

```text
A1 -> approve
```

Deny with alternate instructions:

```text
/codex deny A1 Do not install packages. Inspect existing lockfiles instead.
```

Expected response:

```text
A1 denied. Alternate instructions sent.
```

When the Codex turn completes, expected response:

```text
Codex turn completed.
Thread: Fix auth tests

Tests passed after updating the auth expiry check.
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

The security boundary is intentionally simple: anyone who can command your configured Hermes Telegram session may be able to steer or approve Codex work. Keep Hermes pairing, Telegram bot membership, and Codex approval policy locked down.

Report security issues privately; see [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
