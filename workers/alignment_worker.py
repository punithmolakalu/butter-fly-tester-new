"""
Alignment worker: runs alignment-related tasks in a background thread.
Use PyQt5.QtCore.Qt for QueuedConnection so signal/slot connect(slot, Qt.QueuedConnection) is valid.
"""
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, Qt

# Use Qt from PyQt5.QtCore so Qt.QueuedConnection is known to type checkers
ConnectionType = Qt.ConnectionType


class AlignmentWorker(QObject):
    """Worker for alignment operations; signals are connected with QueuedConnection when used from another thread."""

    progress = pyqtSignal(int)
    message = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

    @pyqtSlot()
    def do_work(self):
        """Run alignment work (override or connect to run your logic)."""
        self.finished.emit(True)


def connect_queued(signal, slot):
    """Connect signal to slot using Qt.QueuedConnection (safe for cross-thread). Use this instead of signal.connect(slot, Qt.QueuedConnection) if the type checker complains about connect(slot, type)."""
    signal.connect(slot, Qt.QueuedConnection)
