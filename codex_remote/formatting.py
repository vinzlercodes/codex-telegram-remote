from __future__ import annotations

from datetime import datetime
from typing import Any


MAX_BLOCK = 1500


def truncate(text: str | None, limit: int = MAX_BLOCK) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def code_block(text: str | None, limit: int = MAX_BLOCK) -> str:
    body = truncate(text or "", limit)
    return "```\n" + body.replace("```", "'''") + "\n```"


def compact_thread(thread: dict[str, Any]) -> str:
    title = thread.get("title") or thread.get("threadName") or thread.get("name") or "(untitled)"
    tid = thread.get("id") or thread.get("threadId") or "?"
    cwd = thread.get("cwd") or thread.get("workingDirectory") or ""
    updated = thread.get("updatedAt") or thread.get("updated_at") or thread.get("updatedAtMs") or ""
    pieces = [f"{tid}  {title}"]
    if cwd:
        pieces.append(f"cwd: {cwd}")
    if updated:
        pieces.append(f"updated: {updated}")
    return "\n".join(pieces)


def compact_workspace(path: str, count: int, latest_title: str, latest_updated: Any = "") -> str:
    pieces = [path, f"threads: {count}"]
    if latest_title:
        pieces.append(f"latest: {truncate(latest_title, 160)}")
    if latest_updated:
        pieces.append(f"updated: {latest_updated}")
    return "\n".join(pieces)


def rate_limits_summary(result: dict[str, Any]) -> str:
    buckets = result.get("rateLimitsByLimitId") or {}
    if not buckets:
        buckets = {"default": result.get("rateLimits") or {}}
    lines = ["Codex limits:"]
    for bucket_id, snapshot in buckets.items():
        if not isinstance(snapshot, dict):
            continue
        name = snapshot.get("limitName") or snapshot.get("limitId") or bucket_id
        plan = snapshot.get("planType") or "unknown"
        lines.append("")
        lines.append(f"{name}  plan: {plan}")
        reached = snapshot.get("rateLimitReachedType")
        if reached:
            lines.append(f"status: {reached}")
        credits = snapshot.get("credits")
        if isinstance(credits, dict):
            if credits.get("unlimited"):
                lines.append("credits: unlimited")
            elif credits.get("balance") is not None:
                lines.append(f"credits: {credits.get('balance')}")
            else:
                lines.append(f"credits available: {credits.get('hasCredits')}")
        for label in ("primary", "secondary"):
            window = snapshot.get(label)
            if isinstance(window, dict):
                lines.append(_rate_window_line(label, window))
    return "\n".join(lines)


def _rate_window_line(name: str, window: dict[str, Any]) -> str:
    duration = window.get("windowDurationMins")
    label = _window_label(duration)
    used = window.get("usedPercent")
    resets_at = window.get("resetsAt")
    line = f"{name} ({label}): {used}% used"
    if resets_at:
        line += f", resets {datetime.fromtimestamp(int(resets_at)).strftime('%Y-%m-%d %H:%M')}"
    return line


def _window_label(duration_mins: Any) -> str:
    try:
        mins = int(duration_mins)
    except (TypeError, ValueError):
        return "window"
    if mins == 60:
        return "hourly"
    if mins == 1440:
        return "daily"
    if mins == 10080:
        return "weekly"
    if mins % 1440 == 0:
        days = mins // 1440
        return f"{days}d"
    if mins % 60 == 0:
        hours = mins // 60
        return f"{hours}h"
    return f"{mins}m"


def thread_transcript(thread: dict[str, Any], max_turns: int | None = None, total_limit: int = 24000) -> str:
    title = thread.get("title") or thread.get("name") or thread.get("threadName") or "(untitled)"
    tid = thread.get("id") or thread.get("threadId") or "?"
    cwd = thread.get("cwd") or ""
    turns = thread.get("turns") or []
    if max_turns is not None and max_turns >= 0:
        turns = turns[-max_turns:]

    lines = [f"Thread: {title}", f"ID: {tid}"]
    if cwd:
        lines.append(f"CWD: {cwd}")
    lines.append(f"Turns shown: {len(turns)}")

    for idx, turn in enumerate(turns, 1):
        status = turn.get("status") or "unknown"
        started = turn.get("startedAt") or ""
        lines.append("")
        lines.append(f"Turn {idx}: {status}" + (f"  started: {started}" if started else ""))
        for item in turn.get("items") or []:
            rendered = _render_thread_item(item)
            if rendered:
                lines.append(rendered)

    text = "\n".join(lines)
    return text if len(text) <= total_limit else text[: total_limit - 38] + "\n\n[truncated: thread too large for chat]"


def _render_thread_item(item: dict[str, Any]) -> str:
    kind = item.get("type") or "item"
    if kind == "userMessage":
        return "User: " + truncate(_user_input_text(item.get("content") or []), 1800)
    if kind == "agentMessage":
        return "Codex: " + truncate(item.get("text") or "", 3000)
    if kind == "plan":
        return "Plan: " + truncate(item.get("text") or "", 1200)
    if kind == "reasoning":
        summary = item.get("summary") or []
        if summary:
            return "Reasoning summary: " + truncate(" ".join(map(str, summary)), 1200)
        return ""
    if kind == "commandExecution":
        status = item.get("status") or "unknown"
        command = truncate(item.get("command") or "", 1200)
        output = truncate(item.get("aggregatedOutput") or "", 1200)
        exit_code = item.get("exitCode")
        line = f"Command ({status}"
        if exit_code is not None:
            line += f", exit {exit_code}"
        line += f"):\n{command}"
        if output:
            line += f"\nOutput:\n{output}"
        return line
    if kind == "fileChange":
        changes = item.get("changes") or []
        paths = ", ".join(str(change.get("path") or "?") for change in changes)
        return f"File changes ({item.get('status') or 'unknown'}): {truncate(paths, 1200)}"
    if kind == "mcpToolCall":
        server = item.get("server") or "mcp"
        tool = item.get("tool") or "tool"
        status = item.get("status") or "unknown"
        return f"MCP tool ({status}): {server}.{tool}"
    if kind == "dynamicToolCall":
        ns = item.get("namespace")
        tool = item.get("tool") or "tool"
        status = item.get("status") or "unknown"
        name = f"{ns}.{tool}" if ns else tool
        return f"Tool ({status}): {name}"
    if kind == "collabAgentToolCall":
        tool = item.get("tool") or "agent"
        status = item.get("status") or "unknown"
        receivers = ", ".join(item.get("receiverThreadIds") or [])
        return f"Agent tool ({status}): {tool}" + (f" -> {receivers}" if receivers else "")
    if kind == "webSearch":
        return "Web search: " + truncate(item.get("query") or "", 1000)
    if kind == "imageView":
        return "Image viewed: " + str(item.get("path") or item.get("url") or "")
    if kind == "imageGeneration":
        return "Image generated: " + truncate(str(item.get("prompt") or item), 1000)
    if kind in {"enteredReviewMode", "exitedReviewMode", "contextCompaction"}:
        return kind
    return f"{kind}: " + truncate(str(item), 1000)


def _user_input_text(content: list[Any]) -> str:
    parts: list[str] = []
    for entry in content:
        if not isinstance(entry, dict):
            parts.append(str(entry))
            continue
        etype = entry.get("type")
        if etype == "text":
            parts.append(str(entry.get("text") or ""))
        elif etype in {"image", "local_image"}:
            parts.append(f"[{etype}: {entry.get('url') or entry.get('path') or ''}]")
        elif etype == "skill":
            parts.append(f"[skill: {entry.get('name') or entry.get('path') or ''}]")
        elif etype == "mention":
            parts.append(f"[mention: {entry.get('name') or entry.get('path') or ''}]")
        else:
            parts.append(str(entry))
    return "\n".join(part for part in parts if part)


def user_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text, "text_elements": []}]


def approval_summary(approval_id: str, method: str, params: dict[str, Any], thread_title: str) -> str:
    kind = method.rsplit("/", 1)[-1]
    lines = [
        f"Codex approval {approval_id}",
        f"Thread: {thread_title or params.get('threadId') or 'unknown'}",
    ]
    cwd = params.get("cwd")
    if cwd:
        lines.append(f"CWD: {cwd}")
    reason = params.get("reason")
    if reason:
        lines.append(f"Reason: {truncate(reason, 500)}")

    command = params.get("command")
    if command:
        lines.append("Command:")
        lines.append(code_block(command, 1200))
    elif method.endswith("fileChange/requestApproval"):
        lines.append("File change approval requested.")
        if params.get("reason"):
            lines.append(code_block(params.get("reason"), 1200))
    elif method.endswith("permissions/requestApproval"):
        perms = params.get("permissions")
        lines.append("Permissions requested:")
        lines.append(code_block(str(perms), 1200))
    elif method.endswith("tool/requestUserInput"):
        questions = params.get("questions") or params.get("input") or params
        lines.append("User input requested:")
        lines.append(code_block(str(questions), 1200))
    elif method.endswith("elicitation/request"):
        lines.append("MCP elicitation requested:")
        lines.append(code_block(str(params), 1200))
    else:
        lines.append(f"Request type: {kind}")
        lines.append(code_block(str(params), 1200))

    if params.get("proposedExecpolicyAmendment"):
        lines.append("Proposed exec policy:")
        lines.append(code_block("\n".join(params["proposedExecpolicyAmendment"]), 800))
    if params.get("proposedNetworkPolicyAmendments"):
        lines.append("Proposed network policy:")
        lines.append(code_block(str(params["proposedNetworkPolicyAmendments"]), 800))

    lines.append("Reply:")
    lines.append(f"/codex approve {approval_id}")
    lines.append(f"/codex session {approval_id}")
    lines.append(f"/codex always {approval_id}")
    lines.append(f"/codex deny {approval_id} [alternate instructions]")
    lines.append(f"/codex cancel {approval_id}")
    return "\n".join(lines)
