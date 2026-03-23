"""Backward-compatible re-exports; implementations live in instrument_simulations.py."""
from instruments.instrument_simulations import AndoSimulationConnection, WavemeterSimulationConnection

__all__ = ("AndoSimulationConnection", "WavemeterSimulationConnection")
