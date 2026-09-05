"""主窗口：无边框悬浮小部件。

- 固定不透明度（设置中调节；0% 进入“小部件模式”，仅主体元素可见）
- 可拖动 / 八向边框缩放（锁定后禁用）
- 标题栏：锁（固定位置）· 层级切换（置顶/普通/置底）· 最小化 · 关闭
- 左侧导航：页面切换 · 日/夜主题切换 · 设置
"""

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout,
                               QLabel, QMenu, QPushButton, QSizeGrip,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from .. import __version__
from ..core import theme as theme_mod
from ..core.logger import get_logger
from ..core.paths import resource_path
from ..core.sysmon import PollThread
from ..pages import load_pages
from .settings import SettingsDialog

log = get_logger("window")

MIN_W, MIN_H = 400, 300
EDGE = 6  # 边框可缩放灵敏度（px）

Z_ICONS = {"top": "顶", "normal": "普", "bottom": "底"}
Z_TIPS = {"top": "始终置顶（最上层）", "normal": "普通层级", "bottom": "桌面底层（不误触、不遮挡）"}
Z_CYCLE = ["top", "normal", "bottom"]


def _default_icon() -> QIcon:
    """内置图标兜底：渐变圆环 + 光点。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#00D4FF"))
    p.drawEllipse(QRect(6, 6, 52, 52))
    p.setBrush(QColor("#7B2FBE"))
    p.drawEllipse(QRect(16, 16, 32, 32))
    p.setBrush(QColor("#0A0E1A"))
    p.drawEllipse(QRect(24, 24, 16, 16))
    p.end()
    return QIcon(pm)


def app_icon() -> QIcon:
    for rel in ("assets/aura.ico", "assets/aura.png"):
        path = resource_path(rel)
        try:
            icon = QIcon(path)
            if not icon.isNull():
                return icon
        except Exception:  # noqa: BLE001
            pass
    return _default_icon()


class EdgeResizer(QWidget):
    """窗口边缘缩放条：贴边 6px，支持水平/垂直/对角缩放。"""

    CURSORS = {
        "left": Qt.CursorShape.SizeHorCursor,
        "right": Qt.CursorShape.SizeHorCursor,
        "top": Qt.CursorShape.SizeVerCursor,
        "bottom": Qt.CursorShape.SizeVerCursor,
        "tl": Qt.CursorShape.SizeFDiagCursor,
        "tr": Qt.CursorShape.SizeBDiagCursor,
        "bl": Qt.CursorShape.SizeBDiagCursor,
        "br": Qt.CursorShape.SizeFDiagCursor,
    }

    def __init__(self, win: "MainWindow", direction: str):
        super().__init__(win)
        self._win = win
        self._dir = direction
        self._start_geo = None
        self._start_pos = None
        self.setMouseTracking(True)
        self.hide()  # 由 _apply_locked 决定可见性

    def enterEvent(self, ev):
        self.setCursor(self.CURSORS[self._dir])
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.unsetCursor()
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._start_geo = self._win.geometry()
            self._start_pos = ev.globalPosition().toPoint()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._start_geo is None:
            return
        if not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        g = self._win.geometry()
        d = ev.globalPosition().toPoint() - self._start_pos
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        if "l" in self._dir:
            w -= d.x()
            x += d.x()
        if "r" in self._dir:
            w += d.x()
        if "t" in self._dir:
            h -= d.y()
            y += d.y()
        if "b" in self._dir:
            h += d.y()
        if w < MIN_W:
            x = g.x() + g.width() - MIN_W
            w = MIN_W
        if h < MIN_H:
            y = g.y() + g.height() - MIN_H
            h = MIN_H
        self._win.setGeometry(QRect(x, y, w, h))
        self._start_pos = ev.globalPosition().toPoint()

    def mouseReleaseEvent(self, ev):
        self._start_geo = None
        super().mouseReleaseEvent(ev)

    def relocate(self):
        """按窗口当前几何重新定位边缘条（覆盖在内容之上）。"""
        gx, gy, gw, gh = 0, 0, self._win.width(), self._win.height()
        e = EDGE
        geo = {
            "left": QRect(0, 0, e, gh),
            "right": QRect(gw - e, 0, e, gh),
            "top": QRect(0, 0, gw, e),
            "bottom": QRect(0, gh - e, gw, e),
            "tl": QRect(0, 0, e * 2, e * 2),
            "tr": QRect(gw - e * 2, 0, e * 2, e * 2),
            "bl": QRect(0, gh - e * 2, e * 2, e * 2),
            "br": QRect(gw - e * 2, gh - e * 2, e * 2, e * 2),
        }
        self._win._edge_geo[self._dir] = geo[self._dir]
        self.setGeometry(geo[self._dir])
        self.raise_()


class MainWindow(QWidget):
    def __init__(self, cfg, bus):
        super().__init__()
        self.cfg = cfg
        self.bus = bus
        self._quitting = False
        self._press_global: QPoint | None = None
        self._tray_msg_shown = False
        self._edge_geo = {}

        self._apply_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("AuraDash")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(MIN_W, MIN_H)

        self._build_ui()
        self._build_edge_resizers()
        self._build_tray()
        self._start_monitor()

        self._geom_timer = QTimer(self)
        self._geom_timer.setSingleShot(True)
        self._geom_timer.setInterval(500)
        self._geom_timer.timeout.connect(self._save_geometry)

        self._restore_geometry()
        self.cfg.changed.connect(self._on_cfg)
        # 先应用一次主题（比窗口构建更早的 QSS 保证初始样式一致）
        QTimer.singleShot(0, self._apply_config)
        # 显示后强制全量 repolish，修复部分控件（标题栏按钮）文字不渲染的问题
        QTimer.singleShot(120, self._force_repolish)

    def _force_repolish(self):
        def walk(w):
            st = w.style()
            st.unpolish(w)
            st.polish(w)
            for child in w.findChildren(QWidget):
                try:
                    st.unpolish(child)
                    st.polish(child)
                except Exception:  # noqa: BLE001
                    pass
        walk(self)

    # ------------------------------------------------------------ 基础
    def _apply_flags(self):
        z = self.cfg.get("z_order", "top")
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinimizeButtonHint
        if z == "top":
            flags |= Qt.WindowType.WindowStaysOnTopHint
        elif z == "bottom":
            flags |= Qt.WindowType.WindowStaysOnBottomHint
        self.setWindowFlags(flags)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._frame = QFrame(self)
        self._frame.setObjectName("RootFrame")
        outer.addWidget(self._frame)

        fv = QVBoxLayout(self._frame)
        fv.setContentsMargins(10, 8, 10, 8)
        fv.setSpacing(6)

        # ---- 标题栏：锁 · 层级 · 最小化 · 关闭 ----
        tb = QHBoxLayout()
        tb.setSpacing(4)
        self._tb_layout = tb
        icon = QLabel(self)
        icon.setPixmap(app_icon().pixmap(20, 20))
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title = QLabel("AURA DASH", self)
        title.setObjectName("CardTitleAccent")
        title.setStyleSheet("font-weight:600; letter-spacing:3px; font-size:12px;")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        tb.addWidget(icon)
        tb.addWidget(title)
        tb.addStretch(1)

        self._btn_lock = QPushButton("锁", self)
        self._btn_lock.setObjectName("BtnIcon")
        self._btn_lock.setCheckable(True)
        self._btn_lock.setFixedSize(28, 26)
        self._btn_lock.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_lock.toggled.connect(self._toggle_lock)
        self._btn_lock.setToolTip("锁定：固定位置与大小（点击解锁）")

        self._btn_z = QPushButton(Z_ICONS["top"], self)
        self._btn_z.setObjectName("BtnIcon")
        self._btn_z.setFixedSize(28, 26)
        self._btn_z.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_z.clicked.connect(self._cycle_z)
        self._btn_z.setToolTip("点击切换：置顶 → 普通 → 置底")

        self._btn_min = QPushButton("—", self)
        self._btn_min.setObjectName("BtnIcon")
        self._btn_min.setFixedSize(28, 26)
        self._btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_min.setToolTip("最小化到任务栏")
        self._btn_min.clicked.connect(self.showMinimized)

        self._btn_close = QPushButton("×", self)
        self._btn_close.setObjectName("BtnClose")
        self._btn_close.setFixedSize(28, 26)
        self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_close.setToolTip("关闭（最小化到托盘）")
        self._btn_close.clicked.connect(self.close)

        for b in (self._btn_lock, self._btn_z, self._btn_min, self._btn_close):
            tb.addWidget(b)
        fv.addLayout(tb)

        # ---- 主区域：左导航 + 页面栈 ----
        row = QHBoxLayout()
        row.setSpacing(6)

        side = QFrame(self)
        side.setObjectName("SideBar")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(4, 8, 4, 8)
        sv.setSpacing(4)

        self._stack = QStackedWidget(self)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        self.pages = []
        page_cls_list = load_pages()
        for i, cls in enumerate(page_cls_list):
            page = cls(SimpleNamespace(cfg=self.cfg, bus=self.bus, window=self))
            page.build()
            self.pages.append(page)
            self._stack.addWidget(page)

            nav = QPushButton(f"{cls.icon}\n{cls.title}", side)
            nav.setObjectName("NavButton")
            nav.setCheckable(True)
            nav.setFixedSize(62, 58)
            nav.setCursor(Qt.CursorShape.PointingHandCursor)
            nav.clicked.connect(lambda _=False, idx=i: self._stack.setCurrentIndex(idx))
            self._nav_group.addButton(nav)
            sv.addWidget(nav)
            if i == 0:
                nav.setChecked(True)

        sv.addStretch(1)

        # ---- 日/夜主题切换 ----
        self._btn_theme = QPushButton(self._theme_icon_text(), side)
        self._btn_theme.setObjectName("NavButton")
        self._btn_theme.setFixedSize(62, 58)
        self._btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_theme.setToolTip("切换 黑夜 / 白天 主题")
        self._btn_theme.clicked.connect(self._toggle_theme)
        sv.addWidget(self._btn_theme)

        # ---- 设置 ----
        gear = QPushButton("⚙\n设置", side)
        gear.setObjectName("NavButton")
        gear.setFixedSize(62, 58)
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.clicked.connect(self._open_settings)
        sv.addWidget(gear)

        ver = QLabel(f"v{__version__}", side)
        ver.setObjectName("SubText")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("font-size:10px;")
        ver.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        sv.addWidget(ver)

        row.addWidget(side)
        row.addWidget(self._stack, 1)
        fv.addLayout(row, 1)

        # 右下角缩放手柄（与边缘条并存）
        grip = QSizeGrip(self._frame)
        grip.setFixedSize(16, 16)
        self._grip = grip
        row.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        self._stack.currentChanged.connect(self._on_page_changed)

    def _build_edge_resizers(self):
        self._edges = {}
        for d in ("left", "right", "top", "bottom", "tl", "tr", "bl", "br"):
            r = EdgeResizer(self, d)
            self._edges[d] = r
            r.show()
        self._relocate_edges()
        self._apply_locked(show_resize=not self.cfg.get("locked", False))

    def _relocate_edges(self):
        for r in self._edges.values():
            r.relocate()

    # ------------------------------------------------------------ 边缘交互
    def _apply_locked(self, show_resize: bool):
        locked = self.cfg.get("locked", False)
        self._btn_lock.setText("锁")
        self._btn_lock.setToolTip("已锁定：固定位置与大小（点击解锁）" if locked
                                  else "锁定：固定位置与大小（点击锁定）")
        for r in self._edges.values():
            r.setVisible(show_resize and not locked)
        self._grip.setVisible(not locked)
        self._relocate_edges()

    def _toggle_lock(self, on: bool):
        self.cfg.set("locked", on)
        self._apply_locked(show_resize=True)

    # ------------------------------------------------------------ 层级
    def _cycle_z(self):
        z = self.cfg.get("z_order", "top")
        idx = (Z_CYCLE.index(z) + 1) % len(Z_CYCLE)
        self.cfg.set("z_order", Z_CYCLE[idx])

    def _apply_z(self):
        z = self.cfg.get("z_order", "top")
        self._btn_z.setText(Z_ICONS.get(z, "●"))
        self._btn_z.setToolTip(f"显示层级：{Z_TIPS.get(z, '')}（点击切换）")
        self._apply_flags()
        self.show()

    # ------------------------------------------------------------ 主题
    def _theme_icon_text(self) -> str:
        name = (self.cfg.get("theme", {}) or {}).get("name", "dark")
        return "☀\n白天" if name == "light" else "☾\n黑夜"

    def _toggle_theme(self):
        name = (self.cfg.get("theme", {}) or {}).get("name", "dark")
        self.cfg.set("theme.name", "light" if name == "dark" else "dark")

    # ------------------------------------------------------------ 托盘
    def _build_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("AuraDash 系统监控仪表盘")
        menu = QMenu()
        act_show = QAction("显示主界面", menu)
        act_show.triggered.connect(self._show_window)
        act_hide = QAction("隐藏窗口", menu)
        act_hide.triggered.connect(self.hide)
        menu.addAction(act_show)
        menu.addAction(act_hide)
        menu.addSeparator()
        self._act_lock = QAction("锁定窗口位置", menu)
        self._act_lock.setCheckable(True)
        self._act_lock.setChecked(self.cfg.get("locked", False))
        self._act_lock.toggled.connect(self._btn_lock.setChecked)
        self._act_auto = QAction("开机自启动", menu)
        self._act_auto.setCheckable(True)
        self._act_auto.setChecked(self.cfg.get("autostart", False))
        menu.addAction(self._act_lock)
        menu.addAction(self._act_auto)
        menu.addSeparator()
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------ 监控
    def _start_monitor(self):
        self._poll = PollThread(interval=self.cfg.get("refresh_sec", 1.0), parent=self)
        self._poll.data.connect(lambda d: self.bus.publish("sysmon:data", d))
        self._poll.start()

    # ------------------------------------------------------------ 配置响应
    def _on_cfg(self, key):
        if key == "*":
            self._apply_flags()
            self._apply_z()
            self._apply_theme()
            self._apply_locked(show_resize=True)
            self._poll.set_interval(self.cfg.get("refresh_sec", 1.0))
            self._sync_tray()
            return
        if key == "z_order":
            self._apply_z()
        if key == "locked":
            self._apply_locked(show_resize=True)
        if key == "refresh_sec":
            self._poll.set_interval(self.cfg.get("refresh_sec", 1.0))
        if key == "window_opacity" or key.startswith("theme") or key == "font_scale":
            self._apply_theme()
        if key == "theme.name":
            self._btn_theme.setText(self._theme_icon_text())
        if key == "autostart":
            self._act_auto.setChecked(self.cfg.get("autostart", False))

    def _apply_config(self):
        self._apply_theme()
        self._apply_z()
        self._apply_locked(show_resize=True)
        self._btn_lock.setChecked(self.cfg.get("locked", False))
        self._btn_theme.setText(self._theme_icon_text())
        self._sync_tray()

    def _sync_tray(self):
        self._act_lock.setChecked(self.cfg.get("locked", False))
        self._act_auto.setChecked(self.cfg.get("autostart", False))

    def _apply_theme(self):
        theme_mod.apply(QApplication.instance(), self.cfg)

    # ------------------------------------------------------------ 拖动
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and not self.cfg.get("locked", False):
            self._press_global = ev.globalPosition().toPoint()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._press_global is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            delta = ev.globalPosition().toPoint() - self._press_global
            self.move(self.pos() + delta)
            self._press_global = ev.globalPosition().toPoint()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._press_global = None
        super().mouseReleaseEvent(ev)

    # ------------------------------------------------------------ 几何
    def _restore_geometry(self):
        wcfg = self.cfg.get("window", {}) or {}
        w = int(wcfg.get("w") or 780)
        h = int(wcfg.get("h") or 540)
        x, y = wcfg.get("x"), wcfg.get("y")
        if x is not None and y is not None:
            self.setGeometry(int(x), int(y), w, h)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.setGeometry(geo.center().x() - w // 2,
                                 geo.center().y() - h // 2, w, h)
            else:
                self.resize(w, h)

    def _save_geometry(self):
        c = self.cfg
        c.set("window.w", self.width())
        c.set("window.h", self.height())
        c.set("window.x", self.x())
        c.set("window.y", self.y())

    def moveEvent(self, _ev):
        self._geom_timer.start()
        self._relocate_edges()

    def resizeEvent(self, _ev):
        self._geom_timer.start()
        self._relocate_edges()

    # ------------------------------------------------------------ 页面
    def _on_page_changed(self, idx):
        page = self.pages[idx] if 0 <= idx < len(self.pages) else None
        if page:
            try:
                page.on_show()
            except Exception:  # noqa: BLE001
                pass

    def _open_settings(self):
        dlg = getattr(self, "_settings_dlg", None)
        if dlg is None:
            dlg = SettingsDialog(self.cfg, self)
            self._settings_dlg = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ------------------------------------------------------------ 生命周期
    def closeEvent(self, ev):
        if not self._quitting and self.tray.isVisible():
            self.hide()
            if not self._tray_msg_shown:
                self.tray.showMessage("AuraDash",
                                      "已最小化到托盘。双击托盘图标或右键菜单可再次打开。",
                                      QSystemTrayIcon.MessageIcon.Information, 2500)
                self._tray_msg_shown = True
            ev.ignore()
            return
        ev.accept()
        self.quit()

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        log.info("AuraDash 退出")
        try:
            self._poll.stop()
            self._poll.wait(2000)
            for page in self.pages:
                stop = getattr(page, "stop", None)
                if callable(stop):
                    stop()
        except Exception:  # noqa: BLE001
            pass
        self.tray.hide()
        QApplication.instance().quit()
