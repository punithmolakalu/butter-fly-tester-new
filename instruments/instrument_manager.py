"""
Instrument manager: single source of connection state for instruments (e.g. Arroyo).
Used by the GUI footer to show Arroyo: Connected / Disconnected.
Uses ArroyoConnection for connection (SCPI from Arroyo manual).
"""
from PyQt5.QtCore import QObject, pyqtSignal

from instruments.connection import ArroyoConnection


class InstrumentManager(QObject):
    """Tracks instrument connections. Emits connection_state_changed for footer."""

    connection_state_changed = pyqtSignal(dict)  # {"Arroyo": True/False, ...}

    def __init__(self, parent=None):
        super(InstrumentManager, self).__init__(parent)
        self._arroyo = None  # ArroyoConnection instance when connected

    def connect_arroyo(self, port: str) -> bool:
        """Connect to Arroyo on given COM port. Emits state change. Returns True if connected."""
        port = (port or "").strip()
        if not port:
            return False
        if self._arroyo and self._arroyo.is_connected():
            self._arroyo.disconnect()
        self._arroyo = ArroyoConnection(port=port)
        ok = self._arroyo.connect()
        self._emit_state()
        return ok

    def disconnect_arroyo(self) -> None:
        """Disconnect Arroyo. Emits state change."""
        if self._arroyo:
            self._arroyo.disconnect()
        self._emit_state()

    def is_arroyo_connected(self) -> bool:
        return self._arroyo is not None and self._arroyo.is_connected()

    def get_arroyo(self) -> ArroyoConnection:
        """For Manual Control / communication with Arroyo. May be None or disconnected."""
        return self._arroyo

    def get_connection_state(self) -> dict:
        """State dict for footer: instrument name -> connected (bool)."""
        return {"Arroyo": self.is_arroyo_connected()}

    def _emit_state(self) -> None:
        self.connection_state_changed.emit(self.get_connection_state())
