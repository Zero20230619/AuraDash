"""主题系统：预设深色/浅色 + 自定义霓虹主色/辅色，动态生成全局 QSS。"""

from .logger import get_logger

log = get_logger("theme")

BASE_DARK = {
    "bg": "#0A0E1A",
    "bg2": "#101830",
    "panel": "rgba(255,255,255,0.045)",
    "panel2": "rgba(255,255,255,0.08)",
    "text": "#E6ECF8",
    "sub": "#8FA3C0",
    "border": "rgba(160,200,255,0.16)",
    "track": "rgba(160,200,255,0.10)",
}

BASE_LIGHT = {
    "bg": "#EDF1F8",
    "bg2": "#FFFFFF",
    "panel": "rgba(10,20,50,0.05)",
    "panel2": "rgba(10,20,50,0.09)",
    "text": "#16203A",
    "sub": "#5A6780",
    "border": "rgba(30,50,110,0.18)",
    "track": "rgba(30,50,110,0.10)",
}


def palette(cfg) -> dict:
    """计算当前主题调色板（自定义绘制组件也从这里取色）。"""
    t = cfg.get("theme", {}) or {}
    base = BASE_LIGHT if t.get("name") == "light" else BASE_DARK
    c1 = t.get("accent1") or "#00D4FF"
    c2 = t.get("accent2") or "#7B2FBE"
    pal = dict(base)
    pal.update({"accent1": c1, "accent2": c2, "theme_name": t.get("name", "dark")})
    return pal


def _qss(cfg) -> str:
    p = palette(cfg)
    font_px = max(9, round(13 * (cfg.get("font_scale", 100) / 100.0)))
    return QSS_TEMPLATE.replace("@@BG@@", p["bg"]).replace("@@BG2@@", p["bg2"]) \
        .replace("@@ACC1@@", p["accent1"]).replace("@@ACC2@@", p["accent2"]) \
        .replace("@@TEXT@@", p["text"]).replace("@@SUB@@", p["sub"]) \
        .replace("@@PANEL@@", p["panel"]).replace("@@PANEL2@@", p["panel2"]) \
        .replace("@@BORDER@@", p["border"]).replace("@@TRACK@@", p["track"]) \
        .replace("@@BASESIZE@@", str(font_px))


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
                stop:0 @@BG@@, stop:1 @@BG2@@);
    border-radius: 16px;
    border: 1px solid @@BORDER@@;
}

QFrame#TitleBar { background: transparent; }
QFrame#SideBar  { background: rgba(0,0,0,0.18); border-radius: 14px; }

/* ---------- 标题栏按钮 ---------- */
QPushButton#BtnIcon { background: transparent; border: none; border-radius: 8px; }
QPushButton#BtnIcon:hover { background: @@PANEL2@@; }
QPushButton#BtnIcon:checked { border: 1px solid @@ACC1@@; color: @@ACC1@@; }
QPushButton#BtnClose { color: #FF6B81; }
QPushButton#BtnClose:hover { background: rgba(255,80,100,0.18); }

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
    background: @@PANEL2@@; border: 1px solid @@BORDER@@; border-radius: 8px;
    padding: 6px 14px; color: @@TEXT@@;
}
QPushButton:hover { border-color: @@ACC1@@; color: @@ACC1@@; }
QPushButton:pressed { background: @@PANEL@@; }
QPushButton:disabled { color: @@SUB@@; border-color: @@BORDER@@; }
QPushButton#Primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @@ACC1@@, stop:1 @@ACC2@@);
    color: #FFFFFF; border: none; font-weight: 600;
}
QPushButton#Primary:hover { color: #FFFFFF; }
QPushButton#Ghost { background: transparent; }

QComboBox, QLineEdit {
    background: rgba(0,0,0,0.20); border: 1px solid @@BORDER@@; border-radius: 8px;
    padding: 5px 10px; color: @@TEXT@@; selection-background-color: @@ACC2@@;
}
QComboBox:hover, QLineEdit:hover, QLineEdit:focus { border-color: @@ACC1@@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: @@BG2@@; color: @@TEXT@@; border: 1px solid @@BORDER@@;
    selection-background-color: rgba(123,47,190,0.45); outline: none;
}

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
    border: 1px solid @@BORDER@@; background: rgba(0,0,0,0.2);
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @@ACC1@@, stop:1 @@ACC2@@);
    border: 1px solid @@ACC1@@;
}

/* ---------- 表格（进程管理器） ---------- */
QTableView {
    background: transparent; border: none; gridline-color: transparent;
    alternate-background-color: rgba(255,255,255,0.02);
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
