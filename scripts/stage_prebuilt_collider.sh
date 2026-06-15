#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_APP_PATH="${SOURCE_APP_PATH:-$ROOT_DIR/magenta-realtime/build/examples/collider/collider_em.app}"
DEST_DIR="$ROOT_DIR/prebuilt/collider"
DEST_APP_PATH="$DEST_DIR/collider_em.app"
AUTO_STAGE="${AUTO_STAGE:-1}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

if [[ ! -d "$SOURCE_APP_PATH" ]]; then
  echo "Error: source app not found: $SOURCE_APP_PATH" >&2
  echo "Build it first with ./scripts/rebuild_all.sh or set SOURCE_APP_PATH." >&2
  exit 1
fi

log "Copying prebuilt Collider app"
mkdir -p "$DEST_DIR"
rm -rf "$DEST_APP_PATH"
cp -R "$SOURCE_APP_PATH" "$DEST_APP_PATH"

if command -v git >/dev/null 2>&1; then
  if command -v git-lfs >/dev/null 2>&1 || git lfs version >/dev/null 2>&1; then
    log "Ensuring Git LFS tracking for prebuilt artifacts"
    git lfs track "prebuilt/collider/**"
  else
    log "Git LFS not found; install it for large binary tracking"
  fi

  if [[ "$AUTO_STAGE" == "1" ]]; then
    log "Staging prebuilt app and .gitattributes"
    git add .gitattributes prebuilt/collider/collider_em.app
  fi
fi

log "Prebuilt app ready at: $DEST_APP_PATH"
log "Next: git status && git commit -m 'Update prebuilt Collider app'"
