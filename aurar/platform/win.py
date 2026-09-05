"""Windows 平台能力：管理员提权、专注助手（Focus Assist）、CPU 温度、开机自启。

所有功能均为“尽力而为”，失败时安全降级并返回 False，不影响主程序运行。
"""

import ctypes
import os
import subprocess
import sys
import time

from ..core.logger import get_logger

log = get_logger("win")

# 专注助手注册表位置（Win10 1809+ / Win11）
_FOCUS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
_FOCUS_VALUES = {}  # 记录启动前的 NOC_MODE 等值，用于恢复

CREATE_NO_WINDOW = 0x08000000


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def relaunch_as_admin() -> bool:
    """以管理员身份重新启动自身（ShellExecuteW runas）。成功返回 True。"""
    try:
        if is_admin():
            return True
        if getattr(sys, "frozen", False):
            exe = sys.executable
            args = subprocess.list2cmdline(sys.argv[1:])
        else:
            exe = sys.executable
            script = os.path.abspath(os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "main.py"))
            args = subprocess.list2cmdline([script] + sys.argv[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, args, None, 1)
        return ret > 32
    except Exception as exc:  # noqa: BLE001
        log.warning("提权重启失败: %s", exc)
        return False


# ---------------------------------------------------------------- CPU 温度

_cpu_temp_cache: dict = {"t": 0.0, "v": None}


def get_cpu_temp(timeout=6.0) -> float | None:
    """读取 CPU 温度（MSAcpi_ThermalZoneTemperature，WMI），10 秒缓存。

    依赖系统 ACPI 热区表与管理员权限，失败时返回 None（界面显示 N/A）。
    """
    now = time.monotonic()
    if now - _cpu_temp_cache["t"] < 10:
        return _cpu_temp_cache["v"]
    value = None
    try:
        cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
            "-ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty CurrentTemperature)"
        ]
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout, creationflags=CREATE_NO_WINDOW)
        text = (out.stdout or "").strip()
        if text:
            value = round(float(text) / 10.0 - 273.15, 1)
    except Exception:  # noqa: BLE001
        value = None
    _cpu_temp_cache.update({"t": now, "v": value})
    return value


# ---------------------------------------------------------------- 专注助手

def focus_assist_supported() -> bool:
    import winreg  # noqa: F401
    return True


def _focus_read_orig():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _FOCUS_KEY) as k:
            for name in ("NOC_MODE", "NOC_GUID", "NOC_DND_STATE"):
                try:
                    _FOCUS_VALUES[name] = winreg.QueryValueEx(k, name)
                except OSError:
                    _FOCUS_VALUES[name] = None
    except OSError as exc:
        log.debug("读取专注助手状态失败: %s", exc)


def set_focus_assist(enabled: bool) -> bool:
    """启用（True）→ 仅限闹钟；关闭（False）→ 恢复用户原设置。HKCU，无需管理员。"""
    import winreg

    try:
        if enabled:
            _focus_read_orig()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _FOCUS_KEY, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as k:
            if enabled:
                winreg.SetValueEx(k, "NOC_MODE", 0, winreg.REG_DWORD, 2)
            else:
                orig = _FOCUS_VALUES.get("NOC_MODE")
                val = orig[0] if orig else 0
                try:
                    winreg.SetValueEx(k, "NOC_MODE", 0, winreg.REG_DWORD, int(val))
                except (TypeError, ValueError):
                    winreg.SetValueEx(k, "NOC_MODE", 0, winreg.REG_DWORD, 0)
        log.info("专注助手 -> %s", "仅限闹钟" if enabled else "恢复原状态")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("专注助手切换失败: %s", exc)
        return False


# ---------------------------------------------------------------- 开机自启

_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(enabled: bool) -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as k:
            if enabled:
                exe = sys.executable if getattr(sys, "frozen", False) else \
                    f'"{sys.executable}" "{os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "main.py"))}"'
                winreg.SetValueEx(k, "AuraDash", 0, winreg.REG_SZ, exe)
            else:
                try:
                    winreg.DeleteValue(k, "AuraDash")
                except FileNotFoundError:
                    pass
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("自启动设置失败: %s", exc)
        return False


def autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY) as k:
            winreg.QueryValueEx(k, "AuraDash")
            return True
    except OSError:
        return False


# ---------------------------------------------------------------- 任务栏分组

def set_app_user_model_id(app_id: str):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:  # noqa: BLE001
        pass
