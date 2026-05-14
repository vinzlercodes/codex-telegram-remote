# Security Policy

## Supported Versions

Security fixes target the latest released version.

## Reporting a Vulnerability

Please report security issues privately by opening a GitHub security advisory or contacting the maintainer listed on the GitHub repository.

Do not open a public issue for vulnerabilities involving approval bypass, unintended command execution, Telegram routing, leaked local paths, or leaked chat/session data.

## Security Model

This plugin treats Telegram access as privileged. Anyone who can send commands to the configured Hermes Telegram bot may be able to ask Codex to inspect files, run commands, or approve actions depending on your Hermes and Codex configuration.

Use `/codex always` only when you understand the requested policy change. Prefer `/codex approve` or `/codex session` for normal use.

