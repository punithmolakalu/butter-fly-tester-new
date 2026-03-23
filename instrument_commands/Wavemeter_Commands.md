# Wavemeter GPIB Command List

The following table lists the GPIB commands (Header = command character(s), Content = value or description).

---

## Command reference

| Item | Header | Content |
|------|--------|---------|
| MASTER RESET | **Z** | Clears the settings on the panel. |
| RESET | **C** | Clears data. |
| SINGLE measurement | **E** | Performs the SINGLE measurement. |
| SRQ signal control | **S** | `S0`: Sends the SRQ. `S1`: Does not send the SRQ. |
| Terminator specification | **D** | `D0`: CR NL\<EOI\>. `D1`: NL. `D2`: \<EOI\>. |
| Header data output control | **H** | `H0`: HEADER OFF. `H1`: HEADER ON. |
| Measurement mode | **K** | `K0`: Wavelength measurement. `K1`: Frequency measurement. |
| FUNCTION | **F** | `F0`: CHECK (for wavelength measurement). `F1`: LASER. `F2`: LED. `F3`: CHOP. |
| Wavelength range | **W** | `W0`: 480 nm to 1000 nm. `W1`: 1000 nm to 1650 nm. |
| RESOLUTION | **RE** | See below. |
| SAMPLE MODE | **M** | `M0`: RUN. `M1`: HOLD. |
| AVERAGE | **A** | `A0`: AVERAGE OFF. `A1`: ON. |
| DRIFT | **RF** | `RF0`: DRIFT OFF. `RF1`: ON. |
| CAL | **CA** | Setting for altitude: `CA0`: 0 m, `CA1`: 500 m, `CA2`: 1000 m, `CA3`: 1500 m, `CA4`: 2000 m. |
| BUZZER | **B** | `B0`: BUZZER OFF. `B1`: ON. |
| DISPLAY | **DS** | `DS0`: DISPLAY OFF. `DS1`: ON. |

---

## RESOLUTION (RE) details

**Wavelength measurement**

| Value | Resolution |
|-------|------------|
| RE0 | 0.0001 nm (when set to AVG) |
| RE1 | 0.001 nm |
| RE2 | 0.01 nm |
| RE3 | 0.1 nm |
| RE4 | 1 nm |

**Frequency measurement**

| Value | Resolution |
|-------|------------|
| RE0 | 10 MHz (when set to AVG) |
| RE1 | 100 MHz |
| RE2 | 1 GHz |
| RE3 | 10 GHz |
| RE4 | 100 GHz |
| RE5 | 1 THz |

---

## Typical usage

- **Wavelength mode:** `K0` then `E` for single measurement.
- **Frequency mode:** `K1` then `E` for single measurement.
- **Wavelength range:** `W0` (480–1000 nm) or `W1` (1000–1650 nm).
- **Single shot:** Send `E` to perform one measurement.
- **Terminator:** Use `D0`, `D1`, or `D2` to match your host (e.g. `D1` for NL only).
