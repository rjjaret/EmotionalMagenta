from __future__ import annotations

import threading
import time

import cv2


class VideoStream:
    """Threaded OpenCV camera reader."""

    def __init__(self, src: int = 0, width: int = 1280, height: int = 720) -> None:
        self.src = src
        self.width = width
        self.height = height

        self._cap = cv2.VideoCapture(self.src)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._frame = None

    def start(self) -> "VideoStream":
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._update, daemon=True)
        self._thread.start()
        return self

    def _update(self) -> None:
        while self._running:
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._lock:
                self._frame = frame

    def read(self):
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
