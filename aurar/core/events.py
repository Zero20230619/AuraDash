"""轻量事件总线：页面 / 模块之间通过主题字符串解耦通信。

约定主题：
    sysmon:data    系统监控快照 dict（1Hz）
    proc:data      进程清单 list[dict]
    theme:changed  主题配色变更
    cfg:*          配置变更（由 Config.changed 信号直接转发，不经过总线）
"""

from collections import defaultdict


class EventBus:
    def __init__(self):
        self._subs = defaultdict(list)

    def subscribe(self, topic: str, fn):
        self._subs[topic].append(fn)

    def unsubscribe(self, topic: str, fn):
        if fn in self._subs.get(topic, []):
            self._subs[topic].remove(fn)

    def publish(self, topic: str, payload=None):
        for fn in list(self._subs.get(topic, [])):
            try:
                fn(payload)
            except Exception as exc:  # noqa: BLE001 - 总线不允许单个订阅者拖垮全局
                import logging

                logging.getLogger("auradash.bus").exception(
                    "event handler error on %s: %s", topic, exc)
