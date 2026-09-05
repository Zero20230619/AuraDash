"""用户配置系统：%APPDATA%\\AuraDash\\config.json，修改实时生效（300ms 防抖落盘）。

所有键使用点分路径访问，例如 ``cfg.get("window.w")``。
"""

import copy
import json
import os
from typing import Any, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .logger import get_logger
from .paths import config_path

DEFAULTS: dict = {
    # ---- 窗口 ----
    "window": {"x": None, "y": None, "w": 780, "h": 540},
    "always_on_top": True,
    # ---- 透明度（0-100） ----
    "opacity_active": 100,
    "opacity_inactive": 70,
    "opacity_duration_ms": 200,
    # ---- 数据 ----
    "refresh_sec": 1.0,           # 0.5 / 1 / 2 / 5
    # ---- 外观 ----
    "font_scale": 100,            # 80 - 150
    "theme": {
        "name": "dark",           # dark | light
        "accent1": "#00D4FF",
        "accent2": "#7B2FBE",
    },
    # ---- 仪表盘卡片 ----
    "card_order": ["clock", "cpu", "gpu", "memory", "disk"],
    "hidden_cards": [],
    # ---- 专注 ----
    "focus_minutes": 25,
    "sound_file": "",             # 留空使用内置提示音
    "focus_assist": True,         # 专注时启用 Windows 专注助手
    # ---- 高级 ----
    "auto_elevate": True,         # 启动时自动申请管理员权限
    "autostart": False,           # 开机自启动（注册表 Run 键）
}

FLOAT_KEYS = ("refresh_sec",)
INT_KEYS = ("opacity_active", "opacity_inactive", "font_scale",
            "opacity_duration_ms", "focus_minutes")


def _deep_get(node: dict, parts):
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    return node


def _deep_set(node: dict, parts, value):
    for p in parts[:-1]:
        nxt = node.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            node[p] = nxt
        node = nxt
    node[parts[-1]] = value


class Config(QObject):
    """配置对象：读取 / 写入 / 落盘 / 变更通知。"""

    changed = Signal(str)  # 传入变更键（点分路径）；"*" 表示整体重置

    def __init__(self, path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._path = path or config_path()
        self._data = copy.deepcopy(DEFAULTS)
        self._load()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self.save)
        self._get_local = get_logger("config")

    # ---------- 读取 ----------
    def get(self, key: str, default: Any = None) -> Any:
        val = _deep_get(self._data, key.split("."))
        return default if val is None else val

    @property
    def data(self) -> dict:
        return self._data

    # ---------- 写入 ----------
    def set(self, key: str, value: Any):
        parts = key.split(".")
        _deep_set(self._data, parts, self._coerce(parts[-1], value))
        if not self._save_timer.isActive():
            self._save_timer.start()
        self.changed.emit(key)

    def set_many(self, items: dict):
        for k, v in items.items():
            self.set(k, v)

    def reset_to_defaults(self):
        self._data = copy.deepcopy(DEFAULTS)
        self.save()
        self.changed.emit("*")

    # ---------- 内部 ----------
    @staticmethod
    def _coerce(key: str, value):
        if key in FLOAT_KEYS:
            return float(value)
        if key in INT_KEYS:
            return int(value)
        return value

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self._merge(self._data, loaded)
        except Exception as exc:  # noqa: BLE001
            self._get_local.warning("配置读取失败，使用默认值: %s", exc)

    @staticmethod
    def _merge(base: dict, loaded: dict):
        """深合并：保留默认结构中未出现在文件里的键。"""
        for k, v in loaded.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                Config._merge(base[k], v)
            else:
                base[k] = v

    def save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except Exception as exc:  # noqa: BLE001
            self._get_local.exception("配置保存失败: %s", exc)
