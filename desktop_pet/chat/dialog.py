"""聊天对话框。网络请求在后台线程中流式进行，界面不会卡顿。

对外暴露 request_started / reply_finished / request_failed 信号，
由外部决定桌宠在聊天各阶段的反应（动画、音效），对话框本身不依赖桌宠。
"""
import html
import logging
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (QDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QTextBrowser,
                             QVBoxLayout)

from .client import ChatSession, DeepSeekClient

log = logging.getLogger(__name__)


class _StreamWorker(QThread):
    chunk = pyqtSignal(str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, client: DeepSeekClient, messages: list[dict], parent=None):
        super().__init__(parent)
        self.client = client
        self.messages = messages
        self.cancelled = False

    def run(self):
        parts = []
        try:
            for piece in self.client.stream_chat(self.messages):
                if self.cancelled:
                    return
                parts.append(piece)
                self.chunk.emit(piece)
        except Exception as e:  # noqa: BLE001 - 网络/鉴权等错误统一反馈到界面
            log.warning("对话请求失败: %s", e)
            if not self.cancelled:
                self.failed.emit(str(e))
            return
        if not self.cancelled:
            self.done.emit("".join(parts))


class _InputEdit(QPlainTextEdit):
    """Enter 发送，Shift+Enter 换行。"""
    submitted = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.submitted.emit()
        else:
            super().keyPressEvent(event)


class ChatDialog(QDialog):
    request_started = pyqtSignal()
    reply_finished = pyqtSignal(str)
    request_failed = pyqtSignal(str)

    def __init__(self, client_factory: Callable[[], Optional[DeepSeekClient]], session: ChatSession,
                 pet_name: str = "大肥鱼", parent=None):
        """client_factory 每次发送时调用，便于配置（如 API Key）修改后立即生效；返回 None 表示未配置。"""
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.client_factory = client_factory
        self.session = session
        self.pet_name = pet_name
        self._worker: Optional[_StreamWorker] = None
        self._pending_text = ""

        self.setWindowTitle(f"和{pet_name}聊天")
        self.resize(420, 520)
        self.view = QTextBrowser(self)
        self.view.setOpenExternalLinks(True)
        self.input = _InputEdit(self)
        self.input.setPlaceholderText("输入消息，Enter 发送，Shift+Enter 换行")
        self.input.setFixedHeight(72)
        self.send_button = QPushButton("发送", self)
        self.clear_button = QPushButton("清空对话", self)

        buttons = QHBoxLayout()
        buttons.addWidget(self.clear_button)
        buttons.addStretch()
        buttons.addWidget(self.send_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.view)
        layout.addWidget(self.input)
        layout.addLayout(buttons)

        self.input.submitted.connect(self.send)
        self.send_button.clicked.connect(self.send)
        self.clear_button.clicked.connect(self.clear)

    # ---- 窗口控制 ----
    def toggle(self, anchor: Optional[QDialog] = None):
        if self.isVisible() and self.isActiveWindow():
            self.hide()
            return
        if not self.isVisible() and anchor is not None:
            self._place_near(anchor)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def _place_near(self, anchor):
        screen = anchor.screen().availableGeometry()
        geo = anchor.frameGeometry()
        x = geo.left() - self.width() - 10
        if x < screen.left():
            x = geo.right() + 10
        x = max(screen.left(), min(x, screen.right() - self.width()))
        y = max(screen.top(), min(geo.bottom() - self.height(), screen.bottom() - self.height()))
        self.move(x, y)

    # ---- 对话 ----
    def send(self):
        text = self.input.toPlainText().strip()
        if not text or self._worker is not None:
            return
        client = self.client_factory()
        if client is None:
            self._append_notice("未配置 DeepSeek API Key，请在右键菜单“设置…”中填写，"
                                "或设置环境变量 DEEPSEEK_API_KEY。")
            return
        self.input.clear()
        self._pending_text = text
        self._append_message("我", text)
        self._append_label(self.pet_name)
        self._set_busy(True)

        worker = _StreamWorker(client, self.session.build_messages(text), self)
        worker.chunk.connect(self._insert_text)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()
        self.request_started.emit()

    def clear(self):
        self._cancel_worker()
        self.session.clear()
        self.view.clear()

    def _on_done(self, reply: str):
        self.session.commit(self._pending_text, reply)
        self._finish_request()
        self.reply_finished.emit(reply)

    def _on_failed(self, message: str):
        self._insert_text(f"（出错了：{message}）")
        self._finish_request()
        self.request_failed.emit(message)

    def _finish_request(self):
        self._worker = None
        self._insert_text("\n")
        self._set_busy(False)

    def _cancel_worker(self):
        if self._worker is not None:
            self._worker.cancelled = True
            self._worker = None
            self._set_busy(False)

    def _set_busy(self, busy: bool):
        self.send_button.setEnabled(not busy)
        self.send_button.setText("思考中…" if busy else "发送")

    # ---- 渲染 ----
    def _append_label(self, name: str):
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.view.document().isEmpty():
            cursor.insertBlock()
        cursor.insertHtml(f"<b>{html.escape(name)}：</b>")
        cursor.insertBlock()
        self.view.setTextCursor(cursor)

    def _append_message(self, name: str, text: str):
        self._append_label(name)
        self._insert_text(text + "\n")

    def _append_notice(self, text: str):
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.view.document().isEmpty():
            cursor.insertBlock()
        cursor.insertHtml(f'<span style="color:#c0392b">{html.escape(text)}</span>')

    def _insert_text(self, text: str):
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.setCharFormat(QTextCharFormat())  # 避免继承上一段的粗体/颜色
        cursor.insertText(text)
        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()

    def closeEvent(self, event):
        # 关闭只是隐藏，进行中的请求继续，历史保留
        event.ignore()
        self.hide()
