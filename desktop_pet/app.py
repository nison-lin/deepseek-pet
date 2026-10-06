"""应用组装层：创建各模块并用信号把它们连接起来。

各模块之间互不引用，所有跨模块的协作都在这里完成。新增功能时通常只需：
1. 在独立模块中实现功能；
2. 在这里创建实例、连接信号、在 _build_menu 中注册菜单项。
"""
import logging
import sys
from typing import Optional

from PyQt5.QtCore import QPoint, QPointF, QSize, Qt
from PyQt5.QtGui import QGuiApplication, QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox

from .balance import BalanceMonitor, BalanceSign, Relay, RelayDialog, format_amount
from .chat import ChatDialog, ChatSession, DeepSeekClient
from .config import Config
from .hotkey import GlobalHotkeyManager, HotkeyEditDialog, parse_hotkey
from .media import SoundPlayer, VideoPlayer
from .pet import BehaviorController, PetMenu, PetWindow
from .pet.behavior import CAT_IDLE
from .resources import ResourceLibrary

log = logging.getLogger(__name__)

PET_NAME = "大肥鱼"
SCALE_OPTIONS = [0.4, 0.5, 0.6, 0.8, 1.0]


class DesktopPetApp:
    def __init__(self, qt_app: QApplication):
        self.qt_app = qt_app
        self.config = Config()
        self.resources = ResourceLibrary()
        if self.resources.icon.exists():
            qt_app.setWindowIcon(QIcon(str(self.resources.icon)))

        window_cfg = self.config.section("window")
        behavior_cfg = self.config.section("behavior")
        sound_cfg = self.config.section("sounds")

        # 媒体
        self.video = VideoPlayer()
        self.sounds = SoundPlayer(volume=sound_cfg.get("volume", 80))

        # 桌宠窗口与行为
        base_size = self._detect_base_size()
        self.window = PetWindow(
            base_size=base_size,
            scale=window_cfg.get("scale", 0.6),
            drag_threshold=behavior_cfg.get("drag_threshold", 4),
            long_press_ms=behavior_cfg.get("long_press_ms", 400),
            always_on_top=window_cfg.get("always_on_top", True),
            foot_anchor=self._detect_foot_anchor(base_size),
        )
        self.behavior = BehaviorController(self.video, self.sounds, self.resources,
                                           behavior_cfg, sound_cfg)
        self.menu = PetMenu(self.window)

        # 脚下的余额牌子
        balance_cfg = self.config.section("balance")
        self.balance_sign = BalanceSign()
        self.window.set_footer(self.balance_sign, overlap=0.06)  # 鞋底刚好压在木板上沿
        self.balance_monitor = BalanceMonitor(balance_cfg.get("refresh_interval", 300))

        # 聊天
        chat_cfg = self.config.section("chat")
        self.chat_session = ChatSession(chat_cfg.get("system_prompt", ""), chat_cfg.get("max_history", 20))
        self.chat_dialog = ChatDialog(self._create_chat_client, self.chat_session, PET_NAME)
        self.hotkeys = GlobalHotkeyManager()
        # 全局快捷键：功能名 -> 配置所在小节、菜单显示名、回调；菜单项在 _build_menu 中补上
        self._hotkey_specs = {
            "chat": {"section": "chat", "label": "聊天快捷键", "callback": self.toggle_chat},
            "pet": {"section": "window", "label": "隐藏/显示快捷键", "callback": self.toggle_pet},
        }
        self._hotkey_ids: dict[str, Optional[int]] = {}

        self._connect_signals()
        self._build_menu()

    # ---- 组装 ----
    def _detect_base_size(self) -> QSize:
        clip = self.resources.random_clip(CAT_IDLE)
        if clip:
            try:
                return QSize(*VideoPlayer.probe_size(clip))
            except Exception:  # noqa: BLE001
                log.exception("读取视频尺寸失败: %s", clip)
        return QSize(640, 360)

    def _detect_foot_anchor(self, base_size: QSize) -> QPointF:
        """脚底中心：取 manifest 中身体范围的底边中点。"""
        box = self.resources.body_box()
        if box:
            left, _top, right, bottom = box
            return QPointF((left + right) / 2, bottom)
        return QPointF(base_size.width() / 2, base_size.height() * 0.92)

    def _connect_signals(self):
        self.video.frame_ready.connect(self.window.set_frame)
        self.window.clicked.connect(self.behavior.on_clicked)
        self.window.drag_started.connect(self.behavior.on_drag_started)
        self.window.drag_finished.connect(self.behavior.on_drag_finished)
        self.window.drag_finished.connect(self._save_position)
        self.window.menu_requested.connect(lambda _: self.behavior.play_sound("menu"))  # 先于菜单弹出
        self.window.menu_requested.connect(self.menu.show_at)

        self.chat_dialog.request_started.connect(self._on_chat_started)
        self.chat_dialog.reply_finished.connect(lambda _: self.behavior.play_sound("chat_done"))
        self.chat_dialog.request_failed.connect(lambda _: self.behavior.play_sound("chat_error"))

        self.balance_monitor.refreshing.connect(lambda _: self.balance_sign.show_loading())
        self.balance_monitor.updated.connect(lambda r: self.balance_sign.show_amount(format_amount(r.amount)))
        self.balance_monitor.failed.connect(lambda _, e: self.balance_sign.show_error(e.short))

        self.qt_app.aboutToQuit.connect(self._shutdown)

    def _build_menu(self):
        """右键菜单，后续功能在此注册即可。"""
        self.menu.add_item("聊天", self.toggle_chat)
        self.menu.add_item("隐藏桌宠", self.toggle_pet)
        for name, spec in self._hotkey_specs.items():
            spec["action"] = self.menu.add_item("", lambda n=name: self._edit_hotkey(n))
            self._update_hotkey_label(name, self.config.section(spec["section"]).get("hotkey", ""))
        self.menu.addSeparator()

        self.menu.add_item("立即刷新余额", self.balance_monitor.refresh)
        self.menu.add_item("更换中转站", self._edit_relays)
        self.menu.addSeparator()

        self.menu.add_submenu("大小").add_choices(
            [(f"{int(s * 100)}%", s) for s in SCALE_OPTIONS],
            self.config.section("window").get("scale"),
            self.set_scale,
        )

        interval = self.config.section("behavior").get("random_action_interval")
        self.menu.add_item("随机动作", self._set_random_enabled, checkable=True, checked=bool(interval))
        self.menu.addSeparator()
        self.menu.add_item("退出", self.qt_app.quit)

    # ---- 启动 / 退出 ----
    def start(self):
        self.window.show()
        self._restore_position()
        self.behavior.start()
        for name, spec in self._hotkey_specs.items():
            self._register_hotkey(name, self.config.section(spec["section"]).get("hotkey", ""))
        self._apply_relay()

    def _shutdown(self):
        self.hotkeys.unregister_all()
        self.balance_monitor.stop()
        self.video.shutdown()
        self._save_position(self.window.pos())

    # ---- 余额 ----
    def _relays(self) -> tuple[list[Relay], int]:
        cfg = self.config.section("balance")
        relays = [Relay.from_dict(r) for r in cfg.get("relays", []) if isinstance(r, dict)]
        current = cfg.get("current", 0)
        return relays, current if 0 <= current < len(relays) else 0

    def _apply_relay(self):
        relays, current = self._relays()
        if not relays:
            self.balance_sign.set_title("")
            self.balance_sign.show_error("未配置中转站")
            return
        self.balance_sign.set_title(relays[current].name)
        self.balance_monitor.set_relay(relays[current])

    def _edit_relays(self):
        relays, current = self._relays()
        result = RelayDialog.ask(relays, current)
        if result is None:
            return
        relays, current = result
        cfg = self.config.section("balance")
        cfg["relays"] = [r.to_dict() for r in relays]
        cfg["current"] = current
        self.config.save()
        self._apply_relay()

    # ---- 功能 ----
    def toggle_chat(self):
        self.chat_dialog.toggle(anchor=self.window)

    def _create_chat_client(self) -> Optional[DeepSeekClient]:
        api_key = self.config.api_key
        if not api_key:
            return None
        chat_cfg = self.config.section("chat")
        return DeepSeekClient(api_key, chat_cfg.get("base_url", "https://api.deepseek.com"),
                              chat_cfg.get("model", "deepseek-chat"))

    def _on_chat_started(self):
        self.behavior.play_sound("chat_start")
        self.behavior.perform("random", name="工作状态-思考冒泡")

    def _register_hotkey(self, name: str, hotkey: str) -> bool:
        spec = self._hotkey_specs[name]
        self.hotkeys.unregister(self._hotkey_ids.get(name))
        self._hotkey_ids[name] = self.hotkeys.register(hotkey, spec["callback"]) if hotkey else None
        self._update_hotkey_label(name, hotkey)
        return self._hotkey_ids[name] is not None

    def _edit_hotkey(self, name: str):
        spec = self._hotkey_specs[name]
        cfg = self.config.section(spec["section"])
        old = cfg.get("hotkey", "")
        new = HotkeyEditDialog.ask(old, title=f"设置{spec['label']}")
        if not new or new == old:
            return
        parsed = parse_hotkey(new)
        for other, other_spec in self._hotkey_specs.items():
            other_key = self.config.section(other_spec["section"]).get("hotkey", "")
            if other != name and other_key and parse_hotkey(other_key) == parsed:
                QMessageBox.warning(None, "快捷键", f"{new} 已被“{other_spec['label']}”使用，请换一个。")
                return
        if self._register_hotkey(name, new):
            cfg["hotkey"] = new
            self.config.save()
        else:
            QMessageBox.warning(None, "快捷键", f"快捷键 {new} 无法注册（格式不支持或已被占用），已恢复为 {old}。")
            self._register_hotkey(name, old)

    def _update_hotkey_label(self, name: str, hotkey: str):
        spec = self._hotkey_specs[name]
        state = hotkey if self._hotkey_ids.get(name) is not None else f"{hotkey}（未生效）"
        spec["action"].setText(f"{spec['label']}：{state}")

    def toggle_pet(self):
        """隐藏 / 显示桌宠，隐藏期间暂停动画以节省资源。"""
        if self.window.isVisible():
            self.menu.hide()
            self.behavior.pause()
            self.window.hide()
        else:
            self.window.show()
            self.window.raise_()
            self.behavior.start()

    def set_scale(self, scale: float):
        center = self.window.frameGeometry().center()
        self.window.set_scale(scale)
        self.window.move(center - self.window.rect().center())
        self.video.target_size = self.window.pixel_size()
        if self.video.current:  # 以新尺寸重新开始当前动画
            self.behavior.start()
        self.config.section("window")["scale"] = scale
        self._save_position(self.window.pos())

    def _set_random_enabled(self, enabled: bool):
        self.behavior.set_random_enabled(enabled)
        self.config.save()

    # ---- 位置 ----
    def _restore_position(self):
        self.video.target_size = self.window.pixel_size()
        pos = self.config.section("window").get("position")
        if pos and QGuiApplication.screenAt(QPoint(*pos) + self.window.rect().center()):
            self.window.move(*pos)
            return
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.window.move(screen.right() - self.window.width(), screen.bottom() - self.window.height())

    def _save_position(self, pos: QPoint):
        self.config.section("window")["position"] = [pos.x(), pos.y()]
        self.config.save()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)  # 关闭聊天窗口等不应退出程序
    pet = DesktopPetApp(qt_app)
    pet.start()
    return qt_app.exec_()
