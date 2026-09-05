"""应用路径管理：用户数据目录与资源目录（兼容 PyInstaller 冻结模式）。"""

import os
import sys


def app_dir() -> str:
    """用户数据根目录（%APPDATA%\\AuraDash，可用环境变量 AURADASH_DIR 覆盖）。"""
    override = os.environ.get("AURADASH_DIR")
    if override:
        return os.path.abspath(override)
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "AuraDash")


def config_path() -> str:
    return os.path.join(app_dir(), "config.json")


def logs_dir() -> str:
    return os.path.join(app_dir(), "logs")


def sounds_dir() -> str:
    return os.path.join(app_dir(), "sounds")


def stats_path() -> str:
    return os.path.join(app_dir(), "focus_stats.json")


def ensure_dirs():
    for d in (app_dir(), logs_dir(), sounds_dir()):
        os.makedirs(d, exist_ok=True)


def resource_path(relative: str) -> str:
    """资源文件路径：冻结模式下从 _MEIPASS 解包目录获取。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative)
