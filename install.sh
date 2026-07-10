#!/usr/bin/env bash
# install.sh — curl-pipe-bash one-liner installer for Antigrafity Manager
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ashkhfi/antigrafity-manager/main/install.sh | bash
#
# Options:
#   --no-antigravity   Skip agy.orig binary download
#   --prefix <dir>     Custom install directory (default: ~/.local/bin)
#   --version <tag>    Install specific release tag (e.g. v1.0.0)
#   --check-update     Check for newer version
set -euo pipefail

REPO_OWNER="ashkhfi"
REPO_NAME="antigrafity-manager"
REPO_BRANCH="${AGM_INSTALL_BRANCH:-main}"
BASE_URL="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${REPO_BRANCH}"
PREFIX="${AGM_PREFIX:-${HOME}/.local/bin}"
SKIP_ANTIGRAVITY=false
AGM_DIR="${HOME}/.agm"
CHECK_UPDATE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-antigravity) SKIP_ANTIGRAVITY=true ;;
    --prefix) PREFIX="$2"; shift ;;
    --version) REPO_BRANCH="$2"; BASE_URL="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${REPO_BRANCH}"; shift ;;
    --check-update) CHECK_UPDATE=true ;;
    --help|-h)
      echo "Usage: curl -fsSL .../install.sh | bash [-- <options>]"
      echo ""
      echo "Options:"
      echo "  --no-antigravity   Skip antigravity-cli binary download"
      echo "  --prefix <dir>     Install to <dir> (default: ~/.local/bin)"
      echo "  --version <tag>    Install a specific release tag (e.g. v1.0.0)"
      echo "  --check-update     Check for newer version"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

preflight() {
  local os
  os="$(uname -s 2>/dev/null || echo Linux)"
  echo "◆ Antigrafity Manager Installer — ${os}"
  echo "  Prefix: ${PREFIX}"
  echo "  Source: ${BASE_URL}"
  echo ""
  if ! command -v curl >/dev/null 2>&1; then echo "✗ curl not found"; exit 1; fi
  if ! command -v python3 >/dev/null 2>&1; then echo "✗ python3 not found"; exit 1; fi
  mkdir -p "${PREFIX}" "${AGM_DIR}"
  echo "✓ Preflight passed"
  echo ""
}

download() {
  local src="$1"; local dst="$2"; local mode="${3:-644}"
  echo "  ↓ ${src}"
  curl -fsSL "${BASE_URL}/${src}" -o "${dst}"
  chmod "${mode}" "${dst}"
}

install_tools() {
  echo "◆ Installing tools to ${PREFIX}"
  download "ag" "${PREFIX}/ag" "755"
  download "agy" "${PREFIX}/agy" "755"
  download "agm-web" "${PREFIX}/agm-web" "755"
  download "agm_backend.py" "${PREFIX}/agm_backend.py"
  download "agm-dashboard.html" "${PREFIX}/agm-dashboard.html"
  download "VERSION" "${PREFIX}/VERSION"
  download "_update.py" "${PREFIX}/_update.py"
  echo ""
}

install_antigravity() {
  if [ "$SKIP_ANTIGRAVITY" = true ]; then
    echo "◆ Skipping antigravity-cli binary download"
    echo ""
    return
  fi

  if [ -f "${PREFIX}/agy.orig" ]; then
    echo "◆ antigravity-cli already installed"
    echo "  Use --force to re-download"
    echo ""
    return
  fi

  echo "◆ Downloading antigravity-cli binary"
  local ARCH
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "  Unsupported architecture: $ARCH"; return ;;
  esac

  local BIN_URL="https://github.com/nicholasgasior/antigravity-cli/releases/latest/download/antigravity-cli-linux-${ARCH}"
  local TMPBIN
  TMPBIN="$(mktemp)"
  if curl -fsSL "${BIN_URL}" -o "${TMPBIN}" 2>/dev/null; then
    mv "${TMPBIN}" "${PREFIX}/agy.orig"
    chmod 755 "${PREFIX}/agy.orig"
    echo "  ✓ antigravity-cli installed"
  else
    echo "  ⚠ Could not download antigravity-cli (agy will not work)"
    rm -f "${TMPBIN}"
  fi
  echo ""
}

create_self_update() {
  cat > "${PREFIX}/agm-self-update" <<-'SELFUPDATE'
#!/usr/bin/env bash
# agm-self-update — update AGM tools
# Usage: agm-self-update [--check]
set -euo pipefail
if [ "${1:-}" = "--check" ]; then
    exec curl -fsSL "https://raw.githubusercontent.com/ashkhfi/antigrafity-manager/main/install.sh" | bash -s -- --check-update
fi
exec curl -fsSL "https://raw.githubusercontent.com/ashkhfi/antigrafity-manager/main/install.sh" | bash
SELFUPDATE
  chmod 755 "${PREFIX}/agm-self-update"
}

do_check_update() {
  local CURRENT="unknown"
  if [ -f "${PREFIX}/VERSION" ]; then
    CURRENT="v$(grep 'AGM_VERSION' "${PREFIX}/VERSION" | head -1 | cut -d'"' -f2)"
  fi
  local LATEST
  LATEST=$(curl -fsSL "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest" 2>/dev/null | python3 -c "
import sys,json
try:
    print(json.load(sys.stdin).get('tag_name',''))
except: pass
" 2>/dev/null || echo "")
  if [ -z "$LATEST" ]; then
    echo "  Could not check for updates"
    return
  fi
  if [ "$CURRENT" = "$LATEST" ]; then
    echo "  ✓ Up to date ($CURRENT)"
  else
    echo ""
    echo "  ⚡ Update available: $CURRENT → $LATEST"
    echo "     https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/tag/$LATEST"
    echo "     Update: agm-self-update  or  curl -fsSL .../install.sh | bash"
    echo ""
  fi
}

main() {
  preflight
  if [ "$CHECK_UPDATE" = true ]; then
    do_check_update
    exit 0
  fi
  install_tools
  install_antigravity
  create_self_update
  echo "═══════════════════════════════════════════"
  echo "  ✓ Install complete!"
  echo "  Tools:  ag  |  agy  |  agm-web  |  agm-self-update"
  echo "  Data:   ~/.agm/"
  echo "═══════════════════════════════════════════"
}

main
