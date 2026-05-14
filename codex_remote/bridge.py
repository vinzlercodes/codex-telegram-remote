from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from .codex_rpc import CodexAppClient, CodexRpcError
from .formatting import (
    approval_summary,
    code_block,
    compact_thread,
    compact_workspace,
    rate_limits_summary,
    thread_transcript,
    truncate,
    user_text,
)
from .state import StateStore


WORKSPACE = Path(__file__).resolve().parents[1]
STATE_DIR = WORKSPACE / ".state"
STATE_FILE = STATE_DIR / "codex_remote_state.json"
DEFAULT_SOCKET = STATE_DIR / "codex-app-server.sock"


class CodexRemoteBridge:
    def __init__(self) -> None:
        socket_override = os.getenv("CODEX_REMOTE_APP_SERVER_SOCKET", "").strip()
        self.socket_path = Path(socket_override) if socket_override else DEFAULT_SOCKET
        self.store = StateStore(STATE_FILE)
        self._lock = threading.RLock()
        self._assistant_buffers: dict[str, str] = {}
        self._client = CodexAppClient(
            self.socket_path,
            server_request_handler=self._handle_server_request,
            notification_handler=self._handle_notification,
        )
        self.store.update(lambda data: data.update({"socket_path": str(self.socket_path)}))

    def handle_command(self, raw_args: str) -> str:
        args = (raw_args or "").strip()
        if not args:
            return self._usage()
        subcmd, rest = self._split_word(args)
        subcmd = subcmd.lower()
        try:
            if subcmd == "list":
                return self._cmd_list(rest)
            if subcmd in {"thread", "show", "chat"}:
                return self._cmd_thread(rest)
            if subcmd in {"workspaces", "workspace-list"}:
                return self._cmd_workspaces()
            if subcmd in {"limits", "usage", "quota"}:
                return self._cmd_limits()
            if subcmd == "new":
                return self._cmd_new(rest)
            if subcmd == "resume":
                return self._cmd_resume(rest)
            if subcmd == "steer":
                return self._cmd_steer(rest)
            if subcmd == "status":
                return self._cmd_status()
            if subcmd in {"approve", "session", "always", "deny", "cancel"}:
                return self._cmd_approval(subcmd, rest)
            if subcmd == "stop-server":
                self._client.stop()
                return "Codex app-server stop requested."
            return self._usage()
        except CodexRpcError as exc:
            return f"Codex app-server error:\n{truncate(str(exc), 1800)}"
        except Exception as exc:
            return f"codex_remote error: {truncate(str(exc), 1800)}"

    def _cmd_list(self, query: str) -> str:
        result = self._client.request(
            "thread/list",
            {
                "archived": False,
                "limit": 10,
                "searchTerm": query.strip() or None,
                "sortDirection": "desc",
                "sortKey": "updated_at",
                "sourceKinds": [],
            },
            timeout=30,
        )
        threads = (result or {}).get("data") or []
        if not threads:
            return "No Codex threads found."
        lines = ["Codex threads:"]
        for thread in threads[:10]:
            lines.append("")
            lines.append(compact_thread(thread))
        return "\n".join(lines)

    def _cmd_thread(self, rest: str) -> str:
        selector, max_turns = self._parse_thread_selector(rest)
        if not selector:
            return "Usage: /codex thread <thread-id-or-title> [all|N]"
        thread_id = self._resolve_thread_id(selector)
        result = self._client.request(
            "thread/read",
            {"threadId": thread_id, "includeTurns": True},
            timeout=30,
        )
        thread = (result or {}).get("thread") or {}
        return thread_transcript(thread, max_turns=max_turns)

    def _cmd_workspaces(self) -> str:
        threads = self._list_threads(limit=250, include_archived=True)
        workspaces: dict[str, dict[str, Any]] = {}
        for thread in threads:
            cwd = str(thread.get("cwd") or thread.get("workingDirectory") or "").strip()
            if not cwd:
                continue
            updated = self._numeric_timestamp(thread.get("updatedAt") or thread.get("updated_at") or thread.get("updatedAtMs") or 0)
            title = thread.get("title") or thread.get("name") or thread.get("threadName") or thread.get("preview") or ""
            entry = workspaces.setdefault(cwd, {"count": 0, "latest_updated": 0, "latest_title": ""})
            entry["count"] += 1
            if updated and updated >= entry.get("latest_updated", 0):
                entry["latest_updated"] = updated
                entry["latest_title"] = title
        if not workspaces:
            return "No Codex workspaces found."
        sorted_items = sorted(
            workspaces.items(),
            key=lambda kv: kv[1].get("latest_updated") or 0,
            reverse=True,
        )
        lines = [f"Codex workspaces: {len(sorted_items)}"]
        for cwd, meta in sorted_items:
            lines.append("")
            lines.append(compact_workspace(cwd, meta["count"], meta.get("latest_title") or "", meta.get("latest_updated") or ""))
        return truncate("\n".join(lines), 24000)

    def _cmd_limits(self) -> str:
        result = self._client.request_null("account/rateLimits/read", timeout=30)
        return rate_limits_summary(result or {})

    def _cmd_new(self, rest: str) -> str:
        cwd, prompt = self._parse_cwd_prompt(rest)
        if not cwd or not prompt:
            return "Usage: /codex new <absolute-cwd> :: <prompt>"
        thread_result = self._client.request(
            "thread/start",
            {
                "cwd": cwd,
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "threadSource": "user",
                "ephemeral": False,
            },
            timeout=30,
        )
        thread = thread_result.get("thread") if isinstance(thread_result, dict) else None
        thread_id = self._thread_id(thread_result)
        if not thread_id:
            return f"Codex started thread but returned no id:\n{code_block(str(thread_result), 1200)}"
        return self._start_turn(thread_id, prompt, cwd=cwd, thread=thread)

    def _cmd_resume(self, rest: str) -> str:
        selector, prompt = self._parse_selector_prompt(rest)
        if not selector or not prompt:
            return "Usage: /codex resume <thread-id-or-title> :: <prompt>"
        thread_id = self._resolve_thread_id(selector)
        resume = self._client.request(
            "thread/resume",
            {
                "threadId": thread_id,
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
            },
            timeout=30,
        )
        thread = resume.get("thread") if isinstance(resume, dict) else None
        return self._start_turn(thread_id, prompt, thread=thread)

    def _cmd_steer(self, text: str) -> str:
        if not text.strip():
            return "Usage: /codex steer <text>"
        active = self._active_session()
        if not active.get("thread_id") or not active.get("turn_id"):
            return "No active Codex turn for this Telegram session."
        self._client.request(
            "turn/steer",
            {
                "threadId": active["thread_id"],
                "expectedTurnId": active["turn_id"],
                "input": user_text(text.strip()),
            },
            timeout=15,
        )
        return "Steer sent."

    def _cmd_status(self) -> str:
        data = self.store.load()
        active = self._active_session(data)
        pending = data.get("pending_approvals", {})
        lines = [
            f"Socket: {data.get('socket_path') or self.socket_path}",
            f"Active thread: {active.get('thread_id') or '(none)'}",
            f"Active turn: {active.get('turn_id') or '(none)'}",
            f"Pending approvals: {len(pending)}",
        ]
        if pending:
            lines.extend(sorted(pending.keys()))
        if data.get("last_task_summary"):
            lines.append("")
            lines.append(truncate(data["last_task_summary"], 1200))
        return "\n".join(lines)

    def _cmd_approval(self, action: str, rest: str) -> str:
        approval_id, tail = self._split_word(rest.strip())
        if not approval_id:
            return f"Usage: /codex {action} <approval-id>"
        data = self.store.load()
        pending = data.get("pending_approvals", {}).get(approval_id)
        if not pending:
            return f"No pending Codex approval: {approval_id}"
        method = pending["method"]
        params = pending.get("params") or {}
        if action == "approve":
            result = self._approval_response(method, "accept", params)
        elif action == "session":
            result = self._approval_response(method, "acceptForSession", params)
        elif action == "always":
            result = self._always_response(method, params)
        elif action == "cancel":
            result = self._approval_response(method, "cancel", params)
        else:
            result = self._approval_response(method, "decline", params)
        self._client.respond(pending["request_id"], result)
        self.store.update(lambda d: d.get("pending_approvals", {}).pop(approval_id, None))
        if action == "deny" and tail.strip():
            self._steer_after_deny(pending, tail.strip())
            return f"{approval_id} denied. Alternate instructions sent."
        if action == "cancel":
            self._interrupt_pending(pending)
            return f"{approval_id} cancelled."
        return f"{approval_id} -> {action}"

    def _start_turn(self, thread_id: str, prompt: str, cwd: str | None = None, thread: dict[str, Any] | None = None) -> str:
        result = self._client.request(
            "turn/start",
            {
                "threadId": thread_id,
                "cwd": cwd,
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "input": user_text(prompt),
            },
            timeout=30,
        )
        turn_id = self._turn_id(result)
        session_key = self._session_key()
        target = self._telegram_target()
        title = self._thread_title(thread, thread_id)
        def save(data):
            data["active_sessions"][session_key] = {
                "thread_id": thread_id,
                "turn_id": turn_id,
                "telegram_target": target,
                "thread_title": title,
            }
            data["last_task_summary"] = f"{title}: {truncate(prompt, 200)}"
        self.store.update(save)
        return f"Codex turn started.\nThread: {title}\nID: {thread_id}\nTurn: {turn_id or '(pending notification)'}"

    def _handle_server_request(self, request_id: str, method: str, params: dict[str, Any]) -> None:
        if method not in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
            "item/tool/requestUserInput",
            "mcpServer/elicitation/request",
        }:
            self._client.respond(request_id, {"decision": "decline"})
            return
        approval_id = self._next_approval_id()
        thread_id = params.get("threadId") or ""
        active = self._active_by_thread(thread_id)
        target = active.get("telegram_target") or self._telegram_target(fallback_home=True)
        title = active.get("thread_title") or thread_id
        def save(data):
            data["pending_approvals"][approval_id] = {
                "request_id": request_id,
                "method": method,
                "params": params,
                "thread_id": thread_id,
                "turn_id": params.get("turnId"),
                "telegram_target": target,
            }
        self.store.update(save)
        self._send_telegram(target, approval_summary(approval_id, method, params, title))

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "turn/started":
            thread_id = params.get("threadId") or ""
            turn = params.get("turn") or {}
            turn_id = turn.get("id")
            if thread_id and turn_id:
                self._update_active_turn(thread_id, turn_id)
            return
        if method == "agent/message/delta":
            turn_id = params.get("turnId") or ""
            if turn_id:
                self._assistant_buffers[turn_id] = self._assistant_buffers.get(turn_id, "") + params.get("delta", "")
            return
        if method == "turn/completed":
            thread_id = params.get("threadId") or ""
            turn = params.get("turn") or {}
            turn_id = turn.get("id") or ""
            active = self._active_by_thread(thread_id)
            target = active.get("telegram_target")
            body = self._assistant_buffers.pop(turn_id, "")
            status = turn.get("status") or "completed"
            if target:
                msg = f"Codex turn {status}.\nThread: {active.get('thread_title') or thread_id}"
                if body.strip():
                    msg += "\n\n" + truncate(body.strip(), 3000)
                self._send_telegram(target, msg)

    def _approval_response(self, method: str, decision: str, params: dict[str, Any]) -> dict[str, Any]:
        if method.endswith("commandExecution/requestApproval"):
            return {"decision": decision}
        if method.endswith("fileChange/requestApproval"):
            return {"decision": decision}
        if method.endswith("permissions/requestApproval"):
            if decision in {"accept", "acceptForSession"}:
                return {
                    "permissions": params.get("permissions") or {},
                    "scope": "session" if decision == "acceptForSession" else "turn",
                }
            return {"permissions": {}, "scope": "turn"}
        if method.endswith("tool/requestUserInput"):
            return {"answers": {}}
        if method.endswith("elicitation/request"):
            if decision == "cancel":
                return {"action": "cancel"}
            if decision == "decline":
                return {"action": "decline"}
            return {"action": "accept", "content": {}}
        return {"decision": decision}

    def _always_response(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        amendments = params.get("proposedExecpolicyAmendment")
        if method.endswith("commandExecution/requestApproval") and amendments:
            return {"decision": {"acceptWithExecpolicyAmendment": {"execpolicy_amendment": amendments}}}
        network = params.get("proposedNetworkPolicyAmendments") or []
        if method.endswith("commandExecution/requestApproval") and network:
            return {"decision": {"applyNetworkPolicyAmendment": {"network_policy_amendment": network[0]}}}
        return self._approval_response(method, "acceptForSession", params)

    def _steer_after_deny(self, pending: dict[str, Any], text: str) -> None:
        thread_id = pending.get("thread_id")
        turn_id = pending.get("turn_id")
        if not thread_id or not turn_id:
            return
        self._client.request(
            "turn/steer",
            {"threadId": thread_id, "expectedTurnId": turn_id, "input": user_text(text)},
            timeout=15,
        )

    def _interrupt_pending(self, pending: dict[str, Any]) -> None:
        thread_id = pending.get("thread_id")
        turn_id = pending.get("turn_id")
        if thread_id and turn_id:
            self._client.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=15)

    def _send_telegram(self, target: str, message: str) -> None:
        try:
            from tools.send_message_tool import send_message_tool
            send_message_tool({"target": target, "message": message})
        except Exception:
            pass

    def _resolve_thread_id(self, selector: str) -> str:
        if self._looks_uuid(selector):
            return selector
        result = self._client.request(
            "thread/list",
            {"archived": False, "limit": 20, "searchTerm": selector, "sourceKinds": []},
            timeout=30,
        )
        threads = (result or {}).get("data") or []
        if not threads:
            raise CodexRpcError(f"No Codex thread matches: {selector}")
        for thread in threads:
            title = thread.get("title") or thread.get("threadName") or ""
            if selector.lower() in title.lower():
                return self._thread_id(thread) or ""
        return self._thread_id(threads[0]) or ""

    def _list_threads(self, limit: int = 100, include_archived: bool = False) -> list[dict[str, Any]]:
        all_threads: list[dict[str, Any]] = []
        archived_options = [False, True] if include_archived else [False]
        for archived in archived_options:
            cursor = None
            while len(all_threads) < limit:
                params = {
                    "archived": archived,
                    "limit": min(100, limit - len(all_threads)),
                    "sortDirection": "desc",
                    "sortKey": "updated_at",
                    "sourceKinds": [],
                }
                if cursor:
                    params["cursor"] = cursor
                result = self._client.request("thread/list", params, timeout=30)
                data = (result or {}).get("data") or []
                all_threads.extend(data)
                cursor = (result or {}).get("nextCursor")
                if not cursor or not data:
                    break
        return all_threads

    def _active_session(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = data or self.store.load()
        return data.get("active_sessions", {}).get(self._session_key(), {})

    def _active_by_thread(self, thread_id: str) -> dict[str, Any]:
        data = self.store.load()
        for active in data.get("active_sessions", {}).values():
            if active.get("thread_id") == thread_id:
                return active
        return {}

    def _update_active_turn(self, thread_id: str, turn_id: str) -> None:
        def update(data):
            for active in data.get("active_sessions", {}).values():
                if active.get("thread_id") == thread_id:
                    active["turn_id"] = turn_id
        self.store.update(update)

    def _next_approval_id(self) -> str:
        def update(data):
            n = int(data.get("approval_counter", 0)) + 1
            data["approval_counter"] = n
            return f"A{n}"
        return self.store.update(update)

    def _telegram_target(self, fallback_home: bool = False) -> str:
        try:
            from gateway.session_context import get_session_env
            platform = get_session_env("HERMES_SESSION_PLATFORM", "")
            chat_id = get_session_env("HERMES_SESSION_CHAT_ID", "")
            thread_id = get_session_env("HERMES_SESSION_THREAD_ID", "")
            if platform == "telegram" and chat_id:
                return f"telegram:{chat_id}:{thread_id}" if thread_id else f"telegram:{chat_id}"
        except Exception:
            pass
        return "telegram" if fallback_home else "telegram"

    def _session_key(self) -> str:
        try:
            from gateway.session_context import get_session_env
            key = get_session_env("HERMES_SESSION_KEY", "")
            if key:
                return key
            platform = get_session_env("HERMES_SESSION_PLATFORM", "")
            chat_id = get_session_env("HERMES_SESSION_CHAT_ID", "")
            thread_id = get_session_env("HERMES_SESSION_THREAD_ID", "")
            if platform and chat_id:
                return f"{platform}:{chat_id}:{thread_id}"
        except Exception:
            pass
        return "telegram:home"

    @staticmethod
    def _split_word(text: str) -> tuple[str, str]:
        parts = text.strip().split(maxsplit=1)
        if not parts:
            return "", ""
        return parts[0], parts[1] if len(parts) > 1 else ""

    @staticmethod
    def _parse_cwd_prompt(text: str) -> tuple[str, str]:
        if "::" not in text:
            return "", ""
        cwd, prompt = text.split("::", 1)
        return cwd.strip(), prompt.strip()

    @staticmethod
    def _parse_selector_prompt(text: str) -> tuple[str, str]:
        if "::" not in text:
            return "", ""
        selector, prompt = text.split("::", 1)
        return selector.strip(), prompt.strip()

    @staticmethod
    def _parse_thread_selector(text: str) -> tuple[str, int | None]:
        text = text.strip()
        if not text:
            return "", None
        selector, maybe_count = CodexRemoteBridge._split_last_word(text)
        if maybe_count.lower() == "all":
            return selector.strip(), None
        if maybe_count.isdigit():
            return selector.strip(), int(maybe_count)
        return text, None

    @staticmethod
    def _split_last_word(text: str) -> tuple[str, str]:
        parts = text.rsplit(maxsplit=1)
        if len(parts) == 1:
            return text, ""
        return parts[0], parts[1]

    @staticmethod
    def _thread_id(result: Any) -> str:
        if not isinstance(result, dict):
            return ""
        thread = result.get("thread") if "thread" in result else result
        if isinstance(thread, dict):
            return str(thread.get("id") or thread.get("threadId") or "")
        return str(result.get("threadId") or result.get("id") or "")

    @staticmethod
    def _turn_id(result: Any) -> str:
        if not isinstance(result, dict):
            return ""
        turn = result.get("turn") if "turn" in result else result
        if isinstance(turn, dict):
            return str(turn.get("id") or turn.get("turnId") or "")
        return str(result.get("turnId") or result.get("id") or "")

    @staticmethod
    def _thread_title(thread: dict[str, Any] | None, thread_id: str) -> str:
        if not thread:
            return thread_id
        return str(thread.get("title") or thread.get("threadName") or thread.get("name") or thread_id)

    @staticmethod
    def _looks_uuid(text: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-fA-F-]{20,}", text.strip()))

    @staticmethod
    def _numeric_timestamp(value: Any) -> int | float:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _usage() -> str:
        return (
            "Usage:\n"
            "/codex list [query]\n"
            "/codex thread <thread-id-or-title> [all|N]\n"
            "/codex workspaces\n"
            "/codex limits\n"
            "/codex new <absolute-cwd> :: <prompt>\n"
            "/codex resume <thread-id-or-title> :: <prompt>\n"
            "/codex steer <text>\n"
            "/codex status\n"
            "/codex approve|session|always|deny|cancel <approval-id>"
        )


_BRIDGE: CodexRemoteBridge | None = None


def get_bridge() -> CodexRemoteBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = CodexRemoteBridge()
    return _BRIDGE
