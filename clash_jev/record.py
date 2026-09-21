"""Record a run as a small video, so it can be watched again next to its decision log.

The recorder runs on its own thread and only reads the newest frame, so it cannot slow the video stream or
the play loop. If it fails, the run carries on without a video. Every picture is stamped with the time since
the run started, so second N of the video is second N of the log (`state_elapsed`).
"""

import threading
import time
from pathlib import Path

import cv2


class Recorder:
    def __init__(self, frame_source, path: Path, started: float, fps: int = 10, width: int = 480):
        self.path, self._frame_source, self._started = path, frame_source, started
        self._fps, self._width = fps, width
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._record, daemon=True)
        self._thread.start()

    def _record(self) -> None:
        try:
            import av

            output = stream = None
            last_tick = -1
            while not self._stop.is_set():
                tick = int((time.time() - self._started) * self._fps)
                if tick <= last_tick:
                    time.sleep(0.01)
                    continue
                frame = self._frame_source()
                height = round(frame.shape[0] * self._width / frame.shape[1] / 2) * 2
                picture = cv2.resize(frame, (self._width, height), interpolation=cv2.INTER_AREA)
                if output is None:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    output = av.open(str(self.path), "w")
                    stream = output.add_stream("libx264", rate=self._fps)
                    stream.width, stream.height, stream.pix_fmt = self._width, height, "yuv420p"
                    stream.options = {"crf": "27", "preset": "veryfast"}
                image = av.VideoFrame.from_ndarray(picture, format="bgr24")
                image.pts = tick  # a busy moment skips pictures, it never shifts the ones after it
                for packet in stream.encode(image):
                    output.mux(packet)
                last_tick = tick
            if output is not None:
                for packet in stream.encode():
                    output.mux(packet)
                output.close()
        except Exception as error:  # noqa: BLE001 (a failed recording must not end the run)
            print(f"recording stopped ({error!r}); the run continues without video", flush=True)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
