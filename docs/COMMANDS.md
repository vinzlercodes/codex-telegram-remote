# Command Reference

All commands are sent through Telegram to Hermes.

## Thread Discovery

```text
/codex list [query]
```

Lists recent Codex threads, optionally filtered by query.

```text
/codex thread <thread-id-or-title> [all|N]
```

Shows a thread transcript. Use `all` for all turns or a number for the last N turns.

```text
/codex workspaces
```

Groups known Codex threads by workspace path.

```text
/codex limits
```

Shows Codex account rate limits if the app-server exposes them.

## Starting Work

```text
/codex new <absolute-cwd> :: <prompt>
```

Starts a new Codex thread in an absolute workspace path.

```text
/codex resume <thread-id-or-title> :: <prompt>
```

Resumes an existing Codex thread and starts a new turn.

```text
/codex steer <text>
```

Sends steering text to the active Codex turn for the current Telegram session.

```text
/codex status
```

Shows socket path, active thread, active turn, pending approvals, and last task summary.

## Approvals

```text
/codex approve <approval-id>
```

Approves the request once.

```text
/codex session <approval-id>
```

Approves equivalent permission for the current Codex session when supported.

```text
/codex always <approval-id>
```

Accepts a proposed Codex exec or network policy amendment when present. Otherwise falls back to session approval.

```text
/codex deny <approval-id> [alternate instructions]
```

Declines the request. If alternate instructions are provided, they are sent to the active Codex turn.

```text
/codex cancel <approval-id>
```

Cancels the request and interrupts the related Codex turn when possible.

