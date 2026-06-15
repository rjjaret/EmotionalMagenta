import csv
import time
import cv2
import os
import sys
import subprocess
from functools import lru_cache
from pathlib import Path


LOCAL_MAGENTA_REALTIME_ROOT = Path(__file__).resolve().parent / "magenta-realtime"
if str(LOCAL_MAGENTA_REALTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(LOCAL_MAGENTA_REALTIME_ROOT))


import IPython.display as ipd

from magenta_rt import MagentaRT2Jax
from magenta_rt import MagentaRT2Mlx
from magenta_rt import MagentaRT2Mlxfn
from magenta_rt import paths

from src.core.analyzer import (
    EmotionAnalyzer,
    subscribe_to_periodic_aggregation,
    unsubscribe_from_periodic_aggregation,
)

def on_aggregate(result: dict):
    print("AGG CALLBACK:", result["emotion"], result["sample_count"])
    # result keys: emotion, probs, sample_count, window_seconds, emit_every_seconds, emitted_at


def get_music(prompt: str = "ambient music", model_name: str = "mrt2_base"):
    print('MAGENTA HOME:', paths.magenta_home())
    print('MODELS DIR  :', paths.models_dir())
    print('CKPT DIR    :', paths.checkpoints_dir())
    model_bundle_path = paths.models_dir() / model_name / f'{model_name}.mlxfn'
    model_state_path = paths.models_dir() / model_name / f'{model_name}_state.safetensors'
    print(f'Using model: {model_name}')
    print(f'Has {model_name} mlxfn:', model_bundle_path.exists())
    print(f'Has {model_name} state:', model_state_path.exists())
    if not model_bundle_path.exists():
        print(f'Missing model bundle: {model_bundle_path}')
        print('Run `mrt models download` to fetch the exported MLX model under models/.')
        return None

    mrt = MagentaRT2Mlxfn(size=model_name)
    embedding = mrt.embed_style(prompt)
    wav, state = mrt.generate(state=None, style=embedding, notes=None, frames=250)

    audio_widget = ipd.Audio(wav.samples.T, rate=48000)
    ipd.display(audio_widget)
    return audio_widget


COLLIDER_BUNDLE_ID = "com.google.collider_em"
_env_collider_path = os.environ.get("COLLIDER_APP_PATH")
_repo_prebuilt_collider_path = (
    Path(__file__).resolve().parent
    / "prebuilt"
    / "collider"
    / "collider_em.app"
)
_backseat_collider_path = (
    Path(__file__).resolve().parent.parent
    / "BackseatPJ"
    / "magenta-realtime-bpj"
    / "build"
    / "examples"
    / "collider"
    / "collider_em.app"
)
COLLIDER_APP_CANDIDATES = [
    Path(_env_collider_path).expanduser() if _env_collider_path else None,
    Path(__file__).resolve().parent / "magenta-realtime" / "build" / "examples" / "collider" / "collider_em.app",
    _repo_prebuilt_collider_path,
    _backseat_collider_path,
    Path.home() / "Applications" / "collider_em.app",
]
COLLIDER_EMOTION_KEY = "Collider_EmotionState"
COLLIDER_EMOTION_PROMPT_KEY = "Collider_EmotionPrompt"
EMOTION_PROMPT_FORMATTING_PATH = Path(__file__).resolve().parent / "emotion_prompt_formatting.csv"


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def resolve_collider_app_path() -> Path | None:
    for candidate in COLLIDER_APP_CANDIDATES:
        if candidate is None:
            continue
        if candidate.exists():
            return candidate
    return None


def set_collider_emotion_prompt(prompt: str) -> bool:
    try:
        subprocess.run(
            ["defaults", "write", COLLIDER_BUNDLE_ID, COLLIDER_EMOTION_PROMPT_KEY, prompt],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print("Failed to write Collider emotion prompt:", exc.stderr.strip() if exc.stderr else exc)
        return False


def set_collider_emotion_state(emotion: str) -> bool:
    try:
        subprocess.run(
            ["defaults", "write", COLLIDER_BUNDLE_ID, COLLIDER_EMOTION_KEY, emotion],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print("Failed to write Collider emotion state:", exc.stderr.strip() if exc.stderr else exc)
        return False


def clear_collider_emotion_prompt() -> bool:
    result = subprocess.run(
        ["defaults", "delete", COLLIDER_BUNDLE_ID, COLLIDER_EMOTION_PROMPT_KEY],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    stderr = (result.stderr or "").strip().lower()
    # Treat missing-key as success so startup/shutdown cleanup is idempotent.
    if "does not exist" in stderr:
        return True
    print("Failed to clear Collider emotion prompt:", result.stderr.strip() if result.stderr else result.returncode)
    return False


@lru_cache(maxsize=1)
def load_emotion_prompt_formatting() -> dict[str, str]:
    formatting: dict[str, str] = {}
    if not EMOTION_PROMPT_FORMATTING_PATH.exists():
        return formatting

    with EMOTION_PROMPT_FORMATTING_PATH.open("r", newline="", encoding="utf-8") as file_handle:
        reader = csv.reader(file_handle)
        for row in reader:
            if len(row) < 2:
                continue
            key = row[0].strip()
            value = row[1].strip()
            if key:
                formatting[key.lower()] = value
    return formatting


def emotion_music_descriptor(emotion: str) -> str:
    descriptors = {
        "happy": "uplifting major-key, buoyant",
        "sad": "melancholic minor-key harmony",
        "angry": "driving percussion, tense harmonic movement",
        "fear": "uneasy atmosphere, suspenseful evolving textures",
        "surprise": "sudden dynamic contrast,unexpected melodic turns",
        "disgust": "gritty timbre, dissonant clusters, rough experimental accents",
        "neutral": "steady pulse, restrained dynamics",
        "calm": "warm sustained chords",
    }
    return descriptors.get(
        (emotion or "neutral").strip().lower(),
        "expressive emotional phrasing",
    )


def format_emotion_prompt(emotion: str) -> str:
    formatting = load_emotion_prompt_formatting()
    normalized = (emotion or "neutral").strip()
    normalized_key = normalized.lower()
    prompt_format = formatting.get("promptformat")

    general_style_prompt = formatting.get("generalstyleprompt", "")
    emotion_prompt = formatting.get(normalized_key, "")
    if not emotion_prompt:
        emotion_prompt = emotion_music_descriptor(normalized)

    if prompt_format:
        values = _SafeFormatDict(
            {
                "GeneralStylePrompt": general_style_prompt,
                "EmotionPrompt": emotion_prompt,
                "emotion": normalized_key,
                "Emotion": normalized,
            }
        )
        return prompt_format.format_map(values).strip()

    parts = [part for part in [general_style_prompt, emotion_prompt] if part]
    return ", ".join(parts) if parts else f"emotional tone: {normalized_key} | musical direction: {emotion_prompt}"


def launch_collider() -> bool:
    collider_app_path = resolve_collider_app_path()
    if collider_app_path is None:
        print("Collider app not found in expected locations:")
        for candidate in COLLIDER_APP_CANDIDATES:
            print(f" - {candidate}")
        print("Build/deploy with: cmake --build build --target deploy_collider_em -j10")
        return False
    try:
        binary_path = collider_app_path / "Contents" / "MacOS" / "collider_em"
        print(f"Launching Collider binary: {binary_path}")
        # Ensure we do not re-focus a stale already-running app instance.
        subprocess.run(["pkill", "-x", "collider_em"], check=False)
        subprocess.Popen([str(binary_path)])
        return True
    except (subprocess.CalledProcessError, OSError) as exc:
        print("Failed to launch Collider app:", exc)
        return False


def run_facial_emotion_collider_callback(
    open_app: bool = True,
    emit_every_seconds: float = 1.2,
    window_seconds: float = 3.0,
    analyze_every_seconds: float = 0.5,
    min_stable_emotion_events: int = 1,
    min_emotion_confidence: float = 0.35,
    min_top_margin: float = 0.06,
    camera_width: int = 320,
    camera_height: int = 240,
):
    clear_collider_emotion_prompt()

    analyzer = EmotionAnalyzer()
    analyzer.start()

    latest_emotion_result = None
    latest_emotion_version = 0

    def on_local_aggregate(result: dict):
        nonlocal latest_emotion_result, latest_emotion_version
        latest_emotion_result = result
        latest_emotion_version += 1
        print("AGG CALLBACK:", result["emotion"], result["sample_count"])

    sub_id = subscribe_to_periodic_aggregation(
        analyzer,
        callback=on_local_aggregate,
        window_seconds=window_seconds,
        emit_every_seconds=emit_every_seconds,
        min_emotion_confidence=min_emotion_confidence,
        min_top_margin=min_top_margin,
    )

    if open_app:
        launch_collider()

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(camera_width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(camera_height))
    cap.set(cv2.CAP_PROP_FPS, 15.0)
    if not cap.isOpened():
        print("Unable to open camera device 0.")
        unsubscribe_from_periodic_aggregation(analyzer, sub_id)
        analyzer.stop()
        return

    last_analyze_at = 0.0
    last_processed_emotion_version = 0
    last_sent_emotion = None
    candidate_emotion = None
    candidate_count = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            current_time = time.time()
            if current_time - last_analyze_at >= analyze_every_seconds:
                # Downsampled input is usually enough for emotion estimation and
                # significantly lowers CPU/GPU contention with audio generation.
                small_frame = cv2.resize(frame, (camera_width, camera_height), interpolation=cv2.INTER_AREA)
                analyzer.analyze(small_frame)
                last_analyze_at = current_time

            if (
                latest_emotion_result is not None
                and latest_emotion_version != last_processed_emotion_version
            ):
                last_processed_emotion_version = latest_emotion_version
                emotion = latest_emotion_result.get("emotion", "neutral")
                if emotion == candidate_emotion:
                    candidate_count += 1
                else:
                    candidate_emotion = emotion
                    candidate_count = 1

                stable_emotion = candidate_emotion if candidate_count >= min_stable_emotion_events else None
                should_send = stable_emotion is not None and stable_emotion != last_sent_emotion

                if should_send:
                    emotion_to_send = stable_emotion or emotion
                    # Neutral hysteresis: require a bit more stability before
                    # switching from a non-neutral state back to neutral.
                    if (
                        emotion_to_send == "neutral"
                        and last_sent_emotion not in (None, "neutral")
                        and candidate_count < 3
                    ):
                        emotion_to_send = last_sent_emotion
                    modified_prompt = format_emotion_prompt(emotion_to_send)
                    print(f"Updating Collider prompt from emotion: {emotion_to_send}")
                    wrote_live_prompt = set_collider_emotion_prompt(modified_prompt)
                    wrote_emotion = set_collider_emotion_state(emotion_to_send)
                    if wrote_live_prompt and wrote_emotion:
                        print("Collider emotion label + prompt updated.")
                        last_sent_emotion = emotion_to_send

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        clear_collider_emotion_prompt()
        unsubscribe_from_periodic_aggregation(analyzer, sub_id)
        cap.release()
        analyzer.stop()
        cv2.destroyAllWindows()
    
def run_callback_example():
    analyzer = EmotionAnalyzer()
    analyzer.start()
    emit_every_seconds = 2.0
    window_seconds = 2.0

    sub_id = subscribe_to_periodic_aggregation(
        analyzer,
        callback=on_aggregate,
        window_seconds=window_seconds,      
        emit_every_seconds=emit_every_seconds,  # callback every N seconds
        min_emotion_confidence=0.50,
        min_top_margin=0.12,
    )

    cap = cv2.VideoCapture(0)
    frame_count = 0
    analysis_throttle = 3

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_count % analysis_throttle == 0:
                analyzer.analyze(frame)
            frame_count += 1

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        unsubscribe_from_periodic_aggregation(analyzer, sub_id)
        cap.release()
        analyzer.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # run_callback_example()
    # get_music()
    run_facial_emotion_collider_callback(
        emit_every_seconds=1.2,
        window_seconds=3.0,
        analyze_every_seconds=0.5,
        open_app=True,
    )


# def run_embedded():
#     camera = VideoStream(src=0, width=1280, height=720).start()
#     analyzer = EmotionAnalyzer()
#     analyzer.start()
#     empty_reads = 0
#     max_empty_reads = 300

#     try:
#         while True:
#             frame = camera.read()
#             if frame is None:
#                 # Camera threads often need a short warm-up before first frame.
#                 empty_reads += 1
#                 if empty_reads >= max_empty_reads:
#                     print("No camera frames received. Check camera permissions/device and try again.")
#                     break
#                 cv2.waitKey(1)
#                 continue
#             empty_reads = 0

#             # Use your own face crop logic here.
#             # For demo, we'll analyze center crop.
#             h, w, _ = frame.shape
#             x1, y1 = w // 4, h // 4
#             x2, y2 = 3 * w // 4, 3 * h // 4
#             face_img = frame[y1:y2, x1:x2]

#             analyzer.analyze(face_img)  # async
#             # Do not print here if you only want interval output.
#             # Use subscribe_to_periodic_aggregation(...) + callback print only.

#             if cv2.waitKey(1) & 0xFF == ord("q"):
#                 break
#     finally:
#         analyzer.stop()
#         camera.stop()
#         cv2.destroyAllWindows()

# if __name__ == "__main__":
#     run_embedded()