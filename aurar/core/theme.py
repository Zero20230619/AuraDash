"""主题系统：白天/黑夜两套预设 + 霓虹主辅色 + 固定不透明度渲染。

不透明度（window_opacity 0-100）只作用于“框架”：
    - 100%：完全渲染（渐变背景 + 边框 + 侧栏）
    - 0%  ：框架完全消失，仅保留卡片等主体元素（桌面小部件模式）
卡片自身的背景与边框按比例保留，保证任意不透明度下内容可读。
"""

from .logger import get_logger

log = get_logger("theme")

BASE_DARK = {
    "bg": "#0A0E1A",
    "bg2": "#101830",
    "text": "#E6ECF8",
    "sub": "#8FA3C0",
    "danger": "#FF6B81",
}

BASE_LIGHT = {
    "bg": "#EEF2F9",
    "bg2": "#FFFFFF",
    "text": "#16203A",
    "sub": "#5A6780",
    "danger": "#E5484D",
}


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = max(0, min(255, int(round(alpha * 255))))
    return f"rgba({r},{g},{b},{a})"


def palette(cfg) -> dict:
    """计算当前主题调色板（自定义绘制组件也从这里取色）。"""
    t = cfg.get("theme", {}) or {}
    base = BASE_LIGHT if t.get("name") == "light" else BASE_DARK
    c1 = t.get("accent1") or "#00D4FF"
    c2 = t.get("accent2") or "#7B2FBE"

    frame = max(0.0, min(1.0, cfg.get("window_opacity", 100) / 100.0))
    # 卡片/控件底色与边框为固定低透明度“玻璃”，不随框架透明度变化：
    # 不透明度为 0 时（小部件模式）卡片依然隐约可见，文字始终可读。
    panel = 0.13
    panel2 = 0.26
    border = 0.15
    track = 0.12

    pal = dict(base)
    pal.update({
        "accent1": c1, "accent2": c2, "theme_name": t.get("name", "dark"),
        "frame": frame,
        # rgba 形式（透明度驱动）
        "bg_rgba": _rgba(base["bg"], frame),
        "bg2_rgba": _rgba(base["bg2"], frame),
        "text_rgba": _rgba(base["text"], 1.0),
        "panel_rgba": _rgba(base["text"], panel) if base is BASE_DARK else "rgba(10,20,50,{:.2f})".format(panel),
        "border_rgba": _rgba(base["sub"] if base is BASE_DARK else base["text"], border),
        "track_rgba": _rgba(base["sub"], track),
        "hover_rgba": _rgba(base["text"], panel2),
    })
    return pal


def _qss(cfg) -> str:
    p = palette(cfg)
    font_px = max(9, round(13 * (cfg.get("font_scale", 100) / 100.0)))
    side_alpha = p["frame"] * 0.18
    reps = {
        "@@BG_RGBA@@": p["bg_rgba"],
        "@@BG2_RGBA@@": p["bg2_rgba"],
        "@@ACC1@@": p["accent1"],
        "@@ACC2@@": p["accent2"],
        "@@TEXT@@": p["text"],
        "@@SUB@@": p["sub"],
        "@@PANEL@@": p["panel_rgba"],
        "@@PANEL2@@": p["hover_rgba"],
        "@@BORDER@@": p["border_rgba"],
        "@@TRACK@@": p["track_rgba"],
        "@@BASESIZE@@": str(font_px),
        "@@DANGER@@": p["danger"],
        "@@SIDE@@": f"rgba(0,0,0,{side_alpha:.2f})",
    }
    qss = QSS_TEMPLATE
    for k, v in reps.items():
        qss = qss.replace(k, v)
    return qss


def apply(app, cfg):
    """应用主题到整个 QApplication。"""
    try:
        app.setStyleSheet(_qss(cfg))
    except Exception as exc:  # noqa: BLE001
        log.exception("主题应用失败: %s", exc)


QSS_TEMPLATE = """
QWidget {
    color: @@TEXT@@;
    font-family: "Segoe UI", "Microsoft YaHei UI";
    font-size: @@BASESIZE@@px;
    background: transparent;
}

QFrame#RootFrame {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 @@BG_RGBA@@, stop:1 @@BG2_RGBA@@);
    border-radius: 16px;
    border: 1px solid @@BORDER@@;
}

QFrame#TitleBar { background: transparent; }
QFrame#SideBar  { background: @@SIDE@@; border-radius: 14px; }

/* ---------- 标题栏按钮 ---------- */
QPushButton#BtnIcon {
    background: transparent; border: none; border-radius: 8px; color: @@SUB@@;
    font-family: "Segoe UI"; font-size: 14px; font-weight: 600; padding: 0px;
}
QPushButton#BtnIcon:hover { background: @@PANEL2@@; color: @@TEXT@@; }
QPushButton#BtnIcon:checked { border: 1px solid @@ACC1@@; color: @@ACC1@@; }
QPushButton#BtnClose { background: transparent; border: none; padding: 0px;
    color: @@DANGER@@; font-family: "Segoe UI"; font-size: 14px; font-weight: 600; }
QPushButton#BtnClose:hover { background: rgba(255,80,100,0.16); color: #FF9AA7; }

/* ---------- 导航 ---------- */
QPushButton#NavButton {
    background: transparent; border: none; border-radius: 10px;
    color: @@SUB@@; padding: 8px 2px; font-size: 11px;
}
QPushButton#NavButton:hover { background: @@PANEL2@@; color: @@TEXT@@; }
QPushButton#NavButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(0,212,255,0.22), stop:1 rgba(123,47,190,0.25));
    color: @@TEXT@@;
    border: 1px solid rgba(0,212,255,0.35);
}

/* ---------- 卡片 ---------- */
QFrame#DashCard {
    background: @@PANEL@@;
    border: 1px solid @@BORDER@@;
    border-radius: 12px;
}
QFrame#DashCard[dragging="true"] {
    background: @@PANEL2@@;
    border: 1px solid @@ACC1@@;
}
QFrame#StatsBox {
    background: @@PANEL@@; border: 1px solid @@BORDER@@; border-radius: 12px;
}
QLabel#CardTitle { color: @@SUB@@; font-size: 12px; letter-spacing: 1px; }
QLabel#CardTitleAccent { color: @@ACC1@@; font-size: 12px; letter-spacing: 1px; }
QLabel#SubText  { color: @@SUB@@; font-size: 12px; }
QLabel#Mono     { font-family: "Bahnschrift", "Consolas"; }
QLabel#BigTime  {
    font-family: "Bahnschrift", "Consolas";
    font-size: 44px; font-weight: 600; color: @@TEXT@@;
    letter-spacing: 2px;
}
QLabel#DateTime { color: @@SUB@@; font-size: 13px; }
QLabel#ValueBig { font-family: "Bahnschrift", "Consolas"; font-size: 20px; font-weight: 600; }

/* ---------- 通用控件 ---------- */
QPushButton {
    background: @@PANEL@@; border: 1px solid @@BORDER@@; border-radius: 8px;
    padding: 6px 14px; color: @@TEXT@@;
}
QPushButton:hover { border-color: @@ACC1@@; color: @@ACC1@@; }
QPushButton:pressed { background: transparent; }
QPushButton:disabled { color: @@SUB@@; border-color: @@BORDER@@; }
QPushButton#Primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @@ACC1@@, stop:1 @@ACC2@@);
    color: #FFFFFF; border: none; font-weight: 600;
}
QPushButton#Primary:hover { color: #FFFFFF; }
QPushButton#Ghost { background: transparent; }

QComboBox, QLineEdit {
    background: @@TRACK@@; border: 1px solid @@BORDER@@; border-radius: 8px;
    padding: 5px 10px; color: @@TEXT@@; selection-background-color: @@ACC2@@;
}
QComboBox:hover, QLineEdit:hover, QLineEdit:focus { border-color: @@ACC1@@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: @@BG2@@; color: @@TEXT@@; border: 1px solid @@BORDER@@;
    selection-background-color: rgba(123,47,190,0.45); outline: none;
}

QSpinBox {
    background: @@TRACK@@; border: 1px solid @@BORDER@@; border-radius: 8px;
    padding: 5px 10px; color: @@TEXT@@;
}
QSpinBox:hover, QSpinBox:focus { border-color: @@ACC1@@; }
QSpinBox::up-button, QSpinBox::down-button {
    background: transparent; border: none; width: 18px;
}
QSpinBox::up-arrow, QSpinBox::down-arrow {
    width: 8px; height: 6px; background: @@SUB@@;
}
QSpinBox::up-arrow:hover, QSpinBox::down-arrow:hover { background: @@ACC1@@; }

QSlider::groove:horizontal {
    height: 4px; background: @@TRACK@@; border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @@ACC1@@, stop:1 @@ACC2@@);
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0;
    background: @@TEXT@@; border-radius: 7px;
    border: 2px solid @@ACC1@@;
}
QSlider::handle:horizontal:hover { background: @@ACC1@@; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid @@BORDER@@; background: @@TRACK@@;
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @@ACC1@@, stop:1 @@ACC2@@);
    border: 1px solid @@ACC1@@;
}
QCheckBox::indicator:hover { border-color: @@ACC1@@; }

/* ---------- 表格（进程管理器） ---------- */
QTableView {
    background: transparent; border: none; gridline-color: transparent;
    alternate-background-color: @@PANEL@@;
    selection-background-color: rgba(0,212,255,0.18);
    selection-color: @@TEXT@@;
}
QTableView::item { padding: 2px 6px; border: none; }
QHeaderView::section {
    background: transparent; border: none; color: @@SUB@@;
    padding: 6px 8px; font-size: 12px; letter-spacing: 1px;
}
QHeaderView::section:hover { color: @@ACC1@@; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {
    background: transparent; width: 8px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: rgba(140,170,220,0.25); border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: @@ACC1@@; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: rgba(140,170,220,0.25); border-radius: 4px; min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QToolTip {
    background: @@BG2@@; color: @@TEXT@@; border: 1px solid @@ACC1@@;
    border-radius: 6px; padding: 4px 8px;
}
QSizeGrip { background: transparent; width: 14px; height: 14px; }
QMessageBox, QDialog { background: @@BG2@@; }
QStatusBar { background: transparent; color: @@SUB@@; }
"""
