"""桌宠窗口：透明、无边框、置顶、不显示在任务栏。

只负责显示帧和把鼠标操作翻译成语义信号（点击 / 拖拽 / 右键），不包含任何业务逻辑。
窗口内部由两层组成：底层可选的“脚下部件”（footer，如余额牌子），上层是动画画面，
因此桌宠的脚会盖在 footer 上，看起来像踩着它。
"""
import math
from typing import Optional

from PyQt5.QtCore import QPoint, QPointF, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QWidget


class _FrameView(QWidget):
    """绘制动画帧的图层，鼠标事件交给父窗口统一处理。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.image: Optional[QImage] = None

    def set_image(self, image: QImage):
        self.image = image
        self.update()

    def paintEvent(self, event):
        if self.image is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self.rect(), self.image)


class PetWindow(QWidget):
    clicked = pyqtSignal(QPoint)          # 窗口内坐标
    drag_started = pyqtSignal()
    drag_finished = pyqtSignal(QPoint)    # 拖拽结束后的窗口位置
    menu_requested = pyqtSignal(QPoint)   # 全局坐标

    def __init__(self, base_size: QSize, scale: float = 1.0, drag_threshold: int = 4,
                 always_on_top: bool = True, foot_anchor: Optional[QPointF] = None,
                 long_press_ms: int = 400):
        """foot_anchor：桌宠脚底中心在原始视频中的坐标，用于摆放 footer。
        long_press_ms：按住不动超过该时长也算开始拖拽，0 表示关闭。
        """
        super().__init__(None)
        self._base_size = base_size
        self._scale = scale
        self._foot_anchor = foot_anchor or QPointF(base_size.width() / 2, base_size.height() * 0.92)
        self._drag_threshold = drag_threshold
        self._long_press_ms = long_press_ms
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._start_drag)
        self._footer: Optional[QWidget] = None
        self._footer_overlap = 0.0
        self._press_global: Optional[QPoint] = None
        self._press_on_pet = False
        self._press_offset = QPoint()
        self._dragging = False

        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint  # Tool: 不进任务栏
        if always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("大肥鱼")
        self._view = _FrameView(self)
        self.set_scale(scale)

    # ---- 布局 ----
    def set_scale(self, scale: float):
        self._scale = scale
        if self._footer is not None and hasattr(self._footer, "set_scale"):
            self._footer.set_scale(scale)
        self._relayout()

    def set_footer(self, widget: QWidget, overlap: float = 0.3):
        """在桌宠脚下挂一个部件，显示在桌宠身后。

        overlap：部件顶部被脚踩住的高度占部件高度的比例。
        部件若实现 set_scale(scale)，缩放时会被调用以调整自身尺寸。
        """
        self._footer = widget
        self._footer_overlap = overlap
        widget.setParent(self)
        widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        if hasattr(widget, "set_scale"):
            widget.set_scale(self._scale)
        widget.show()
        self._relayout()

    def _relayout(self):
        view_size = self._base_size * self._scale
        self._view.setGeometry(QRect(QPoint(0, 0), view_size))
        width, height = view_size.width(), view_size.height()
        if self._footer is not None:
            size = self._footer.size()
            x = self._foot_anchor.x() * self._scale - size.width() / 2
            y = self._foot_anchor.y() * self._scale - size.height() * self._footer_overlap
            self._footer.move(round(x), round(y))
            height = max(height, math.ceil(y + size.height()))
            self._footer.lower()
        self.setFixedSize(width, height)

    # ---- 显示 ----
    def pixel_size(self) -> tuple[int, int]:
        """动画区域的物理像素尺寸，用于让解码输出与屏幕像素一一对应。"""
        dpr = self.devicePixelRatioF()
        return round(self._view.width() * dpr), round(self._view.height() * dpr)

    def set_frame(self, image: QImage):
        image.setDevicePixelRatio(self.devicePixelRatioF())
        self._view.set_image(image)

    def _is_opaque(self, pos: QPoint) -> bool:
        image = self._view.image
        if image is None or not self._view.geometry().contains(pos):
            return False
        x = int(pos.x() * image.width() / max(self._view.width(), 1))
        y = int(pos.y() * image.height() / max(self._view.height(), 1))
        return image.valid(x, y) and image.pixelColor(x, y).alpha() > 0

    def _on_footer(self, pos: QPoint) -> bool:
        return self._footer is not None and self._footer.geometry().contains(pos)

    # ---- 鼠标交互 ----
    def mousePressEvent(self, event):
        on_pet = self._is_opaque(event.pos())
        if event.button() == Qt.LeftButton and (on_pet or self._on_footer(event.pos())):
            self._press_global = event.globalPos()
            self._press_on_pet = on_pet  # 按在 footer 上只能拖拽，不算点击桌宠
            self._press_offset = event.globalPos() - self.frameGeometry().topLeft()
            self._dragging = False
            if self._long_press_ms > 0:
                self._long_press_timer.start(self._long_press_ms)
        else:
            event.ignore()

    def _start_drag(self):
        """移动超过阈值或长按到时，进入拖拽状态（只触发一次）。"""
        self._long_press_timer.stop()
        if self._press_global is not None and not self._dragging:
            self._dragging = True
            self.drag_started.emit()

    def mouseMoveEvent(self, event):
        if self._press_global is None or not event.buttons() & Qt.LeftButton:
            return
        if not self._dragging:
            if (event.globalPos() - self._press_global).manhattanLength() < self._drag_threshold:
                return
            self._start_drag()
        self.move(event.globalPos() - self._press_offset)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._press_global is None:
            return
        self._long_press_timer.stop()
        self._press_global = None
        if self._dragging:
            self._dragging = False
            self.drag_finished.emit(self.pos())
        elif self._press_on_pet:
            self.clicked.emit(event.pos())

    def contextMenuEvent(self, event):
        if self._is_opaque(event.pos()) or self._on_footer(event.pos()):
            self.menu_requested.emit(event.globalPos())

    def hideEvent(self, event):
        # 按住鼠标时被隐藏，丢弃这次按下，避免之后误触发拖拽
        self._long_press_timer.stop()
        self._press_global = None
        self._dragging = False
        super().hideEvent(event)
