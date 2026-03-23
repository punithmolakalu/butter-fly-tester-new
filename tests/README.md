# Tests / terminal scripts

## `per_prm_thorlabs_terminal_test.py`

Hardware script (no main GUI). Two modes:

### `--mode arroyo-step` (default)

Arroyo laser current (default **400 mA**), TEC **25 °C**, **TEC ON** then **laser ON**, then **Thorlabs** (app driver, **mW**) + **PRM**.

- **`--sweep continuous` (default):** move to `--start`, then one move to `--end`; **Thorlabs read spacing (degrees) defaults to `--prm-speed` (°/s)** — e.g. **5 °/s → every 5°**, **10 °/s → every 10°**. Override with `--sample-every-deg 20`, etc.
- **`--sweep step`:** default **`--step -1`** = same as **`--prm-speed`** (degrees between stops).

**jog-plot:** default **`--power-every-deg -1`** = spacing equals **`--jog-velocity`** (°/s). **`--power-every-deg 0`** = query every poll.

### `--mode jog-plot`

**Kinesis** `KCubeDCServo` **jog** (SingleStep) + **PyVISA** PM100 in **dBm** (`SENS:POW:UNIT DBM`, `MEAS:POW?`) + **matplotlib** live + final plot. Same pattern as the standalone jog script; prints **PRM angle** and **PM100 (dBm)** per sample. Requires **pythonnet** and Thorlabs Kinesis. Optional: `pip install matplotlib`.

**Run from the project root** (folder containing `main.py`):

```bash
python tests/per_prm_thorlabs_terminal_test.py
python tests/per_prm_thorlabs_terminal_test.py --mode jog-plot
```

Uses the same addresses as the main app: `instruments/instrument_config.ini` and `instruments/saved_connections.ini`.

**Examples:**

```bash
python tests/per_prm_thorlabs_terminal_test.py --prm-speed 5 --start 0 --end 20 --step 0.5
python tests/per_prm_thorlabs_terminal_test.py --arroyo-port COM4 --thorlabs "USB0::0x1313::..." --prm-serial YOUR_SERIAL
python tests/per_prm_thorlabs_terminal_test.py --skip-laser-on
python tests/per_prm_thorlabs_terminal_test.py --arroyo-only-setup
python tests/per_prm_thorlabs_terminal_test.py --mode jog-plot --jog-step-deg 360 --jog-velocity 25 --wavelength-nm 635
python tests/per_prm_thorlabs_terminal_test.py --mode jog-plot --no-plot --reverse
# PM100 (MEAS:POW?) only every 10° of motion (default is 5°); use 0 to query every poll:
python tests/per_prm_thorlabs_terminal_test.py --mode jog-plot --power-every-deg 10
python tests/per_prm_thorlabs_terminal_test.py --mode jog-plot --power-every-deg 0
```

**Safety:** Use appropriate laser safety. Arroyo-step turns **laser output OFF** on exit; TEC is left as-is. Jog-plot does not use Arroyo unless you run the other mode first.
