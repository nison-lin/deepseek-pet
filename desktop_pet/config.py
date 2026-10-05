"""配置加载与保存。

用户配置保存在项目根目录的 config.json 中，缺失的字段使用 DEFAULT_CONFIG 补齐。
"""
import copy
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
RESOURCE_DIR = ROOT_DIR / "resource"
CONFIG_PATH = ROOT_DIR / "config.json"

DEFAULT_CONFIG = {
    "window": {
        "scale": 0.6,           # 相对于视频原始尺寸的缩放
        "position": None,       # [x, y]，None 表示放在屏幕右下角
        "always_on_top": True,
    },
    "behavior": {
        "random_action_interval": [20, 60],  # 待机时随机动作的间隔（秒），设为 null 关闭
        "drag_threshold": 4,                 # 鼠标移动超过多少像素算拖拽
        "long_press_ms": 400,                # 按住不动超过多少毫秒也算拖拽，0 表示关闭
    },
    "sounds": {
        # 各事件对应的音频（相对 resource/sounds），多个则随机播放一个
        "volume": 80,
        "click": ["duck/Ya1.mp3"],
        "drag": ["duck/Ya1.mp3"],
        "idle": [],                 # 待机时触发随机小动作时播放，留空则不出声
        "menu": ["duck/Ya2.mp3"],   # 右键打开菜单时播放
        "chat_start": ["agent/start.wav"],
        "chat_done": ["agent/done.wav"],
        "chat_error": ["agent/error.wav"],
    },
    "chat": {
        "hotkey": "Alt+Shift+C",  # 如 "F8"、"Ctrl+Num5"，修饰键可省略
        "api_key": "",          # 留空则读取环境变量 DEEPSEEK_API_KEY
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "system_prompt": "你是一只可爱的桌面宠物“大肥鱼”，说话简短、活泼。",
        "max_history": 20,      # 保留的历史消息条数（不含 system）
    },
    "balance": {
        "refresh_interval": 300,  # 自动刷新间隔（秒），0 表示只手动刷新
        "current": 0,             # 当前查看的中转站序号
        "relays": [],
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


_MISSING = object()


def _sync(current: dict, base: dict, disk: dict):
    """三方合并（原地修改 current）：本进程没改过的字段（与 base 相同）采用 disk 上的新值。"""
    for key, disk_value in disk.items():
        value = current.get(key, _MISSING)
        if isinstance(value, dict) and isinstance(disk_value, dict):
            sub_base = base.get(key)
            _sync(value, sub_base if isinstance(sub_base, dict) else {}, disk_value)
        elif value is _MISSING or value == base.get(key, _MISSING):
            current[key] = copy.deepcopy(disk_value)


class Config:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.data = copy.deepcopy(DEFAULT_CONFIG)
        self._snapshot = copy.deepcopy(self.data)  # 上次读写文件时的内容，用于判断本进程改了什么
        self.load()

    def _read(self):
        if not self.path.exists():
            return None
        try:
            with open(self.path, encoding="utf-8") as f:
                return _deep_merge(DEFAULT_CONFIG, json.load(f))
        except (OSError, json.JSONDecodeError) as e:
            log.error("读取配置失败: %s", e)
            return None

    def load(self):
        if not self.path.exists():
            self.save()
            return
        disk = self._read()
        if disk is None:
            log.error("使用默认配置")
            return
        self.data = disk
        self._snapshot = copy.deepcopy(disk)

    def save(self):
        """只写回本进程改动过的字段，运行期间在外部对 config.json 的修改不会被覆盖，并会同步到内存。"""
        disk = self._read()
        if disk is not None:
            _sync(self.data, self._snapshot, disk)
        self._snapshot = copy.deepcopy(self.data)
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.error("保存配置失败: %s", e)

    def section(self, name: str) -> dict:
        return self.data.setdefault(name, {})

    @property
    def api_key(self) -> str:
        return self.data["chat"].get("api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
