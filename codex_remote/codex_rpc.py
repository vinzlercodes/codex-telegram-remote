from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable


class CodexRpcError(RuntimeError):
    pass


WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class CodexAppClient:
    def __init__(
        self,
        socket_path: Path,
        server_request_handler: Callable[[str, str, dict[str, Any]], None],
        notification_handler: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self.socket_path = socket_path
        self.server_request_handler = server_request_handler
        self.notification_handler = notification_handler
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._proc: subprocess.Popen | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._ready = threading.Event()
        self._start_lock = threading.Lock()
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    def ensure_started(self, timeout: float = 20.0) -> None:
        with self._start_lock:
            if self._thread and self._thread.is_alive() and self._ready.is_set():
                return
            self._ready.clear()
            self._thread = threading.Thread(target=self._thread_main, name="codex-app-rpc", daemon=True)
            self._thread.start()
        if not self._ready.wait(timeout):
            raise CodexRpcError(self._last_error or "Codex app-server connection timed out")

    def stop(self) -> None:
        if self._loop and not self._loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._close(), self._loop).result(5)
            except Exception:
                pass
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def request(self, method: str, params: dict[str, Any] | None = None, timeout: float = 60.0) -> Any:
        self.ensure_started()
        if not self._loop:
            raise CodexRpcError("Codex app-server loop not running")
        fut = asyncio.run_coroutine_threadsafe(self._request(method, params or {}, timeout), self._loop)
        return fut.result(timeout + 5)

    def request_null(self, method: str, timeout: float = 60.0) -> Any:
        self.ensure_started()
        if not self._loop:
            raise CodexRpcError("Codex app-server loop not running")
        fut = asyncio.run_coroutine_threadsafe(self._request(method, None, timeout), self._loop)
        return fut.result(timeout + 5)

    def respond(self, request_id: str, result: dict[str, Any]) -> None:
        self.ensure_started()
        if not self._loop:
            raise CodexRpcError("Codex app-server loop not running")
        asyncio.run_coroutine_threadsafe(self._send_response(request_id, result), self._loop).result(10)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._connect_and_read())
        finally:
            loop.close()

    async def _connect_and_read(self) -> None:
        try:
            await self._ensure_process()
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(str(self.socket_path)),
                    timeout=10,
                )
            except OSError:
                if self._proc is None:
                    try:
                        self.socket_path.unlink()
                    except FileNotFoundError:
                        pass
                    await self._ensure_process()
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_unix_connection(str(self.socket_path)),
                        timeout=10,
                    )
                else:
                    raise
            await self._websocket_handshake()
            read_task = asyncio.create_task(self._read_loop())
            await self._send_initialize()
            self._ready.set()
            await read_task
        except Exception as exc:
            self._last_error = str(exc)
            self._ready.set()
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(CodexRpcError(str(exc)))

    async def _ensure_process(self) -> None:
        if self.socket_path.exists():
            return
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        cmd = ["codex", "app-server", "--listen", f"unix://{self.socket_path}"]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.socket_path.exists():
                return
            if self._proc.poll() is not None:
                err = (self._proc.stderr.read() if self._proc.stderr else "").strip()
                raise CodexRpcError(err or f"codex app-server exited with {self._proc.returncode}")
            await asyncio.sleep(0.1)
        raise CodexRpcError("Timed out waiting for Codex app-server socket")

    async def _send_initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "clientInfo": {"name": "hermes-codex-remote", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            },
            timeout=15,
        )
        await self._write({"method": "initialized", "params": {}})

    async def _request(self, method: str, params: Any, timeout: float) -> Any:
        if not self._writer:
            raise CodexRpcError("Codex app-server writer not connected")
        req_id = self._next_id
        self._next_id += 1
        fut = self._loop.create_future()  # type: ignore[union-attr]
        self._pending[req_id] = fut
        await self._write({"id": req_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(req_id, None)

    async def _send_response(self, request_id: str, result: dict[str, Any]) -> None:
        await self._write({"id": request_id, "result": result})

    async def _write(self, msg: dict[str, Any]) -> None:
        if not self._writer:
            raise CodexRpcError("Codex app-server writer not connected")
        await self._send_ws_frame(0x1, json.dumps(msg, separators=(",", ":")).encode("utf-8"))

    async def _read_loop(self) -> None:
        while True:
            text = await self._read_ws_message()
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                fut = self._pending.get(msg["id"])
                if fut and not fut.done():
                    if "error" in msg:
                        fut.set_exception(CodexRpcError(str(msg["error"])))
                    else:
                        fut.set_result(msg.get("result"))
                continue
            method = msg.get("method")
            params = msg.get("params") or {}
            if "id" in msg and method:
                self.server_request_handler(str(msg["id"]), method, params)
            elif method:
                self.notification_handler(method, params)

    async def _close(self) -> None:
        if self._writer:
            try:
                await self._send_ws_frame(0x8, b"")
            except Exception:
                pass
            self._writer.close()
            await self._writer.wait_closed()

    async def _websocket_handshake(self) -> None:
        if not self._reader or not self._writer:
            raise CodexRpcError("Codex app-server socket not connected")
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET / HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self._writer.write(request.encode("ascii"))
        await self._writer.drain()
        response = await asyncio.wait_for(self._reader.readuntil(b"\r\n\r\n"), timeout=10)
        head = response.decode("iso-8859-1")
        if " 101 " not in head.split("\r\n", 1)[0]:
            raise CodexRpcError(f"Codex app-server websocket upgrade failed: {head.splitlines()[0]}")
        expected = base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")
        if f"sec-websocket-accept: {expected.lower()}" not in head.lower():
            raise CodexRpcError("Codex app-server websocket accept header mismatch")

    async def _send_ws_frame(self, opcode: int, payload: bytes) -> None:
        if not self._writer:
            raise CodexRpcError("Codex app-server writer not connected")
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self._writer.write(bytes(header) + mask + masked)
        await self._writer.drain()

    async def _read_ws_message(self) -> str:
        chunks: list[bytes] = []
        while True:
            fin, opcode, payload = await self._read_ws_frame()
            if opcode == 0x8:
                raise CodexRpcError("Codex app-server websocket closed")
            if opcode == 0x9:
                await self._send_ws_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode in {0x1, 0x2, 0x0}:
                chunks.append(payload)
                if fin:
                    return b"".join(chunks).decode("utf-8")

    async def _read_ws_frame(self) -> tuple[bool, int, bytes]:
        if not self._reader:
            raise CodexRpcError("Codex app-server reader not connected")
        first, second = await self._reader.readexactly(2)
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(await self._reader.readexactly(2), "big")
        elif length == 127:
            length = int.from_bytes(await self._reader.readexactly(8), "big")
        mask = await self._reader.readexactly(4) if masked else b""
        payload = await self._reader.readexactly(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        return fin, opcode, payload
