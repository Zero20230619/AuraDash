"""系统监控采集：后台线程轮询 CPU / GPU / 内存 / 磁盘 / 温度，1Hz 快照。

采集完全在独立 QThread 中执行，信号投递回 UI 线程，绝不阻塞界面。
"""

import time

import psutil
from PySide6.QtCore import QThread, Signal

from .logger import get_logger
from ..platform import win

log = get_logger("sysmon")

TEMP_EVERY_TICKS = 10  # 温度读取较慢，每 10 个周期读一次并缓存


class _GPUSource:
    """NVIDIA GPU（pynvml → GPUtil 回退），不可用时 ok=False。"""

    def __init__(self):
        self.ok = False
        self._nvml = None
        self._gpu_util = None
        try:
            import pynvml  # type: ignore

            pynvml.nvmlInit()
            self._nvml = pynvml
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.ok = True
            log.info("GPU 数据源: pynvml")
        except Exception:  # noqa: BLE001
            try:
                import GPUtil  # type: ignore

                self._gpu_util = GPUtil
                self.ok = True
                log.info("GPU 数据源: GPUtil")
            except Exception:  # noqa: BLE001
                log.info("未检测到 NVIDIA GPU / 驱动，GPU 卡片将显示为不可用")

    def read(self) -> dict:
        if not self.ok:
            return {"ok": False}
        try:
            if self._nvml is not None:
                nv = self._nvml
                util = nv.nvmlDeviceGetUtilizationRates(self._handle)
                mem = nv.nvmlDeviceGetMemoryInfo(self._handle)
                temp = nv.nvmlDeviceGetTemperature(self._handle, nv.NVML_TEMPERATURE_GPU)
                vram_pct = (mem.used / mem.total * 100.0) if mem.total else 0.0
                return {
                    "ok": True, "usage": float(util.gpu),
                    "vram_used": mem.used, "vram_total": mem.total, "vram_pct": vram_pct,
                    "temp_c": float(temp),
                }
            gpus = self._gpu_util.getGPUs()
            if not gpus:
                return {"ok": False}
            g = gpus[0]
            return {
                "ok": True, "usage": float(g.load * 100.0),
                "vram_used": int(g.memoryUsed * 1024 * 1024),
                "vram_total": int(g.memoryTotal * 1024 * 1024),
                "vram_pct": float(g.memoryUtil * 100.0),
                "temp_c": float(g.temperature),
            }
        except Exception as exc:  # noqa: BLE001
            log.debug("GPU 读取失败: %s", exc)
            return {"ok": False}


class PollThread(QThread):
    data = Signal(dict)

    def __init__(self, interval=1.0, parent=None):
        super().__init__(parent)
        self.interval = interval
        self._alive = True
        self._gpu = None
        self._tick = 0
        self._prev_cpu_total = None
        self._prev_cpu_per = None
        self._prev_ts = None
        self._prev_io = None

    def stop(self):
        self._alive = False

    def set_interval(self, sec: float):
        self.interval = max(0.3, float(sec))

    # ---------------- 采集逻辑 ----------------
    def _snapshot(self) -> dict:
        now = time.monotonic()
        dt = max(0.05, (now - self._prev_ts) if self._prev_ts else 0.1)
        self._prev_ts = now

        # ---- CPU ----
        cpu_per = psutil.cpu_percent(interval=None, percpu=True)
        cpu_total = sum(cpu_per) / len(cpu_per) if cpu_per else 0.0
        cpu = {
            "total": round(cpu_total, 1),
            "per_core": [round(v, 1) for v in cpu_per],
            "freq_mhz": None,
        }
        try:
            freq = psutil.cpu_freq()
            if freq:
                cpu["freq_mhz"] = int(freq.current)
        except Exception:  # noqa: BLE001
            pass

        self._tick += 1
        if self._tick % TEMP_EVERY_TICKS == 1 or self._tick == 1:
            cpu["temp_c"] = win.get_cpu_temp()
        else:
            cpu["temp_c"] = getattr(self, "_cpu_temp_cache", None)

        # ---- 内存 ----
        vm = psutil.virtual_memory()
        mem = {"total": vm.total, "used": vm.used, "percent": round(vm.percent, 1)}

        # ---- GPU ----
        if self._gpu is None:
            self._gpu = _GPUSource()
        gpu = self._gpu.read()

        # ---- 磁盘 ----
        disks = []
        try:
            io = psutil.disk_io_counters(perdisk=True) or {}
            for part in psutil.disk_partitions(all=False):
                if "cdrom" in part.opts.lower():
                    continue
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except OSError:
                    continue
                # 本分区 io 速率（无分区统计时用总量）
                pio = io.get(part.device, io.get(part.device.replace(":", ""))) if io else None
                if pio and self._prev_io:
                    old = self._prev_io.get(part.device)
                    if old:
                        read_bps = (pio.read_bytes - old.read_bytes) / dt
                        write_bps = (pio.write_bytes - old.write_bytes) / dt
                    else:
                        read_bps = write_bps = 0.0
                else:
                    read_bps = write_bps = 0.0
                disks.append({
                    "mount": part.mountpoint.rstrip("\\") or part.device[:2],
                    "device": part.device,
                    "total": usage.total, "used": usage.used,
                    "percent": round(usage.percent, 1),
                    "read_bps": max(0.0, read_bps),
                    "write_bps": max(0.0, write_bps),
                })
            self._prev_io = {d["device"]: io.get(d["device"]) for d in disks} if disks else None
        except Exception as exc:  # noqa: BLE001
            log.debug("磁盘读取失败: %s", exc)

        return {"cpu": cpu, "mem": mem, "gpu": gpu, "disk": disks,
                "ts": time.time()}

    def run(self):
        log.info("监控线程启动，刷新周期 %.1fs", self.interval)
        while self._alive:
            try:
                snap = self._snapshot()
                self.data.emit(snap)
            except Exception as exc:  # noqa: BLE001
                log.exception("监控采集异常: %s", exc)
            # 细粒度睡眠，可及时响应 stop
            t = 0.0
            while self._alive and t < self.interval:
                time.sleep(min(0.1, self.interval - t))
                t += 0.1
        log.info("监控线程退出")
