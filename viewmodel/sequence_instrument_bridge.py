"""
Exposes the same live instrument connections the GUI uses (workers) to TestSequenceExecutor / LIV.

The GUI connects Arroyo, Gentec, Thorlabs, Actuator, Ando on worker threads; LIV must use those
objects, not a separate InstrumentManager. During LIV, background polling is paused to avoid
serial/GPIB contention.
"""

import time
from typing import Any, Optional


class SequenceInstrumentBridge:
    """Maps get_arroyo() / get_instrument(name) to MainViewModel worker connections."""

    _MAP = {
        "Arroyo": "_worker",
        "Gentec": "_gentec_worker",
        "Thorlabs_Powermeter": "_thorlabs_worker",
        "Thorlabs": "_thorlabs_worker",
        "Actuators": "_actuator_worker",
        "Actuator": "_actuator_worker",
        "Ando": "_ando_worker",
        "Wavemeter": "_wavemeter_worker",
    }

    def __init__(self, viewmodel: Any):
        self._vm = viewmodel
        self._paused: list = []  # (QTimer, should_restart_fn)

    def get_arroyo(self) -> Optional[Any]:
        w = getattr(self._vm, "_worker", None)
        if w is None:
            return None
        return getattr(w, "_arroyo", None)

    def get_instrument(self, name: str) -> Optional[Any]:
        if (name or "").strip() == "Arroyo":
            return self.get_arroyo()
        key = self._MAP.get(name)
        if not key:
            return None
        w = getattr(self._vm, key, None)
        if w is None:
            return None
        if "gentec" in key:
            return getattr(w, "_gentec", None)
        if "thorlabs" in key:
            return getattr(w, "_thorlabs", None)
        if "actuator" in key:
            return getattr(w, "_actuator", None)
        if "ando" in key:
            return getattr(w, "_ando", None)
        if "wavemeter" in key:
            return getattr(w, "_wavemeter", None)
        return None

    def pause_for_liv(self) -> None:
        """Stop UI polling so LIV thread can use serial/VISA safely."""
        self._paused.clear()
        vm = self._vm
        specs = [
            ("_poll_timer", lambda: getattr(vm, "_arroyo_connected", False)),
            ("_gentec_poll_timer", lambda: getattr(vm, "_gentec_connected", False)),
            ("_thorlabs_poll_timer", lambda: getattr(vm, "_thorlabs_connected", False)),
            ("_actuator_poll_timer", lambda: getattr(vm, "_actuator_connected", False)),
            ("_ando_poll_timer", lambda: getattr(vm, "_ando_connected", False)),
            ("_wavemeter_poll_timer", lambda: getattr(vm, "_wavemeter_connected", False)),
        ]
        for attr, should_restart in specs:
            t = getattr(vm, attr, None)
            if t is not None and getattr(t, "isActive", lambda: False)():
                t.stop()
                self._paused.append((t, should_restart))
        # Let any in-flight Arroyo read_all on the worker thread finish before LIV touches serial.
        time.sleep(0.75)

    def resume_after_liv(self) -> None:
        for t, should_restart in self._paused:
            try:
                if should_restart():
                    t.start()
            except Exception:
                pass
        self._paused.clear()
