"""
Background gather of *IDN? (or device-specific ID) for connected instruments — does not block the GUI thread.
"""
from __future__ import annotations

import traceback
from typing import Any, List, Optional

from PyQt5.QtCore import Q_ARG, QMetaObject, QObject, QThread, Qt, pyqtSignal


class GatherInstrumentInfoThread(QThread):
    """Runs on a secondary thread; uses BlockingQueuedConnection into each instrument worker thread + main-thread PRM."""

    result_ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, viewmodel: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel

    def run(self) -> None:
        try:
            lines: List[str] = []
            lines.append("Instrument identification (SCPI *IDN? where supported)")
            lines.append("")
            vm = self._vm
            workers: List[Any] = [
                vm._worker,
                vm._ando_worker,
                vm._actuator_worker,
                vm._wavemeter_worker,
                vm._gentec_worker,
                vm._thorlabs_worker,
            ]
            for w in workers:
                ok = QMetaObject.invokeMethod(
                    w,
                    "append_instrument_info_line",
                    Qt.BlockingQueuedConnection,
                    Q_ARG("PyQt_PyObject", lines),
                )
                if not ok:
                    lines.append("{}: (internal: could not invoke identify slot)".format(type(w).__name__))
            ok_p = QMetaObject.invokeMethod(
                vm,
                "append_instrument_info_prm_line",
                Qt.BlockingQueuedConnection,
                Q_ARG("PyQt_PyObject", lines),
            )
            if not ok_p:
                lines.append("PRM: (internal: could not invoke identify slot)")
            self.result_ready.emit("\n".join(lines))
        except Exception:
            self.failed.emit(traceback.format_exc())
