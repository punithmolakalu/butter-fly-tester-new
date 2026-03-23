"""
Ando AQ6317B Optical Spectrum Analyzer (OSA)

Instrument: Ando AQ6317B. GP-IB (SCPI-style) commands per Ando AQ6317B GP-IB Commands Reference.
Connection: GPIB via PyVISA (e.g. GPIB0::5::INSTR). Address from Connection tab.
Details: Center wavelength, span, resolution, sensitivity, ref level; sweep (single/repeat/stop);
         DFB-LD / LED analysis. REMOTE/LOCAL. Use only the selected GPIB address for this instrument.
"""
from __future__ import annotations

import re
import struct
import time
import warnings
from typing import List, Optional

warnings.filterwarnings("ignore", category=UserWarning, module="gpib_ctypes")

try:
    import pyvisa  # type: ignore[reportMissingImports]
    PYVISA_AVAILABLE = True
except ImportError:
    pyvisa = None
    PYVISA_AVAILABLE = False


# ----- Connection: GPIB scan (used by Connection tab for Ando and Wavemeter lists) -----
def scan_gpib_resources() -> List[str]:
    """Return list of GPIB resource strings from VISA (e.g. GPIB0::5::INSTR).

    Merges default and @py backends. Uses several list_resources() query patterns because
    NI-VISA and pyvisa-py do not always return the same set from a single call to
    list_resources() with no argument — secondary GPIB interfaces or some devices can
    be missed without explicit GPIB?* / GPIB?*::INSTR patterns.

    Runs synchronously; the UI layer (MainViewModel) already invokes this on a worker thread.
    """
    if not PYVISA_AVAILABLE:
        return []
    seen: set = set()
    merged: List[str] = []

    _QUERIES = (
        "GPIB?*::INSTR",
        "GPIB?*",
        "?*::INSTR",
    )

    def _is_gpib_instr(r: str) -> bool:
        """Keep connectable GPIB instrument resources; drop INTFC/other non-INSTR nodes."""
        u = r.upper().strip()
        return "GPIB" in u and "::" in r and u.endswith("::INSTR")

    def add_gpib_from_rm(rm) -> None:
        for q in _QUERIES:
            try:
                for r in rm.list_resources(q):
                    if r and _is_gpib_instr(r) and r not in seen:
                        seen.add(r)
                        merged.append(r)
            except Exception:
                pass
        # Last resort: default pattern (some backends only populate this)
        try:
            for r in rm.list_resources():
                if r and _is_gpib_instr(r) and r not in seen:
                    seen.add(r)
                    merged.append(r)
        except Exception:
            pass

    try:
        add_gpib_from_rm(pyvisa.ResourceManager())
    except Exception:
        pass
    try:
        add_gpib_from_rm(pyvisa.ResourceManager("@py"))
    except Exception:
        pass

    return sorted(merged)


def probe_gpib_andos(timeout_ms: int = 2000, addresses=None) -> List[tuple]:
    """Probe GPIB addresses with *IDN?; return list of (address, idn_string). Used to detect instruments."""
    if not PYVISA_AVAILABLE:
        return []
    addrs = addresses or scan_gpib_resources()
    if not addrs:
        return []
    results = []
    rm = None
    for addr in addrs:
        try:
            if rm is None:
                rm = pyvisa.ResourceManager()
            res = rm.open_resource(addr, open_timeout=500)
            res.timeout = timeout_ms
            idn = res.query("*IDN?").strip()
            res.close()
            if idn:
                results.append((addr, idn))
        except Exception:
            pass
    return results


# ----- Instrument: AndoConnection -----
class AndoConnection:
    """Ando AQ6317B connection via GPIB. Connect to the selected address only (no shared state with wavemeter)."""

    def __init__(self, address=None, config_file=None, instrument_name='Ando'):
        if not PYVISA_AVAILABLE:
            raise ImportError("pyvisa is not available. Please install pyvisa and pyvisa-py.")
        self.gpib_connection = None
        self.connected = False
        self.instrument_name = instrument_name
        self.rm = None
        self.enabled = True
        self.timeout = 5.0
        a = (address or '').strip()
        self.gpib_address = f"GPIB0::{a}::INSTR" if a.isdigit() else (a or 'GPIB0::1::INSTR')

    def connect(self, address=None) -> bool:
        if not self.enabled or not PYVISA_AVAILABLE:
            return False
        addr = (address or self.gpib_address).strip()
        if not addr:
            return False
        timeout_ms = max(10000, int(self.timeout * 1000))
        open_timeout_ms = max(10000, timeout_ms)
        for backend in (None, "@py"):
            try:
                if self.gpib_connection:
                    try:
                        self.gpib_connection.close()
                    except Exception:
                        pass
                    self.gpib_connection = None
                if self.rm:
                    try:
                        self.rm.close()
                    except Exception:
                        pass
                    self.rm = None
                self.rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
                try:
                    self.gpib_connection = self.rm.open_resource(addr, open_timeout=open_timeout_ms)
                except TypeError:
                    self.gpib_connection = self.rm.open_resource(addr)
                conn = self.gpib_connection
                if conn is None:
                    continue
                conn.timeout = timeout_ms
                conn.write_termination = "\n"
                conn.read_termination = "\n"
                time.sleep(0.2)
                idn = conn.query("*IDN?")
                if idn is not None and str(idn).strip():
                    self.connected = True
                    self.write_command("REMOTE")
                    time.sleep(0.1)
                    return True
                conn.close()
                self.gpib_connection = None
            except Exception:
                if self.gpib_connection:
                    try:
                        self.gpib_connection.close()
                    except Exception:
                        pass
                    self.gpib_connection = None
                if backend == "@py":
                    break
        self.connected = False
        return False

    def disconnect(self) -> None:
        if self.gpib_connection:
            try:
                self.set_local_mode()
                time.sleep(0.1)
                self.gpib_connection.close()
            except Exception:
                pass
            self.gpib_connection = None
            self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self.gpib_connection is not None)

    def write_command(self, command: str) -> bool:
        if not self.is_connected():
            return False
        try:
            # Let PyVISA handle termination (resource write_termination/read_termination).
            # Appending our own newline can trigger repeated warnings:
            # "write message already ends with termination characters".
            command = command.strip()
            conn = self.gpib_connection
            if conn is None:
                return False
            conn.write(command)
            return True
        except Exception:
            return False

    def read_response(self, timeout=None):
        if not self.is_connected():
            return None
        conn = self.gpib_connection
        if conn is None:
            return None
        original_timeout = getattr(conn, "timeout", 5000)
        try:
            if timeout:
                conn.timeout = int(timeout * 1000)
            response = conn.read().strip()
            if not response:
                raise IOError("Ando read timeout (device may be off or not responding)")
            return response
        except Exception:
            raise
        finally:
            conn.timeout = original_timeout

    def query(self, command: str):
        if not self.is_connected() or not self.write_command(command):
            return None
        time.sleep(0.1)
        return self.read_response()

    def identify(self): return self.query("*IDN?")
    def reset(self): return self.write_command("*RST")

    def set_remote_mode(self) -> bool:
        return self.is_connected() and self.write_command("REMOTE")

    def set_local_mode(self) -> bool:
        if not self.is_connected():
            return False
        try:
            self.write_command("LOCAL")
            return True
        except Exception:
            return False

    def get_center_wl(self):
        """Query center wavelength (nm). Returns float or None."""
        r = self.query("CTRWL?")
        if r is None:
            return None
        try:
            return float(str(r).strip())
        except (TypeError, ValueError):
            return None

    def get_span(self):
        """Query span (nm). Returns float or None."""
        r = self.query("SPAN?")
        if r is None:
            return None
        try:
            return float(str(r).strip())
        except (TypeError, ValueError):
            return None

    def get_ref_level(self):
        """Query reference level (dBm). Returns float or None."""
        r = self.query("REFL?")
        if r is None:
            return None
        try:
            return float(str(r).strip())
        except (TypeError, ValueError):
            return None

    def get_log_scale(self):
        """Query level scale (dB/DIV). 0 = linear. Returns float or None."""
        r = self.query("LSCL?")
        if r is None:
            return None
        try:
            return float(str(r).strip())
        except (TypeError, ValueError):
            return None

    def get_resolution(self):
        """Query resolution (nm). Returns float or None."""
        r = self.query("RESOLN?")
        if r is None:
            return None
        try:
            return float(str(r).strip())
        except (TypeError, ValueError):
            return None

    def set_center_wavelength(self, wavelength_nm: float) -> bool:
        return self.is_connected() and self.write_command(f"CTRWL {wavelength_nm:.3f}")

    def set_center_wl(self, wavelength_nm: float) -> bool:
        return self.set_center_wavelength(wavelength_nm)

    def set_span(self, span_nm: float) -> bool:
        return self.is_connected() and self.write_command(f"SPAN {span_nm:.3f}")

    def set_resolution(self, resolution_nm: float) -> bool:
        return self.is_connected() and self.write_command(f"RESLN{resolution_nm:.3f}")

    def set_ref_level(self, level_dbm: float) -> bool:
        if not self.is_connected():
            return False
        try:
            L = float(level_dbm)
            if -90 <= L <= 20:
                return self.write_command(f"REFL{L:.1f}")
        except (TypeError, ValueError):
            pass
        return False

    def set_log_scale(self, dB_per_div: float) -> bool:
        if not self.is_connected():
            return False
        try:
            v = float(dB_per_div)
            if v == 0:
                return self.write_command("SCALEMODE0")
            if 0.1 <= v <= 10.0:
                return self.write_command(f"LSCL{v:.1f}")
        except (TypeError, ValueError):
            pass
        return False

    def set_sensitivity(self, sensitivity: str) -> bool:
        if not self.is_connected():
            return False
        sens_map = {"MID": "SMID", "HIGH": "SHI1", "HIGH1": "SHI1", "HIGH2": "SHI2", "HIGH3": "SHI3",
                    "LOW": "SLO1", "LOW1": "SLO1", "LOW2": "SLO2", "AUTO": "SNAT", "NORMAL RANGE AUTO": "SNAT",
                    "NORMAL RANGE HOLD": "SNHD", "HOLD": "SNHD"}
        cmd = sens_map.get(str(sensitivity).upper().strip(), "SMID")
        return self.write_command(cmd)

    def set_sensitivity_index(self, index: int) -> bool:
        # Order matches alignment window dropdown: Normal range auto, Normal range hold, Mid, High1, High2, High3
        modes = ["NORMAL RANGE AUTO", "NORMAL RANGE HOLD", "MID", "HIGH1", "HIGH2", "HIGH3"]
        return 0 <= index < len(modes) and self.set_sensitivity(modes[index])

    def set_sampling_points(self, points: int) -> bool:
        if not self.is_connected():
            return False
        points = max(11, min(20001, int(points)))
        return self.write_command(f"SMPL{points}")

    def analysis_dfb_ld(self) -> bool:
        return self.is_connected() and self.write_command("DFBAN")

    def analysis_led(self) -> bool:
        return self.is_connected() and self.write_command("LEDAN")

    def analysis_fp_ld(self) -> bool:
        return self.is_connected() and self.write_command("FPAN")

    def trace_write_a(self) -> bool:
        """Select trace A as active write target (same as WRTA)."""
        return self.is_connected() and self.write_command("WRTA")

    def peak_search(self) -> bool:
        """Run peak search (PKSR)."""
        return self.is_connected() and self.write_command("PKSR")

    def query_peak_wavelength_nm(self):
        """Peak wavelength after search / marker (nm)."""
        r = self.query("PKWL?")
        if r is None:
            return None
        try:
            return float(str(r).strip().split(",")[0])
        except (TypeError, ValueError, IndexError):
            return None

    def query_peak_level_dbm(self):
        """Peak level (dBm) after search."""
        r = self.query("PKLVL?")
        if r is None:
            return None
        try:
            return float(str(r).strip().split(",")[0])
        except (TypeError, ValueError, IndexError):
            return None

    def query_spectral_width_nm(self):
        """Spectral width result (nm), if analysis populated."""
        r = self.query("SPWD?")
        if r is None:
            return None
        try:
            return float(str(r).strip().split(",")[0])
        except (TypeError, ValueError, IndexError):
            return None

    def query_smsr_db(self):
        """Side-mode suppression ratio (dB), DFB analysis / SMSR measurement."""
        for cmd in ("SMSR?", "MSR?"):
            r = self.query(cmd)
            if r is None:
                continue
            try:
                return float(str(r).strip().split(",")[0])
            except (TypeError, ValueError, IndexError):
                continue
        return None

    def wait_sweep_done(self, timeout_s: float = 180.0, poll_s: float = 0.25) -> bool:
        """Poll SWEEP? until idle or timeout."""
        t0 = time.time()
        while (time.time() - t0) < float(timeout_s):
            if self.is_sweep_done():
                return True
            time.sleep(float(poll_s))
        return self.is_sweep_done()

    def _parse_float_list_text(self, text: str) -> List[float]:
        if not text:
            return []
        s = str(text).strip()
        parts = re.split(r"[,\s;]+", s)
        out: List[float] = []
        for p in parts:
            if not p:
                continue
            try:
                out.append(float(p))
            except (TypeError, ValueError):
                continue
        return out

    def query_sampling_points(self) -> Optional[int]:
        """Return SMPL point count (11–20001) from SMPL?, or None."""
        r = self.query("SMPL?")
        if r is None:
            return None
        m = re.search(r"(\d+)", str(r).strip())
        if not m:
            return None
        try:
            n = int(m.group(1))
            return max(11, min(20001, n))
        except (TypeError, ValueError):
            return None

    def query_data_point_count(self) -> Optional[int]:
        """DTNUM? — number of data points (if supported)."""
        r = self.query("DTNUM?")
        if r is None:
            return None
        m = re.search(r"(\d+)", str(r).strip())
        if not m:
            return None
        try:
            return int(m.group(1))
        except (TypeError, ValueError):
            return None

    def _prepare_trace_read(self) -> None:
        """REMOTE + trace A write target — helps WDATA?/LDATA? return trace A after sweep."""
        try:
            self.write_command("REMOTE")
            time.sleep(0.02)
            self.write_command("WRTA")
            time.sleep(0.05)
        except Exception:
            pass

    def _parse_ieee_block_floats(self, raw: bytes) -> List[float]:
        """Parse optional IEEE 488.2 definite-length binary block of 4-byte floats."""
        if not raw or len(raw) < 4:
            return []
        i = 0
        if raw[0:1] == b"#":
            nd = int(chr(raw[1])) if len(raw) > 2 else 0
            if nd <= 0 or len(raw) < 2 + nd:
                return []
            try:
                nbytes = int(raw[2 : 2 + nd].decode("ascii"))
            except Exception:
                return []
            i = 2 + nd
            payload = raw[i : i + nbytes]
        else:
            payload = raw
        if len(payload) < 4 or (len(payload) % 4) != 0:
            return []
        n = len(payload) // 4
        try:
            return list(struct.unpack(f">{n}f", payload))
        except Exception:
            try:
                return list(struct.unpack(f"<{n}f", payload))
            except Exception:
                return []

    def read_trace_data(self, query_cmd: str = "WDATA?") -> List[float]:
        """
        Read wavelength or level trace (WDATA? / LDATA? / WDATB? / LDATB?).

        Ensures REMOTE + WRTA before reads. Tries: full query string parse, PyVISA ascii/binary,
        raw IEEE block, then **range query** ``WDATA R1-R{n}?`` / ``LDATA R1-R{n}?`` when the
        full trace query returns empty (common on some GPIB stacks / large payloads).
        """
        if not self.is_connected() or self.gpib_connection is None:
            return []
        conn = self.gpib_connection
        q = (query_cmd or "").strip()
        if not q.endswith("?"):
            q = q + "?"
        base = q.replace("?", "").strip().upper()
        is_wdata = base.startswith("WDATA")
        is_ldata = base.startswith("LDATA")
        old_timeout = getattr(conn, "timeout", 5000)

        def _try_parse_query_string(cmd: str) -> List[float]:
            """Single PyVISA query() then split floats (handles comma/space-separated ASCII)."""
            try:
                s = conn.query(cmd)
                if s is None:
                    return []
                out = self._parse_float_list_text(str(s))
                return out if out else []
            except Exception:
                return []

        def _range_variants(n: int) -> List[str]:
            """Different manuals use slightly different range syntax."""
            if n <= 0:
                return []
            r = f"R1-R{n}"
            # Primary: WDATA R1-R501? style
            variants = [
                f"{base} {r}?",
                f"{base}? {r}",
                f"{base} {r}",
            ]
            return variants

        def _read_once(cmd: str) -> List[float]:
            """One attempt: ascii_values, space, binary, raw."""
            try:
                vals = conn.query_ascii_values(cmd, separator=",")
                if vals:
                    return [float(x) for x in vals]
            except Exception:
                pass
            try:
                vals = conn.query_ascii_values(cmd, separator=" ")
                if vals:
                    return [float(x) for x in vals]
            except Exception:
                pass
            try:
                vals = conn.query_binary_values(cmd, datatype="f", is_big_endian=True)
                if vals:
                    return [float(x) for x in vals]
            except Exception:
                pass
            try:
                vals = conn.query_binary_values(cmd, datatype="f", is_big_endian=False)
                if vals:
                    return [float(x) for x in vals]
            except Exception:
                pass
            try:
                conn.write(cmd.rstrip("\n"))
                time.sleep(0.08)
                raw = conn.read_raw()
                if not raw:
                    txt = conn.read()
                    return self._parse_float_list_text(str(txt))
                floats = self._parse_ieee_block_floats(bytes(raw))
                if floats:
                    return floats
                return self._parse_float_list_text(raw.decode("ascii", errors="ignore"))
            except Exception:
                return []
            return []

        self._prepare_trace_read()
        try:
            conn.timeout = max(int(old_timeout), 180000)
            # 1) Direct Resource.query on full command (often works when query_ascii_values does not)
            out = _try_parse_query_string(q)
            if out:
                return out
            # 2) PyVISA helpers + raw
            out = _read_once(q)
            if out:
                return out
            # 3) Point count for range fallback
            n = self.query_data_point_count() or self.query_sampling_points()
            if n and (is_wdata or is_ldata):
                for rcmd in _range_variants(n):
                    out = _try_parse_query_string(rcmd)
                    if out:
                        return out
                    out = _read_once(rcmd if rcmd.endswith("?") else rcmd + "?")
                    if out:
                        return out
                    # Chunk if still empty (very long GPIB lines)
                    if n > 256:
                        merged: List[float] = []
                        step = 256
                        start = 1
                        while start <= n:
                            end = min(start + step - 1, n)
                            chunk_cmd = f"{base} R{start}-R{end}?"
                            chunk = _try_parse_query_string(chunk_cmd)
                            if not chunk:
                                chunk = _read_once(chunk_cmd)
                            if not chunk:
                                merged = []
                                break
                            merged.extend(chunk)
                            start = end + 1
                        if merged:
                            return merged
            return []
        except Exception:
            return []
        finally:
            try:
                conn.timeout = old_timeout
            except Exception:
                pass

    def read_wdata_trace(self) -> List[float]:
        return self.read_trace_data("WDATA?")

    def read_ldata_trace(self) -> List[float]:
        return self.read_trace_data("LDATA?")

    def sweep_auto(self) -> bool:
        return self.is_connected() and self.write_command("AUTO")

    def single_sweep(self) -> bool:
        return self.is_connected() and self.write_command("SGL")

    def sweep_single(self) -> bool:
        return self.single_sweep()

    def repeat_sweep(self) -> bool:
        return self.is_connected() and self.write_command("RPT")

    def sweep_repeat(self) -> bool:
        return self.repeat_sweep()

    def stop_sweep(self) -> bool:
        if not self.is_connected():
            return False
        try:
            self.write_command("REMOTE")
            time.sleep(0.02)
            return self.write_command("STP")
        except Exception:
            return False

    def sweep_stop(self) -> bool:
        return self.stop_sweep()

    def query_sweep_status(self):
        return self.query("SWEEP?")

    def is_sweep_done(self) -> bool:
        try:
            status = self.query_sweep_status()
            if status is None:
                return False
            status_str = str(status).strip()
            if status_str == '0' or status_str.upper() in ['STOP', 'STP', '']:
                return True
            if status_str in ['1', '2', 'SINGLE', 'SGL', 'REPEAT', 'RPT']:
                return False
            return True
        except Exception:
            return False
