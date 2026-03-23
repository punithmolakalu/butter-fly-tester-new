#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
"""
PER-style terminal tests (no main GUI).

Modes (--mode):

  arroyo-step (default)
    1) Arroyo: laser current (default 400 mA), TEC 25 °C, TEC ON, laser ON
    2) Thorlabs (mW) + PRM: read spacing follows PRM speed by default (5 °/s → sample every 5°,
       10 °/s → every 10°). Override with --sample-every-deg / --power-every-deg / --step.
    3) Terminal: PRM angle (deg), Thorlabs (mW)

  jog-plot
    Kinesis KCubeDCServo jog + PyVISA PM100 (dBm) + live matplotlib plot.
    PM100 uses SENS:CORR:WAV, SENS:POW:UNIT DBM, MEAS:POW? (same as standalone script).
    Default: MEAS:POW? spacing (deg) = --jog-velocity (°/s). Override with --power-every-deg; 0 = every poll.

Run from project root:

  python tests/per_prm_thorlabs_terminal_test.py
  python tests/per_prm_thorlabs_terminal_test.py --mode jog-plot --thorlabs "USB0::..." --prm-serial 27271352

Laser safety: use --skip-laser-on for arroyo-step, or jog-plot (no Arroyo).
"""
from __future__ import annotations

import argparse
import configparser
import os
import sys
import threading
import time
from typing import Any, Tuple, cast

# Project root = parent of tests/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _instruments_dir() -> str:
    import instruments.connection as _conn

    return os.path.dirname(os.path.abspath(_conn.__file__))


def load_saved_connection_addresses() -> dict:
    """Same sources as the app: instrument_config.ini then saved_connections.ini."""
    defaults = {
        "arroyo_port": "",
        "thorlabs_visa": "",
        "prm_serial": "",
    }
    inst_dir = _instruments_dir()
    cfg_path = os.path.join(inst_dir, "instrument_config.ini")
    if os.path.exists(cfg_path):
        try:
            cfg = configparser.ConfigParser()
            cfg.read(cfg_path)
            if cfg.has_section("Connection"):
                for k in ("arroyo_port", "thorlabs_visa", "prm_serial"):
                    if cfg.has_option("Connection", k):
                        defaults[k] = cfg.get("Connection", k).strip()
            if cfg.has_section("Arroyo") and cfg.has_option("Arroyo", "port"):
                v = cfg.get("Arroyo", "port").strip()
                if v:
                    defaults["arroyo_port"] = v
            if cfg.has_section("Thorlabs_Powermeter"):
                for opt in ("resource", "resource_string"):
                    if cfg.has_option("Thorlabs_Powermeter", opt):
                        v = cfg.get("Thorlabs_Powermeter", opt).strip()
                        if v:
                            defaults["thorlabs_visa"] = v
                            break
            if cfg.has_section("PRM") and cfg.has_option("PRM", "serial_number"):
                v = cfg.get("PRM", "serial_number").strip()
                if v:
                    defaults["prm_serial"] = v
        except Exception:
            pass
    saved = os.path.join(inst_dir, "saved_connections.ini")
    if os.path.exists(saved):
        try:
            cfg = configparser.ConfigParser()
            cfg.read(saved)
            if cfg.has_section("saved"):
                for k in defaults:
                    if cfg.has_option("saved", k):
                        defaults[k] = cfg.get("saved", k).strip()
        except Exception:
            pass
    return defaults


def _print_row_mw(n: int, angle_deg: float, power_mw: float) -> None:
    print(
        "[SAMPLE] {:5d}  PRM_angle = {:10.4f} deg   Thorlabs = {:14.6g} mW".format(
            n, float(angle_deg), float(power_mw)
        ),
        flush=True,
    )


def _sample_spacing_deg(user_spec: float, speed_deg_per_s: float, *, zero_means_every_poll: bool) -> float:
    """
    Angular spacing between power meter reads (degrees).
    user_spec < 0: follow speed (e.g. 5 °/s → read every 5°).
    user_spec == 0: if zero_means_every_poll, return 0 (read every poll); else use speed.
    user_spec > 0: use that many degrees between reads.
    """
    u = float(user_spec)
    sp = max(0.1, min(float(speed_deg_per_s), 180.0))
    if zero_means_every_poll and u == 0.0:
        return 0.0
    if u < 0.0 or (u == 0.0 and not zero_means_every_poll):
        return sp
    return max(0.1, min(u, 360.0))


def _print_row_dbm(n: int, angle_deg: float, power_dbm: float) -> None:
    print(
        "[SAMPLE] {:5d}  PRM_angle = {:10.4f} deg   PM100    = {:14.6f} dBm".format(
            n, float(angle_deg), float(power_dbm)
        ),
        flush=True,
    )


# ----- jog-plot: pythonnet + Kinesis (lazy) -----

KINESIS_DIR = r"C:\Program Files\Thorlabs\Kinesis"


def _import_clr() -> Any:
    """Import clr from pythonnet with a helpful error if unavailable."""
    try:
        import clr  # type: ignore[import-not-found]

        return clr  # type: ignore[no-any-return]
    except ModuleNotFoundError:
        pass

    try:
        import pythonnet  # type: ignore
    except Exception as e:
        raise RuntimeError("pythonnet is not installed. Install with: pip install pythonnet") from e

    load_err = None
    for args in (("netfx",), tuple()):
        try:
            pythonnet.load(*args)  # type: ignore
            import clr  # type: ignore[import-not-found]

            return clr  # type: ignore[no-any-return]
        except Exception as e:
            load_err = e

    raise RuntimeError("Failed to load .NET runtime for pythonnet: {}".format(load_err)) from load_err


def _setup_kinesis_dll_paths() -> None:
    if os.path.isdir(KINESIS_DIR):
        if KINESIS_DIR not in sys.path:
            sys.path.append(KINESIS_DIR)
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(KINESIS_DIR)
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(os.getcwd())
        except Exception:
            pass


def _open_pm100_pyvisa(resource: str, timeout_ms: int = 5000) -> Tuple[Any, Any]:
    try:
        import pyvisa  # type: ignore[import-not-found]
    except Exception as e:
        raise RuntimeError("pyvisa is not installed. Install with: pip install pyvisa") from e

    rm = cast(Any, pyvisa.ResourceManager())
    inst = cast(Any, rm.open_resource(resource))
    inst.timeout = int(timeout_ms)
    inst.write_termination = "\n"
    inst.read_termination = "\n"
    return rm, inst


def _to_float_net(value) -> float:
    try:
        return float(value)
    except TypeError:
        return float(str(value))


def _list_kinesis_serials(DeviceManagerCLI) -> list:
    DeviceManagerCLI.BuildDeviceList()
    try:
        return [str(sn).strip() for sn in DeviceManagerCLI.GetDeviceList()]
    except Exception:
        return []


def _connect_controller_with_retry(controller, serial_num: str, DeviceManagerCLI) -> None:
    available = _list_kinesis_serials(DeviceManagerCLI)
    print("[INFO] Kinesis devices: {}".format(available), flush=True)
    if available and serial_num not in available:
        raise RuntimeError("Serial {} not in Kinesis list: {}".format(serial_num, available))

    last_error = None
    for attempt in (1, 2):
        try:
            DeviceManagerCLI.BuildDeviceList()
        except Exception:
            pass
        time.sleep(0.2)
        try:
            controller.Connect(serial_num)
            return
        except Exception as exc:
            last_error = exc
            try:
                controller.Disconnect(True)
            except Exception:
                try:
                    controller.Disconnect()
                except Exception:
                    pass
            if attempt == 1:
                print("[INFO] First motor connect failed; refreshing Kinesis and retrying.", flush=True)
                time.sleep(0.4)

    if last_error is not None:
        raise last_error
    raise RuntimeError("PRM Connect failed after retries")


def _create_live_plot():
    import matplotlib.pyplot as plt

    plt.ion()
    fig, ax = plt.subplots(figsize=(9, 5))
    (line,) = ax.plot([], [], color="tab:blue", linewidth=1.5)
    ax.set_xlabel("Angle (deg)")
    ax.set_ylabel("Power (dBm)")
    ax.set_title("Power vs Angle (jog-plot test)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.show(block=False)
    try:
        fig.canvas.draw_idle()
        fig.canvas.flush_events()
    except Exception:
        pass
    return fig, ax, line


def _update_live_plot(fig, ax, line, angles_deg, powers_dbm) -> None:
    import matplotlib.pyplot as plt

    if not angles_deg or not powers_dbm:
        return
    line.set_data(angles_deg, powers_dbm)
    xmin = min(angles_deg)
    xmax = max(angles_deg)
    if xmin == xmax:
        xmin -= 0.5
        xmax += 0.5
    ymin = min(powers_dbm)
    ymax = max(powers_dbm)
    if ymin == ymax:
        ymin -= 0.5
        ymax += 0.5
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    try:
        line.figure.canvas.draw_idle()
        line.figure.canvas.flush_events()
    except Exception:
        pass
    plt.pause(0.01)


def _plot_power_vs_angle_final(angles_deg, powers_dbm) -> None:
    import matplotlib.pyplot as plt

    if not angles_deg or not powers_dbm:
        print("[INFO] No samples — skipping final plot.", flush=True)
        return
    plt.figure(figsize=(9, 5))
    plt.plot(angles_deg, powers_dbm, color="tab:blue", linewidth=1.5)
    plt.xlabel("Angle (deg)")
    plt.ylabel("Power (dBm)")
    plt.title("Power vs Angle")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def run_jog_plot_mode(args: argparse.Namespace, addrs: dict) -> int:
    """Kinesis jog + PyVISA PM100 dBm + matplotlib + terminal samples."""
    thorlabs_r = (args.thorlabs or addrs["thorlabs_visa"] or "").strip()
    prm_sn = (args.prm_serial or addrs["prm_serial"] or "").strip()
    if not thorlabs_r:
        print("[FAIL] No Thorlabs VISA resource — use --thorlabs or instrument_config.ini", flush=True)
        return 1
    if not prm_sn:
        print("[FAIL] No PRM serial — use --prm-serial or instrument_config.ini", flush=True)
        return 1

    _setup_kinesis_dll_paths()
    _clr = cast(Any, _import_clr())
    _clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
    _clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
    _clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")

    from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore
    from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo  # type: ignore
    from Thorlabs.MotionControl.GenericMotorCLI import DeviceConfiguration  # type: ignore
    from Thorlabs.MotionControl.GenericMotorCLI import MotorDirection  # type: ignore
    from Thorlabs.MotionControl.GenericMotorCLI.ControlParameters import JogParametersBase  # type: ignore
    from System import Decimal  # type: ignore

    print("[INFO] PM100 resource: {}".format(thorlabs_r), flush=True)
    rm = None
    pm = None
    angles_deg: list = []
    powers_dbm: list = []
    fig = ax = line = None
    if not args.no_plot:
        fig, ax, line = _create_live_plot()

    controller = None
    n = 0
    try:
        rm, pm = _open_pm100_pyvisa(thorlabs_r, timeout_ms=int(args.pm_timeout_ms))
        pm = cast(Any, pm)
        try:
            idn = pm.query("*IDN?").strip()
        except Exception:
            idn = "Unknown"
        print("[INFO] PM100 IDN: {}".format(idn), flush=True)

        wav = float(args.wavelength_nm)
        pm.write("SENS:CORR:WAV {:.6f}NM".format(wav))
        pm.write("SENS:POW:UNIT DBM")
        try:
            unit = pm.query("SENS:POW:UNIT?").strip()
        except Exception as exc:
            unit = "UNKNOWN ({})".format(exc)
        print("[INFO] PM100 power unit: {}".format(unit), flush=True)

        print("[INFO] PRM serial: {}".format(prm_sn), flush=True)
        DeviceManagerCLI.BuildDeviceList()
        controller = KCubeDCServo.CreateKCubeDCServo(prm_sn)
        if controller is None:
            print("[FAIL] CreateKCubeDCServo returned None", flush=True)
            return 1

        _connect_controller_with_retry(controller, prm_sn, DeviceManagerCLI)

        if not controller.IsSettingsInitialized():
            controller.WaitForSettingsInitialized(3000)

        controller.StartPolling(50)
        time.sleep(0.1)
        controller.EnableDevice()
        time.sleep(0.1)

        config = controller.LoadMotorConfiguration(
            prm_sn, DeviceConfiguration.DeviceSettingsUseOptionType.UseDeviceSettings
        )
        config.DeviceSettingsName = str("PRM1-Z8")
        config.UpdateCurrentConfiguration()

        if not args.no_home:
            print("[INFO] Homing motor (timeout 60 s)...", flush=True)
            controller.Home(60000)
            time.sleep(0.2)

        jv = float(args.jog_velocity)
        if jv <= 0:
            jv = 10.0
        if jv > 25.0:
            jv = 25.0

        jog_params = controller.GetJogParams()
        jog_params.StepSize = Decimal(float(args.jog_step_deg))
        jog_params.VelocityParams.MaxVelocity = Decimal(float(jv))
        jog_params.JogMode = JogParametersBase.JogModes.SingleStep
        controller.SetJogParams(jog_params)

        direction = MotorDirection.Backward if args.reverse else MotorDirection.Forward
        ped = _sample_spacing_deg(float(args.power_every_deg), jv, zero_means_every_poll=True)
        print(
            "[INFO] MoveJog {} step={} deg max_vel={} poll={} ms; MEAS:POW? when Δangle≥{} deg (match speed; 0=every poll)".format(
                "Backward" if args.reverse else "Forward",
                args.jog_step_deg,
                jv,
                args.poll_ms,
                ped,
            ),
            flush=True,
        )
        print("[INFO] --- samples: index | PRM_angle (deg) | PM100 (dBm) ---", flush=True)

        controller.MoveJog(direction, 0)
        time.sleep(0.25)

        def _device_busy(ctrl) -> bool:
            try:
                v = ctrl.IsDeviceBusy
                return bool(v() if callable(v) else v)
            except Exception:
                return False

        last_angle_for_power: float | None = None
        while _device_busy(controller):
            angle_deg = _to_float_net(controller.Position)
            take_power = (
                ped <= 0.0
                or last_angle_for_power is None
                or abs(angle_deg - last_angle_for_power) >= ped
            )
            if take_power:
                try:
                    power_dbm = float(str(pm.query("MEAS:POW?")).strip())
                except Exception:
                    power_dbm = float("nan")
                last_angle_for_power = angle_deg
                n += 1
                _print_row_dbm(n, angle_deg, power_dbm)
                angles_deg.append(angle_deg)
                powers_dbm.append(power_dbm)
                if fig is not None and ax is not None and line is not None:
                    _update_live_plot(fig, ax, line, angles_deg, powers_dbm)
            time.sleep(max(0.01, float(args.poll_ms) / 1000.0))

        print("[INFO] --- done: {} samples ---".format(n), flush=True)
        return 0

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.", flush=True)
        return 130
    except Exception as ex:
        print("[FAIL] {}".format(ex), flush=True)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if controller is not None:
            try:
                controller.StopPolling()
            except Exception:
                pass
            try:
                controller.Disconnect(False)
            except Exception:
                pass
            print("[INFO] PRM disconnected.", flush=True)
        if pm is not None:
            try:
                pm.close()
            except Exception:
                pass
        if rm is not None:
            try:
                rm.close()
            except Exception:
                pass
        if not args.no_plot:
            import matplotlib.pyplot as plt

            plt.ioff()
            if not args.no_final_plot:
                _plot_power_vs_angle_final(angles_deg, powers_dbm)


def run_arroyo_step_mode(args: argparse.Namespace, addrs: dict) -> int:
    from instruments.connection import ArroyoConnection, ThorlabsPowermeterConnection, PRMConnection
    from instruments.prm import DEFAULT_ACCEL as PRM_DEFAULT_ACCEL

    arroyo_port = (args.arroyo_port or addrs["arroyo_port"] or "").strip()
    thorlabs_r = (args.thorlabs or addrs["thorlabs_visa"] or "").strip()
    prm_sn = (args.prm_serial or addrs["prm_serial"] or "").strip()

    arroyo = None
    thor = None
    prm = None

    try:
        if not arroyo_port:
            print(
                "[WARN] No Arroyo COM port — set [Arroyo] port in instruments/instrument_config.ini or use --arroyo-port",
                flush=True,
            )
        else:
            print("[INFO] Arroyo connecting: {}".format(arroyo_port), flush=True)
            arroyo = ArroyoConnection(port=arroyo_port)
            if not arroyo.connect():
                print("[FAIL] Arroyo connect failed.", flush=True)
                return 1
            print("[OK] Arroyo connected.", flush=True)

        if arroyo and arroyo.is_connected():
            print("[INFO] Laser set current = {} mA".format(args.current), flush=True)
            if not arroyo.laser_set_current(args.current):
                print("[WARN] laser_set_current failed", flush=True)
            time.sleep(0.15)
            print("[INFO] TEC set temperature = {} °C".format(args.tec_temp), flush=True)
            if not arroyo.set_temp(args.tec_temp):
                print("[WARN] set_temp failed", flush=True)
            time.sleep(0.15)

            if not args.skip_laser_on:
                print("[INFO] TEC output ON", flush=True)
                arroyo.set_output(1)
                time.sleep(0.35)
                print("[INFO] Laser output ON", flush=True)
                arroyo.laser_set_output(1)
                time.sleep(0.35)
            else:
                print("[INFO] Skipping TEC/laser output ON (--skip-laser-on)", flush=True)

        if args.arroyo_only_setup:
            print("[INFO] --arroyo-only-setup: done.", flush=True)
            return 0

        if not thorlabs_r:
            print(
                "[FAIL] No Thorlabs VISA resource — set in instrument_config.ini [Thorlabs_Powermeter] or use --thorlabs",
                flush=True,
            )
            return 1
        print("[INFO] Thorlabs connecting: {}".format(thorlabs_r), flush=True)
        thor = ThorlabsPowermeterConnection(resource=thorlabs_r)
        if not thor.connect():
            print("[FAIL] Thorlabs connect failed.", flush=True)
            return 1
        print("[OK] Thorlabs connected.", flush=True)

        if not prm_sn:
            print(
                "[FAIL] No PRM serial — set [PRM] serial_number in instrument_config.ini or use --prm-serial",
                flush=True,
            )
            return 1
        print("[INFO] PRM connecting: {}".format(prm_sn), flush=True)
        prm = PRMConnection(serial_number=prm_sn)
        prm.connect(verbose=True)
        print("[OK] PRM connected.", flush=True)

        spd = float(args.prm_speed)
        if spd <= 0:
            spd = 10.0
        if spd > 25.0:
            print("[WARN] Clamping PRM speed -> max 25 deg/s", flush=True)
            spd = 25.0
        print("[INFO] PRM set_speed {} deg/s, accel {} deg/s^2".format(spd, PRM_DEFAULT_ACCEL), flush=True)
        prm.set_speed(spd, PRM_DEFAULT_ACCEL)

        start = float(args.start)
        end = float(args.end)

        if args.sweep == "continuous":
            sed = _sample_spacing_deg(float(args.sample_every_deg), spd, zero_means_every_poll=False)
            poll = max(0.01, float(args.continuous_poll_ms) / 1000.0)
            travel = abs(end - start)
            max_sec = travel / max(spd, 0.01) + 120.0

            print(
                "[INFO] Continuous sweep: start {:.4f}° → {:.4f}°; Thorlabs every ≥{:.2f}°; PRM speed {:.2f}°/s".format(
                    start, end, sed, spd
                ),
                flush=True,
            )
            print("[INFO] --- samples: index | PRM_angle (deg) | Thorlabs (mW) ---", flush=True)

            prm.move_to(start)
            time.sleep(max(0.05, float(args.dwell)))

            move_done = threading.Event()
            move_err: list = []

            def _run_move_to_end() -> None:
                try:
                    prm.move_to(end)
                except Exception as e:
                    move_err.append(e)
                finally:
                    move_done.set()

            th = threading.Thread(target=_run_move_to_end, daemon=True)
            th.start()

            n = 0
            last_ang: float | None = None
            t0 = time.time()
            while (time.time() - t0) <= max_sec:
                pos = prm.get_position()
                if pos is not None:
                    ang = float(pos)
                    if last_ang is None or abs(ang - last_ang) >= sed:
                        p_mw = thor.read_power_mw()
                        if p_mw is not None:
                            n += 1
                            last_ang = ang
                            _print_row_mw(n, ang, float(p_mw))
                if move_done.is_set() and not th.is_alive():
                    break
                time.sleep(poll)

            th.join(timeout=10.0)
            if move_err:
                print("[WARN] PRM move thread: {}".format(move_err[0]), flush=True)

            posf = prm.get_position()
            if posf is not None:
                angf = float(posf)
                if last_ang is None or abs(angf - last_ang) >= max(0.05, sed * 0.25):
                    p_mw = thor.read_power_mw()
                    if p_mw is not None:
                        n += 1
                        _print_row_mw(n, angf, float(p_mw))

            print("[INFO] --- done: {} samples ---".format(n), flush=True)
            return 0

        # ----- step sweep (stop at each --step deg) -----
        raw_step = float(args.step)
        if raw_step < 0 or raw_step == 0:
            step_mag = spd
        else:
            step_mag = raw_step
        step_mag = max(0.1, min(step_mag, 360.0))
        direction = 1.0 if end >= start else -1.0
        step = step_mag * direction

        print(
            "[INFO] Step sweep PRM from {:.4f} to {:.4f} deg, step {:.4f} deg, dwell {:.3f} s".format(
                start, end, abs(step), args.dwell
            ),
            flush=True,
        )
        print("[INFO] --- samples: index | PRM_angle (deg) | Thorlabs (mW) ---", flush=True)

        cur = start
        n = 0
        while True:
            prm.move_to(cur)
            time.sleep(max(0.05, float(args.dwell)))
            pos = prm.get_position()
            p_mw = thor.read_power_mw()
            if p_mw is None:
                print("[WARN] Thorlabs read None at angle command {:.4f}".format(cur), flush=True)
            if pos is not None and p_mw is not None:
                n += 1
                _print_row_mw(n, float(pos), float(p_mw))

            reached = (direction > 0 and cur >= end) or (direction < 0 and cur <= end)
            if reached:
                break
            cur += step
            if direction > 0 and cur > end:
                cur = end
            if direction < 0 and cur < end:
                cur = end

        print("[INFO] --- done: {} samples ---".format(n), flush=True)
        return 0

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.", flush=True)
        return 130
    except Exception as ex:
        print("[FAIL] {}".format(ex), flush=True)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if prm is not None and prm.is_connected():
            try:
                prm.disconnect()
                print("[INFO] PRM disconnected.", flush=True)
            except Exception:
                pass
        if thor is not None and thor.is_connected():
            try:
                thor.disconnect()
                print("[INFO] Thorlabs disconnected.", flush=True)
            except Exception:
                pass
        if arroyo is not None and arroyo.is_connected():
            try:
                arroyo.laser_set_output(0)
                time.sleep(0.2)
                print("[INFO] Laser output OFF (TEC left as-is).", flush=True)
            except Exception:
                pass
            try:
                arroyo.disconnect()
                print("[INFO] Arroyo disconnected.", flush=True)
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="PER terminal tests: Arroyo+step sweep or Kinesis jog + PM100 dBm plot")
    ap.add_argument(
        "--mode",
        choices=("arroyo-step", "jog-plot"),
        default="arroyo-step",
        help="arroyo-step: full chain + PRMConnection step sweep (mW). jog-plot: Kinesis jog + PyVISA dBm + matplotlib.",
    )
    # arroyo-step
    ap.add_argument("--current", type=float, default=400.0, help="Laser set current (mA)")
    ap.add_argument("--tec-temp", type=float, default=25.0, help="TEC setpoint (°C)")
    ap.add_argument("--prm-speed", type=float, default=10.0, help="PRM max velocity deg/s (arroyo-step)")
    ap.add_argument("--start", type=float, default=0.0, help="First angle (arroyo-step)")
    ap.add_argument("--end", type=float, default=45.0, help="Last angle (arroyo-step)")
    ap.add_argument(
        "--sweep",
        choices=("continuous", "step"),
        default="continuous",
        help="arroyo-step: continuous=one move to --end, sample by --sample-every-deg; step=stop every --step deg",
    )
    ap.add_argument(
        "--step",
        type=float,
        default=-1.0,
        help="arroyo-step step mode: degrees between stops; default -1 = same as --prm-speed (e.g. 5 °/s → 5° steps)",
    )
    ap.add_argument(
        "--sample-every-deg",
        type=float,
        default=-1.0,
        help="arroyo-step continuous: read Thorlabs every N°; default -1 = N = --prm-speed (5 °/s → every 5°)",
    )
    ap.add_argument(
        "--continuous-poll-ms",
        type=float,
        default=50.0,
        help="arroyo-step continuous mode: loop sleep (ms) between position checks",
    )
    ap.add_argument("--dwell", type=float, default=0.15, help="Seconds after move before read (arroyo-step step mode)")
    ap.add_argument("--skip-laser-on", action="store_true")
    ap.add_argument("--arroyo-only-setup", action="store_true")
    # jog-plot
    ap.add_argument("--jog-step-deg", type=float, default=360.0, help="Jog step size (deg), default 360 like sample")
    ap.add_argument("--jog-velocity", type=float, default=25.0, help="Jog max velocity (deg/s)")
    ap.add_argument("--wavelength-nm", type=float, default=635.0, help="PM100 SENS:CORR:WAV (nm) for jog-plot")
    ap.add_argument("--poll-ms", type=float, default=100.0, help="Delay between samples while jogging (ms)")
    ap.add_argument("--pm-timeout-ms", type=int, default=5000, help="PyVISA timeout for PM100")
    ap.add_argument("--no-home", action="store_true", help="Skip PRM Home() in jog-plot")
    ap.add_argument("--reverse", action="store_true", help="Jog backward instead of forward")
    ap.add_argument("--no-plot", action="store_true", help="jog-plot: no matplotlib windows")
    ap.add_argument("--no-final-plot", action="store_true", help="jog-plot: skip plot at end (still live if not --no-plot)")
    ap.add_argument(
        "--power-every-deg",
        type=float,
        default=-1.0,
        help="jog-plot: MEAS:POW? every N°; default -1 = N = --jog-velocity (5 °/s → every 5°); 0 = every poll",
    )
    # shared
    ap.add_argument("--arroyo-port", type=str, default="")
    ap.add_argument("--thorlabs", type=str, default="")
    ap.add_argument("--prm-serial", type=str, default="")

    args = ap.parse_args()
    addrs = load_saved_connection_addresses()

    if args.mode == "jog-plot":
        return int(run_jog_plot_mode(args, addrs) or 0)

    return int(run_arroyo_step_mode(args, addrs) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
