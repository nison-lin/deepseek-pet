"""设置窗口：集中放置快捷键、中转站和 DeepSeek API Key。

窗口本身不读写配置，也不直接操作各功能模块，数据和修改动作都由外部以回调传入。
快捷键和中转站点击“修改”后立即生效；API Key 在关闭窗口时交给外部保存。
"""
from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)


class SettingsDialog(QDialog):
    def __init__(self, hotkeys: list[tuple[str, str]], hotkey_text: Callable[[str], str],
                 edit_hotkey: Callable[[str], None], relay_text: Callable[[], str],
                 edit_relays: Callable[[], None], api_key: str, parent: Optional[QWidget] = None):
        """hotkeys：[(功能名, 显示名)]；hotkey_text(功能名) 返回当前快捷键的显示文字；
        edit_hotkey / edit_relays 弹出对应的修改窗口；relay_text() 返回当前中转站的显示文字。"""
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

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hotkey_box)
        layout.addWidget(relay_box)
        layout.addWidget(key_box)
        layout.addWidget(buttons)
        self._refresh()

    def _run(self, action: Callable, *args):
        action(*args)
        self._refresh()

    def _refresh(self):
        for name, label in self._hotkey_labels.items():
            label.setText(self._hotkey_text(name))
        self._relay_label.setText(self._relay_text())

    @property
    def api_key(self) -> str:
        return self.key_edit.text().strip()
