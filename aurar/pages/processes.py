"""第 2 页 · 进程管理器：实时进程表格（虚拟渲染）、列排序、搜索、双击结束进程。

稳定性设计：数据更新采用“原位 dataChanged”，列表滚动位置保持稳定；
未变化的行不重建，避免误点击。
"""

import time

import psutil
from PySide6.QtCore import (QAbstractTableModel, QFileInfo, QModelIndex,
                            QRegularExpression, QSortFilterProxyModel, QSize, Qt,
                            QThread, Signal)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileIconProvider,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QStyle, QTableView, QVBoxLayout)

from ..core.logger import get_logger
from ..ui.widgets import make_label
from .base import Page

log = get_logger("proc")

COLS = ("名称", "PID", "CPU %", "内存 (MB)")


# ------------------------------------------------------------------ 采线程
class ProcessMonitor(QThread):
    data = Signal(list)

    def __init__(self, interval=1.0, parent=None):
        super().__init__(parent)
        self.interval = interval
        self._alive = True

    def stop(self):
        self._alive = False

    def set_interval(self, sec: float):
        self.interval = max(0.5, float(sec))

    def _collect(self) -> list:
        cores = max(1, psutil.cpu_count() or 1)
        rows = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent",
                                      "memory_info", "exe"]):
            try:
                info = p.info
                name = info.get("name") or f"PID {info.get('pid')}"
                mem = info.get("memory_info")
                rows.append({
                    "name": name,
                    "pid": int(info.get("pid") or 0),
                    # 与任务管理器一致：按核心数归一化（psutil 返回值可达 100%×核心数）
                    "cpu": round(float(info.get("cpu_percent") or 0.0) / cores, 1),
                    "mem_mb": round((mem.rss if mem else 0) / 1048576.0, 1),
                    "exe": info.get("exe") or "",
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return rows

    def run(self):
        # 首次调用用于预热 CPU 采样（psutil 约定：首次返回 0.0）
        try:
            for _ in psutil.process_iter(["cpu_percent"]):
                pass
        except Exception:  # noqa: BLE001
            pass
        while self._alive:
            try:
                self.data.emit(self._collect())
            except Exception as exc:  # noqa: BLE001
                log.exception("进程采集异常: %s", exc)
            t = 0.0
            while self._alive and t < self.interval:
                time.sleep(min(0.1, self.interval - t))
                t += 0.1


# ------------------------------------------------------------------ 表格模型
class ProcessTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._icon_provider = None
        self._icon_cache: dict[str, QPixmap] = {}
        self._fallback_icon = None

    def _icon(self, exe: str) -> QPixmap:
        """按可执行文件路径取进程图标（QFileIconProvider + 缓存）。"""
        key = exe or ""
        if key in self._icon_cache:
            return self._icon_cache[key]
        if len(self._icon_cache) > 1500:
            self._icon_cache.clear()
        try:
            if self._icon_provider is None:
                self._icon_provider = QFileIconProvider()
            if exe:
                icon = self._icon_provider.icon(QFileInfo(exe))
            else:
                icon = QFileIconProvider().icon(QFileInfo(""))
            pix = icon.pixmap(QSize(16, 16))
            if pix.isNull():
                pix = self._fallback()
        except Exception:  # noqa: BLE001
            pix = self._fallback()
        self._icon_cache[key] = pix
        return pix

    def _fallback(self) -> QPixmap:
        if self._fallback_icon is None:
            self._fallback_icon = QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_FileIcon).pixmap(QSize(16, 16))
        return self._fallback_icon

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row["name"]
            if col == 1:
                return str(row["pid"])
            if col == 2:
                return f"{row['cpu']:.1f}"
            if col == 3:
                return f"{row['mem_mb']:.0f}"
        elif role == Qt.ItemDataRole.DecorationRole and col == 0:
            return self._icon(row.get("exe", ""))
        elif role == Qt.ItemDataRole.UserRole:  # 排序用原始值
            if col == 0:
                return (row["name"] or "").lower()
            if col == 1:
                return row["pid"]
            if col == 2:
                return row["cpu"]
            if col == 3:
                return row["mem_mb"]
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (1, 2, 3):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def set_rows(self, rows: list[dict]):
        old_len = len(self._rows)
        new_len = len(rows)
        self._rows = rows
        if new_len == old_len and new_len > 0:
            # 原位更新 → 滚动位置与选中态保持稳定
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(new_len - 1, len(COLS) - 1))
        else:
            self.beginResetModel()
            self.endResetModel()

    def row_at(self, r: int) -> dict:
        if 0 <= r < len(self._rows):
            return self._rows[r]
        return {}


class ProcProxy(QSortFilterProxyModel):
    """数值列排序 + 名称列大小写不敏感过滤。"""

    def lessThan(self, left, right):
        if left.column() == 0:
            return (left.data() or "") < (right.data() or "")
        return (left.data(Qt.ItemDataRole.UserRole) or 0) < \
               (right.data(Qt.ItemDataRole.UserRole) or 0)


# ------------------------------------------------------------------ 页面
class ProcessesPage(Page):
    id = "processes"
    title = "进程"
    icon = "▤"
    order = 1

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._monitor = ProcessMonitor(interval=self.cfg.get("process_refresh_sec", 5.0))
        self._rows_cache = []

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("🔍 搜索进程名…")
        self._search.setClearButtonEnabled(True)
        self._count = make_label("", "SubText", parent=self)
        bar.addWidget(self._search, 1)
        bar.addWidget(self._count)
        root.addLayout(bar)

        self._model = ProcessTableModel(self)
        self._proxy = ProcProxy(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self._proxy.setFilterKeyColumn(0)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self._table = QTableView(self)
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(26)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self._table.setColumnWidth(c, 88 if c == 1 else 110)
        self._table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self._table.doubleClicked.connect(self._on_double)
        root.addWidget(self._table, 1)

        tip = make_label("双击进程 → 确认后结束  ·  点击列头排序  ·  每 5 秒自动刷新（列表位置保持稳定）",
                         "SubText", size=11, parent=self)
        root.addWidget(tip)

        self._search.textChanged.connect(self._apply_filter)
        self._monitor.data.connect(self._on_proc_data)
        self.cfg.changed.connect(self._on_cfg)
        self._monitor.start()

    def _on_cfg(self, key):
        if key in ("process_refresh_sec", "*"):
            self._monitor.set_interval(self.cfg.get("process_refresh_sec", 5.0))

    def stop(self):
        self._monitor.stop()
        self._monitor.wait(2000)

    def _apply_filter(self, text):
        if text:
            self._proxy.setFilterRegularExpression(
                QRegularExpression(text.strip(), QRegularExpression.PatternOption.CaseInsensitiveOption))
        else:
            self._proxy.setFilterRegularExpression(QRegularExpression())

    def _on_proc_data(self, rows):
        self._rows_cache = rows
        self._count.setText(f"共 {len(rows)} 个进程")
        self._model.set_rows(rows)

    def _on_double(self, proxy_index):
        src = self._proxy.mapToSource(proxy_index)
        info = self._model.row_at(src.row())
        if not info:
            return
        pid = info["pid"]
        name = info["name"]
        ret = QMessageBox.question(
            self, "结束进程",
            f"确定结束进程「{name}」吗？\nPID: {pid}\n\n系统关键进程可能需要管理员权限。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            log.info("已结束进程 %s (%s)", name, pid)
        except psutil.NoSuchProcess:
            QMessageBox.information(self, "结束进程", "该进程已退出。")
        except psutil.AccessDenied:
            QMessageBox.warning(
                self, "结束进程",
                "权限不足。\n此进程受保护，请以管理员身份运行 AuraDash（默认自动提权）。")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "结束进程", f"操作失败：{exc}")
