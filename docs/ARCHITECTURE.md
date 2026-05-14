# Architecture

`codex-telegram-remote` sits between Hermes Telegram messages and Codex app-server.

```text
Telegram
  -> Hermes Telegram gateway
  -> Hermes plugin command: /codex
  -> CodexRemoteBridge
  -> CodexAppClient
  -> codex app-server over Unix socket + websocket
  -> Codex thread/turn/approval APIs
```

Responses flow back through Hermes:

```text
Codex notification or approval request
  -> CodexAppClient
  -> CodexRemoteBridge
  -> tools.send_message_tool
  -> Telegram chat/thread
```

## Main Components

- Root `__init__.py`: registers `/codex` with Hermes.
- `codex_remote.bridge.CodexRemoteBridge`: command parser, session routing, approval routing, state updates.
- `codex_remote.codex_rpc.CodexAppClient`: starts `codex app-server`, opens Unix socket, performs websocket framing, sends JSON-RPC style requests.
- `codex_remote.state.StateStore`: local JSON state under `.state/`.
- `codex_remote.formatting`: Telegram-safe summaries and transcript formatting.

## State

Runtime state is stored in:

```text
.state/codex_remote_state.json
```

This file may contain Telegram chat routing, Codex thread IDs, active turn IDs, and local workspace paths. It is ignored by git.

## Socket

Default socket:

```text
.state/codex-app-server.sock
```

Override:

```bash
CODEX_REMOTE_APP_SERVER_SOCKET=/absolute/path/to/socket
```

## Approval Flow

1. Codex requests approval through app-server.
2. Bridge assigns an approval ID like `A1`.
3. Bridge stores pending approval state locally.
4. Bridge sends Telegram instructions.
5. User replies with `/codex approve A1`, `/codex deny A1`, or related command.
6. Bridge responds to Codex app-server and removes pending approval.

