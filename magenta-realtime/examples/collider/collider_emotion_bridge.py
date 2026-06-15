#!/usr/bin/env python3
"""Collider emotion bridge.

Runs the same emotion pipeline used by EmotionalMagenta (EmotionAnalyzer +
periodic aggregation), then writes results into Collider defaults keys so the
standalone app can consume them in real time.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

import cv2

COLLIDER_BUNDLE_ID = "com.google.collider_em"
COLLIDER_EMOTION_KEY = "Collider_EmotionState"
COLLIDER_BRIDGE_STATUS_KEY = "Collider_EmotionBridgeStatus"
COLLIDER_BRIDGE_DETAIL_KEY = "Collider_EmotionBridgeDetail"

_running = True


def _on_signal(_signum, _frame) -> None:
    global _running
    _running = False


signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT, _on_signal)


def write_collider_emotion(emotion: str) -> None:
    subprocess.run(
        ["defaults", "write", COLLIDER_BUNDLE_ID, COLLIDER_EMOTION_KEY, emotion],
        check=False,
        capture_output=True,
        text=True,
    )


def write_bridge_status(status: str, detail: str) -> None:
    subprocess.run(
        ["defaults", "write", COLLIDER_BUNDLE_ID, COLLIDER_BRIDGE_STATUS_KEY, status],
        check=False,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["defaults", "write", COLLIDER_BUNDLE_ID, COLLIDER_BRIDGE_DETAIL_KEY, detail],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--camera-width", type=int, default=640)
    parser.add_argument("--camera-height", type=int, default=480)
    parser.add_argument("--analyze-every-seconds", type=float, default=0.4)
    parser.add_argument("--emit-every-seconds", type=float, default=1.2)
    parser.add_argument("--window-seconds", type=float, default=3.0)
    parser.add_argument("--min-emotion-confidence", type=float, default=0.2)
    parser.add_argument("--min-top-margin", type=float, default=0.0)
    parser.add_argument("--min-stable-events", type=int, default=1)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    if not (project_root / "src" / "core" / "analyzer.py").exists():
        print(f"Collider emotion bridge: analyzer not found under {project_root}", file=sys.stderr)
        write_collider_emotion("neutral")
        return 1

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from src.core.analyzer import (
            EmotionAnalyzer,
            subscribe_to_periodic_aggregation,
            unsubscribe_from_periodic_aggregation,
        )
    except Exception as exc:
        print(f"Collider emotion bridge: failed to import analyzer: {exc}", file=sys.stderr)
        write_collider_emotion("neutral")
        return 1

    write_bridge_status("starting", "Initializing emotion analyzer...")

    analyzer = EmotionAnalyzer()
    analyzer.start()

    latest_emotion_result: dict | None = None
    latest_emotion_version = 0

    def on_local_aggregate(result: dict) -> None:
        nonlocal latest_emotion_result, latest_emotion_version
        latest_emotion_result = result
        latest_emotion_version += 1

    sub_id = subscribe_to_periodic_aggregation(
        analyzer,
        callback=on_local_aggregate,
        window_seconds=args.window_seconds,
        emit_every_seconds=args.emit_every_seconds,
        min_emotion_confidence=args.min_emotion_confidence,
        min_top_margin=args.min_top_margin,
    )

    camera_candidates = [args.camera_index, 0, 1, 2]
    seen = set()
    camera_indices = [i for i in camera_candidates if not (i in seen or seen.add(i))]
    camera_pos = 0

    def open_camera(index: int):
        cam = cv2.VideoCapture(index)
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, float(args.camera_width))
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, float(args.camera_height))
        cam.set(cv2.CAP_PROP_FPS, 15.0)
        return cam

    cap = open_camera(camera_indices[camera_pos])

    last_analyze_at = 0.0
    last_processed_emotion_version = 0
    last_sent_emotion: str | None = None
    candidate_emotion: str | None = None
    candidate_count = 0

    write_collider_emotion("neutral")
    write_bridge_status("running", "Camera connected. Detecting emotion...")

    no_frame_reads = 0

    try:
        while _running:
            ok, frame = cap.read()
            if not ok:
                no_frame_reads += 1
                if no_frame_reads >= 30:
                    if camera_pos + 1 < len(camera_indices):
                        camera_pos += 1
                        cap.release()
                        cap = open_camera(camera_indices[camera_pos])
                        write_bridge_status("starting", f"Switching to camera index {camera_indices[camera_pos]}...")
                    else:
                        write_bridge_status("error", "No camera frames. Check camera permissions and availability.")
                    no_frame_reads = 0
                time.sleep(0.05)
                continue
            no_frame_reads = 0

            now = time.time()
            if now - last_analyze_at >= args.analyze_every_seconds:
                small = cv2.resize(
                    frame,
                    (args.camera_width, args.camera_height),
                    interpolation=cv2.INTER_AREA,
                )
                analyzer.analyze(small)
                last_analyze_at = now

            if latest_emotion_result is None or latest_emotion_version == last_processed_emotion_version:
                continue

            last_processed_emotion_version = latest_emotion_version
            emotion = str(latest_emotion_result.get("emotion", "neutral"))
            if emotion == candidate_emotion:
                candidate_count += 1
            else:
                candidate_emotion = emotion
                candidate_count = 1

            stable = candidate_emotion if candidate_count >= args.min_stable_events else None
            if stable is None or stable == last_sent_emotion:
                continue

            emotion_to_send = stable
            if (
                emotion_to_send == "neutral"
                and last_sent_emotion not in (None, "neutral")
                and candidate_count < 3
            ):
                emotion_to_send = last_sent_emotion

            write_collider_emotion(emotion_to_send)
            write_bridge_status("running", f"Detected emotion: {emotion_to_send}")
            last_sent_emotion = emotion_to_send
    finally:
        write_bridge_status("stopped", "Emotion bridge stopped.")
        unsubscribe_from_periodic_aggregation(analyzer, sub_id)
        analyzer.stop()
        cap.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
