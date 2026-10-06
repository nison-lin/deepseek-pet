"""右键菜单。菜单本身不依赖任何功能模块，由外部通过 add_item 注册菜单项。"""
from typing import Any, Callable, Optional

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QWidget

# 配色与余额木牌（balance/sign.py）保持一致
MENU_STYLE = """
QMenu {
    background-color: #fbf3e6;
    border: 2px solid #c98f52;
    border-radius: 10px;
    padding: 6px 4px;
    font-family: "Microsoft YaHei UI";
    font-size: 10pt;
    color: #4a2a10;
}
QMenu::item {
    padding: 6px 28px 6px 34px;
    margin: 1px 2px;
    border-radius: 6px;
    background: transparent;
}
QMenu::item:exclusive, QMenu::item:non-exclusive {
    padding-left: 18px;  /* Qt 会再加上勾选框宽度(16px)，与普通项文字对齐 */
}
QMenu::item:selected {
    background-color: #e8bf86;
}
QMenu::item:disabled {
    color: #b8a48c;
}
QMenu::separator {
    height: 1px;
    background: #e3c9a4;
    margin: 5px 12px;
}
QMenu::indicator {
    width: 12px;
    height: 12px;
    border: 2px solid #c98f52;
    background: #fffaf2;
}
QMenu::indicator:non-exclusive {
    border-radius: 4px;
}
QMenu::indicator:non-exclusive:checked {
    background: #c98f52;
}
QMenu::indicator:exclusive {
    border-radius: 8px;
}
QMenu::indicator:exclusive:checked {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                stop:0 #7a4a22, stop:0.55 #7a4a22, stop:0.65 #fffaf2, stop:1 #fffaf2);
}
"""


class PetMenu(QMenu):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # 透明背景 + 去掉系统方形阴影，样式表里的圆角才能真正显示
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(MENU_STYLE)

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
