"""中转站管理对话框：选择当前查看的中转站，并可新增 / 编辑 / 删除 / 测试。"""
import json
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                             QLineEdit, QListWidget, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from .client import BalanceError, Relay, fetch_balance, format_amount


class RelayDialog(QDialog):
    def __init__(self, relays: list[Relay], current: int, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle("更换中转站")
        self.resize(560, 300)
        self.relays = [Relay(**r.to_dict()) for r in relays]  # 编辑副本，取消时不影响原数据

        self.list = QListWidget(self)
        add_button = QPushButton("新增", self)
        remove_button = QPushButton("删除", self)
        test_button = QPushButton("测试查询", self)

        self.name_edit = QLineEdit(self)
        self.url_edit = QLineEdit(self)
        self.key_edit = QLineEdit(self)
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("在此填写该中转站的 API Key")
        self.field_edit = QLineEdit(self)
        self.field_edit.setPlaceholderText("可选，如 data.balance 或 quota - quota_used；留空自动识别")

        form = QFormLayout()
        form.addRow("名称", self.name_edit)
        form.addRow("查询地址", self.url_edit)
        form.addRow("API Key", self.key_edit)
        form.addRow("余额字段", self.field_edit)
        form.addRow("", test_button)

        list_buttons = QHBoxLayout()
        list_buttons.addWidget(add_button)
        list_buttons.addWidget(remove_button)
        left = QVBoxLayout()
        left.addWidget(self.list)
        left.addLayout(list_buttons)

        body = QHBoxLayout()
        body.addLayout(left, 2)
        body.addLayout(form, 5)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("使用选中的中转站")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        layout = QVBoxLayout(self)
        layout.addLayout(body)
        layout.addWidget(buttons)

        for relay in self.relays:
            self.list.addItem(relay.name)
        self.list.currentRowChanged.connect(self._load_row)
        for edit in (self.name_edit, self.url_edit, self.key_edit, self.field_edit):
            edit.textEdited.connect(self._save_row)
        add_button.clicked.connect(self._add)
        remove_button.clicked.connect(self._remove)
        test_button.clicked.connect(self._test)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        self.list.setCurrentRow(min(max(current, 0), len(self.relays) - 1))
        self._load_row(self.list.currentRow())

    # ---- 编辑 ----
    def _load_row(self, row: int):
        relay = self.relays[row] if 0 <= row < len(self.relays) else None
        for edit, value in ((self.name_edit, relay.name if relay else ""),
                            (self.url_edit, relay.url if relay else ""),
                            (self.key_edit, relay.api_key if relay else ""),
                            (self.field_edit, relay.balance_field if relay else "")):
            edit.setText(value)
            edit.setEnabled(relay is not None)

    def _save_row(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self.relays):
            return
        relay = self.relays[row]
        relay.name = self.name_edit.text().strip()
        relay.url = self.url_edit.text().strip()
        relay.api_key = self.key_edit.text().strip()
        relay.balance_field = self.field_edit.text().strip()
        self.list.item(row).setText(relay.name or "（未命名）")

    def _add(self):
        self.relays.append(Relay(name=f"中转站{len(self.relays) + 1}", url="https://"))
        self.list.addItem(self.relays[-1].name)
        self.list.setCurrentRow(len(self.relays) - 1)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _remove(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self.relays):
            return
        if QMessageBox.question(self, "删除中转站", f"确定删除“{self.relays[row].name}”吗？") != QMessageBox.Yes:
            return
        del self.relays[row]
        self.list.takeItem(row)
        self._load_row(self.list.currentRow())

    def _test(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self.relays):
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = fetch_balance(self.relays[row], timeout=10)
        except BalanceError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "测试查询", f"查询失败：{e.short}\n\n{e}")
            return
        QApplication.restoreOverrideCursor()
        raw = json.dumps(result.raw, ensure_ascii=False, indent=2)[:1500]
        QMessageBox.information(self, "测试查询", f"识别到的余额：{format_amount(result.amount)}\n\n原始返回：\n{raw}")

    def _accept(self):
        for relay in self.relays:
            if not relay.name or not relay.url.startswith(("http://", "https://")):
                QMessageBox.warning(self, "更换中转站", f"“{relay.name or '未命名'}”的名称或查询地址无效。")
                return
        if not self.relays:
            QMessageBox.warning(self, "更换中转站", "至少需要保留一个中转站。")
            return
        self.accept()

    # ---- 结果 ----
    @classmethod
    def ask(cls, relays: list[Relay], current: int, parent=None) -> Optional[tuple[list[Relay], int]]:
        """确认后返回 (编辑后的中转站列表, 选中的序号)，取消返回 None。"""
        dialog = cls(relays, current, parent)
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.relays, max(dialog.list.currentRow(), 0)
