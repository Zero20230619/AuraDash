"""第 3 页 · 专注时钟（番茄钟）：倒计时 + 随机间隔“双叮”提醒 + 专注助手屏蔽通知。

创新点：专注中每隔 3~5 分钟（随机秒数）提醒一次，第一次提醒后 10 秒再响
第二次，随后进入下一轮随机等待 —— 基于“随机奖励”心理学机制增强持续专注动力。
"""

import datetime
import json
import os
import random

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout)

from ..core.logger import get_logger
from ..core.paths import sounds_dir, stats_path
from ..platform import sounds as sound_mod
from ..platform import win
from ..ui.widgets import RingGauge, make_label
from .base import Page

log = get_logger("focus")

PRESETS = (15, 25, 45, 60)


class _Player:
    """QSoundEffect 封装，失败时回退系统蜂鸣。"""

    def __init__(self):
        self._effects = {}
        self._ok = False
        try:
            from PySide6.QtMultimedia import QSoundEffect  # noqa: PLC0415

            self._cls = QSoundEffect
            self._ok = True
        except Exception:  # noqa: BLE001
            self._cls = None
            log.warning("QtMultimedia 不可用，提示音回退为系统蜂鸣")

    def play(self, path: str, volume=0.85):
        if not self._ok:
            import sys
            from PySide6.QtWidgets import QApplication  # noqa: PLC0415

            app = QApplication.instance()
            if app:
                app.beep()
            return
        try:
            eff = self._effects.get(path)
            if eff is None:
                eff = self._cls()
                eff.setSource(QUrl.fromLocalFile(path))
                eff.setVolume(volume)
                self._effects[path] = eff
            eff.play()
        except Exception as exc:  # noqa: BLE001
            log.debug("播放失败: %s", exc)


class FocusPage(Page):
    id = "focus"
    title = "专注"
    icon = "◷"
    order = 2

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._running = False
        self._remain = 0.0
        self._total = 0.0
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._player = None  # 惰性创建：首次播放才加载 QtMultimedia（省 ~30MB）
        self._next_remind = None
        self._second_remind = False
        self._finishing = False

    def _get_player(self) -> "_Player":
        if self._player is None:
            self._player = _Player()
        return self._player

    # ---------------- 构建 ----------------
    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(10)

        clock_row = QHBoxLayout()
        clock_row.addStretch(1)

        self._gauge = RingGauge(230, thickness=13, sub="剩余",
                                color_provider=self._page_colors,
                                center_mode="none", parent=self)
        self._time_lb = make_label("25:00", "Mono", parent=self._gauge)
        self._time_lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._time_lb.setStyleSheet(
            "font-family: 'Bahnschrift','Consolas'; font-size: 44px; font-weight: 600;"
            "color: #E6ECF8; background: transparent;")
        self._gauge_layout_overlay()
        clock_row.addWidget(self._gauge)
        clock_row.addStretch(1)
        root.addLayout(clock_row)

        self._status = make_label("待机中 · 选择时长后开始", "SubText", parent=self)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        ctrl.addStretch(1)
        self._combo = QComboBox(self)
        self._combo.setEditable(True)
        for m in PRESETS:
            self._combo.addItem(f"{m} 分钟", m)
        self._combo.setCurrentIndex(1)
        self._combo.setFixedWidth(130)
        self._combo.editTextChanged.connect(self._on_duration_text)
        ctrl.addWidget(self._combo)

        self._btn_start = QPushButton("开始", self)
        self._btn_start.setObjectName("Primary")
        self._btn_start.setFixedWidth(96)
        self._btn_start.clicked.connect(self.start)
        self._btn_pause = QPushButton("暂停", self)
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self.pause)
        self._btn_reset = QPushButton("重置", self)
        self._btn_reset.clicked.connect(self.reset)
        for b in (self._btn_start, self._btn_pause, self._btn_reset):
            ctrl.addWidget(b)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        hint = make_label(
            "专注中每 3~5 分钟随机“叮”一次提醒，10 秒后补第二声，帮助保持专注节奏。\n"
            "开启后自动启用 Windows 专注助手（仅限闹钟），结束后恢复原设置。",
            "SubText", size=11, parent=self)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(hint)

        self._stats = make_label("", "SubText", parent=self)
        self._stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._stats)

        root.addStretch(1)

        self._combo.setCurrentText(f"{self.cfg.get('focus_minutes', 25)} 分钟")
        self._configure(self.cfg.get("focus_minutes", 25) * 60)
        self._update_stats_label()

    def _gauge_layout_overlay(self):
        g = self._gauge
        # 倒计时文字居中于环形仪表
        self._time_lb.setGeometry(0, g.height() // 2 - 30, g.width(), 48)

    def _page_colors(self):
        from ..core import theme as theme_mod

        p = theme_mod.palette(self.cfg)
        return p["accent1"], p["accent2"]

    # ---------------- 状态机 ----------------
    def _configure(self, total_sec):
        self._total = total_sec
        self._remain = total_sec
        self._render()

    def _on_duration_text(self, text):
        try:
            mins = int("".join(ch for ch in text if ch.isdigit()) or 0)
            if not self._running and mins > 0:
                self._configure(mins * 60)
                self.cfg.set("focus_minutes", mins)
        except ValueError:
            pass

    def start(self):
        if self._running:
            return
        if self._remain <= 0:
            self._configure(self._total or 25 * 60)
        self._running = True
        self._finishing = False
        self._tick.start()
        self._btn_start.setEnabled(False)
        self._btn_pause.setEnabled(True)
        self._status.setText("专注中 · 放松，保持节奏")
        self._schedule_next_remind()
        self._set_assist(True)

    def pause(self):
        if not self._running:
            return
        self._running = False
        self._tick.stop()
        self._btn_start.setEnabled(True)
        self._btn_pause.setEnabled(False)
        self._status.setText("已暂停")
        self._set_assist(False)

    def reset(self):
        self._running = False
        self._tick.stop()
        self._finishing = False
        self._btn_start.setEnabled(True)
        self._btn_pause.setEnabled(False)
        self._configure(self._total or 25 * 60)
        self._status.setText("待机中 · 选择时长后开始")
        self._set_assist(False)

    def _on_tick(self):
        if not self._running:
            return
        self._remain = max(0.0, self._remain - 1)
        self._render()
        self._check_remind()
        if self._remain <= 0:
            self._finish()

    # ---------------- 随机双叮提醒 ----------------
    def _schedule_next_remind(self):
        # 3~5 分钟随机整数秒
        self._next_remind = random.randint(180, 300)
        self._second_remind = False
        log.debug("下次随机提醒于 %d 秒后", self._next_remind)

    def _check_remind(self):
        if self._running and not self._second_remind:
            self._next_remind -= 1
            if self._next_remind <= 0:
                self._play_ding()
                self._tick_second()

    def _tick_second(self):
        # 第一声后 10 秒补第二声，然后进入下一轮随机等待
        self._second_remind = True
        QTimer.singleShot(10000, self._second_ding)

    def _second_ding(self):
        if self._running and self._second_remind and not self._finishing:
            self._play_ding()
            self._schedule_next_remind()

    def _play_ding(self):
        path = self._sound_path()
        self._get_player().play(path)

    def _sound_path(self) -> str:
        user = self.cfg.get("sound_file", "") or ""
        if user and os.path.exists(user):
            return user
        return sound_mod.ensure_sound_files(sounds_dir())["ding"]

    # ---------------- 结束 ----------------
    def _finish(self):
        self._running = False
        self._finishing = True
        self._tick.stop()
        self._btn_start.setEnabled(True)
        self._btn_pause.setEnabled(False)
        self._set_assist(False)
        self._status.setText("专注结束")
        chime = sound_mod.ensure_sound_files(sounds_dir())["chime"]
        self._get_player().play(chime, volume=0.9)
        self._record_session()
        self._update_stats_label()
        QMessageBox.information(self, "专注结束",
                                "专注结束，休息一下吧！\n起身活动、喝口水，给大脑一点休息时间。")

    def _record_session(self):
        total_min = round(self._total / 60.0, 1)
        try:
            data = self._load_stats()
            data.append({
                "date": datetime.date.today().isoformat(),
                "minutes": total_min,
                "finished": True,
            })
            with open(stats_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            log.warning("专注统计保存失败: %s", exc)

    def _load_stats(self) -> list:
        try:
            if os.path.exists(stats_path()):
                with open(stats_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            pass
        return []

    def _update_stats_label(self):
        today = datetime.date.today().isoformat()
        items = [s for s in self._load_stats() if s.get("date") == today]
        minutes = sum(float(s.get("minutes", 0)) for s in items)
        self._stats.setText(f"今日专注：{len(items)} 次  ·  累计 {minutes:.0f} 分钟")

    # ---------------- 专注助手 ----------------
    _assist_was_on = False

    def _set_assist(self, enabled):
        if not self.cfg.get("focus_assist", True):
            return
        if enabled:
            ok = win.set_focus_assist(True)
            self._assist_was_on = ok
            self._status.setText("专注中 · 通知已屏蔽（仅限闹钟）" if ok
                                 else "专注中 · 通知屏蔽不可用")
        elif self._assist_was_on:
            win.set_focus_assist(False)
            self._assist_was_on = False

    # ---------------- 渲染 ----------------
    def _render(self):
        frac = (self._remain / self._total * 100.0) if self._total else 0
        self._gauge.set_target(frac)
        total = int(self._remain)
        h, m, s = total // 3600, (total % 3600) // 60, total % 60
        text = f"{m:02d}:{s:02d}" if h == 0 else f"{h}:{m:02d}:{s:02d}"
        self._time_lb.setText(text)

    def on_show(self):
        self._render()
        self._gauge_layout_overlay()

    def stop(self):
        """应用退出时恢复专注助手、停止计时器。"""
        self._tick.stop()
        self._set_assist(False)
