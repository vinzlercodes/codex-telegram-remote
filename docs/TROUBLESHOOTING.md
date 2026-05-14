# Troubleshooting

## `/codex status` Does Not Respond

Check Hermes loaded the plugin. The plugin root must include:

```text
__init__.py
plugin.yaml
codex_remote/
```

Restart Hermes after cloning or updating the plugin.

## `codex app-server` Fails

Run:

```bash
codex app-server --help
```

If this fails, update Codex CLI or confirm the installed Codex build supports app-server.

## Socket Timeout

The bridge waits for the default socket:

```text
.state/codex-app-server.sock
```

If another app-server manages the socket, set:

```bash
CODEX_REMOTE_APP_SERVER_SOCKET=/absolute/path/to/socket
```

Then restart Hermes.

## Approval Messages Do Not Reach Telegram

Confirm Hermes exposes:

```text
tools.send_message_tool
gateway.session_context
```

Also confirm commands are sent from the Telegram session where you expect replies. The bridge routes responses to the active Telegram chat/thread when Hermes provides session env values.

## Pending Approval Stuck

Run:

```text
/codex status
```

Then cancel the approval:

```text
/codex cancel A1
```

Use the actual approval ID from status output.

## Wrong Thread Resumed

Prefer full thread IDs when titles are similar:

```text
/codex resume <thread-id> :: Continue
```

`/codex resume <title> :: ...` uses Codex thread search and picks the first matching title if there is no exact unique match.

