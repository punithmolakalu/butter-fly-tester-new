"""Safe PyVISA teardown: stale or already-closed sessions should not disturb shutdown."""
from __future__ import annotations

import threading
from typing import Any

# Serialize VISA open/query during multi-instrument startup (Ando + Wavemeter on same PC/USB-GPIB).
_pyvisa_open_lock = threading.RLock()


def pyvisa_open_lock() -> threading.RLock:
    """Re-entrant lock: hold while opening GPIB/USB resources or first SCPI exchange after open."""
    return _pyvisa_open_lock


def safe_close_pyvisa_resource(res: Any) -> None:
    """Close a PyVISA Resource; ignore InvalidSession (device gone, double-close, driver race)."""
    if res is None:
        return
    try:
        close = getattr(res, "close", None)
        if callable(close):
            close()
    except Exception as ex:
        try:
            from pyvisa.errors import InvalidSession, VisaIOError

            if isinstance(ex, (InvalidSession, VisaIOError)):
                return
        except ImportError:
            pass


def safe_close_pyvisa_resource_manager(rm: Any) -> None:
    """Close a ResourceManager; ignore errors from already-closed backend."""
    if rm is None:
        return
    try:
        close = getattr(rm, "close", None)
        if callable(close):
            close()
    except Exception as ex:
        try:
            from pyvisa.errors import InvalidSession, VisaIOError

            if isinstance(ex, (InvalidSession, VisaIOError)):
                return
        except ImportError:
            pass
