# Rebuild Guide (EmotionalMagenta + Collider)

This project can be rebuilt from scratch on macOS with one script:

```bash
./scripts/rebuild_all.sh
```

## What the script rebuilds

1. Uses your current active Python environment (whatever interpreter is on `PATH`).
2. Installs this repo in editable mode (`pip install -e .`).
3. Downloads Magenta Runtime resources and model artifacts via `mrt`:
   - `mrt models init`
   - `mrt models download mrt2_base` (default model)
4. Reconfigures and rebuilds Collider from project-local `magenta-realtime`:
   - `cmake -S magenta-realtime -B magenta-realtime/build`
   - `cmake --build magenta-realtime/build --target deploy_collider_em -j10`
5. The in-repo `magenta-realtime` tree preserves upstream structure but includes only Collider-required parts (`core`, `examples/common`, `examples/collider`, and examples workspace files).

## Required prerequisites

- macOS
- Python available in your current environment (`python` on PATH)
- CMake on PATH
- Network access to HuggingFace or GCS (used by `mrt models ...`)
- `magenta-realtime` exists inside this repo

## Environment variables (optional)

- `MODEL_NAME` (default: `mrt2_base`)
- `DOWNLOAD_MODELS` (`1` to download, `0` to skip)
- `AUTO_INSTALL_CMAKE` (`1` to auto-install cmake via Homebrew if missing)
- `MAGENTA_REALTIME_BUILD_DIR` (default: `magenta-realtime/build`)
- `JOBS` (default: `10`)

Example:

```bash
MODEL_NAME=mrt2_small JOBS=8 ./scripts/rebuild_all.sh
```

## Collider path resolution

`main.py` now checks these Collider app locations in order:

1. `COLLIDER_APP_PATH` environment variable (if set)
2. `magenta-realtime/build/examples/collider/collider_em.app`
3. `~/Applications/collider_em.app`

So after a local Collider rebuild, the app is discovered automatically without manual copying.
