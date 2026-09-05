"""日志系统：控制台 + 按天滚动文件，保留最近 30 天。"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

_ROOT = "auradash"


def setup_logging(log_dir: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(_ROOT)
    if logger.handlers:  # 幂等
        return logger
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")

    try:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        logger.addHandler(stream)
    except Exception:  # noqa: BLE001
        pass

    try:
        os.makedirs(log_dir, exist_ok=True)
        fh = TimedRotatingFileHandler(
            os.path.join(log_dir, "auradash.log"),
            when="midnight", interval=1, backupCount=30, encoding="utf-8")
        fh.suffix = "%Y%m%d"
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("日志文件初始化失败: %s", exc)

    return logger


def get_logger(name: str = "") -> logging.Logger:
    if name:
        return logging.getLogger(f"{_ROOT}.{name}")
    return logging.getLogger(_ROOT)
