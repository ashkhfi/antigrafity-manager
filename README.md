<p align="center">
  <img src="https://img.shields.io/badge/version-v1.0.0-8b5cf6?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11%2B-8b5cf6?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-8b5cf6?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/github/stars/ashkhfi/antigrafity-manager?style=for-the-badge&color=8b5cf6" alt="Stars">
  <img src="https://img.shields.io/github/last-commit/ashkhfi/antigrafity-manager?style=for-the-badge&color=8b5cf6&label=updated" alt="Updated">
</p>

# <p align="center">⚡ Antigrafity Manager</p>
<p align="center"><i>Standalone toolkit for managing multiple Google OAuth accounts with auto-rotation, quota tracking, and web dashboard</i></p>

<p align="center">
  <b>Zero external deps</b> &nbsp;·&nbsp; Python stdlib only &nbsp;·&nbsp; No npm/pip install needed
</p>

<br>

---

## 🚀 Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/ashkhfi/antigrafity-manager/v1.0.0/install.sh | bash
```

| Option | Description |
|---|---|
| `--no-antigravity` | Skip antigravity-cli binary download |
| `--prefix ~/tools` | Custom install directory |

> [!TIP]
> Already installed? Run `agm-self-update` or re-run the curl command.

---

## 🧰 Tools

| Command | Description | Requires |
|---|---|---|
| `ag` | Add accounts via Google OAuth flow | Python 3.11+ |
| `agy` | Token rotator — `--list`, `--switch`, auto-rotate | `agy.orig` binary |
| `agm-web` | Web dashboard (port 8877) | Python 3.11+ |
| `agm-self-update` | Re-run installer | — |

### Version info

All tools support `--version` / `-v`:

```bash
ag --version       →  Antigrafity Manager v1.0.0
agy --version      →  Antigrafity Manager v1.0.0
agm-web --version  →  Antigrafity Manager v1.0.0
```

---

## 📖 Usage

### Web Dashboard

```bash
agm-web                    # → http://localhost:8877
agm-web --port 9000        # custom port
agm-web --import-9router   # import from legacy SQLite DB
```

> Dashboard features: ⌘K command palette · real-time quota tracking · session-limit progress bars · per-account health · account switching · CLI reference page

### Add Account

```bash
ag
```

1. Opens Google OAuth URL in browser
2. Sign in → authorize → paste redirect URL back
3. Account saved automatically to `~/.agm/accounts.json`

### Token Rotation

```bash
agy --status            # Show current active account + rotation queue
agy --list              # List all accounts with status
agy --switch <email>    # Switch active account (no restart needed)
agy <command> [args]    # Run with auto-rotate on 429/errors
```

> `agy` wraps antigravity-cli. On 429 or error, it automatically marks the token, picks the next healthy account, and retries. Zero downtime.

### Systemd (auto-start)

```bash
sudo systemctl enable --now agm-web
```

---

## 📁 Data

Everything lives under `~/.agm/`:

```
~/.agm/
├── accounts.json   # Account registry + OAuth tokens (JSON v3)
├── usage.db        # Daily quota/usage history (auto-populated)
└── settings.json   # Rotation strategy & preferences
```

---

## 🏗 Architecture

```
~/.local/bin/
├── ag                   # CLI add-account
├── agy                  # Token rotator wrapper
├── agm-web              # Web launcher script
├── agm_backend.py       # HTTP server (ThreadingHTTPServer)
├── agm-dashboard.html   # SPA frontend (NEXUS design)
└── agy.orig             # antigravity-cli binary
```

> Full Python stdlib — zero pip/npm dependencies. Just the binary for `agy` token rotation.

---

## 📦 Releases

| Version | Date | Notes |
|---|---|---|
| [v1.0.0](https://github.com/ashkhfi/antigrafity-manager/releases/tag/v1.0.0) | 2026-07-10 | Initial release — all tools, dashboard, rotation, systemd |

```bash
# Install specific version
curl -fsSL https://raw.githubusercontent.com/ashkhfi/antigrafity-manager/v1.0.0/install.sh | bash
```

---

## 🛠 From Source

```bash
git clone https://github.com/ashkhfi/antigrafity-manager.git
cd antigrafity-manager
./install.sh
```

---

<p align="center">
  <sub>Built with ❤️ ·  Python stdlib only ·  No bloat</sub>
</p>
