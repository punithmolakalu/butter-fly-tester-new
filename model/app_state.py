"""
Application state and data. No UI dependencies.
"""
from typing import Any, Dict


class AppState:
    """Holds application data. ViewModel reads/writes through this or via its own state."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
