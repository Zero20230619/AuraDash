"""通用控件：霓虹卡片、环形进度仪表（发光描边+数字动画）、迷你进度条、格式化。"""

from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, QRectF, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QLinearGradient,
                           QPainter, QPen)
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QWidget


# ---------------------------------------------------------------- 格式化
def fmt_bytes(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def fmt_bps(n: float) -> str:
    return f"{fmt_bytes(n)}/s" if n else "0 B/s"


# ---------------------------------------------------------------- 霓虹卡片
class NeonCard(QFrame):
    """带发光阴影的玻璃卡片，header 区域可拖拽排序。"""

    def __init__(self, card_id: str, title: str, parent=None, color="rgba(0,212,255,0.35)"):
        super().__init__(parent)
        self.card_id = card_id
        self.setObjectName("DashCard")
        self.setProperty("dragging", False)
        self.setAcceptDrops(True)
        self.setMinimumSize(240, 150)
        self.setMouseTracking(True)

        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(26)
        glow.setOffset(0, 0)
        glow.setColor(QColor(30, 60, 130, 70))
        self.setGraphicsEffect(glow)
        self._glow_color = color


class RingGauge(QWidget):
    """环形进度仪表：渐变霓虹描边 + 双层辉光 + 中心数值动画。"""

    def __init__(self, size=150, thickness=11, sub="", color_provider=None,
                 center_font_size=None, center_mode="value", parent=None):
        super().__init__(parent)
        self._size = size
        self._th = thickness
        self._sub = sub
        self._color_provider = color_provider or (
            lambda: {"c1": "#00D4FF", "c2": "#7B2FBE",
                     "text": "#E9F0FC", "sub": "#96A4C8",
                     "track": QColor(240, 250, 255, 26)})
        self._font_size = center_font_size or int(size * 0.23)
        self._center_mode = center_mode  # "value" 显示百分比 | "none" 留空给自定义控件
        self._v = 0.0
        self._target = 0.0
        self._anim = None
        self.setFixedSize(size, size)

    # value 属性（可动画）
    def _get_v(self):
        return self._v

    def _set_v(self, v):
        self._v = float(v)
        self.update()

    value = Property(float, _get_v, _set_v)

    def set_target(self, v, duration=550):
        v = max(0.0, min(100.0, float(v)))
        if abs(v - self._target) < 0.05:
            return
        self._target = v
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(duration)
        self._anim.setStartValue(self._v)
        self._anim.setEndValue(v)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def set_sub(self, sub: str):
        self._sub = sub
        self.update()

    def paintEvent(self, _ev):
        cp = self._color_provider()
        if isinstance(cp, (tuple, list)):
            cp = {"c1": cp[0], "c2": cp[1],
                  "text": "#E9F0FC", "sub": "#96A4C8",
                  "track": QColor(240, 250, 255, 26)}
        c1 = QColor(cp["c1"])
        c2 = QColor(cp["c2"])
        text_c = QColor(cp.get("text", "#E9F0FC"))
        sub_c = QColor(cp.get("sub", "#96A4C8"))
        track_c = QColor(cp.get("track", QColor(240, 250, 255, 26)))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = self._th + 7
        rect = QRectF(margin, margin,
                      self.width() - 2 * margin, self.height() - 2 * margin)
        frac = max(0.0, min(100.0, self._v)) / 100.0

        # 轨道
        pen = QPen(track_c, self._th)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        if frac > 0.002:
            # 辉光层（3 圈渐弱 alpha）
            for i, alpha in ((1, 50), (2, 30), (3, 14)):
                glow = QPen(QColor(c1.red(), c1.green(), c1.blue(), alpha),
                            self._th + 2 + i * 4)
                glow.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(glow)
                p.drawArc(rect, 90 * 16, -360 * 16 * frac)
            # 主渐变弧
            grad = QConicalGradient(rect.center(), 90)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            pen2 = QPen(QBrush(grad), self._th)
            pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen2)
            p.drawArc(rect, 90 * 16, -360 * 16 * frac)

        # 中心文字
        if self._center_mode == "value":
            f = QFont("Bahnschrift", )
            f.setPixelSize(self._font_size)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            p.setPen(text_c)
            p.drawText(rect.adjusted(0, -6, 0, 0), Qt.AlignmentFlag.AlignCenter,
                       f"{self._v:.0f}")
            fs = QFont("Segoe UI")
            fs.setPixelSize(max(9, int(self._font_size * 0.42)))
            p.setFont(fs)
            p.setPen(sub_c)
            p.drawText(rect.adjusted(0, 0, 0, -self._font_size * 0.9),
                       Qt.AlignmentFlag.AlignCenter, "%")
        if self._sub:
            fs = QFont("Segoe UI")
            fs.setPixelSize(max(9, int(self._font_size * 0.42)))
            p.setFont(fs)
            p.setPen(sub_c)
            p.drawText(rect.adjusted(0, self._font_size * 0.55, 0, 0),
                       Qt.AlignmentFlag.AlignCenter, self._sub)


class MiniBar(QWidget):
    """迷你水平渐变进度条（磁盘占用 / 每核心占用）。"""

    def __init__(self, color_provider=None, parent=None, height=8):
        super().__init__(parent)
        self._v = 0.0
        self._cp = color_provider or (
            lambda: {"c1": "#00D4FF", "c2": "#7B2FBE"})
        self.setFixedHeight(height)

    def set_value(self, v):
        self._v = max(0.0, min(100.0, float(v)))
        self.update()

    def paintEvent(self, _ev):
        cp = self._cp()
        if isinstance(cp, (tuple, list)):
            c1 = QColor(cp[0])
            c2 = QColor(cp[1])
        else:
            c1 = QColor(cp["c1"])
            c2 = QColor(cp["c2"])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 1, self.width(), self.height() - 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(140, 165, 210, 40))
        p.drawRoundedRect(r, 4, 4)
        if self._v > 0.3:
            w = max(4, r.width() * self._v / 100.0)
            grad = QLinearGradient(0, 0, r.width(), 0)
            grad.setColorAt(0, c1)
            grad.setColorAt(1, c2)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(0, 1, w, self.height() - 2), 4, 4)


def mono_font(size: int, weight=QFont.Weight.DemiBold) -> QFont:
    f = QFont("Bahnschrift")
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def make_label(text="", cls="SubText", size=None, weight=None, parent=None):
    lb = QLabel(text, parent)
    lb.setObjectName(cls)
    if size:
        f = lb.font()
        f.setPixelSize(size)
        if weight:
            f.setWeight(weight)
        lb.setFont(f)
    return lb
