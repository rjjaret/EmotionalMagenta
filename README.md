# EmotionalMagenta

Emotional Magenta is the accessibility award winning project from the Music Hackspace Hackathon at Berklee College of Music on June 6-7, 2026. It connects live facial emotion analysis to Magenta Realtime music generation application Collider.

The current main flow:
- Reads webcam frames and performs periodic emotion analysis.
- Aggregates emotion signals over a time window for stability.
- Launches and updates the revised Collider app with a special emotion prompt node with the latest detected emotion. 

## Repository Layout

- `main.py`: Primary runtime entrypoint (camera + emotion + Collider bridge).
- `src/core/analyzer.py`: Emotion analysis and aggregation helpers.
- `magenta-realtime/`: Local Magenta Realtime source and Collider example project.
- `scripts/rebuild_all.sh`: One-command rebuild/bootstrap script.
- `REBUILD.md`: Detailed rebuild notes and options.

## Requirements

- macOS
- Python 3.12+
- Webcam access (for live emotion detection)
- Network access for model downloads (`mrt models ...`)

## Quick Start

No local build is required for normal use. The repo includes a prebuilt `collider_em.app`.

1. Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

2. Install project dependencies:

```bash
pip install -e .
```

3. Run the app.:

The first time it runs may take a little longer while it downloads the emotion detection model.
```bash
python main.py
```

Press `q` in the OpenCV loop to exit.

## Build Scripts

If you need to build from source or refresh the checked-in prebuilt app, use these scripts:

Useful environment overrides:
- `MODEL_NAME` (default `mrt2_base`)
- `DOWNLOAD_MODELS` (`1` or `0`)
- `AUTO_INSTALL_CMAKE` (`1` or `0`)
- `MAGENTA_REALTIME_BUILD_DIR` (default `magenta-realtime/build`)
- `JOBS` (default `10`)

```bash
./scripts/rebuild_all.sh
```

Optional overrides for `rebuild_all.sh`:
- `MODEL_NAME` (default `mrt2_base`)
- `DOWNLOAD_MODELS` (`1` or `0`)
- `AUTO_INSTALL_CMAKE` (`1` or `0`)
- `MAGENTA_REALTIME_BUILD_DIR` (default `magenta-realtime/build`)
- `JOBS` (default `10`)

## Collider App Discovery

`main.py` looks for the Collider app in this order:

1. `COLLIDER_APP_PATH` (environment variable)
2. `prebuilt/collider/collider_em.app` (checked-in prebuilt app)
3. `magenta-realtime/build/examples/collider/collider_em.app`
4. `~/Applications/collider_em.app`

If the app is missing, run `./scripts/rebuild_all.sh` or set `COLLIDER_APP_PATH` explicitly.

## Shipping Prebuilt Collider In Git

Yes. You can include a built Collider app so users can run immediately without building first.

Recommended approach:
1. Build Collider once on a trusted macOS machine.
2. Copy the app bundle to `prebuilt/collider/collider_em.app`.
3. Commit with Git LFS enabled for `prebuilt/collider/**`.

Git LFS setup (once per clone):

```bash
git lfs install
git lfs track "prebuilt/collider/**"
git add .gitattributes prebuilt/collider/collider_em.app
git commit -m "Add prebuilt Collider app"
```

Or use the helper script to copy from your latest local build and stage changes:

```bash
./scripts/stage_prebuilt_collider.sh
```

Optional overrides:
- `SOURCE_APP_PATH=/absolute/path/to/collider_em.app`
- `AUTO_STAGE=0` (copy only, do not run `git add`)

Notes:
- Prebuilt macOS apps may trigger Gatekeeper prompts on first run.
- If architecture matters, publish separate bundles (Apple Silicon and Intel) or provide one universal build.
- Source build remains available as fallback via `./scripts/rebuild_all.sh`.

## Troubleshooting

### Camera not opening

Symptoms:
- `Unable to open camera device 0.`

Checks:
- Confirm macOS camera permission is enabled for your terminal app and/or IDE.
- Close other apps that may be holding the camera.
- Re-run from an activated virtual environment.

### Models missing or not found

Symptoms:
- Missing model bundle/state messages.
- Prompt like: `Run mrt models download`.

Fix:

```bash
mrt models init
mrt models download mrt2_base
```

Also verify that these files exist:
- `models/mrt2_base/mrt2_base.mlxfn`
- `models/mrt2_base/mrt2_base_state.safetensors`

### Collider app not found

Symptoms:
- `Collider app not found in expected locations`.

Fix:

```bash
./scripts/rebuild_all.sh
```

Or set an explicit app path:

```bash
export COLLIDER_APP_PATH="/absolute/path/to/collider_em.app"
python main.py
```

### Python environment issues

Symptoms:
- Import errors for `magenta_rt`, `opencv-python`, or `deepface`.

Fix:

```bash
source .venv/bin/activate
pip install -e .
```

If needed, recreate the environment with Python 3.12.

### Build tool issues (CMake missing)

Symptoms:
- `cmake: command not found`.

Fix:
- Install CMake and verify it is on `PATH`.
- Or run the helper script with auto-install enabled:

```bash
AUTO_INSTALL_CMAKE=1 ./scripts/rebuild_all.sh
```

### Runtime exits or interrupted run

Symptoms:
- Process exits with code `130`.

Explanation:
- Exit code 130 usually means the process was interrupted (for example, Ctrl+C).

If this was unintentional, restart with:

```bash
python main.py
```
