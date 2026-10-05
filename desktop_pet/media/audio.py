"""简单音效播放器：新音效会打断正在播放的音效。"""
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

log = logging.getLogger(__name__)


class SoundPlayer(QObject):
    def __init__(self, volume: int = 80, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._player.setVolume(volume)
        self._player.error.connect(lambda _: log.warning("音频播放失败: %s", self._player.errorString()))

    def play(self, path: Path):
        self._player.stop()
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(str(path))))
        self._player.play()

    def stop(self):
        self._player.stop()

    def set_volume(self, volume: int):
        self._player.setVolume(volume)
