"""设置窗口：集中放置开机自启动、快捷键、中转站以及 DeepSeek 的 API Key 和系统提示词。

窗口本身不读写配置，也不直接操作各功能模块，数据和修改动作都由外部以回调传入。
开机自启动、快捷键和中转站修改后立即生效；API Key 和系统提示词在关闭窗口时交给外部保存。
"""
from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
                             QWidget)


class SettingsDialog(QDialog):
    def __init__(self, hotkeys: list[tuple[str, str]], hotkey_text: Callable[[str], str],
                 edit_hotkey: Callable[[str], None], relay_text: Callable[[], str],
                 edit_relays: Callable[[], None], api_key: str, system_prompt: str,
                 default_system_prompt: str,
                 autostart: Optional[tuple[bool, Callable[[bool], bool]]] = None,
                 parent: Optional[QWidget] = None):
        """hotkeys：[(功能名, 显示名)]；hotkey_text(功能名) 返回当前快捷键的显示文字；
        edit_hotkey / edit_relays 弹出对应的修改窗口；relay_text() 返回当前中转站的显示文字；
        default_system_prompt 供“恢复默认”按钮使用；
        autostart：(当前是否开启, 开关函数)，开关函数成功返回 True，切换后立即调用；None 表示不支持。"""
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)
        self._hotkey_text = hotkey_text
        self._relay_text = relay_text

        # 快捷键
        hotkey_box = QGroupBox("快捷键", self)
        grid = QGridLayout(hotkey_box)
        self._hotkey_labels: dict[str, QLabel] = {}
        for row, (name, label) in enumerate(hotkeys):
            value = QLabel(self)
            button = QPushButton("修改…", self)
            button.clicked.connect(lambda _=False, n=name: self._run(edit_hotkey, n))
            grid.addWidget(QLabel(label, self), row, 0)
            grid.addWidget(value, row, 1)
            grid.addWidget(button, row, 2)
            self._hotkey_labels[name] = value
        grid.setColumnStretch(1, 1)

        # 中转站
        relay_box = QGroupBox("余额查询", self)
        relay_row = QHBoxLayout(relay_box)
        self._relay_label = QLabel(self)
        relay_button = QPushButton("更换中转站…", self)
        relay_button.clicked.connect(lambda: self._run(edit_relays))
        relay_row.addWidget(QLabel("当前中转站", self))
        relay_row.addWidget(self._relay_label, 1)
        relay_row.addWidget(relay_button)

        # DeepSeek API Key
        key_box = QGroupBox("DeepSeek 聊天", self)
        key_layout = QVBoxLayout(key_box)
        self.key_edit = QLineEdit(api_key, self)
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-…")
        show_key = QCheckBox("显示", self)
        show_key.toggled.connect(lambda on: self.key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key", self))
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(show_key)
        hint = QLabel("可在 platform.deepseek.com 的 API keys 页面创建，修改后下一条消息即生效。"
                      "留空则读取环境变量 DEEPSEEK_API_KEY。", self)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        key_layout.addLayout(key_row)
        key_layout.addWidget(hint)

        # 系统提示词
        self.prompt_edit = QPlainTextEdit(system_prompt, self)
        self.prompt_edit.setPlaceholderText("设定桌宠的人设和说话风格；留空则不发送系统提示词")
        self.prompt_edit.setFixedHeight(self.prompt_edit.fontMetrics().lineSpacing() * 5 + 12)
        reset_prompt = QPushButton("恢复默认", self)
        reset_prompt.clicked.connect(lambda: self.prompt_edit.setPlainText(default_system_prompt))
        prompt_header = QHBoxLayout()
        prompt_header.addWidget(QLabel("系统提示词", self))
        prompt_header.addStretch(1)
        prompt_header.addWidget(reset_prompt)
        prompt_hint = QLabel("修改后下一条消息即生效，已有的对话历史会保留。", self)
        prompt_hint.setStyleSheet("color: gray;")
        key_layout.addSpacing(6)
        key_layout.addLayout(prompt_header)
        key_layout.addWidget(self.prompt_edit)
        key_layout.addWidget(prompt_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)

        # 常规
        general_box = QGroupBox("常规", self)
        general_row = QHBoxLayout(general_box)
        self.autostart_check = QCheckBox("开机时自动启动", self)
        self.autostart_check.setChecked(autostart is not None and autostart[0])
        self.autostart_check.setEnabled(autostart is not None)
        if autostart is not None:
            self.autostart_check.toggled.connect(lambda on: self._toggle_autostart(on, autostart[1]))
        else:
            self.autostart_check.setToolTip("当前系统不支持")
        general_row.addWidget(self.autostart_check)

        layout = QVBoxLayout(self)
        layout.addWidget(general_box)
        layout.addWidget(hotkey_box)
        layout.addWidget(relay_box)
        layout.addWidget(key_box)
        layout.addWidget(buttons)
        self._refresh()

    def _run(self, action: Callable, *args):
        action(*args)
        self._refresh()

    def _toggle_autostart(self, enabled: bool, set_enabled: Callable[[bool], bool]):
        if set_enabled(enabled):
            return
        self.autostart_check.blockSignals(True)
        self.autostart_check.setChecked(not enabled)
        self.autostart_check.blockSignals(False)
        QMessageBox.warning(self, "开机自启动", f"{'开启' if enabled else '关闭'}开机自启动失败，详细信息见日志。")

    def _refresh(self):
        for name, label in self._hotkey_labels.items():
            label.setText(self._hotkey_text(name))
        self._relay_label.setText(self._relay_text())

    @property
    def api_key(self) -> str:
        return self.key_edit.text().strip()

    @property
    def system_prompt(self) -> str:
        return self.prompt_edit.toPlainText().strip()
