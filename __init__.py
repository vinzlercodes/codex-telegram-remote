from __future__ import annotations

try:
    from .codex_remote.bridge import get_bridge
except ImportError:
    from codex_remote.bridge import get_bridge


def _handle_codex(raw_args: str) -> str:
    return get_bridge().handle_command(raw_args)


def register(ctx) -> None:
    ctx.register_command(
        name="codex",
        handler=_handle_codex,
        description="Control Codex app threads remotely",
        args_hint="<list|new|resume|steer|status|approve|session|always|deny|cancel>",
    )
