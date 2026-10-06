"""余额监视器：在后台线程中查询余额，并按间隔自动刷新。"""
import logging
import threading
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from .client import BalanceError, Relay, fetch_balance

log = logging.getLogger(__name__)


class BalanceMonitor(QObject):
    refreshing = pyqtSignal(object)        # Relay
    updated = pyqtSignal(object, bool)     # BalanceResult, 是否为手动查询
    failed = pyqtSignal(object, object)    # Relay, BalanceError

    _done = pyqtSignal(int, object, object)  # 代号, 结果, 错误

    def __init__(self, interval_sec: float = 300, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.relay: Optional[Relay] = None
        self._generation = 0
        self._busy = False
        self._manual = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.refresh())
        self.set_interval(interval_sec)
        self._done.connect(self._on_done)

    def set_interval(self, interval_sec: float):
        """interval_sec <= 0 表示关闭自动刷新。"""
        self._interval_ms = int(interval_sec * 1000) if interval_sec and interval_sec > 0 else 0

    def set_relay(self, relay: Relay):
        self.relay = relay
        self._busy = False  # 切换后旧请求的结果会被丢弃
        self.refresh()

    def refresh(self, manual: bool = False):
        """manual：用户主动发起的查询（定时刷新与切换中转站时为 False）。"""
        if self.relay is None or self._busy:
            return
        self._timer.stop()
        self._generation += 1
        self._busy = True
        self._manual = manual
        relay = Relay(**self.relay.to_dict())  # 拷贝一份，避免线程中读取到被修改的配置
        threading.Thread(target=self._run, args=(self._generation, relay),
                         name="balance-fetch", daemon=True).start()
        self.refreshing.emit(relay)

    def stop(self):
        self._timer.stop()
        self._generation += 1

    def _run(self, gen: int, relay: Relay):
        try:
            self._done.emit(gen, fetch_balance(relay), None)
        except BalanceError as e:
            self._done.emit(gen, relay, e)
        except Exception as e:  # noqa: BLE001
            log.exception("查询余额出错")
            self._done.emit(gen, relay, BalanceError("查询失败", str(e)))

    def _on_done(self, gen: int, result, error: Optional[BalanceError]):
        if gen != self._generation:
            return
        self._busy = False
        if error is None:
            self.updated.emit(result, self._manual)
        else:
            log.warning("查询余额失败（%s）: %s", result.name, error)
            self.failed.emit(result, error)
        if self._interval_ms:
            self._timer.start(self._interval_ms)
