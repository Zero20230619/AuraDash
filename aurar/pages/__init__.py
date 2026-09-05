"""页面插件系统。

目录内任何继承 ``aurar.pages.base.Page`` 的模块会被自动发现并注册，
主框架按 ``order`` 排序后动态生成导航标签 —— 新增页面只需添加模块文件，
无需修改核心框架代码。
"""

import importlib
import pkgutil

from .base import Page, PAGES

__all__ = ["Page", "PAGES", "load_pages"]


def load_pages():
    """动态导入 pages 包下的所有模块，注册全部页面插件。

    注意：新增页面模块时需在此处显式导入（或传给 PyInstaller 的
    --hidden-import），以保证打包时被静态分析收录。
    """
    import aurar.pages as pkg

    # 显式导入内建页面（同时保证 PyInstaller 收录）
    from . import dashboard, focus, processes  # noqa: F401,E402

    for mod in pkgutil.iter_modules(pkg.__path__):
        if not mod.name.startswith("_"):
            importlib.import_module(f"{pkg.__name__}.{mod.name}")
    return sorted(PAGES, key=lambda p: p.order if p.order is not None else 99)
