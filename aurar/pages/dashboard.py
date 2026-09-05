"""第 1 页 · 系统仪表盘：实时时钟 + CPU / GPU / 内存 / 磁盘数据卡片。

交互：
    - 长按卡片标题拖拽 → 自由排序（持久化到 config.json）
    - 卡片右上角 × → 临时隐藏（设置页可恢复）
    - 每刷新周期（≥1Hz）更新所有可见卡片
"""

import datetime

from PySide6.QtCore import QEvent, QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QPushButton,
                               QVBoxLayout)

from ..core import theme as theme_mod
from ..ui.widgets import (MiniBar, NeonCard, RingGauge, fmt_bps, fmt_bytes,
                          make_label)
from .base import Page

MIME_CARD = "application/x-auradash-card"

GAUGE = 112  # 卡片内主环形仪表尺寸


# ------------------------------------------------------------------ 基类
class DashCard(NeonCard):
    """带可拖拽标题的仪表盘卡片。body 区域由子类填充。"""

    def __init__(self, card_id: str, title: str, page: "DashboardPage"):
        super().__init__(card_id, title)
        self._page = page
        self._press_global = None
        self._dragging = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        grip = make_label("≡", "SubText", size=14, parent=self)
        grip.setMouseTracking(True)
        title_lb = make_label(title, "CardTitleAccent", size=12, parent=self)
        title_lb.setMouseTracking(True)
        close = QPushButton("✕", self)
        close.setObjectName("BtnIcon")
        close.setFixedSize(22, 22)
        close.setToolTip("隐藏此卡片（设置页可恢复）")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(lambda: self._page.hide_card(self.card_id))
        header.addWidget(grip)
        header.addWidget(title_lb)
        header.addStretch(1)
        header.addWidget(close)
        root.addLayout(header)

        self._body = QHBoxLayout()  # 横向布局：仪表 + 信息列
        self._body.setSpacing(10)
        root.addLayout(self._body)

        for w in (grip, title_lb):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            w.installEventFilter(self)

    # ---- 子类接口 ----
    def update_data(self, snap: dict):  # noqa: ARG002
        pass

    # ---- 拖拽排序 ----
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press_global = ev.globalPosition().toPoint()
            self._press_el = ev.position().toPoint()
            self._dragging = False
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._press_global is not None and not self._dragging:
            d = (ev.globalPosition().toPoint() - self._press_global).manhattanLength()
            if d > 14:
                self._start_drag(ev.position().toPoint())
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._press_global = None
        self._dragging = False
        super().mouseReleaseEvent(ev)

    def _start_drag(self, pos):
        self._dragging = True
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_CARD, self.card_id.encode("utf-8"))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(pos)
        drag.exec(Qt.DropAction.MoveAction)
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME_CARD) and \
                ev.mimeData().data(MIME_CARD).data().decode() != self.card_id:
            ev.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            ev.ignore()

    def dragLeaveEvent(self, _ev):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, ev):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if ev.mimeData().hasFormat(MIME_CARD):
            drag_id = ev.mimeData().data(MIME_CARD).data().decode()
            self._page.reorder(drag_id, self.card_id)
            ev.acceptProposedAction()

    def eventFilter(self, obj, ev):
        # 把标题/grip 上的鼠标拖拽事件转发到卡片自身
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress:
            self.mousePressEvent(ev)
            return True
        if t == QEvent.Type.MouseMove:
            self.mouseMoveEvent(ev)
            return True
        if t == QEvent.Type.MouseButtonRelease:
            self.mouseReleaseEvent(ev)
            return True
        return super().eventFilter(obj, ev)

    # ---- 工具 ----
    def _transparent(self, w):
        """非交互区域允许鼠标事件穿透，以便整卡拖动。"""
        w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


# ------------------------------------------------------------------ 卡片实现
class ClockCard(DashCard):
    def __init__(self, page):
        super().__init__("clock", "实时时钟", page)
        self._time = make_label("--:--:--", "BigTime", parent=self)
        self._date = make_label("", "DateTime", parent=self)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self._time)
        col.addWidget(self._date)
        self._body.addLayout(col, 1)
        for w in (self._time, self._date):
            self._transparent(w)

    def update_data(self, snap):  # noqa: ARG002
        now = datetime.datetime.now()
        self._time.setText(now.strftime("%H:%M:%S"))
        self._date.setText(
            f"{now.year} 年 {now.month} 月 {now.day} 日 · 星期{'一二三四五六日'[now.weekday()]}")


class CpuCard(DashCard):
    def __init__(self, page):
        super().__init__("cpu", "CPU", page)
        self._gauge = RingGauge(GAUGE, sub="占用率",
                                color_provider=page.colors, parent=self)
        self._transparent(self._gauge)
        self._body.addWidget(self._gauge)

        col = QVBoxLayout()
        col.setSpacing(6)
        self._sub = make_label("—", "SubText", parent=self)
        self._sub.setWordWrap(True)
        self._toggle = QPushButton("每核心 ▾", self)
        self._toggle.setObjectName("Ghost")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._toggle_cores)
        col.addWidget(self._sub)
        col.addWidget(self._toggle)
        col.addStretch(1)
        self._body.addLayout(col, 1)

        self._cores = QFrame(self)
        self._cores_ly = QVBoxLayout(self._cores)
        self._cores_ly.setContentsMargins(0, 2, 0, 2)
        self._cores_ly.setSpacing(3)
        self._cores.hide()
        self._core_bars = []
        self._body.addWidget(self._cores)

    def _ensure_cores(self, n):
        while len(self._core_bars) < n:
            row = QHBoxLayout()
            row.setSpacing(6)
            lb = make_label(f"核{len(self._core_bars) + 1:02d}", "SubText", size=10,
                            parent=self._cores)
            lb.setFixedWidth(30)
            bar = MiniBar(color_provider=self._page.colors, parent=self._cores)
            row.addWidget(lb)
            row.addWidget(bar, 1)
            self._cores_ly.addLayout(row)
            self._core_bars.append(bar)

    def _toggle_cores(self):
        show = not self._cores.isVisible()
        self._cores.setVisible(show)
        self._toggle.setText("每核心 ▴" if show else "每核心 ▾")
        self.updateGeometry()

    def update_data(self, snap):
        cpu = snap.get("cpu", {})
        self._gauge.set_target(cpu.get("total", 0))
        parts = []
        if cpu.get("temp_c") is not None:
            parts.append(f"温度 {cpu['temp_c']:.0f}°C")
        if cpu.get("freq_mhz"):
            parts.append(f"频率 {cpu['freq_mhz'] / 1000:.1f} GHz")
        self._sub.setText(" · ".join(parts) or "温度与频率不可用")
        per = cpu.get("per_core") or []
        self._ensure_cores(len(per))
        for bar, v in zip(self._core_bars, per):
            bar.set_value(v)


class GpuCard(DashCard):
    def __init__(self, page):
        super().__init__("gpu", "GPU", page)
        self._gauge = RingGauge(GAUGE, sub="占用率",
                                color_provider=page.colors, parent=self)
        self._transparent(self._gauge)
        self._body.addWidget(self._gauge)

        col = QVBoxLayout()
        col.setSpacing(6)
        vram_row = QHBoxLayout()
        vram_row.setSpacing(8)
        self._vram = RingGauge(64, thickness=7, sub="显存",
                               color_provider=page.colors, parent=self)
        self._vram._font_size = 13
        self._vram.setFixedSize(64, 64)
        self._transparent(self._vram)
        self._sub = make_label("", "SubText", parent=self)
        self._sub.setWordWrap(True)
        vram_row.addWidget(self._vram)
        vram_row.addWidget(self._sub, 1)
        col.addLayout(vram_row)
        col.addStretch(1)
        self._body.addLayout(col, 1)

    def update_data(self, snap):
        gpu = snap.get("gpu", {}) or {}
        if not gpu.get("ok"):
            self._gauge.set_target(0)
            self._vram.set_target(0)
            self._sub.setText("未检测到 NVIDIA GPU\n（或驱动未安装）")
            return
        self._gauge.set_target(gpu.get("usage", 0))
        self._vram.set_target(gpu.get("vram_pct", 0))
        temp = f"{gpu['temp_c']:.0f}°C" if gpu.get("temp_c") else "N/A"
        self._sub.setText(f"{fmt_bytes(gpu.get('vram_used', 0))} / "
                          f"{fmt_bytes(gpu.get('vram_total', 0))}\n温度 {temp}")


class MemCard(DashCard):
    def __init__(self, page):
        super().__init__("memory", "内存", page)
        self._gauge = RingGauge(GAUGE, sub="占用率",
                                color_provider=page.colors, parent=self)
        self._transparent(self._gauge)
        self._body.addWidget(self._gauge)

        col = QVBoxLayout()
        col.setSpacing(6)
        self._sub = make_label("", "SubText", parent=self)
        self._sub.setWordWrap(True)
        col.addWidget(self._sub)
        col.addStretch(1)
        self._body.addLayout(col, 1)

    def update_data(self, snap):
        mem = snap.get("mem", {})
        self._gauge.set_target(mem.get("percent", 0))
        self._sub.setText(f"已用 {fmt_bytes(mem.get('used', 0))}\n"
                          f"共 {fmt_bytes(mem.get('total', 0))}")


class DiskCard(DashCard):
    def __init__(self, page):
        super().__init__("disk", "磁盘", page)
        self._rows = {}
        self._rows_layout = QVBoxLayout()
        self._body.addLayout(self._rows_layout, 1)

    def update_data(self, snap):
        disks = snap.get("disk", []) or []
        for d in disks:
            mount = d.get("mount", "?")
            if mount not in self._rows:
                row = QHBoxLayout()
                row.setSpacing(8)
                lb = make_label(mount, "SubText", size=11, parent=self)
                lb.setFixedWidth(22)
                bar = MiniBar(color_provider=self._page.colors, parent=self)
                lb2 = make_label("", "SubText", size=10, parent=self)
                lb2.setFixedWidth(150)
                row.addWidget(lb)
                row.addWidget(bar, 1)
                row.addWidget(lb2)
                self._rows_layout.addLayout(row)
                self._rows[mount] = (bar, lb2)
            bar, lb2 = self._rows[mount]
            bar.set_value(d.get("percent", 0))
            lb2.setText(f"{d.get('percent', 0):.0f}%   ↓{fmt_bps(d.get('read_bps') or 0)}"
                        f"  ↑{fmt_bps(d.get('write_bps') or 0)}")


CARD_FACTORIES = {
    "clock": ClockCard,
    "cpu": CpuCard,
    "gpu": GpuCard,
    "memory": MemCard,
    "disk": DiskCard,
}


# ------------------------------------------------------------------ 页面
class DashboardPage(Page):
    id = "dashboard"
    title = "仪表盘"
    icon = "◈"
    order = 0

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._cards: dict[str, DashCard] = {}
        self._grid = QGridLayout()
        self._grid.setSpacing(10)
        self.setLayout(self._grid)

    def colors(self):
        p = theme_mod.palette(self.cfg)
        return p["accent1"], p["accent2"]

    def build(self):
        for cid, factory in CARD_FACTORIES.items():
            card = factory(self)
            self._cards[cid] = card
        hint = make_label("≡ 长按标题拖拽排序   ·   ✕ 隐藏卡片（设置页可恢复）",
                          "SubText", size=11, parent=self)
        self._grid.addWidget(hint, 99, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        self._grid.setRowStretch(99, 1)
        self.subscribe("sysmon:data", self.on_data)
        self.cfg.changed.connect(self._on_cfg)
        self._relayout()

    def _on_cfg(self, key):
        if key in ("card_order", "hidden_cards", "*"):
            self._relayout()

    def _visible_order(self):
        hidden = set(self.cfg.get("hidden_cards", []))
        order = list(self.cfg.get("card_order", []))
        order += [cid for cid in CARD_FACTORIES if cid not in order]
        return [cid for cid in order if cid in self._cards and cid not in hidden]

    def _relayout(self):
        for card in self._cards.values():
            self._grid.removeWidget(card)
        for i, cid in enumerate(self._visible_order()):
            card = self._cards[cid]
            self._grid.addWidget(card, i // 2, i % 2)
            card.setMinimumHeight(160)
        self._grid.setRowStretch(99, 1)

    def hide_card(self, cid: str):
        hidden = [h for h in self.cfg.get("hidden_cards", []) if h != cid]
        hidden.append(cid)
        self.cfg.set("hidden_cards", hidden)

    def reorder(self, drag_id: str, target_id: str):
        # 更新完整顺序（含隐藏卡片）
        full = list(self.cfg.get("card_order", []))
        full = [c for c in full if c != drag_id]
        idx = full.index(target_id) if target_id in full else 0
        full.insert(idx, drag_id)
        self.cfg.set("card_order", full)

    def on_data(self, snap: dict):
        for card in self._cards.values():
            try:
                card.update_data(snap)
            except Exception:  # noqa: BLE001
                pass
