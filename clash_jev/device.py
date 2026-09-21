"""The live game: screenshots in, taps out, over ADB. Works with any Android emulator."""

import atexit
import os
import subprocess
import threading
import time

import cv2
import numpy


class AdbDevice:
    def __init__(self, serial: str | None = None, adb_path: str = "adb"):
        self._base = [adb_path, *(["-s", serial] if serial else [])]
        self._size: tuple[int, int] | None = None
        self._session: subprocess.Popen | None = None  # a kept-open `adb shell` for fast taps

    def _shell(self, *command: str) -> str:
        result = subprocess.run([*self._base, "shell", *command], capture_output=True, text=True, check=False)
        return result.stdout.strip()

    def screen_size(self) -> tuple[int, int]:
        """The device's real (width, height). Taps are in these pixels, whatever size frames arrive at."""
        if self._size is None:
            reported = self._shell("wm", "size").splitlines()[-1]  # "Override size" wins when present
            width, height = reported.split(":")[1].strip().split("x")
            self._size = int(width), int(height)
        return self._size

    def frame(self) -> numpy.ndarray:
        """Current screen as a BGR image. Uncompressed capture: ~3x faster than asking for a PNG."""
        data = subprocess.run([*self._base, "exec-out", "screencap"], capture_output=True, check=True).stdout
        if data[:4] == b"\x89PNG":
            image = cv2.imdecode(numpy.frombuffer(data, numpy.uint8), cv2.IMREAD_COLOR)
        else:
            width, height = (int(value) for value in numpy.frombuffer(data[:8], numpy.uint32))
            pixels = numpy.frombuffer(data[len(data) - width * height * 4 :], numpy.uint8)
            image = cv2.cvtColor(pixels.reshape(height, width, 4), cv2.COLOR_RGBA2BGR)
        if image is None:
            raise RuntimeError("ADB returned a screenshot that could not be decoded")
        return image

    def tap(self, x: int, y: int) -> None:
        subprocess.run([*self._base, "shell", "input", "tap", str(x), str(y)], check=True)

    def play(self, card_xy: tuple[int, int], square_xy: tuple[int, int]) -> None:
        """Tap the card, then the square, through one open shell. Faster than two separate commands."""
        commands = (
            f"input tap {card_xy[0]} {card_xy[1]}; input tap {square_xy[0]} {square_xy[1]}; echo played\n"
        )
        try:
            if self._session is None or self._session.poll() is not None:
                self._session = subprocess.Popen(
                    [*self._base, "shell"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            self._session.stdin.write(commands)
            self._session.stdin.flush()
            while line := self._session.stdout.readline():
                if "played" in line:
                    return
            raise BrokenPipeError("the shell closed before confirming the taps")
        except (OSError, ValueError):  # no open shell available: fall back to two separate commands
            self._session = None
            self.tap(*card_xy)
            self.tap(*square_xy)


class StreamDevice(AdbDevice):
    """Live play: the screen arrives as an H.264 video stream and `frame()` returns the newest picture.

    The stream is much faster than taking a screenshot for every reading.
    """

    STREAM_SIZE = 720  # stream width; readings are taken at 419 wide, so this is plenty

    def __init__(self, serial: str | None = None, adb_path: str = "adb", dry_run: bool = False):
        super().__init__(serial, adb_path)
        self.dry_run = dry_run
        self._latest: numpy.ndarray | None = None
        self.frame_id = 0  # counts decoded pictures, so viewers can wait for a new one
        self._latest_at = 0.0
        self._stop = False
        threading.Thread(target=self._stream, daemon=True).start()
        atexit.register(self.close)

    def _stream(self) -> None:
        import av

        size = None
        while not self._stop:  # screenrecord ends itself after 3 minutes; start the next one
            try:
                if size is None:  # also the way back after the device was unplugged while the bot started
                    width, height = self.screen_size()
                    size = f"{self.STREAM_SIZE}x{round(height * self.STREAM_SIZE / width / 2) * 2}"
                    # A bot process that crashed or was killed leaves its recorder running on the device.
                    self._shell("pkill", "-f", "screenrecord")
                self._record_once(av, size)
            except Exception as error:  # noqa: BLE001 (the stream thread must never die)
                print(f"video stream interrupted ({error!r}) — restarting it", flush=True)
                time.sleep(1)
            time.sleep(0.2)

    def _record_once(self, av, size: str) -> None:
        command = [*self._base, "exec-out", "screenrecord", "--output-format=h264", "--size", size]
        self._process = subprocess.Popen(
            [*command, "--bit-rate", "8M", "--time-limit", "180", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        decoder = av.CodecContext.create("h264", "r")
        decoder.thread_count = 1  # frame threading would hold pictures back; one thread decodes 720p easily
        pipe = self._process.stdout.fileno()
        # os.read returns whatever has arrived. A fixed-size read would sit on finished frames
        # whenever a calm screen makes the bitrate drop.
        while chunk := os.read(pipe, 1 << 16):
            try:
                pictures = [picture for packet in decoder.parse(chunk) for picture in decoder.decode(packet)]
            except av.error.FFmpegError:
                continue  # a damaged packet (typical right after a restart): the next keyframe recovers
            if pictures:
                # PyAV frames must be converted in this thread only. Converting one frame from
                # several threads crashes in libswscale.
                self._latest = pictures[-1].to_ndarray(format="bgr24")
                self.frame_id += len(pictures)
                self._latest_at = time.time()
        self._process.wait()

    def frame(self) -> numpy.ndarray:
        deadline = time.time() + 5
        while self._latest is None and time.time() < deadline:
            time.sleep(0.02)
        # A still screen sends no new video frames, so an old picture is still the current screen.
        return self._latest.copy() if self._latest is not None else super().frame()

    def tap(self, x: int, y: int) -> None:
        if not self.dry_run:
            super().tap(x, y)

    def play(self, card_xy: tuple[int, int], square_xy: tuple[int, int]) -> None:
        if not self.dry_run:
            super().play(card_xy, square_xy)

    def close(self) -> None:
        self._stop = True
        if getattr(self, "_process", None):
            self._process.terminate()


class ImageDevice(AdbDevice):
    """A saved screenshot standing in for the emulator: see the whole pipeline with no emulator attached."""

    def __init__(self, path: str):
        self._frame = cv2.imread(path)
        if self._frame is None:
            raise FileNotFoundError(path)

    def screen_size(self) -> tuple[int, int]:
        return self._frame.shape[1], self._frame.shape[0]

    def frame(self) -> numpy.ndarray:
        return self._frame.copy()

    def tap(self, x: int, y: int) -> None:
        pass

    def play(self, card_xy: tuple[int, int], square_xy: tuple[int, int]) -> None:
        pass
