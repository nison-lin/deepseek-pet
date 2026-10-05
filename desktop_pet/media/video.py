"""带透明通道的视频播放器。

在后台线程中用 PyAV 解码（VP8/VP9 使用 libvpx 以保留 alpha 通道），
按视频帧率把 QImage 帧通过信号发送到主线程。播放器只负责“播放”，不关心业务含义。
"""
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import av
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QImage

log = logging.getLogger(__name__)

ALPHA_CUTOFF = 16  # 低于该值的半透明噪点视为全透明，使其可被鼠标穿透


def _create_decoder(stream):
    """FFmpeg 内置的 vp8/vp9 解码器会丢弃 alpha，优先使用 libvpx。"""
    name = stream.codec_context.name
    if name in ("vp8", "vp9"):
        try:
            return av.CodecContext.create(f"libvpx-{name}", "r")
        except Exception:  # noqa: BLE001 - 缺少 libvpx 时退回默认解码器
            log.warning("libvpx-%s 不可用，透明通道将丢失", name)
    return stream.codec_context


def _to_qimage(frame, width: int, height: int) -> QImage:
    rgba = np.ascontiguousarray(frame.reformat(width=width, height=height, format="rgba").to_ndarray())
    alpha = rgba[..., 3]
    alpha[alpha < ALPHA_CUTOFF] = 0
    image = QImage(rgba.data, width, height, rgba.strides[0], QImage.Format_RGBA8888)
    # 转换会深拷贝数据，脱离 numpy 缓冲区；预乘格式绘制更快
    return image.convertToFormat(QImage.Format_ARGB32_Premultiplied)


class VideoPlayer(QObject):
    frame_ready = pyqtSignal(QImage)
    finished = pyqtSignal(object)        # 片段正常播完（循环播放不会触发），参数为路径
    error = pyqtSignal(object, str)      # 片段解码失败

    # 内部信号携带“代号”，用于丢弃已被 stop/play 打断的旧线程发来的帧
    _frame = pyqtSignal(int, QImage)
    _ended = pyqtSignal(int, object)
    _failed = pyqtSignal(int, object, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.target_size: Optional[tuple[int, int]] = None  # 输出尺寸，None 为原始尺寸
        self.current: Optional[Path] = None
        self._generation = 0
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._frame.connect(self._on_frame)
        self._ended.connect(self._on_ended)
        self._failed.connect(self._on_failed)

    @staticmethod
    def probe_size(path: Path) -> tuple[int, int]:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            return stream.width, stream.height

    def play(self, path: Path, loop: bool = False):
        self.stop()
        stop_event = threading.Event()
        self._stop_event = stop_event
        self.current = path
        self._thread = threading.Thread(
            target=self._run,
            args=(self._generation, path, loop, stop_event, self.target_size),
            name=f"video-{path.stem}",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        if self._stop_event:
            self._stop_event.set()
            self._stop_event = None
        self._generation += 1
        self.current = None

    def shutdown(self, timeout: float = 1.0):
        thread = self._thread
        self.stop()
        if thread and thread.is_alive():
            thread.join(timeout)

    # ---- 后台线程 ----
    def _run(self, gen: int, path: Path, loop: bool, stop: threading.Event, size):
        try:
            while not stop.is_set():
                self._decode_once(gen, path, stop, size)
                if not loop:
                    break
        except Exception as e:  # noqa: BLE001
            log.exception("播放视频失败: %s", path)
            if not stop.is_set():
                self._failed.emit(gen, path, str(e))
            return
        if not stop.is_set():
            self._ended.emit(gen, path)

    def _decode_once(self, gen: int, path: Path, stop: threading.Event, size):
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            decoder = _create_decoder(stream)
            interval = 1.0 / float(stream.average_rate or 24)
            width, height = size or (stream.width, stream.height)
            next_time = time.perf_counter()
            for packet in container.demux(stream):
                for frame in decoder.decode(packet):
                    if stop.is_set():
                        return
                    image = _to_qimage(frame, width, height)
                    delay = next_time - time.perf_counter()
                    if delay > 0:
                        if stop.wait(delay):
                            return
                    elif delay < -interval * 5:
                        next_time = time.perf_counter()  # 严重落后时重新对齐，避免快进
                    self._frame.emit(gen, image)
                    next_time += interval

    # ---- 主线程 ----
    def _on_frame(self, gen: int, image: QImage):
        if gen == self._generation:
            self.frame_ready.emit(image)

    def _on_ended(self, gen: int, path: Path):
        if gen == self._generation:
            self.current = None
            self.finished.emit(path)

    def _on_failed(self, gen: int, path: Path, message: str):
        if gen == self._generation:
            self.current = None
            self.error.emit(path, message)
