# Antigrafity Manager

A standalone tool suite for managing, rotating, and monitoring Google Antigravity (Gemini Code Assist / Google Cloud Code Assist) accounts. No external dependencies — Python stdlib only.

![GitHub](https://img.shields.io/badge/python-3.11%2B-blue)
![GitHub](https://img.shields.io/badge/license-MIT-green)

## Features

- **CLI** — Add new accounts via Google OAuth flow, auto-complete from browser callback
- **Token Rotator** — Auto-switch accounts when rate-limited (429) or on errors; retry commands with the next healthy account
- **Web Dashboard** — Modern SPA with command palette (⌘K), real-time quota tracking, session-limit meters, account switching

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/ashkhfi/antigrafity-manager/main/install.sh | bash
```

Options:
```bash
# Skip antigravity-cli binary download
curl -fsSL ... | bash -s -- --no-antigravity

# Custom install prefix
curl -fsSL ... | bash -s -- --prefix ~/tools
```

## Tools

| Command | Description | Requires |
|---|---|---|
| `ag` | CLI — add new accounts via Google OAuth | Python 3.11+ |
| `agy` | Token rotator — auto-rotates on 429/errors | `agy.orig` (antigravity-cli binary) |
| `agm-web` | Web dashboard launcher | Python 3.11+ |
| `agm-self-update` | Re-run the installer to update | — |

## Usage

### Web Dashboard
```bash
agm-web
# → http://localhost:8877
```

### Add Account
```bash
ag
```
Opens Google OAuth URL → authorize → paste redirect URL back → account saved.

### Token Rotation
```bash
agy --status            # Show current active account
agy --list              # List all accounts
agy --switch <email>    # Switch active account (no restart needed)
agy <command> [args]    # Run command with auto-rotation on 429/errors
```

## Data

All data stored at `~/.agm/`:

- `accounts.json` — Account registry with OAuth tokens (JSON v3)
- `usage.db` — Daily quota/usage history (auto-populated by web dashboard)
- `settings.json` — Rotation strategy and preferences

## Requirements

- Python 3.11+
- Linux (macOS untested)
- One Google Cloud Code Assist / Google One AI Pro subscription per account
- `agy.orig` binary (required for `agy` token rotation) — auto-downloaded by installer, or install manually from [antigravity-cli releases](https://github.com/ashkhfi/antigrafity-manager/releases) and place at `~/.local/bin/agy.orig`

> **Note:** `agy` without `agy.orig` will print an installation reminder and exit. The other tools (`ag`, `agm-web`) work without it.

## Architecture

```
~/.local/bin/
├── ag                   — CLI add-account (304 LOC)
├── agy                  — Token rotator wrapper (213 LOC)
├── agm-web              — Web launcher (<30 lines)
├── agm_backend.py       — HTTP server (955 LOC, ThreadingHTTPServer)
└── agm-dashboard.html   — SPA frontend (NEXUS design, ~500 LOC)

~/.agm/
├── accounts.json        — Account database
├── usage.db             — Quota/usage tracking
└── settings.json        — User preferences
```

## Build from Source

```bash
git clone https://github.com/ashkhfi/antigrafity-manager.git
cd antigrafity-manager
./install.sh
```

## License

MIT
