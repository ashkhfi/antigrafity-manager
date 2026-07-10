#!/usr/bin/env bash
# release.sh — Build and publish a new release
# Usage: ./release.sh v1.1.0
set -euo pipefail

TAG="${1:?Usage: ./release.sh v1.1.0}"
REPO="ashkhfi/antigrafity-manager"
TMPDIR=$(mktemp -d)

# Read current version from VERSION file
CURRENT=$(python3 -c "
import sys
for line in open('VERSION'):
    if 'VERSION' in line:
        print(line.split('=')[1].strip('\"').strip())
        break
" 2>/dev/null || echo "0.0.0")

echo "Release: $CURRENT → $TAG"

# Validate tag format
if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Invalid tag: $TAG (expected v1.2.3)"
    exit 1
fi

# Update VERSION file
echo "AGM_VERSION=\"${TAG#v}\"" > VERSION

# Build release tarball (safe files only)
echo "Building tarball..."
tar czf "$TMPDIR/agm-${TAG}.tar.gz" \
    ag agy agy.orig agm-web agm_backend.py agm-dashboard.html VERSION

echo "Contents:"
tar tzf "$TMPDIR/agm-${TAG}.tar.gz"

# Commit
git add -A
git commit -m "release: ${TAG}" || echo "Nothing to commit"
git tag "$TAG"

# Push
git push origin main
git push origin "$TAG"

# Create GitHub Release with tarball
echo "Creating GitHub Release..."
gh release create "$TAG" \
    --title "$TAG" \
    --notes "## $TAG" \
    --target main \
    "$TMPDIR/agm-${TAG}.tar.gz#agm-${TAG}.tar.gz"

# Cleanup
rm -rf "$TMPDIR"

echo "Done: https://github.com/${REPO}/releases/tag/${TAG}"
