"""打包脚本：python build.py → dist/ds-pet.exe（加 --no-resource 则不复制 resource）

- exe 只包含代码和运行库，resource 不打包，运行时从 exe 所在目录读取；
- 在独立的虚拟环境中打包，避免把本机（如 Anaconda）里无关的大型库打进 exe；
- PyInstaller 读取 Qt 路径时不支持非 ASCII 字符，而项目目录含中文，
  因此把源码复制到临时的纯英文目录中构建，完成后把 exe 拷回 dist/。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD_ROOT = Path(tempfile.gettempdir()) / "dfy_pet_build"
VENV_DIR = BUILD_ROOT / "venv"
SRC_DIR = BUILD_ROOT / "src"
PYINSTALLER = "pyinstaller==6.22.3"
EXE_NAME = "ds-pet.exe"
COPY_ITEMS = ["main.py", "pet.spec", "requirements.txt", "desktop_pet"]
NO_RESOURCE = False


def run(*args, cwd: Path = ROOT):
    print(">", " ".join(map(str, args)))
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    # Anaconda 的 Python 把 ffi/lzma/expat 等运行库放在 Library\bin，不加入 PATH 时
    # PyInstaller 找不到它们，打出的 exe 会因 ctypes 等模块加载失败而无法运行
    conda_bin = Path(sys.base_prefix) / "Library" / "bin"
    if conda_bin.is_dir():
        env["PATH"] = f"{conda_bin}{os.pathsep}{env.get('PATH', '')}"
    subprocess.run([str(a) for a in args], check=True, cwd=cwd, env=env)


def ensure_ascii(path: Path):
    if not str(path).isascii():
        sys.exit(f"临时目录 {path} 含非 ASCII 字符，请设置环境变量 TEMP 为纯英文路径后重试。")


def prepare_sources():
    if SRC_DIR.exists():
        shutil.rmtree(SRC_DIR)
    SRC_DIR.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for item in COPY_ITEMS:
        src = ROOT / item
        if src.is_dir():
            shutil.copytree(src, SRC_DIR / item, ignore=ignore)
        else:
            shutil.copy2(src, SRC_DIR / item)
    (SRC_DIR / "resource").mkdir()
    shutil.copy2(ROOT / "resource" / "icon.ico", SRC_DIR / "resource" / "icon.ico")  # exe 图标


def copy_with_retry(src: Path, dst: Path, attempts: int = 10):
    """刚生成的 exe 可能正被杀毒软件扫描而暂时无法访问，稍等重试。"""
    for i in range(attempts):
        try:
            shutil.copy2(src, dst)
            return
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(1)


def main():
    ensure_ascii(BUILD_ROOT)
    python = VENV_DIR / "Scripts" / "python.exe"
    if not python.exists():
        print(f"创建打包用虚拟环境 {VENV_DIR} ...")
        venv.create(VENV_DIR, with_pip=True)
    run(python, "-m", "pip", "install", "-q", "-r", ROOT / "requirements.txt", PYINSTALLER)

    prepare_sources()
    run(python, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", BUILD_ROOT / "dist", "--workpath", BUILD_ROOT / "work", "pet.spec", cwd=SRC_DIR)

    # dist/ 即发布目录：exe + resource，整个文件夹拷走即可运行
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    exe = dist / EXE_NAME
    copy_with_retry(BUILD_ROOT / "dist" / EXE_NAME, exe)
    if not NO_RESOURCE:
        if (dist / "resource").exists():
            shutil.rmtree(dist / "resource")
        shutil.copytree(ROOT / "resource", dist / "resource")
    print(f"\n完成：{exe}（{exe.stat().st_size / 1e6:.0f} MB）")
    print("运行时需要 resource 文件夹与 exe 位于同一目录。")


if __name__ == "__main__":
    NO_RESOURCE = "--no-resource" in sys.argv  # 只更新 exe，不复制资源
    main()
