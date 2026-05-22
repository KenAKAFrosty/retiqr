"""
OpenCV VideoCapture wrapper.

Runs a background thread that continuously reads frames from the camera
and calls on_frame(img: np.ndarray) in that thread.  The caller must be
thread-safe (e.g. post to a queue or use asyncio.call_soon_threadsafe).
"""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)


class Camera:
    def __init__(self, device: int = 0, width: int = 1280, height: int = 720):
        self._device = device
        self._width = width
        self._height = height
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.on_frame = None  # callable(np.ndarray) — set by caller

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="camera")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self):
        import cv2  # type: ignore

        cap = cv2.VideoCapture(self._device)
        if not cap.isOpened():
            log.error("Cannot open camera device %d", self._device)
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        log.info("Camera %d opened (%dx%d)", self._device,
                 int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                 int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        try:
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    log.warning("Camera read failed, retrying")
                    continue
                if self.on_frame:
                    # Convert BGR (OpenCV default) to contiguous RGB for zxingcpp
                    self.on_frame(frame[:, :, ::-1].copy())
        finally:
            cap.release()
            log.info("Camera %d released", self._device)
