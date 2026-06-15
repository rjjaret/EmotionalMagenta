#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_NAME="${MODEL_NAME:-mrt2_base}"
DOWNLOAD_MODELS="${DOWNLOAD_MODELS:-1}"
AUTO_INSTALL_CMAKE="${AUTO_INSTALL_CMAKE:-1}"
JOBS="${JOBS:-10}"
QUIET_CMAKE_DEV_WARNINGS="${QUIET_CMAKE_DEV_WARNINGS:-1}"

MAGENTA_REALTIME_DIR="$ROOT_DIR/magenta-realtime"
MAGENTA_REALTIME_BUILD_DIR="${MAGENTA_REALTIME_BUILD_DIR:-$MAGENTA_REALTIME_DIR/build}"
COLLIDER_APP_BUILD_PATH="$MAGENTA_REALTIME_BUILD_DIR/examples/collider/collider_em.app"
STAGE_PREBUILT_SCRIPT="$ROOT_DIR/scripts/stage_prebuilt_collider.sh"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

ensure_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 1
  fi
}

ensure_cmake() {
  if command -v cmake >/dev/null 2>&1; then
    return
  fi

  if [[ "$AUTO_INSTALL_CMAKE" == "1" ]] && command -v brew >/dev/null 2>&1; then
    log "cmake not found; installing with Homebrew"
    brew install cmake
  fi

  if ! command -v cmake >/dev/null 2>&1; then
    echo "Error: required command not found: cmake" >&2
    echo "Install it with: brew install cmake" >&2
    echo "Or set AUTO_INSTALL_CMAKE=1 with Homebrew available." >&2
    exit 1
  fi
}

log "Using root: $ROOT_DIR"
log "Using python from active environment: $(command -v python || echo unavailable)"
log "Using in-repo magenta-realtime source: $MAGENTA_REALTIME_DIR"

ensure_cmd python
ensure_cmd pip
if [[ ! -d "$MAGENTA_REALTIME_DIR" ]]; then
  echo "Error: missing in-repo source at $MAGENTA_REALTIME_DIR" >&2
  echo "Collider source must live in this project under magenta-realtime/." >&2
  echo "Expected Collider CMake project there (for target deploy_collider_em)." >&2
  exit 1
fi

if [[ ! -f "$MAGENTA_REALTIME_DIR/CMakeLists.txt" ]]; then
  echo "Error: missing CMakeLists.txt at $MAGENTA_REALTIME_DIR/CMakeLists.txt" >&2
  echo "Collider source appears incomplete under magenta-realtime/." >&2
  exit 1
fi

ensure_cmake

log "Installing project dependencies"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "$ROOT_DIR"

if [[ "$DOWNLOAD_MODELS" == "1" ]]; then
  if ! python -c 'from magenta_rt.cli import main; main()' --help >/dev/null 2>&1; then
    echo "Error: Magenta CLI is not importable from active python." >&2
    echo "Ensure the active environment contains magenta_rt (try: python -m pip install -e .)." >&2
    exit 1
  fi

  log "Using Magenta CLI from active python"
  log "Downloading shared Magenta resources"
  python -c 'from magenta_rt.cli import main; main()' models init

  log "Downloading exported model: $MODEL_NAME"
  python -c 'from magenta_rt.cli import main; main()' models download "$MODEL_NAME"
else
  log "Skipping model downloads (DOWNLOAD_MODELS=$DOWNLOAD_MODELS)"
fi

log "Configuring Collider build: $MAGENTA_REALTIME_DIR"
cmake_configure_args=(
  -S "$MAGENTA_REALTIME_DIR"
  -B "$MAGENTA_REALTIME_BUILD_DIR"
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5
)

# Third-party CMake projects (TF Lite deps) currently emit dev/deprecation
# warnings on newer CMake versions. This keeps rebuild output cleaner.
if [[ "$QUIET_CMAKE_DEV_WARNINGS" == "1" ]]; then
  cmake_configure_args+=(
    -Wno-dev
    -DCMAKE_POLICY_DEFAULT_CMP0169=OLD
  )
fi

cmake "${cmake_configure_args[@]}"

log "Building and deploying Collider app"
cmake --build "$MAGENTA_REALTIME_BUILD_DIR" --target deploy_collider_em -j"$JOBS"

if [[ -d "$COLLIDER_APP_BUILD_PATH" ]]; then
  log "Collider app available at: $COLLIDER_APP_BUILD_PATH"

  if [[ -x "$STAGE_PREBUILT_SCRIPT" ]]; then
    log "Staging prebuilt Collider app"
    "$STAGE_PREBUILT_SCRIPT"
  else
    log "Skipping prebuilt staging; script not executable: $STAGE_PREBUILT_SCRIPT"
  fi
else
  log "Collider app not found in build output: $COLLIDER_APP_BUILD_PATH"
  log "You can also use an already installed app at ~/Applications/collider_em.app"
fi

log "Rebuild complete"
