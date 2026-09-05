"""生成 AuraDash 内置资源：app 图标（ico/png）、README 横幅、内置提示音。

用法：python tools/make_assets.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import QApplication

ASSETS = os.path.join(ROOT, "assets")
DOCS = os.path.join(ROOT, "docs")


def _draw_logo(p: QPainter, size: int, quality: bool = True):
    """霓虹光环 + 中心发光体（logo 主体），可复用于 icon 与 banner。"""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size
    pad = s * 0.10
    box = QRectF(pad, pad, s - 2 * pad, s - 2 * pad)

    # 背景圆角方块
    grad = QLinearGradient(box.topLeft(), box.bottomRight())
    grad.setColorAt(0, QColor("#0A0E1A"))
    grad.setColorAt(1, QColor("#141C38"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#9AA8C4"))
    p.drawRoundedRect(box.adjusted(-1, -1, 1, 1), s * 0.22, s * 0.22)
    p.setBrush(grad)
    p.drawRoundedRect(box, s * 0.22, s * 0.22)

    cx, cy = s / 2, s / 2
    r = s * 0.30
    # 外圈辉光
    for i, alpha in ((0, 60), (1, 100), (2, 150)):
        glow = QPen(QColor(0, 212, 255, alpha), s * 0.055 + i * s * 0.028)
        glow.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(glow)
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
    # 主环（渐变）
    ring = QPen(QColor("#00D4FF"), s * 0.075)
    p.setPen(ring)
    p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
    p.setPen(QPen(QColor("#7B2FBE"), s * 0.075))
    p.drawEllipse(QRectF(cx - r * 0.62, cy - r * 0.62, 2 * r * 0.62, 2 * r * 0.62))

    # 中心内核
    core = QRadialGradient(cx - s * 0.05, cy - s * 0.05, s * 0.14)
    core.setColorAt(0, QColor(255, 255, 255, 230))
    core.setColorAt(1, QColor(123, 47, 190, 200))
    p.setBrush(core)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - s * 0.10, cy - s * 0.10, s * 0.20, s * 0.20))


def make_icon():
    img = QImage(256, 256, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    _draw_logo(p, 256)
    p.end()
    ico = os.path.join(ASSETS, "aura.ico")
    png = os.path.join(ASSETS, "aura.png")
    img.save(ico, "ICO")
    img.save(png, "PNG")
    print(f"图标: {ico} / {png}")
    return ico


def make_banner():
    w, h = 1280, 420
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#0A0E1A"))
    p = QPainter(img)
    # 背景渐变 + 光晕
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0, QColor("#0A0E1A"))
    grad.setColorAt(0.55, QColor("#101A36"))
    grad.setColorAt(1, QColor("#1B1030"))
    p.fillRect(0, 0, w, h, grad)
    glow = QRadialGradient(w * 0.72, h * 0.35, h * 1.15)
    glow.setColorAt(0, QColor(0, 212, 255, 90))
    glow.setColorAt(0.55, QColor(123, 47, 190, 55))
    glow.setColorAt(1, QColor(0, 0, 0, 0))
    p.setBrush(glow)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(0, 0, w, h)

    _draw_logo(p, 300)
    # 平移 logo 到左侧
    p.translate(w * 0.16, h * 0.20)

    p.setPen(QColor("#E6ECF8"))
    f = QFont("Bahnschrift")
    f.setPixelSize(76)
    f.setWeight(QFont.Weight.DemiBold)
    p.setFont(f)
    p.drawText(QRectF(w * 0.44, h * 0.26, w * 0.5, 100),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "AURA DASH")

    p.setPen(QColor("#8FA3C0"))
    f2 = QFont("Microsoft YaHei UI")
    f2.setPixelSize(26)
    p.setFont(f2)
    p.drawText(QRectF(w * 0.45, h * 0.52, w * 0.5, 60),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "Windows 桌面硬件监控仪表盘 · 进程管理 · 番茄专注")

    p.setPen(QColor("#00D4FF"))
    f3 = QFont("Consolas")
    f3.setPixelSize(20)
    p.setFont(f3)
    p.drawText(QRectF(w * 0.45, h * 0.70, w * 0.5, 40),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "Python · PySide6 · psutil · 实时数据 · 插件式架构")
    p.end()
    path = os.path.join(DOCS, "hero.png")
    img.save(path, "PNG")
    print(f"横幅: {path}")


def make_sounds():
    from aurar.platform import sounds
    out = sounds.ensure_sound_files(os.path.join(ASSETS, "sounds"))
    for k, v in out.items():
        print(f"提示音 {k}: {v}")


def main():
    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)
    _app = QApplication.instance() or QApplication([])
    make_icon()
    make_banner()
    make_sounds()
    print("done.")


if __name__ == "__main__":
    main()
