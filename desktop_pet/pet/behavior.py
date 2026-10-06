"""行为控制器：一个小型状态机，决定在什么事件下播放哪段动画和音效。

    IDLE ──随机计时──> ACTION ──播完──> IDLE
      │ 点击                              ^
      v                                   │
    CLICK ──播完────────────────────────>─┤
    任意状态 ──拖拽开始──> DRAG ──拖拽结束─┘
"""
import logging
import random
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, QPoint, QTimer

from ..media import SoundPlayer, VideoPlayer
from ..resources import ResourceLibrary

log = logging.getLogger(__name__)

# 动画分类（对应 resource/videos 下的子目录）
CAT_IDLE = "idle"
CAT_CLICK = "click"
CAT_DRAG = "drag"
CAT_RANDOM = "random"


class PetState(Enum):
    IDLE = auto()
    ACTION = auto()   # 一次性动作（随机动作或外部触发的动作）
    CLICK = auto()
    DRAG = auto()


class BehaviorController(QObject):
    def __init__(self, player: VideoPlayer, sounds: SoundPlayer, resources: ResourceLibrary,
                 behavior_config: dict, sound_config: dict, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.player = player
        self.sounds = sounds
        self.resources = resources
        self.behavior_config = behavior_config
        self.sound_config = sound_config
        self.state = PetState.IDLE
        self._last_clip: Optional[Path] = None

        self._random_timer = QTimer(self)
        self._random_timer.setSingleShot(True)
        self._random_timer.timeout.connect(self._on_random_timeout)

        player.finished.connect(self._on_clip_finished)
        player.error.connect(self._on_clip_error)

    # ---- 对外接口 ----
    def start(self):
        self._enter_idle()

    def pause(self):
        """停止动画和随机动作（如桌宠被隐藏时），调用 start() 恢复。"""
        self._random_timer.stop()
        self.state = PetState.IDLE
        self.player.stop()

    def on_clicked(self, _pos: QPoint = QPoint()):
        if self.state != PetState.DRAG:
            self._play_once(CAT_CLICK, PetState.CLICK, sound_key="click")

    def on_drag_started(self):
        clip = self._pick(CAT_DRAG)
        self._set_state(PetState.DRAG)
        if clip:
            self._play(clip, loop=True)
        self.play_sound("drag")

    def on_drag_finished(self, _pos: QPoint = QPoint()):
        if self.state == PetState.DRAG:
            self._enter_idle()

    def perform(self, category: str, name: Optional[str] = None,
                sound_key: Optional[str] = None) -> bool:
        """播放一次指定动作，结束后自动回到待机。拖拽中不会被打断。"""
        if self.state == PetState.DRAG:
            return False
        return self._play_once(category, PetState.ACTION, name=name, sound_key=sound_key)

    def set_random_enabled(self, enabled: bool):
        self.behavior_config["random_action_interval"] = (
            self.behavior_config.get("random_action_interval") or [20, 60]) if enabled else None
        self._schedule_random()

    def play_sound(self, key: str):
        candidates = [p for p in map(self.resources.sound, self.sound_config.get(key, [])) if p]
        if candidates:
            self.sounds.play(random.choice(candidates))

    # ---- 内部 ----
    def _set_state(self, state: PetState):
        self.state = state
        self._schedule_random()

    def _pick(self, category: str, name: Optional[str] = None) -> Optional[Path]:
        clip = self.resources.find_clip(category, name) if name else \
            self.resources.random_clip(category, exclude=self._last_clip)
        if clip is None:
            log.warning("找不到动画: %s/%s", category, name or "*")
        return clip

    def _play(self, clip: Path, loop: bool = False):
        self._last_clip = clip
        self.player.play(clip, loop=loop)

    def _play_once(self, category: str, state: PetState, name: Optional[str] = None,
                   sound_key: Optional[str] = None) -> bool:
        clip = self._pick(category, name)
        if clip is None:
            return False
        self._set_state(state)
        self._play(clip)
        if sound_key:
            self.play_sound(sound_key)
        return True

    def _enter_idle(self):
        self._set_state(PetState.IDLE)
        clip = self._pick(CAT_IDLE)
        if clip:
            self._play(clip, loop=True)

    def _schedule_random(self):
        self._random_timer.stop()
        interval = self.behavior_config.get("random_action_interval")
        if self.state == PetState.IDLE and interval:
            low, high = interval
            self._random_timer.start(int(random.uniform(low, high) * 1000))

    def _on_random_timeout(self):
        if self.state == PetState.IDLE:
            self._play_once(CAT_RANDOM, PetState.ACTION, sound_key="idle")

    def _on_clip_finished(self, _path: Path):
        if self.state in (PetState.ACTION, PetState.CLICK):
            self._enter_idle()

    def _on_clip_error(self, path: Path, message: str):
        log.error("动画播放失败 %s: %s", path, message)
        if self.state != PetState.IDLE:  # 待机动画本身出错时不再重试，避免死循环
            self._enter_idle()
