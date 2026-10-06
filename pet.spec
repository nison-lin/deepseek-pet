# PyInstaller 打包配置，请通过 python build.py 调用。
# 产物为单个 ds-pet.exe，只含代码和运行库；resource 不打包，运行时从 exe 旁边读取。
from pathlib import Path

ROOT = Path(SPECPATH)

# 程序用不到、但 PyInstaller 会顺带收集的大模块
EXCLUDES = [
    "tkinter", "unittest", "pydoc_data", "test",
    "PyQt5.QtWebEngine", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtQuickWidgets", "PyQt5.Qt3DCore",
    "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtPositioning", "PyQt5.QtLocation",
    "PyQt5.QtSensors", "PyQt5.QtSerialPort", "PyQt5.QtSql", "PyQt5.QtTest",
    "PyQt5.QtDesigner", "PyQt5.QtHelp", "PyQt5.QtXmlPatterns", "PyQt5.QtOpenGL",
    "PyQt5.QtPrintSupport", "PyQt5.QtSvg", "PyQt5.QtWebSockets", "PyQt5.QtDBus",
]

# Qt 插件/翻译中用不到的部分（只需要 windows 平台插件、图片格式和多媒体后端）
DROP_PATTERNS = (
    "Qt5\\translations\\", "Qt5/translations/",
    "d3dcompiler_47.dll", "opengl32sw.dll", "libGLESv2.dll", "libEGL.dll",
    "Qt5Quick", "Qt5Qml", "Qt5WebSockets", "Qt5Svg", "Qt5DBus", "Qt5Pdf",
)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=[],
    hiddenimports=[],
    excludes=EXCLUDES,
    noarchive=False,
)
a.binaries = [b for b in a.binaries if not any(p in b[0] or p in b[1] for p in DROP_PATTERNS)]
a.datas = [d for d in a.datas if not any(p in d[0] for p in DROP_PATTERNS)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="ds-pet",          # 需与 build.py 中的 EXE_NAME 一致
    icon=str(ROOT / "resource" / "icon.ico"),
    console=False,          # 不显示命令行窗口
    upx=False,              # UPX 压缩容易被杀毒软件误报，且会拖慢启动
    debug=False,
    strip=False,
)
