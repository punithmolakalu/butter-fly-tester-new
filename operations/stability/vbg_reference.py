"""
Reference mapping: VBG-style stability flow ↔ this app's instruments.

The GUI uses ``instruments/ando.AndoConnection`` and ``TemperatureStabilityProcess.run()``.
This module documents the command alignment only (no runtime logic).

Arroyo (TEC)
  - Set temperature: ``ArroyoController.set_tec_temperature`` → in app: ``set_temp(...)`` + TEC output.

Ando AQ6317B (reference vs this codebase)
  - Reference ``trigger_sweep``     → ``AndoConnection.single_sweep()``  (SCPI ``SGL``)
  - Reference ``wait_for_sweep``    → ``AndoConnection.wait_sweep_done()``
  - Reference ``DFB_ANALYSIS``      → ``analysis_dfb_ld()`` → ``DFBAN`` (DFB-LD mode)
                                    → LED: ``LEDAN``; FP: ``FPAN`` via ``_analysis_command(ando, name)``
  - Reference ``read_all_analysis_results`` → ``AndoConnection.read_all_analysis_results()``
      (ANA? / ANAR? + PKWL? / SPWD? / SMSR? fallbacks)

Live plots
  - Each measured point still emits ``stability_live_point(T, FWHM, SMSR, peak_nm)`` on the executor;
    ``TemperatureStabilityWindow.append_live_point`` appends to pyqtgraph curves (main window wiring).

When ``ContinuousScan`` is true in the recipe TS block, the VBG path skips ``SGL`` + wait (repeat sweep
already running); analysis + read still run each step.
"""

# Command labels for documentation / external tooling (not imported by hot path).
ANDO_COMMAND_MAP = {
    "single_sweep": "SGL",
    "stop_sweep": "STP",
    "repeat_sweep": "RPT",
    "analysis_dfb": "DFBAN",
    "analysis_led": "LEDAN",
    "analysis_fp": "FPAN",
    "peak_search": "PKSR",
    "query_analysis": "ANA?",
    "query_analysis_result": "ANAR?",
    "peak_wavelength_nm": "PKWL?",
    "spectral_width_nm": "SPWD?",
    "smsr_db": "SMSR? / MSR?",
}
