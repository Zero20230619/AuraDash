"""页面插件基类：统一接口 IPage 的 Python 实现。

新增页面步骤（无需改动核心框架）：
    1. 在 ``aurar/pages/`` 下新建模块；
    2. 继承 ``Page``，声明 ``id / title / icon / order`` 并实现 ``build()``；
    3. 完成 —— ``load_pages()`` 自动发现并注册，主框架自动生成导航标签。
"""

from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

PAGES = []

_META_BASE = type(QWidget)  # PySide6 使用 Shiboken.ObjectType，自定义元类须继承它


class PageMeta(_META_BASE):
    def __init__(cls, name, bases, ns):
        super().__init__(name, bases, ns)
        if bases and bases[0].__name__ == "Page" and not ns.get("_abstract"):
            PAGES.append(cls)


class Page(QWidget, metaclass=PageMeta):
    """所有页面的基类。``ctx`` 提供 bus / cfg / window 三件套。"""

    id: str = ""
    title: str = ""
    icon: str = "◆"
    order: int = 99

    def __init__(self, ctx: SimpleNamespace, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.bus = ctx.bus
        self.cfg = ctx.cfg
        self._subs = []

    # -------- 生命周期（子类覆盖） --------
    def build(self):
        """构建页面内容。在窗口准备好后调用一次。"""

    def on_show(self):
        """页面被切到时调用。"""

    def on_data(self, snapshot: dict):
        """系统监控数据到达（可选覆盖）。"""

    # -------- 工具 --------
    def subscribe(self, topic: str, fn):
        self.bus.subscribe(topic, fn)
        self._subs.append((topic, fn))

    def unsub(self):
        for topic, fn in self._subs:
            self.bus.unsubscribe(topic, fn)

    def t(self, key: str, zh: str) -> str:
        """国际化入口：先仅中文，未来在此接入多语言表。"""
        return zh
