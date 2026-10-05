"""资源索引：扫描 resource 目录，按分类提供动画与音频路径。"""
import json
import random
from pathlib import Path
from typing import Optional

from .config import RESOURCE_DIR

VIDEO_EXTS = {".webm", ".mp4", ".mov"}


class ResourceLibrary:
    def __init__(self, root: Path = RESOURCE_DIR):
        self.root = root
        self.video_dir = root / "videos"
        self.sound_dir = root / "sounds"
        self._clips: dict[str, list[Path]] = {}
        self.scan()

    def scan(self):
        """以 videos 下的子目录（相对路径，如 'events/balance'）为分类名。"""
        self._clips.clear()
        if not self.video_dir.is_dir():
            return
        for file in self.video_dir.rglob("*"):
            if file.suffix.lower() in VIDEO_EXTS:
                category = file.parent.relative_to(self.video_dir).as_posix()
                self._clips.setdefault(category, []).append(file)
        for files in self._clips.values():
            files.sort()

    @property
    def categories(self) -> list[str]:
        return sorted(self._clips)

    def clips(self, category: str) -> list[Path]:
        return list(self._clips.get(category, []))

    def random_clip(self, category: str, exclude: Optional[Path] = None) -> Optional[Path]:
        files = self._clips.get(category, [])
        candidates = [f for f in files if f != exclude] or files
        return random.choice(candidates) if candidates else None

    def find_clip(self, category: str, name: str) -> Optional[Path]:
        return next((f for f in self._clips.get(category, []) if f.stem == name), None)

    def body_box(self) -> Optional[tuple[int, int, int, int]]:
        """manifest.json 中桌宠身体在视频画面里的范围 (left, top, right, bottom)。"""
        try:
            with open(self.video_dir / "manifest.json", encoding="utf-8") as f:
                box = json.load(f).get("body_box")
            return tuple(int(v) for v in box) if box and len(box) == 4 else None
        except (OSError, ValueError, TypeError):
            return None

    def sound(self, relative: str) -> Optional[Path]:
        path = self.sound_dir / relative
        return path if path.is_file() else None

    @property
    def icon(self) -> Path:
        return self.root / "icon.ico"
