"""AuraDash 入口：权限检查 → 配置加载 → 主题 → 主窗口 → 事件循环。

用法：
    python main.py                正常启动（默认尝试自动提权）
    python main.py --no-elevate    不申请管理员权限
    python main.py --screenshot DIR  开发者工具：截取各页面截图后退出
"""

import argparse
import os
import sys

AURADASH_APPID = "Zero1.AuraDash.1"


def _build_parser():
    parser = argparse.ArgumentParser(prog="AuraDash",
                                     description="Windows 桌面系统监控仪表盘")
    parser.add_argument("--no-elevate", action="store_true",
                        help="启动时不申请管理员权限")
    parser.add_argument("--screenshot", metavar="DIR",
                        help="开发者工具：将各页面截图保存到 DIR 后退出")
    parser.add_argument("--version", action="version", version="AuraDash 1.0.0")
    return parser


def _maybe_elevate(args) -> bool:
    """默认按配置自动提权重启；返回 True 表示本次进程应退出。"""
    from aurar.core.config import Config
    from aurar.platform import win

    if args.no_elevate or args.screenshot:
        return False
    cfg = Config()
    if not cfg.get("auto_elevate", True):
        return False
    if win.is_admin():
        return False
    ok = win.relaunch_as_admin()
    if ok:
        print("[AuraDash] 以管理员权限重新启动…")
        return True
    print("[AuraDash] 提权被取消，以普通权限运行（进程管理与温度读取受限）")
    return False


def _capture(window, out_dir: str):
    """逐页截图：切换页面 → 等待数据刷新 → 截图保存。"""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    os.makedirs(out_dir, exist_ok=True)
    app = QApplication.instance()
    stack = window._stack

    def shot(idx):
        if idx >= stack.count():
            window.quit()  # 停止监控线程后退出
            return
        stack.setCurrentIndex(idx)
        page = window.pages[idx]
        page.on_show()
        QTimer.singleShot(900, lambda: _save(idx))

    def _save(idx):
        pix = window.grab()  # 截取完整窗口（含标题栏与渐变背景）
        path = os.path.join(out_dir, f"page{idx}_{window.pages[idx].id}.png")
        pix.save(path)
        print(f"[AuraDash] 截图已保存: {path}")
        QTimer.singleShot(200, lambda: shot(idx + 1))

    QTimer.singleShot(1200, lambda: shot(0))


def main():
    args = _build_parser().parse_args()

    # 截图模式：使用临时数据目录，避免污染用户配置
    if args.screenshot:
        os.environ.setdefault("AURADASH_DIR",
                              os.path.join(os.path.abspath("."), ".screenshot_data"))

    if _maybe_elevate(args):
        sys.exit(0)

    from PySide6.QtWidgets import QApplication, QMessageBox

    from aurar import __version__
    from aurar.core import ensure_dirs, get_logger
    from aurar.core.config import Config
    from aurar.core.events import EventBus
    from aurar.core.logger import setup_logging
    from aurar.core.paths import logs_dir
    from aurar.platform import win

    ensure_dirs()
    setup_logging(logs_dir())
    log = get_logger("main")

    app = QApplication(sys.argv)
    app.setApplicationName("AuraDash")
    app.setOrganizationName("AuraDash")
    app.setApplicationVersion(__version__)
    win.set_app_user_model_id(AURADASH_APPID)

    cfg = Config()
    bus = EventBus()

    from aurar.ui.main_window import MainWindow, app_icon

    app.setWindowIcon(app_icon())
    win_ = MainWindow(cfg, bus)
    # 兜底：任何退出路径都先停掉后台采集线程
    app.aboutToQuit.connect(win_.quit)

    if args.screenshot:
        win_.show()
        _capture(win_, args.screenshot)
    else:
        win_.show()
        log.info("AuraDash v%s 启动完成（管理员: %s）",
                 __version__, win.is_admin())

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
