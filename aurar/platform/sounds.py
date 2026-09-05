"""内置提示音：纯 Python 合成 WAV（正弦+指数衰减+轻谐波），零外部资源。

ding   ：清脆高音“叮”（1568Hz，随机节奏提醒 + 按钮提示）
chime  ：523/659Hz 双音结束提示（专注结束）
click_start / click_pause / click_reset：开始 / 暂停 / 重置 按键音
"""

import math
import os
import struct
import wave

from ..core.logger import get_logger

log = get_logger("sounds")

_RATE = 44100


def _synthesize(path: str, notes, total_sec: float, decay: float = 6.0):
    frames = bytearray()
    n_total = int(_RATE * total_sec)
    for i in range(n_total):
        t = i / _RATE
        v = 0.0
        for freq, amp, dur in notes:
            if t < dur:
                env = math.exp(-decay * t / dur)  # 指数衰减
                v += amp * env * math.sin(2 * math.pi * freq * t)
                v += 0.25 * amp * env * math.sin(2 * math.pi * freq * 2 * t)  # 轻谐波
        sample = int(max(-1.0, min(1.0, v)) * 32767 * 0.55)
        frames += struct.pack("<h", sample)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        w.writeframes(bytes(frames))
    log.info("生成提示音: %s", path)


def _write_all(sound_dir: str, force: bool = False) -> dict:
    os.makedirs(sound_dir, exist_ok=True)
    # 名称 -> (合成参数, …)
    specs = {
        # 清脆“叮”：1568Hz 主音 + 2093Hz 高频泛音，快衰减
        "ding": ([(1568.0, 1.0, 0.30), (2093.0, 0.45, 0.18)], 0.30, 8.0),
        # 结束双音：E5 → A5
        "chime": ([(523.25, 0.8, 0.30), (659.25, 1.0, 1.05)], 1.15, 4.5),
        # 开始：明亮上行 B5
        "click_start": ([(987.77, 1.0, 0.16)], 0.16, 7.0),
        # 暂停：短促 D5
        "click_pause": ([(587.33, 1.0, 0.14)], 0.14, 7.0),
        # 重置：双声 A5 → 高音
        "click_reset": ([(660.0, 0.85, 0.09), (880.0, 0.9, 0.16)], 0.18, 7.0),
    }
    paths = {}
    for name, (args) in specs.items():
        path = os.path.join(sound_dir, f"{name}.wav")
        if force or not os.path.exists(path):
            _synthesize(path, args[0], args[1], decay=args[2])
        paths[name] = path
    return paths


def ensure_sound_files(sound_dir: str) -> dict:
    """保证内置音效存在，返回 {"ding","chime","click_start","click_pause","click_reset": path}。"""
    return _write_all(sound_dir)


def regenerate_sound_files(sound_dir: str) -> dict:
    """强制重新生成（资源打包时使用）。"""
    return _write_all(sound_dir, force=True)
