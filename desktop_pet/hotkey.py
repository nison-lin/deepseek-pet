"""全局快捷键（Windows，基于 RegisterHotKey，无需额外依赖）以及快捷键录制对话框。

快捷键以 "修饰键+...+按键" 文本保存，例如 "Alt+Shift+C"、"F8"、"Ctrl+Num5"、"Pause"。
修饰键可有可无，按键可以是任意虚拟键（字母、数字、符号、F1-F24、小键盘、媒体键等）。
"""
import ctypes
import logging
import re
import sys
from ctypes import wintypes
from typing import Callable, Optional

from PyQt5.QtCore import QAbstractNativeEventFilter, QCoreApplication, QEvent, Qt, pyqtSignal
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

# 修饰键的显示顺序与 Qt 一致，保证旧配置（如 "Alt+Shift+C"）格式不变
_MOD_NAMES = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))
_MOD_ALIASES = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
                "shift": MOD_SHIFT, "win": MOD_WIN, "meta": MOD_WIN}
_QT_MODIFIERS = {Qt.ControlModifier: MOD_CONTROL, Qt.AltModifier: MOD_ALT,
                 Qt.ShiftModifier: MOD_SHIFT, Qt.MetaModifier: MOD_WIN}
# 修饰键自身的虚拟键码（含左右区分）-> 对应的修饰标志
_MODIFIER_VKS = {0x10: MOD_SHIFT, 0xA0: MOD_SHIFT, 0xA1: MOD_SHIFT,
                 0x11: MOD_CONTROL, 0xA2: MOD_CONTROL, 0xA3: MOD_CONTROL,
                 0x12: MOD_ALT, 0xA4: MOD_ALT, 0xA5: MOD_ALT, 0x5B: MOD_WIN, 0x5C: MOD_WIN}

# 虚拟键码 -> 显示名称
_VK_NAMES = {
    0x03: "Break", 0x08: "Backspace", 0x09: "Tab", 0x0C: "Clear", 0x0D: "Enter",
    0x13: "Pause", 0x14: "CapsLock", 0x1B: "Esc", 0x20: "Space",
    0x21: "PgUp", 0x22: "PgDown", 0x23: "End", 0x24: "Home",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2C: "Print", 0x2D: "Ins", 0x2E: "Del", 0x5D: "Menu",
    0x6A: "Num*", 0x6B: "Num+", 0x6C: "NumSeparator", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/",
    0x90: "NumLock", 0x91: "ScrollLock",
    0xA6: "BrowserBack", 0xA7: "BrowserForward", 0xA8: "BrowserRefresh", 0xA9: "BrowserStop",
    0xAA: "BrowserSearch", 0xAB: "BrowserFavorites", 0xAC: "BrowserHome",
    0xAD: "VolumeMute", 0xAE: "VolumeDown", 0xAF: "VolumeUp",
    0xB0: "MediaNext", 0xB1: "MediaPrevious", 0xB2: "MediaStop", 0xB3: "MediaPlay",
    0xB4: "LaunchMail", 0xB5: "LaunchMedia", 0xB6: "LaunchApp1", 0xB7: "LaunchApp2",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
_VK_NAMES.update({vk: chr(vk) for vk in range(0x30, 0x3A)})  # 0-9
_VK_NAMES.update({vk: chr(vk) for vk in range(0x41, 0x5B)})  # A-Z
_VK_NAMES.update({0x60 + i: f"Num{i}" for i in range(10)})
_VK_NAMES.update({0x70 + i: f"F{i + 1}" for i in range(24)})
# 名称（小写）-> 虚拟键码，额外兼容 Qt 及常见写法
_NAME_TO_VK = {name.lower(): vk for vk, name in _VK_NAMES.items()}
_NAME_TO_VK.update({
    "return": 0x0D, "escape": 0x1B, "pageup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "insert": 0x2D, "delete": 0x2E, "printscreen": 0x2C, "prtsc": 0x2C, "apps": 0x5D,
})
_VK_CODE_RE = re.compile(r"vk_([0-9a-f]{1,2})")


def format_hotkey(modifiers: int, vk: int) -> str:
    names = [name for mod, name in _MOD_NAMES if modifiers & mod]
    names.append(_VK_NAMES.get(vk, f"VK_{vk:02X}"))
    return "+".join(names)


def _key_to_vk(name: str) -> Optional[tuple[int, int]]:
    """按键名称 -> (需要附加的修饰键, 虚拟键码)。"""
    vk = _NAME_TO_VK.get(name.lower())
    if vk:
        return 0, vk
    match = _VK_CODE_RE.fullmatch(name.lower())
    if match:
        return 0, int(match.group(1), 16)
    if len(name) == 1 and sys.platform == "win32":
        # 其他符号（如 "!"、"+"）按当前键盘布局换算，例如 "!" -> Shift+1
        res = ctypes.windll.user32.VkKeyScanW(ord(name)) & 0xFFFF
        if res != 0xFFFF:
            shift_state = res >> 8
            mods = ((MOD_SHIFT if shift_state & 1 else 0) | (MOD_CONTROL if shift_state & 2 else 0)
                    | (MOD_ALT if shift_state & 4 else 0))
            return mods, res & 0xFF
    return None


def parse_hotkey(text: str) -> Optional[tuple[int, int]]:
    """把 'Ctrl+Alt+D'、'F8' 这样的文本解析为 (Win32 修饰键, 虚拟键码)，修饰键可以为空。"""
    rest = text.strip()
    modifiers = 0
    # 逐个剥离前缀修饰键，剩下的整体作为按键名（因此 "Ctrl++"、"Num+" 也能正确解析）
    while "+" in rest[:-1]:
        head, tail = rest.split("+", 1)
        mod = _MOD_ALIASES.get(head.strip().lower())
        if mod is None:
            break
        modifiers |= mod
        rest = tail.strip()
    key = _key_to_vk(rest) if rest else None
    if key is None:
        return None
    return modifiers | key[0], key[1]


def _qt_to_win_modifiers(qt_mods) -> int:
    return sum(win for qt, win in _QT_MODIFIERS.items() if int(qt_mods) & int(qt))


def _is_typing_key(modifiers: int, vk: int) -> bool:
    """不带 Ctrl/Alt/Win 的字母、数字、空格、符号键会影响其他程序的正常打字。"""
    if modifiers & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        return False
    return (vk == 0x20 or 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A
            or 0xBA <= vk <= 0xC0 or 0xDB <= vk <= 0xDE)

class GlobalHotkeyManager(QAbstractNativeEventFilter):
    """注册系统级快捷键，按下时在 Qt 主线程中调用回调。"""

    def __init__(self):
        super().__init__()
        self.supported = sys.platform == "win32"
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1
        if self.supported:
            self._user32 = ctypes.windll.user32
            QCoreApplication.instance().installNativeEventFilter(self)
        else:
            log.warning("当前平台不支持全局快捷键")

    def register(self, hotkey: str, callback: Callable[[], None]) -> Optional[int]:
        """注册成功返回 id，失败（格式错误或被其他程序占用）返回 None。"""
        parsed = parse_hotkey(hotkey)
        if not self.supported or parsed is None:
            log.warning("无法注册快捷键: %s", hotkey)
            return None
        modifiers, vk = parsed
        hotkey_id = self._next_id
        if not self._user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk):
            log.warning("快捷键 %s 注册失败，可能已被其他程序占用", hotkey)
            return None
        self._next_id += 1
        self._callbacks[hotkey_id] = callback
        return hotkey_id

    def unregister(self, hotkey_id: Optional[int]):
        if hotkey_id in self._callbacks:
            self._user32.UnregisterHotKey(None, hotkey_id)
            del self._callbacks[hotkey_id]

    def unregister_all(self):
        for hotkey_id in list(self._callbacks):
            self.unregister(hotkey_id)

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam in self._callbacks:
                self._callbacks[msg.wParam]()
                return True, 0
        return False, 0


class HotkeyRecorder(QLineEdit):
    """按键录制框：直接读取原生虚拟键码，单键、小键盘、媒体键、Tab/Esc/Enter 等都能录入。"""

    changed = pyqtSignal(str)

    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignCenter)
        parsed = parse_hotkey(current) if current else None
        self.hotkey = format_hotkey(*parsed) if parsed else current
        self.setText(self.hotkey)

    def event(self, e):
        # 抢在焦点切换、对话框默认按钮和快捷键之前处理所有按键
        if e.type() == QEvent.ShortcutOverride:
            e.accept()
            return True
        if e.type() == QEvent.KeyPress:
            self.keyPressEvent(e)
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        vk = e.nativeVirtualKey()
        mods = _qt_to_win_modifiers(e.modifiers())
        if vk in _MODIFIER_VKS:
            # Qt 对修饰键自身的事件会翻转对应标志位，这里按键码补回
            self._show_modifiers(mods | _MODIFIER_VKS[vk])
        elif vk:
            self._record(mods, vk)

    def keyReleaseEvent(self, e):
        vk = e.nativeVirtualKey()
        mods = _qt_to_win_modifiers(e.modifiers())
        if vk == 0x2C and not e.isAutoRepeat():
            # Windows 下 PrintScreen 通常只有松开事件
            self._record(mods, vk)
        elif vk in _MODIFIER_VKS:
            self._show_modifiers(mods & ~_MODIFIER_VKS[vk])

    def _show_modifiers(self, mods: int):
        if mods:
            self.setText("+".join(name for mod, name in _MOD_NAMES if mods & mod) + "+…")
        else:
            self.setText(self.hotkey)

    def _record(self, modifiers: int, vk: int):
        self.hotkey = format_hotkey(modifiers, vk)
        self.setText(self.hotkey)
        self.changed.emit(self.hotkey)


class HotkeyEditDialog(QDialog):
    def __init__(self, current: str, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("设置聊天快捷键")
        self.recorder = HotkeyRecorder(current, self)
        self.warning = QLabel(self)
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #c0392b;")
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("请按下新的快捷键（单个按键或任意组合均可，如 F8、Pause、Ctrl+Num5）："))
        layout.addWidget(self.recorder)
        layout.addWidget(self.warning)
        layout.addWidget(self.buttons)
        self.recorder.changed.connect(self._on_changed)
        self._on_changed(self.recorder.hotkey)
        self.recorder.setFocus()

    def _on_changed(self, hotkey: str):
        parsed = parse_hotkey(hotkey) if hotkey else None
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(parsed is not None)
        if parsed and _is_typing_key(*parsed):
            self.warning.setText("提示：该按键没有 Ctrl/Alt/Win 修饰，设置后在其他程序中将无法正常输入这个键。")
        else:
            self.warning.clear()
        self.warning.setVisible(bool(self.warning.text()))

    @classmethod
    def ask(cls, current: str, parent=None) -> Optional[str]:
        dialog = cls(current, parent)
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.recorder.hotkey or None
