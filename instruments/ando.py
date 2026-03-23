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
from typing import Any, Dict, List, Optional

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
                    # Clear host read buffer so the next query is not a stale *IDN? line (USB-GPIB).
                    try:
                        from pyvisa.constants import BufferOperation

                        conn.flush(BufferOperation.read_buf)
                    except Exception:
                        try:
                            conn.flush()  # type: ignore[call-arg]
                        except Exception:
                            pass
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

    def _flush_read_buffer(self, conn) -> None:
        """Drop stale bytes in the host read buffer (USB-GPIB often leaves *IDN? lines behind)."""
        if conn is None:
            return
        try:
            from pyvisa.constants import BufferOperation

            conn.flush(BufferOperation.read_buf)
        except Exception:
            try:
                conn.flush()  # type: ignore[call-arg]
            except Exception:
                pass

    @staticmethod
    def _looks_like_idn_response(text: str) -> bool:
        """True if text matches a typical *IDN? reply (stale buffer can return this for PKWL? etc.)."""
        t = (text or "").strip()
        if len(t) < 12:
            return False
        u = t.upper()
        return "ANDO" in u and "AQ6317" in u and "," in t

    def _query_once(self, conn, cmd: str) -> Optional[str]:
        """Single write+read; caller flushes buffer first."""
        qfn = getattr(conn, "query", None)
        if callable(qfn):
            try:
                r = qfn(cmd)
                if r is None:
                    return None
                return str(r).strip()
            except Exception:
                pass
        if not self.write_command(cmd):
            return None
        time.sleep(0.15)
        try:
            return self.read_response()
        except (IOError, OSError, Exception):
            # Empty read / timeout — callers treat None as "no data" (avoids aborting long Spectrum sequences).
            return None

    def query(self, command: str):
        if not self.is_connected():
            return None
        conn = self.gpib_connection
        if conn is None:
            return None
        cmd = (command or "").strip()
        if not cmd:
            return None
        is_idn_query = cmd.upper().startswith("*IDN")
        last: Optional[str] = None
        for attempt in range(2):
            self._flush_read_buffer(conn)
            time.sleep(0.03 if attempt == 0 else 0.12)
            self._flush_read_buffer(conn)
            last = self._query_once(conn, cmd)
            if last is None:
                return None
            if is_idn_query or not self._looks_like_idn_response(last) or attempt == 1:
                return last
            # Stale *IDN? line read for a different command — retry once after longer settle.
        return last

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
        parts = [p.strip() for p in str(r).split(",") if p.strip()]
        try:
            # Many AQ6317B firmwares return the same 5-field ANA-style line for PKWL? (not a single value).
            # Layout matches query_analysis_ana: [0]=width nm, [1]=peak λ nm, [2]=peak dBm, …
            if len(parts) >= 5:
                return float(parts[1])
            if len(parts) >= 2:
                return float(parts[1])
            return float(parts[0])
        except (TypeError, ValueError, IndexError):
            return None

    def query_peak_level_dbm(self):
        """Peak level (dBm) after search."""
        r = self.query("PKLVL?")
        if r is None:
            return None
        parts = [p.strip() for p in str(r).split(",") if p.strip()]
        try:
            if len(parts) >= 5:
                return float(parts[2])
            if len(parts) >= 3:
                return float(parts[2])
            return float(parts[0])
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

    @staticmethod
    def _split_analysis_fields(text: Optional[str]) -> List[str]:
        """Comma- or semicolon-separated fields from ANA?/ANAR? (some firmware uses ';')."""
        s = str(text or "").strip()
        if not s:
            return []
        if "," in s:
            return [p.strip() for p in s.split(",") if p.strip()]
        if ";" in s:
            return [p.strip() for p in s.split(";") if p.strip()]
        return [s]

    @staticmethod
    def _analysis_dict_has_numeric_peak(d: Any) -> bool:
        """True if dict has a usable peak wavelength (ANA 5-field or ANAR DFB/LED)."""
        if not isinstance(d, dict):
            return False
        if d.get("PK_WL_nm") is not None:
            return True
        fields = d.get("fields")
        if isinstance(fields, (list, tuple)) and len(fields) >= 3:
            try:
                float(fields[1])
                return True
            except (TypeError, ValueError):
                pass
        return False

    def _parse_ana_numeric_response(self, r: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse ANA? body into WD/PK fields when the reply is numeric CSV (DFB-style)."""
        if r is None:
            return None
        raw = str(r).strip()
        parts = self._split_analysis_fields(raw)
        if len(parts) < 3:
            return {"raw": raw, "fields": parts}
        out: Dict[str, Any] = {"raw": raw, "fields": parts}
        try:
            out["WD_3dB_nm"] = float(parts[0])
            out["PK_WL_nm"] = float(parts[1])
            out["PK_LVL_dBm"] = float(parts[2])
            if len(parts) >= 4:
                out["EXTRA_nm"] = float(parts[3])
            if len(parts) >= 5:
                out["SMSR_dB"] = float(parts[4])
        except (TypeError, ValueError, IndexError):
            return {"raw": raw, "fields": parts}
        return out

    def query_analysis_ana(self, analysis_hint: str = "") -> Optional[Dict[str, Any]]:
        """
        ANA? — on many AQ6317B units this returns comma-separated analysis **results** (DFB-style).
        The command table also lists ANA? as "analysis mode"; some firmware returns text or short replies here
        and puts numbers on **ANAR?** only — we fall back to query_analysis_anar in that case.

        ``analysis_hint`` is passed through when falling back to ANAR (e.g. LED vs DFB field layout).
        """
        r = self.query("ANA?")
        parsed = self._parse_ana_numeric_response(r)
        if parsed is not None and self._analysis_dict_has_numeric_peak(parsed):
            return parsed
        fb = self.query_analysis_anar(analysis_hint)
        if isinstance(fb, dict) and self._analysis_dict_has_numeric_peak(fb):
            return fb
        return parsed if parsed is not None else fb

    def query_analysis_anar(self, analysis_hint: str = "") -> Optional[Dict[str, Any]]:
        """
        ANAR? — analysis result readback (comma-separated; layout depends on analysis mode).

        Typical DFB-LD (4 fields): PK WL (nm), PK LVL (dBm), SMSR (dB), MODE OFFSET (nm).
        LED (5 fields): MEAN WL, TOTAL POWER (dBm), PK WL, PK LVL, SPEC WD (nm).
        """
        r = self.query("ANAR?")
        if r is None:
            return None
        parts = self._split_analysis_fields(r)
        out: Dict[str, Any] = {"raw": str(r).strip(), "fields": parts}
        if not parts:
            return out
        a = str(analysis_hint or "").strip().upper()
        try:
            if "LED" in a and len(parts) >= 5:
                out["MEAN_WL_nm"] = float(parts[0])
                out["TOTAL_POWER_dBm"] = float(parts[1])
                out["PK_WL_nm"] = float(parts[2])
                out["PK_LVL_dBm"] = float(parts[3])
                out["SPEC_WD_nm"] = float(parts[4])
            elif len(parts) >= 4:
                # DFB / FP / default 4-field: PK WL, PK LVL, SMSR, MODE OFFSET
                out["PK_WL_nm"] = float(parts[0])
                out["PK_LVL_dBm"] = float(parts[1])
                out["SMSR_dB"] = float(parts[2])
                out["MODE_OFFSET_nm"] = float(parts[3])
            elif len(parts) >= 1:
                out["PK_WL_nm"] = float(parts[0])
                if len(parts) >= 2:
                    out["PK_LVL_dBm"] = float(parts[1])
        except (TypeError, ValueError, IndexError):
            pass
        return out

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

    def _strip_leading_count_prefix(self, values: List[float], expected_n: Optional[int] = None) -> List[float]:
        """
        Some AQ6317B firmware prefixes trace CSV with a point count (first field = N, then N values).
        If detected, drop the first element so WDATA/LDATA align with DTNUM?/SMPL.
        """
        if len(values) < 2:
            return values
        n0 = values[0]
        try:
            n_int = int(round(float(n0)))
        except (TypeError, ValueError):
            return values
        rest = values[1:]
        if len(rest) == n_int:
            return rest
        if expected_n is not None and len(rest) == expected_n and n_int in (len(rest), len(values) - 1):
            return rest
        return values

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
        """
        Per AQ6317B GP-IB reference:
        - REMOTE: programmatic control
        - SD0: string delimiter comma (consistent ASCII trace export)
        - TRACE A: active trace A (Data Output applies to displayed trace)
        - WRTA: trace A is write target (same sweep data)
        - DSPA: display trace A (ensures A is the active trace for data output)
        """
        try:
            self.write_command("REMOTE")
            time.sleep(0.02)
            self.write_command("SD0")
            time.sleep(0.02)
            self.write_command("TRACE A")
            time.sleep(0.02)
            self.write_command("WRTA")
            time.sleep(0.02)
            self.write_command("DSPA")
            time.sleep(0.05)
        except Exception:
            pass

    def _read_gpib_full_binary_response(self, conn) -> bytes:
        """
        Read one instrument message; if IEEE definite-length block (#...), keep reading until
        header-declared byte count is satisfied (single read_raw() is often incomplete).
        """
        try:
            raw = conn.read_raw()
        except Exception:
            return b""
        if not raw or raw[0:1] != b"#":
            return raw or b""
        if len(raw) < 2:
            return raw
        try:
            nd = int(chr(raw[1]))
        except (ValueError, IndexError):
            return raw
        if nd <= 0 or len(raw) < 2 + nd:
            return raw
        try:
            nbytes = int(raw[2 : 2 + nd].decode("ascii"))
        except Exception:
            return raw
        total = 2 + nd + nbytes
        buf = bytearray(raw)
        while len(buf) < total:
            try:
                more = conn.read_raw()
            except Exception:
                break
            if not more:
                break
            buf.extend(more)
        return bytes(buf[:total]) if len(buf) >= total else bytes(buf)

    def _parse_trace_write_raw_ascii(self, raw: bytes) -> List[float]:
        """
        Same as common AQ6317B snapshot scripts: comma-separated ASCII, first field = point
        count, remaining fields = trace samples (nm or dBm).
        """
        data_str = raw.decode("ascii", errors="ignore").strip()
        parts = [p.strip() for p in data_str.split(",") if p.strip()]
        if len(parts) < 2:
            return self._parse_float_list_text(data_str)
        try:
            n0 = int(round(float(parts[0])))
            if len(parts) == n0 + 1:
                return [float(x) for x in parts[1:]]
        except (TypeError, ValueError):
            pass
        # Fallback: match scripts that always drop the first field
        try:
            return [float(x) for x in parts[1:]]
        except (TypeError, ValueError):
            return []

    def _read_trace_legacy_write_raw(self, cmd_no_query: str) -> List[float]:
        """
        Hardware path used by working snapshot tools: ``write('WDATA')`` / ``write('LDATA')``
        (no ``?``), then ``read_raw``. Differs from ``WDATA?`` / ``LDATA?`` query responses.
        """
        conn = self.gpib_connection
        if conn is None or not self.is_connected():
            return []
        c = str(cmd_no_query or "").strip().upper().rstrip("?")
        if c not in ("WDATA", "LDATA"):
            return []
        try:
            conn.write(c)
            time.sleep(0.06)
            raw = self._read_gpib_full_binary_response(conn)
            if not raw:
                return []
            if raw[0:1] == b"#":
                floats = self._parse_ieee_block_floats(raw)
                if floats:
                    return floats
            return self._parse_trace_write_raw_ascii(raw)
        except Exception:
            return []

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

        For trace **A**, tries first the same sequence as common bench scripts: ``write('WDATA')`` /
        ``write('LDATA')`` (no ``?``) then ``read_raw`` — many AQ6317B units return ASCII
        ``count,value,...`` or an IEEE float block; this differs from ``WDATA?`` / ``LDATA?`` and
        matches matplotlib snapshot tools. After ``REMOTE``/``SD0``/``TRACE A``/``WRTA``/``DSPA``,
        falls back to ``DTNUM?``/``SMPL?`` + range queries, then full queries.
        """
        if not self.is_connected() or self.gpib_connection is None:
            return []
        conn = self.gpib_connection
        q = (query_cmd or "").strip()
        if not q.endswith("?"):
            q = q + "?"
        base = q.replace("?", "").strip().upper()
        # WDATA/WDATB/WDATC share WDAT*; LDATA/LDATB/LDATC share LDAT*
        is_wdata = base.startswith("WDAT")
        is_ldata = base.startswith("LDAT")
        old_timeout = getattr(conn, "timeout", 5000)

        def _finalize(vals: List[float], expected_n: Optional[int]) -> List[float]:
            if not vals:
                return []
            return self._strip_leading_count_prefix(vals, expected_n)

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
            # Primary: WDATA R1-R501? style (reference: WDATA R{start}-R{end})
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
                raw = self._read_gpib_full_binary_response(conn)
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

        def _range_chunked(total: int) -> List[float]:
            merged: List[float] = []
            step = 256
            start = 1
            while start <= total:
                end = min(start + step - 1, total)
                chunk_cmd = f"{base} R{start}-R{end}?"
                # Per-chunk count prefix: do not pass total N (would confuse strip vs chunk length).
                chunk = _finalize(_try_parse_query_string(chunk_cmd), None)
                if not chunk:
                    chunk = _finalize(_read_once(chunk_cmd), None)
                if not chunk:
                    return []
                merged.extend(chunk)
                start = end + 1
            return merged

        self._prepare_trace_read()
        try:
            conn.timeout = max(int(old_timeout), 180000)
            # 0) Snapshot-style: write WDATA/LDATA without "?", then read_raw — matches many AQ6317B
            #    lab scripts (comma ASCII with leading count, or IEEE block). Differs from WDATA?/LDATA?.
            if base in ("WDATA", "LDATA"):
                legacy = self._read_trace_legacy_write_raw(base)
                legacy = _finalize(legacy, None)
                if legacy:
                    return legacy

            n = self.query_data_point_count() or self.query_sampling_points()

            # Prefer exact-length range reads when we know N (reference Data Output Commands).
            if n and (is_wdata or is_ldata):
                for rcmd in _range_variants(n):
                    out = _finalize(_try_parse_query_string(rcmd), n)
                    if len(out) == n:
                        return out
                    out = _finalize(
                        _read_once(rcmd if rcmd.endswith("?") else rcmd + "?"),
                        n,
                    )
                    if len(out) == n:
                        return out
                if n > 256:
                    merged = _range_chunked(n)
                    if len(merged) == n:
                        return merged

            # Full trace query (may be long; some stacks truncate — range path above is preferred).
            out = _finalize(_try_parse_query_string(q), n)
            if out:
                return out
            out = _finalize(_read_once(q), n)
            if out:
                return out
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
