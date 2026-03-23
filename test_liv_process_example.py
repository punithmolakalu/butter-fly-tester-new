"""
Standalone test for the LIV process using real instruments.

Run from project root:

    python test_liv_process_example.py

This:
- Connects instruments via InstrumentManager (same as GUI "Connect All")
- Builds a simple in‑memory example recipe for LIV
- Runs the full LIV process once (no GUI, no popups)
- Prints key numeric results to the console

Adjust currents / temperature to safe values for your device before use.
"""

import sys
import time
from pathlib import Path


def _ensure_root_on_path() -> Path:
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def build_example_recipe(fiber_coupled: bool = True) -> dict:
    """
    Build a minimal recipe dict that LIVMainParameters.from_recipe understands.

    NOTE: Change currents / temperature to safe values for your DUT.
    """
    return {
        "FiberCoupled": bool(fiber_coupled),
        "GENERAL": {
            "FiberCoupled": bool(fiber_coupled),
            "Wavelength": 1550.0,
        },
        "OPERATIONS": {
            "LIV": {
                "min_current_mA": 400.0,
                "max_current_mA": 1200.0,
                "increment_mA": 10.0,
                "wait_time_ms": 50.0,
                "temperature": 25.0,
                "rated_current_mA": 1350.0,
                "rated_power_mW": 100.0,
                "se_data_points": 5,
            }
        },
    }


def main() -> None:
    root = _ensure_root_on_path()
    print(f"[LIV TEST] Project root = {root}")

    # Import after path is fixed – avoid InstrumentManager here to prevent circular import
    from instruments.connection import (
        ArroyoConnection,
        GentecConnection,
        ThorlabsPowermeterConnection,
        ActuatorConnection,
        AndoConnection,
    )
    from operations.LIV.liv_core import LIVMain, LIVMainParameters, LIVMainThread

    # 1) Connect instruments directly using the same connection classes as the GUI
    print("[LIV TEST] Connecting instruments directly ...")

    # Using default config/ports from each connection class (instrument_config.ini)
    arroyo = ArroyoConnection()
    arroyo_ok = arroyo.connect()

    gentec = GentecConnection()
    gentec_ok = gentec.connect()

    thorlabs = ThorlabsPowermeterConnection()
    thorlabs_ok = thorlabs.connect()

    actuator = ActuatorConnection()
    actuator_ok = actuator.connect()

    ando = AndoConnection()
    ando_ok = ando.connect()

    print(f"[LIV TEST] Arroyo connected:   {arroyo_ok}")
    print(f"[LIV TEST] Gentec connected:   {gentec_ok}")
    print(f"[LIV TEST] Thorlabs connected: {thorlabs_ok}")
    print(f"[LIV TEST] Actuator connected: {actuator_ok}")
    print(f"[LIV TEST] Ando connected:     {ando_ok}")

    # 2) Build LIV parameters from example recipe
    full_recipe = build_example_recipe(fiber_coupled=True)
    liv_params = LIVMainParameters.from_recipe(full_recipe)

    # 3) Create LIVMain and wire instruments
    liv = LIVMain()
    liv.set_instruments(
        arroyo=arroyo,
        gentec=gentec,
        thorlabs_pm=thorlabs,
        actuator=actuator,
        ando=ando,
    )

    # Log status messages so you see the exact flow (laser on, temp, sweep, etc.)
    liv.status_message.connect(lambda msg: print(f"[LIV] {msg}"))

    # 4) Run LIV in its own thread (same pattern as test_sequence_executor)
    result_holder = {"res": None}

    def on_done(res):
        result_holder["res"] = res

    thread = LIVMainThread(liv, liv_params)
    thread.test_completed.connect(on_done)
    thread.start()

    # Wait until the LIV thread finishes
    while thread.isRunning():
        time.sleep(0.2)

    result = result_holder["res"] or thread.result
    if result is None:
        print("[LIV TEST] ERROR: LIV thread did not return a result.")
        return

    # 5) Print key numeric results
    print("\n=== LIV RESULT (single‑run test) ===")
    print(f"Passed:                {result.passed}")
    print(f"Fail reasons:          {result.fail_reasons}")
    print(f"Final power (mW):      {result.final_power:.3f}")
    print(f"Thorlabs avg (mW):     {result.thorlabs_average_power_mw:.3f}")
    print(f"Calib factor:          {result.thorlabs_calib_factor:.4f}")
    print(f"P@Ir (mW):             {result.power_at_rated_current:.3f}")
    print(f"I@Pr (mA):             {result.current_at_rated_power:.3f}")
    print(f"Threshold Ith (mA):    {result.threshold_current:.3f}")
    print(f"Slope efficiency (mW/mA): {result.slope_efficiency:.6f}")
    print(f"Num LIV points:        {len(result.current_array)}")


if __name__ == "__main__":
    main()

