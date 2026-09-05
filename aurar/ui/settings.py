"""设置对话框：全部配置实时生效（写入 config.json，无需重启）。"""

import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QTabWidget,
                               QVBoxLayout, QWidget)

from ..core.logger import get_logger
from ..core.paths import app_dir
from ..pages.dashboard import CARD_FACTORIES
from ..platform import win

log = get_logger("settings")

REFRESH_OPTIONS = [("0.5 秒", 0.5), ("1 秒", 1.0), ("2 秒", 2.0), ("5 秒", 5.0)]


def _hint(text):
    lb = QLabel(text)
    lb.setObjectName("SubText")
    lb.setWordWrap(True)
    return lb


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("AuraDash 设置")
        self.setMinimumWidth(460)
        self._updating = False

        root = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._tab_appearance(), "外观")
        tabs.addTab(self._tab_window(), "窗口与数据")
        tabs.addTab(self._tab_cards(), "卡片")
        tabs.addTab(self._tab_advanced(), "高级")
        root.addWidget(tabs)
        root.addWidget(_hint("所有修改即时保存与应用，无需重启程序；保存在 %APPDATA%\\AuraDash\\config.json"))

        self.cfg.changed.connect(self._refresh)
        self._refresh("*")

    # ------------------------------------------------ 外观
    def _tab_appearance(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._sl_active = self._slider(0, 100)
        self._sl_active.valueChanged.connect(lambda v: self._set("opacity_active", v))
        form.addRow("激活时透明度 (%)", self._sl_active)

        self._sl_inactive = self._slider(0, 100)
        self._sl_inactive.valueChanged.connect(lambda v: self._set("opacity_inactive", v))
        form.addRow("失焦时透明度 (%)", self._sl_inactive)

        self._cmb_theme = QComboBox()
        self._cmb_theme.addItem("深空黑（dark）", "dark")
        self._cmb_theme.addItem("极夜浅（light）", "light")
        self._cmb_theme.currentIndexChanged.connect(
            lambda _: self._set("theme.name", self._cmb_theme.currentData()))
        form.addRow("主题模式", self._cmb_theme)

        c1_row = QHBoxLayout()
        self._btn_c1 = QPushButton("主色")
        self._btn_c1.clicked.connect(lambda: self._pick_accent("theme.accent1", self._btn_c1))
        self._btn_c2 = QPushButton("辅色")
        self._btn_c2.clicked.connect(lambda: self._pick_accent("theme.accent2", self._btn_c2))
        c1_row.addWidget(self._btn_c1)
        c1_row.addWidget(self._btn_c2)
        form.addRow("霓虹配色", c1_row)

        self._sl_font = self._slider(80, 150)
        self._sl_font.valueChanged.connect(lambda v: self._set("font_scale", v))
        form.addRow("字体缩放 (%)", self._sl_font)
        return w

    # ------------------------------------------------ 窗口与数据
    def _tab_window(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._chk_pin = QCheckBox("始终置顶（悬浮小部件）")
        self._chk_pin.toggled.connect(lambda on: self._set("always_on_top", on))
        form.addRow(self._chk_pin)

        self._cmb_refresh = QComboBox()
        for label, val in REFRESH_OPTIONS:
            self._cmb_refresh.addItem(label, val)
        self._cmb_refresh.currentIndexChanged.connect(
            lambda _: self._set("refresh_sec", self._cmb_refresh.currentData()))
        form.addRow("数据刷新频率", self._cmb_refresh)

        form.addRow(_hint("拖动窗口右下角可缩放（最小 400×300）；窗口位置与大小自动记忆。\n"
                          "刷新频率越低占用越小；监控采集在独立线程执行，不阻塞界面。"))
        return w

    # ------------------------------------------------ 卡片
    def _tab_cards(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setSpacing(8)

        for cid, cls in CARD_FACTORIES.items():
            cb = QCheckBox(f"{cls.title} 卡片")
            cb.toggled.connect(lambda on, i=cid: self._toggle_card(i, on))
            root.addWidget(cb)
            setattr(self, f"_chk_card_{cid}", cb)
        root.addWidget(_hint("隐藏的卡片可通过这里恢复显示；卡片顺序在仪表盘页长按标题拖拽调整。"))
        root.addStretch(1)
        return w

    # ------------------------------------------------ 高级
    def _tab_advanced(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._chk_autostart = QCheckBox("开机自启动")
        self._chk_autostart.toggled.connect(self._set_autostart)
        form.addRow(self._chk_autostart)

        self._chk_elevate = QCheckBox("启动时自动申请管理员权限（进程管理 / 温度读取需要）")
        self._chk_elevate.toggled.connect(lambda on: self._set("auto_elevate", on))
        form.addRow(self._chk_elevate)

        self._chk_assist = QCheckBox("专注时启用 Windows 专注助手（仅限闹钟）")
        self._chk_assist.toggled.connect(lambda on: self._set("focus_assist", on))
        form.addRow(self._chk_assist)

        row = QHBoxLayout()
        self._ed_sound = QLineEdit()
        self._ed_sound.setPlaceholderText("留空使用内置“叮”提示音")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._pick_sound)
        row.addWidget(self._ed_sound, 1)
        row.addWidget(browse)
        form.addRow("提醒音效文件", row)

        btns = QHBoxLayout()
        reset = QPushButton("恢复默认设置")
        reset.setObjectName("Ghost")
        reset.clicked.connect(self._reset)
        open_dir = QPushButton("打开配置目录")
        open_dir.setObjectName("Ghost")
        open_dir.clicked.connect(self._open_dir)
        btns.addWidget(reset)
        btns.addWidget(open_dir)
        form.addRow(btns)

        admin = "以管理员运行" if win.is_admin() else "普通权限（未提权）"
        form.addRow(_hint(f"当前状态：{admin}；数据目录：{app_dir()}"))
        return w

    # ------------------------------------------------ 交互
    def _slider(self, lo, hi):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        return s

    def _set(self, key, value):
        if self._updating:
            return
        self.cfg.set(key, value)

    def _toggle_card(self, cid, on):
        if self._updating:
            return
        hidden = [h for h in self.cfg.get("hidden_cards", []) if h != cid]
        if not on:
            hidden.append(cid)
        self.cfg.set("hidden_cards", hidden)

    def _pick_accent(self, key, btn):
        color = QColorDialog.getColor(QColor(self.cfg.get(key, "#00D4FF")), self,
                                      "选择霓虹颜色")
        if color.isValid():
            self.cfg.set(key, color.name())

    def _pick_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择提示音（wav/mp3）", "", "音频文件 (*.wav *.mp3 *.ogg)")
        if path:
            self.cfg.set("sound_file", path)

    def _set_autostart(self, on):
        if self._updating:
            return
        if win.set_autostart(on):
            self.cfg.set("autostart", on)
        else:
            self._updating = True
            self._chk_autostart.setChecked(False)
            self._updating = False

    def _reset(self):
        from PySide6.QtWidgets import QMessageBox

        ret = QMessageBox.question(self, "恢复默认", "确定恢复所有默认设置吗？")
        if ret == QMessageBox.StandardButton.Yes:
            self.cfg.reset_to_defaults()

    def _open_dir(self):
        try:
            os.makedirs(app_dir(), exist_ok=True)
            os.startfile(app_dir())  # noqa: S606
        except Exception:  # noqa: BLE001
            log.warning("打开配置目录失败")

    # ------------------------------------------------ 刷新
    def _refresh(self, key):
        if self._updating:
            return
        if key not in ("*", "opacity_active", "opacity_inactive",
                       "font_scale", "always_on_top", "refresh_sec",
                       "hidden_cards", "autostart", "auto_elevate",
                       "focus_assist", "sound_file") and not key.startswith("theme"):
            return
        self._updating = True
        try:
            self._sl_active.setValue(int(self.cfg.get("opacity_active", 100)))
            self._sl_inactive.setValue(int(self.cfg.get("opacity_inactive", 70)))
            self._sl_font.setValue(int(self.cfg.get("font_scale", 100)))
            self._cmb_refresh.setCurrentIndex(max(0, [
                v for _, v in REFRESH_OPTIONS].index(float(self.cfg.get("refresh_sec", 1.0)))))
            name = (self.cfg.get("theme", {}) or {}).get("name", "dark")
            self._cmb_theme.setCurrentIndex(0 if name == "dark" else 1)
            self._btn_c1.setStyleSheet(
                f"background:{self.cfg.get('theme.accent1', '#00D4FF')}; color:#FFF;"
                "border:1px solid rgba(255,255,255,0.5);")
            self._btn_c2.setStyleSheet(
                f"background:{self.cfg.get('theme.accent2', '#7B2FBE')}; color:#FFF;"
                "border:1px solid rgba(255,255,255,0.5);")
            self._chk_pin.setChecked(bool(self.cfg.get("always_on_top", True)))
            self._chk_autostart.setChecked(bool(self.cfg.get("autostart", False)))
            self._chk_elevate.setChecked(bool(self.cfg.get("auto_elevate", True)))
            self._chk_assist.setChecked(bool(self.cfg.get("focus_assist", True)))
            self._ed_sound.setText(self.cfg.get("sound_file", "") or "")
            hidden = set(self.cfg.get("hidden_cards", []))
            for cid in CARD_FACTORIES:
                getattr(self, f"_chk_card_{cid}").setChecked(cid not in hidden)
        finally:
            self._updating = False
