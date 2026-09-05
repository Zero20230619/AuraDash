"""内置提示音：纯 Python 合成 WAV（正弦+指数衰减+轻谐波），无需外部资源。

ding  ：880Hz“叮”（随机节奏提醒，与第二次提醒共用）
chime ：523/659Hz 双音结束提示（专注结束）
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


def ensure_sound_files(sound_dir: str) -> dict:
    """生成（若缺失）内置音效，返回 {"ding": path, "chime": path}。"""
    os.makedirs(sound_dir, exist_ok=True)
    ding = os.path.join(sound_dir, "ding.wav")
    chime = os.path.join(sound_dir, "chime.wav")
    if not os.path.exists(ding):
        _synthesize(ding, [(880.0, 1.0, 0.45)], 0.45, decay=7.0)
    if not os.path.exists(chime):
        _synthesize(chime, [(523.25, 0.8, 0.35), (659.25, 1.0, 1.05)], 1.15, decay=4.5)
    return {"ding": ding, "chime": chime}
