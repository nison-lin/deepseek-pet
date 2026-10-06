"""开机自启动（Windows）：在当前用户的注册表 Run 项中写入启动命令，无需管理员权限。

是否已开启以注册表为准，不另存到 config.json，避免两边不一致。
"""
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DsPet"

supported = sys.platform == "win32"
if supported:
    import winreg


def command() -> str:
    """启动本程序的命令行。打包后直接运行 exe；源码运行时用 pythonw，开机时不弹出命令行窗口。"""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    if pythonw.exists():
        python = pythonw
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{python}" "{main_py}"'


def _read() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)[0]
    except OSError:
        return ""


def is_enabled() -> bool:
    return supported and bool(_read())


def set_enabled(enabled: bool) -> bool:
    """成功返回 True。"""
    if not supported:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as e:
        log.error("设置开机自启动失败: %s", e)
        return False


def refresh():
    """已开启时，若程序被移动过位置则更新启动命令，避免开机时找不到程序。"""
    if is_enabled() and _read() != command():
        log.info("更新开机自启动命令: %s", command())
        set_enabled(True)
