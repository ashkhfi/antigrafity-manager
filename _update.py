# ponytail: drop when all tools are v2+ and users are on latest
"""Background update checker — stdlib only, zero deps."""
import json
import os
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

REPO = "ashkhfi/antigrafity-manager"
VERSION_FILE = Path(__file__).parent / "VERSION"
CACHE_FILE = Path.home() / ".agm" / ".last_update_check"
CHECK_INTERVAL = 86400  # once per day
_done = False


def _read_local():
    try:
        v = VERSION_FILE.read_text().strip().split("=")[1].strip('" ')
        return v
    except Exception:
        return "0.0.0"


def _compare(a, b):
    """Return True if remote > local. Handles 'v1.0.0' and '1.0.0'."""
    def norm(s):
        return tuple(int(x) for x in s.lstrip("v").split(".") if x.isdigit())
    try:
        return norm(a) > norm(b)
    except Exception:
        return False


def _fetch_latest():
    try:
        req = Request(
            f"https://api.github.com/repos/{REPO}/releases/latest",
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "agm"},
        )
        with urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return data.get("tag_name", ""), data.get("html_url", "")
    except Exception:
        return "", ""


def _should_check():
    """True if cache is stale or missing."""
    try:
        if not CACHE_FILE.exists():
            return True
        age = time.time() - CACHE_FILE.stat().st_mtime
        return age > CHECK_INTERVAL
    except Exception:
        return True


def _write_cache(tag):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(tag)
    except Exception:
        pass


def check_update(silent=True):
    """Check for updates in background. Returns immediately.

    silent=True: only print when update available.
    Returns: (local_version, remote_version, url) if checked, None if cached/no update.
    """
    local = _read_local()

    if not _should_check():
        return None

    # Run in daemon thread so tools never block
    def _do_check():
        global _done
        tag, url = _fetch_latest()
        if tag and _compare(tag, local):
            _write_cache(tag)
            if not silent:
                print(f"\n  ⚡ Update available: {local} → {tag}")
                print(f"     {url}")
                print(f"     Run: agm-self-update\n")
        else:
            _write_cache(local)
        _done = True

    t = threading.Thread(target=_do_check, daemon=True)
    t.start()
    return None


def get_latest_sync():
    """Blocking call to get latest tag. For agm-self-update."""
    tag, url = _fetch_latest()
    return tag, url


def self_update():
    """Download and install latest release. Works without agy.orig."""
    import subprocess
    import tarfile
    import tempfile
    import sys

    tag, url = get_latest_sync()
    if not tag:
        print("Failed to fetch latest release from GitHub.")
        print(f"Manual: https://github.com/{REPO}/releases")
        return False

    local = _read_local()
    if not _compare(tag, local):
        print(f"Already up to date (v{local})")
        return True

    print(f"Updating: v{local} → {tag}")

    dl_url = f"https://github.com/{REPO}/releases/download/{tag}/agm-{tag}.tar.gz"
    tmp = tempfile.mkdtemp()
    tar_path = os.path.join(tmp, "release.tar.gz")

    try:
        print(f"Downloading: {dl_url}")
        req = Request(dl_url, headers={"User-Agent": "agm"})
        with urlopen(req, timeout=30) as r:
            with open(tar_path, "wb") as f:
                while chunk := r.read(8192):
                    f.write(chunk)
    except URLError as e:
        print(f"Download failed: {e}")
        print(f"Manual: {url}")
        return False

    prefix = Path(os.environ.get("AGM_PREFIX", Path.home() / ".local" / "bin"))

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            # Extract only known safe files
            safe = {"ag", "agm-web", "agm_backend.py", "agm-dashboard.html", "VERSION"}
            for m in tar.getmembers():
                name = os.path.basename(m.name)
                if name in safe and not m.isdir():
                    m.name = name
                    tar.extract(m, str(prefix))

        # Don't overwrite agy or agy.orig — they may have local config
        # Don't overwrite install.sh
        print(f"Updated to {tag}")
        print("Files: ag, agm-web, agm_backend.py, agm-dashboard.html, VERSION")
        print("Note: agy/agy.orig preserved (not overwritten)")
        return True
    except Exception as e:
        print(f"Extract failed: {e}")
        return False
    finally:
        try:
            os.remove(tar_path)
            os.rmdir(tmp)
        except Exception:
            pass
