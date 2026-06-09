from __future__ import annotations

from collections import deque
import importlib
import logging
import queue
import threading
import time
import uuid
from typing import Callable, Deque, Dict, Tuple


LOGGER = logging.getLogger(__name__)


class _PeriodicAggregationSubscription:
    """Collects analyzer results over a time window and emits at a fixed interval."""

    def __init__(
        self,
        analyzer: "EmotionAnalyzer",
        callback: Callable[[dict], None],
        window_seconds: float,
        emit_every_seconds: float,
        poll_interval_seconds: float = 0.1,
        min_emotion_confidence: float = 0.45,
        min_top_margin: float = 0.10,
    ) -> None:
        self._analyzer = analyzer
        self._callback = callback
        self._window_seconds = window_seconds
        self._emit_every_seconds = emit_every_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._min_emotion_confidence = min_emotion_confidence
        self._min_top_margin = min_top_margin
        self._samples: Deque[tuple[float, Dict[str, float]]] = deque()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _worker(self) -> None:
        next_emit = time.monotonic() + self._emit_every_seconds

        while self._running:
            now = time.monotonic()
            _, probs = self._analyzer.get_results()
            if probs:
                self._samples.append((now, probs))

            cutoff = now - self._window_seconds
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()

            if now >= next_emit:
                payload = self._aggregate_payload()
                try:
                    self._callback(payload)
                except Exception:
                    # Callbacks are user code; keep worker alive on callback failure.
                    pass

                while next_emit <= now:
                    next_emit += self._emit_every_seconds

            time.sleep(self._poll_interval_seconds)

    def _aggregate_payload(self) -> dict:
        if not self._samples:
            return {
                "emotion": "neutral",
                "probs": {"neutral": 1.0},
                "sample_count": 0,
                "window_seconds": self._window_seconds,
                "emit_every_seconds": self._emit_every_seconds,
                "emitted_at": time.time(),
            }

        totals: Dict[str, float] = {}
        for _, probs in self._samples:
            for emotion, prob in probs.items():
                totals[emotion] = totals.get(emotion, 0.0) + float(prob)

        sample_count = len(self._samples)
        averaged = {emotion: total / sample_count for emotion, total in totals.items()}

        sorted_probs = sorted(averaged.items(), key=lambda item: item[1], reverse=True)
        top_emotion, top_prob = sorted_probs[0]
        second_prob = sorted_probs[1][1] if len(sorted_probs) > 1 else 0.0
        top_margin = top_prob - second_prob

        # Avoid overconfident weak classifications from noisy frames.
        if top_prob < self._min_emotion_confidence or top_margin < self._min_top_margin:
            top_emotion = "neutral"
            averaged = dict(averaged)
            averaged["neutral"] = max(averaged.get("neutral", 0.0), top_prob)

        return {
            "emotion": top_emotion,
            "probs": averaged,
            "sample_count": sample_count,
            "window_seconds": self._window_seconds,
            "emit_every_seconds": self._emit_every_seconds,
            "emitted_at": time.time(),
        }


class EmotionAnalyzer:
    """Background emotion analyzer with non-blocking enqueue API."""

    def __init__(self) -> None:
        self._queue: "queue.Queue" = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_emotion = "neutral"
        self._last_probs: Dict[str, float] = {"neutral": 1.0}
        self._deepface_class = None
        self._deepface_error: Exception | None = None
        self._logged_deepface_error = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def analyze(self, face_img) -> None:
        if not self._running:
            return
        try:
            # Keep only the latest frame to limit latency.
            if self._queue.full():
                self._queue.get_nowait()
            self._queue.put_nowait(face_img)
        except queue.Empty:
            pass
        except queue.Full:
            pass

    def get_results(self) -> Tuple[str, Dict[str, float]]:
        with self._lock:
            return self._last_emotion, dict(self._last_probs)

    def stop(self) -> None:
        subscriptions = getattr(self, "_periodic_subscriptions", None)
        if subscriptions:
            for subscription in list(subscriptions.values()):
                subscription.stop()
            subscriptions.clear()

        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _worker(self) -> None:
        while self._running:
            try:
                frame = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            emotion, probs = self._analyze_with_fallback(frame)
            with self._lock:
                self._last_emotion = emotion
                self._last_probs = probs

    def _analyze_with_fallback(self, face_img) -> Tuple[str, Dict[str, float]]:
        try:
            DeepFace = self._get_deepface()

            result = DeepFace.analyze(
                img_path=face_img,
                actions=["emotion"],
                enforce_detection=False,
                detector_backend="opencv",
                silent=True,
            )

            # DeepFace can return a dict or a list[dict].
            if isinstance(result, list):
                result = result[0]

            probs = result.get("emotion", {})
            if not probs:
                return "neutral", {"neutral": 1.0}

            emotion = max(probs, key=probs.get)
            probs = {k: float(v) / 100.0 for k, v in probs.items()}
            return emotion, probs
        except Exception as exc:
            self._log_deepface_failure(exc)
            return "neutral", {"neutral": 1.0}

    def _get_deepface(self):
        if self._deepface_class is not None:
            return self._deepface_class
        if self._deepface_error is not None:
            raise self._deepface_error

        try:
            self._deepface_class = importlib.import_module("deepface.DeepFace")
            return self._deepface_class
        except Exception as exc:
            self._deepface_error = exc
            self._log_deepface_failure(exc)
            raise

    def _log_deepface_failure(self, exc: Exception) -> None:
        if self._logged_deepface_error:
            return
        LOGGER.error("EmotionAnalyzer falling back to neutral because DeepFace is unavailable: %s", exc)
        self._logged_deepface_error = True


def subscribe_to_periodic_aggregation(
    analyzer: EmotionAnalyzer,
    callback: Callable[[dict], None],
    window_seconds: float = 5.0,
    emit_every_seconds: float = 5.0,
    min_emotion_confidence: float = 0.45,
    min_top_margin: float = 0.10,
) -> str:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be > 0")
    if emit_every_seconds <= 0:
        raise ValueError("emit_every_seconds must be > 0")
    if not 0.0 <= min_emotion_confidence <= 1.0:
        raise ValueError("min_emotion_confidence must be between 0.0 and 1.0")
    if not 0.0 <= min_top_margin <= 1.0:
        raise ValueError("min_top_margin must be between 0.0 and 1.0")

    registry: Dict[str, _PeriodicAggregationSubscription] = getattr(
        analyzer, "_periodic_subscriptions", {}
    )
    setattr(analyzer, "_periodic_subscriptions", registry)

    sub_id = uuid.uuid4().hex
    subscription = _PeriodicAggregationSubscription(
        analyzer=analyzer,
        callback=callback,
        window_seconds=window_seconds,
        emit_every_seconds=emit_every_seconds,
        min_emotion_confidence=min_emotion_confidence,
        min_top_margin=min_top_margin,
    )
    registry[sub_id] = subscription
    subscription.start()
    return sub_id


def unsubscribe_from_periodic_aggregation(analyzer: EmotionAnalyzer, sub_id: str) -> bool:
    registry: Dict[str, _PeriodicAggregationSubscription] = getattr(
        analyzer, "_periodic_subscriptions", {}
    )
    subscription = registry.pop(sub_id, None)
    if subscription is None:
        return False
    subscription.stop()
    return True
