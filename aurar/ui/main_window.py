"""主窗口：无边框悬浮小部件。

- 始终置顶（可关闭） / 可拖动 / 右下角可缩放
- 激活时完全不透明，失焦/未悬停时平滑渐变为半透明（可配置，200ms）
- 左侧导航动态生成（页面插件系统），关闭隐藏到托盘
"""

from types import SimpleNamespace

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QPropertyAnimation,
                            QRect, QSize, Qt, QTimer)
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


class MainWindow(QWidget):
    def __init__(self, cfg, bus):
        super().__init__()
        self.cfg = cfg
        self.bus = bus
        self._quitting = False
        self._press_global: QPoint | None = None
        self._drag_active = False
        self._tray_msg_shown = False

        self._init_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("AuraDash")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(MIN_W, MIN_H)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_anim.setDuration(cfg.get("opacity_duration_ms", 200))
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._build_ui()
        self._build_tray()
        self._start_monitor()

        self._geom_timer = QTimer(self)
        self._geom_timer.setSingleShot(True)
        self._geom_timer.setInterval(500)
        self._geom_timer.timeout.connect(self._save_geometry)

        self._restore_geometry()
        self.cfg.changed.connect(self._on_cfg)

        QTimer.singleShot(0, self._apply_config)

    # ------------------------------------------------------------ 基础
    def _init_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinimizeButtonHint
        if self.cfg.get("always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
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

        # 标题栏
        tb = QHBoxLayout()
        tb.setSpacing(6)
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

        self._btn_pin = QPushButton("置顶", self)
        self._btn_pin.setObjectName("BtnIcon")
        self._btn_pin.setCheckable(True)
        self._btn_pin.setChecked(self.cfg.get("always_on_top", True))
        self._btn_pin.setFixedHeight(26)
        self._btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_pin.toggled.connect(self._toggle_pin)

        self._btn_min = QPushButton("─", self)
        self._btn_min.setObjectName("BtnIcon")
        self._btn_min.setFixedSize(26, 26)
        self._btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_min.clicked.connect(self.showMinimized)

        self._btn_close = QPushButton("✕", self)
        self._btn_close.setObjectName("BtnIcon")
        self._btn_close.setProperty("class", "close")
        self._btn_close.setStyleSheet("#BtnIcon { color: #FF6B81; }")
        self._btn_close.setFixedSize(26, 26)
        self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_close.clicked.connect(self.close)

        for b in (self._btn_pin, self._btn_min, self._btn_close):
            tb.addWidget(b)
        fv.addLayout(tb)

        # 主区域：左导航 + 页面栈
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

        # 右下角缩放手柄
        grip = QSizeGrip(self._frame)
        grip.setFixedSize(16, 16)
        row.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        self._stack.currentChanged.connect(self._on_page_changed)

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
        self._act_pin = QAction("窗口置顶", menu)
        self._act_pin.setCheckable(True)
        self._act_pin.setChecked(self._btn_pin.isChecked())
        self._act_pin.toggled.connect(self._btn_pin.setChecked)
        self._act_auto = QAction("开机自启动", menu)
        self._act_auto.setCheckable(True)
        self._act_auto.setChecked(self.cfg.get("autostart", False))
        menu.addAction(self._act_pin)
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
        if key in ("always_on_top", "opacity_duration_ms", "opacity_active",
                   "opacity_inactive", "*"):
            if key == "*":
                self._init_flags()
                self._btn_pin.setChecked(self.cfg.get("always_on_top", True))
            elif key == "always_on_top":
                self._init_flags()
                self._btn_pin.setChecked(self.cfg.get("always_on_top", True))
            self._opacity_anim.stop()
            self._opacity_anim.setDuration(self.cfg.get("opacity_duration_ms", 200))
        if key in ("refresh_sec", "*"):
            self._poll.set_interval(self.cfg.get("refresh_sec", 1.0))
        if key == "*" or key.startswith("theme") or key == "font_scale":
            self._apply_theme()
        if key == "autostart":
            self._act_auto.setChecked(self.cfg.get("autostart", False))

    def _apply_config(self):
        self._apply_theme()
        self._btn_pin.setChecked(self.cfg.get("always_on_top", True))
        self._act_pin.setChecked(self._btn_pin.isChecked())
        self._act_auto.setChecked(self.cfg.get("autostart", False))

    def _apply_theme(self):
        theme_mod.apply(QApplication.instance(), self.cfg)

    def _toggle_pin(self, on):
        self.cfg.set("always_on_top", on)
        self._init_flags()
        self.show()

    # ------------------------------------------------------------ 透明度
    def _animate_opacity(self, target):
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(target)
        self._opacity_anim.start()

    def _is_focused(self):
        return self.isActiveWindow()

    def _fade_to(self, active: bool):
        key = "opacity_active" if active else "opacity_inactive"
        self._animate_opacity(self.cfg.get(key, 100) / 100.0)

    def changeEvent(self, ev):
        if ev.type() == QEvent.Type.ActivationChange:
            self._fade_to(self._is_focused())
        super().changeEvent(ev)

    def enterEvent(self, ev):
        if self._is_focused():
            self._fade_to(True)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._fade_to(False)
        super().leaveEvent(ev)

    # ------------------------------------------------------------ 拖动
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press_global = ev.globalPosition().toPoint()
            self._press_local = ev.position().toPoint()
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

    def resizeEvent(self, _ev):
        self._geom_timer.start()

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
