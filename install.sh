#!/usr/bin/env bash
#
# install.sh — curl-pipe-bash one-liner installer for the AGM tool suite
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<USER>/agm/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/<USER>/agm/main/install.sh | bash -s -- --no-antigravity
#
# Options:
#   --no-antigravity   Skip antigravity-cli binary download
#   --prefix <dir>     Install to <dir> instead of ~/.local/bin
#   --version <tag>    Install a specific release tag instead of main
#

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
REPO_OWNER="ashkhfi"
REPO_NAME="antigrafity-manager"
REPO_BRANCH="${AGM_INSTALL_BRANCH:-main}"
BASE_URL="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${REPO_BRANCH}"
PREFIX="${AGM_PREFIX:-${HOME}/.local/bin}"
SKIP_ANTIGRAVITY=false
AGM_DIR="${HOME}/.agm"

# ── Parse flags ─────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-antigravity) SKIP_ANTIGRAVITY=true ;;
    --prefix) PREFIX="$2"; shift ;;
    --version) REPO_BRANCH="$2"; shift ;;
    --help|-h)
      echo "Usage: curl -fsSL ${BASE_URL}/install.sh | bash [-- <options>]"
      echo ""
      echo "Options:"
      echo "  --no-antigravity   Skip antigravity-cli binary download"
      echo "  --prefix <dir>     Install to <dir> (default: ~/.local/bin)"
      echo "  --version <tag>    Install a specific release tag (default: main)"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

# ── Preflight ───────────────────────────────────────────────────────────────
preflight() {
  local os
  os="$(uname -s 2>/dev/null || echo "Linux")"

  echo "◆ AGM Installer — ${os}"
  echo "  Prefix: ${PREFIX}"
  echo "  Source: ${BASE_URL}"
  echo ""

  # Check curl
  if ! command -v curl >/dev/null 2>&1; then
    echo "✗ curl not found. Install curl and retry."
    echo "  Debian/Ubuntu: apt-get install -y curl"
    echo "  RHEL/Fedora:   dnf install -y curl"
    echo "  Alpine:        apk add curl"
    exit 1
  fi

  # Check python3 (required for agm-web and agm_backend.py)
  if ! command -v python3 >/dev/null 2>&1; then
    echo "✗ python3 not found. Install Python 3 and retry."
    exit 1
  fi

  mkdir -p "${PREFIX}"
  mkdir -p "${AGM_DIR}"

  echo "✓ Preflight passed"
  echo ""
}

# ── Download helpers ────────────────────────────────────────────────────────
download() {
  local src="$1"
  local dst="$2"
  local mode="${3:-644}"

  echo "  ↓ ${src} → ${dst}"
  curl -fsSL "${BASE_URL}/${src}" -o "${dst}"
  chmod "${mode}" "${dst}"
}

# ── Install AGM suite ───────────────────────────────────────────────────────
install_agm() {
  echo "◆ Installing AGM tools to ${PREFIX}"

  download "agm"               "${PREFIX}/agm"              755
  download "ag"                "${PREFIX}/ag"               755
  download "agy"               "${PREFIX}/agy"              755
  download "agm-web"           "${PREFIX}/agm-web"          755
  download "agm_backend.py"    "${PREFIX}/agm_backend.py"   755
  download "agm-dashboard.html" "${PREFIX}/agm-dashboard.html" 644

  echo "✓ AGM tools installed"
  echo ""
}

# ── Optional: antigravity-cli ───────────────────────────────────────────────
install_antigravity() {
  if "${SKIP_ANTIGRAVITY}"; then
    echo "◆ Skipping antigravity-cli (--no-antigravity)"
    echo ""
    return
  fi

  echo "◆ Installing antigravity-cli"

  local arch
  arch="$(uname -m)"
  local os
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"

  # Map arch to Go-style names
  case "${arch}" in
    x86_64)  arch="amd64" ;;
    aarch64) arch="arm64" ;;
    armv7l)  arch="arm"   ;;
  esac

  local antigravity_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/latest/download/antigravity-cli_${os}_${arch}.tar.gz"
  local tmpdir
  tmpdir="$(mktemp -d)"

  echo "  ↓ ${antigravity_url}"
  if curl -fsSL "${antigravity_url}" -o "${tmpdir}/antigravity.tar.gz" 2>/dev/null; then
    tar -xzf "${tmpdir}/antigravity.tar.gz" -C "${tmpdir}"
    find "${tmpdir}" -name "antigravity-cli*" -type f -exec cp {} "${PREFIX}/antigravity-cli" \;
    chmod 755 "${PREFIX}/antigravity-cli"
    echo "✓ antigravity-cli installed"
  else
    echo "  (antigravity-cli binary not found for ${os}/${arch}; skipping)"
  fi

  rm -rf "${tmpdir}"
  echo ""
}

# ── Initialize ~/.agm ───────────────────────────────────────────────────────
init_agm_dir() {
  echo "◆ Initializing ${AGM_DIR}"

  mkdir -p "${AGM_DIR}/accounts"
  mkdir -p "${AGM_DIR}/logs"
  mkdir -p "${AGM_DIR}/config"

  # Default config if not present
  if [[ ! -f "${AGM_DIR}/config/config.yaml" ]]; then
    cat > "${AGM_DIR}/config/config.yaml" <<-'EOF'
# AGM configuration
# See https://github.com/<USER>/agm for documentation
accounts_dir: ~/.agm/accounts
log_dir: ~/.agm/logs
log_level: info
EOF
    echo "  Created ${AGM_DIR}/config/config.yaml"
  fi

  echo "✓ ${AGM_DIR} initialized"
  echo ""
}

# ── Post-install message ────────────────────────────────────────────────────
post_install() {
  echo "══════════════════════════════════════════════════"
  echo "  AGM tool suite installed!"
  echo ""
  echo "  Installed to: ${PREFIX}"
  echo "    agm               — TUI (main interface)"
  echo "    ag                — CLI add account"
  echo "    agy               — Token rotator"
  echo "    agm-web           — Web wrapper"
  echo "    agm_backend.py    — Web backend"
  echo "    agm-dashboard.html — Web frontend"
  if [[ -x "${PREFIX}/antigravity-cli" ]]; then
    echo "    antigravity-cli   — Official Google binary"
  fi
  echo ""
  echo "  Make sure ${PREFIX} is in your PATH:"
  echo "    export PATH=\"${PREFIX}:\$PATH\""
  echo "    # Add to ~/.bashrc or ~/.zshrc to persist"
  echo ""
  echo "  Quick start:"
  echo "    agm"
  echo "══════════════════════════════════════════════════"
}

# ── Self-update helper ──────────────────────────────────────────────────────
create_self_update() {
  cat > "${PREFIX}/agm-self-update" <<-SELFUPDATE
#!/usr/bin/env bash
# agm-self-update — re-run the AGM installer
exec curl -fsSL "${BASE_URL}/install.sh" | bash "\$@"
SELFUPDATE
  chmod 755 "${PREFIX}/agm-self-update"
}

# ── Main ────────────────────────────────────────────────────────────────────
main() {
  preflight
  install_agm
  install_antigravity
  init_agm_dir
  create_self_update
  post_install
}

main "$@"
