"""余额牌子：画在桌宠脚下的小木牌，只负责显示文字。"""
from typing import Optional

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import (QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath,
                         QPen)
from PyQt5.QtWidgets import QWidget

BASE_SIZE = QSize(230, 66)  # 缩放为 1.0 时的尺寸（与视频像素同一尺度）

WOOD_LIGHT = QColor("#e8bf86")
WOOD_DARK = QColor("#c98f52")
WOOD_EDGE = QColor("#7a4a22")
GRAIN = QColor(122, 74, 34, 60)
TEXT_NORMAL = QColor("#4a2a10")
TEXT_MUTED = QColor("#7a5a3c")
TEXT_ERROR = QColor("#a8321e")


class BalanceSign(QWidget):
    def __init__(self, parent: Optional[QWidget] = None, top_margin: float = 0.12):
        """top_margin：顶部被脚踩住、不放文字的高度比例。"""
        super().__init__(parent)
        self._top_margin = top_margin
        self._scale = 1.0
        self._title = ""
        self._text = "--"
        self._color = TEXT_MUTED
        self.set_scale(1.0)

    # ---- 对外接口 ----
    def set_scale(self, scale: float):
        self._scale = scale
        self.setFixedSize(BASE_SIZE * scale)
        self.update()

    def set_title(self, title: str):
        self._title = title
        self.update()

    def show_loading(self):
        self._set_text("查询中…", TEXT_MUTED)

    def show_amount(self, text: str):
        self._set_text(text, TEXT_NORMAL)

    def show_error(self, text: str):
        self._set_text(text, TEXT_ERROR)

    def _set_text(self, text: str, color: QColor):
        self._text = text
        self._color = color
        self.update()

    # ---- 绘制 ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        s = self._scale
        board = QRectF(self.rect()).adjusted(1.5 * s, 1.5 * s, -1.5 * s, -4 * s)

        # 底部阴影
        shadow = QPainterPath()
        shadow.addRoundedRect(board.translated(0, 3 * s), 10 * s, 10 * s)
        painter.fillPath(shadow, QColor(0, 0, 0, 50))

        # 木板
        path = QPainterPath()
        path.addRoundedRect(board, 10 * s, 10 * s)
        gradient = QLinearGradient(board.topLeft(), board.bottomLeft())
        gradient.setColorAt(0, WOOD_LIGHT)
        gradient.setColorAt(1, WOOD_DARK)
        painter.fillPath(path, gradient)

        # 木纹
        painter.save()
        painter.setClipPath(path)
        painter.setPen(QPen(GRAIN, max(1.0, 1.2 * s)))
        for ratio in (0.2, 0.9):  # 避开文字区域
            y = board.top() + board.height() * ratio
            painter.drawLine(int(board.left()), int(y), int(board.right()), int(y + 2 * s))
        painter.restore()

        painter.setPen(QPen(WOOD_EDGE, max(1.0, 2.5 * s)))
        painter.drawPath(path)

        # 文字（避开被脚踩住的顶部）
        text_rect = board.adjusted(12 * s, board.height() * self._top_margin, -12 * s, -3 * s)
        if self._title:
            title_rect, main_rect = self._split(text_rect, 0.4)
            self._draw_text(painter, title_rect, self._title, 10 * s, TEXT_MUTED, bold=False)
        else:
            main_rect = text_rect
        self._draw_text(painter, main_rect, self._text, 17 * s, self._color, bold=True)

    @staticmethod
    def _split(rect: QRectF, ratio: float) -> tuple[QRectF, QRectF]:
        top = QRectF(rect.left(), rect.top(), rect.width(), rect.height() * ratio)
        bottom = QRectF(rect.left(), top.bottom(), rect.width(), rect.height() - top.height())
        return top, bottom

    @staticmethod
    def _draw_text(painter: QPainter, rect: QRectF, text: str, size: float, color: QColor, bold: bool):
        font = QFont("Microsoft YaHei UI")
        font.setBold(bold)
        font.setPixelSize(max(6, round(size)))
        # 过长时逐步缩小字号
        while font.pixelSize() > 6 and QFontMetricsF(font).horizontalAdvance(text) > rect.width():
            font.setPixelSize(font.pixelSize() - 1)
        painter.setFont(font)
        painter.setPen(color)
        elided = painter.fontMetrics().elidedText(text, Qt.ElideRight, int(rect.width()))
        painter.drawText(rect, Qt.AlignCenter, elided)
