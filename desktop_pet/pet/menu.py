"""右键菜单。菜单本身不依赖任何功能模块，由外部通过 add_item 注册菜单项。"""
from typing import Any, Callable, Optional

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QWidget


class PetMenu(QMenu):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

    def add_item(self, text: str, callback: Callable[[], None], *,
                 checkable: bool = False, checked: bool = False) -> QAction:
        action = self.addAction(text)
        action.setCheckable(checkable)
        if checkable:
            action.setChecked(checked)
            action.toggled.connect(lambda state: callback(state))
        else:
            action.triggered.connect(lambda: callback())
        return action

    def add_choices(self, options: list[tuple[str, Any]], current: Any,
                    callback: Callable[[Any], None]) -> QActionGroup:
        """一组互斥的单选菜单项，选中时以对应的值调用 callback。"""
        group = QActionGroup(self)
        for text, value in options:
            action = group.addAction(text)
            action.setCheckable(True)
            action.setChecked(value == current)
            action.triggered.connect(lambda _=False, v=value: callback(v))
            self.addAction(action)
        return group

    def add_submenu(self, title: str) -> "PetMenu":
        submenu = PetMenu(self)
        submenu.setTitle(title)
        self.addMenu(submenu)
        return submenu

    def show_at(self, global_pos: QPoint):
        self.popup(global_pos)
