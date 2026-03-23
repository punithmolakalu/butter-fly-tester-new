# Complete Ando AQ6317B GP-IB Commands Reference

This document contains **ALL** GP-IB commands available in the Ando AQ6317B Controller system.

---

## Table of Contents

1. [System Commands](#system-commands)
2. [Sweep Commands](#sweep-commands)
3. [Wavelength/Span Commands](#wavelengthspan-commands)
4. [Level Commands](#level-commands)
5. [Resolution/Sensitivity Commands](#resolutionsensitivity-commands)
6. [Trace Commands](#trace-commands)
7. [Marker Commands](#marker-commands)
8. [Peak Search Commands](#peak-search-commands)
9. [Analysis Commands](#analysis-commands)
10. [Display Commands](#display-commands)
11. [Memory Commands](#memory-commands)
12. [Measurement Mode Commands](#measurement-mode-commands)
13. [Pulse Measurement Commands](#pulse-measurement-commands)
14. [Power Meter Commands](#power-meter-commands)
15. [Analog Output Commands](#analog-output-commands)
16. [Program Commands](#program-commands)
17. [Floppy Disk Commands](#floppy-disk-commands)
18. [Data Output Commands](#data-output-commands)
19. [Advanced/Long Term Commands](#advancedlong-term-commands)
20. [Copy/Output Commands](#copyoutput-commands)
21. [Panel Switch Commands](#panel-switch-commands)

---

## System Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `*IDN?` | Instrument identification | Yes | None |
| `*RST` | Reset instrument | No | None |
| `STATUS?` | Get instrument status | Yes | None |
| `REMOTE` | Set instrument to remote mode | No | None |
| `REMOTE?` | Query remote mode status | Yes | None |
| `INIT` | Nonvolatile initialization | No | None |
| `DATE` | Set date | No | Date string |
| `TIME` | Set time | No | Time string |
| `BUZZER` | Sound buzzer | No | None |
| `BZCLK` | Buzzer click sound | No | None |
| `BZWRN` | Buzzer warning sound | No | None |
| `WCAL` | Wavelength calibration | No | None |
| `WCALS` | Wavelength calibration (built-in) | No | None |
| `WLSFT` | Wavelength shift | No | Shift value |
| `WLSHIFT` | Wavelength shift (alternative) | No | Shift value |
| `LVSFT` | Level shift | No | Shift value |
| `LEVELSHIFT` | Level shift (alternative) | No | Shift value |
| `ATOFS` | Auto offset | No | None |
| `AUTO OFFSET` | Auto offset (alternative) | No | None |
| `OPALIGN` | Optical alignment | No | None |
| `OPTICAL ALIGNMENT` | Optical alignment (alternative) | No | None |
| `SET CLOCK` | Set clock | No | None |
| `SET COLOR` | Set color | No | None |
| `DEFCL` | Default color patterns | No | None |
| `TLSADR` | TLS address | No | Address |
| `GP2ADR` | GP-IB2 address | No | Address |
| `UCWRN` | Uncal warning display | No | None |
| `ARESDSP` | Actual resolution display | No | None |
| `LOGLMT` | Log data limits | No | None |
| `HD` | Talker data header | No | None |

---

## Sweep Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `AUTO` | Auto sweep mode | No | None |
| `SINGLE` | Single sweep | No | None |
| `SGL` | Single sweep (short) | No | None |
| `REPEAT` | Repeat sweep | No | None |
| `RPT` | Repeat sweep (short) | No | None |
| `STOP` | Stop sweep | No | None |
| `STP` | Stop sweep (short) | No | None |
| `SEGMENT` | Segment measure | No | None |
| `SMEAS` | Segment measure (short) | No | None |
| `SEGMENT MEASURE` | Segment measure (full) | No | None |
| `SEGP{points}` | Set segment points | No | 1-20001 |
| `SEGPOINT{points}` | Set segment points (alternative) | No | 1-20001 |
| `SEGMENT POINT {points}` | Set segment points (full) | No | 1-20001 |
| `SWPI{interval}` | Set sweep interval | No | 1-99999 seconds |
| `SWPINTVL{interval}` | Set sweep interval (alternative) | No | 1-99999 seconds |
| `SWP INTVL {seconds}sec` | Set sweep interval (full) | No | 1-99999 seconds |
| `SWPM{mode}` | Set sweep marker mode | No | 0 (full) or 1 (L1-L2) |
| `SWPMKR0` | Sweep marker full | No | None |
| `SWPMKR1` | Sweep marker L1-L2 | No | None |
| `SWEEP?` | Query sweep mode | Yes | None |

---

## Wavelength/Span Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `CTRWL {wavelength}` | Set center wavelength | Yes | 600.00-1750.00 nm |
| `CTRWL?` | Query center wavelength | Yes | None |
| `CENTER WL {wavelength}nm` | Set center wavelength (full) | No | 600.00-1750.00 nm |
| `CTR FREQ {frequency}THz` | Set center frequency | No | 171.500-499.500 THz |
| `CENTER FREQ {frequency}THz` | Set center frequency (full) | No | 171.500-499.500 THz |
| `SPAN {span}` | Set wavelength span | Yes | 0, 0.5-1200.0 nm |
| `SPAN?` | Query span | Yes | None |
| `SPAN WL {span}nm` | Set wavelength span (full) | No | 0, 0.5-1200.0 nm |
| `SPAN FREQ {span}THz` | Set frequency span | No | 0, 0.10-350.00 THz |
| `STARTWL{wavelength}` | Set start wavelength | No | 0.00-1750.00 nm |
| `START WL {wavelength}nm` | Set start wavelength (full) | No | 0.00-1750.00 nm |
| `STOPWL{wavelength}` | Set stop wavelength | No | 600.00-2350.00 nm |
| `STOP WL {wavelength}nm` | Set stop wavelength (full) | No | 600.00-2350.00 nm |
| `WLMODE0` | Wavelength mode: Air | No | None |
| `WLMODE1` | Wavelength mode: Vacuum | No | None |
| `WLMODE` | Wavelength mode | No | 0 or 1 |
| `ATCTR{on_off}` | Auto center mode | Yes | 1 (ON) or 0 (OFF) |
| `ATCTR1` | Auto center ON | No | None |
| `ATCTR0` | Auto center OFF | No | None |
| `CTR=P` | Set center to peak | No | None |

---

## Level Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `REFL{level}` | Set reference level (dBm) | Yes | -90.0 to 20.0 dBm |
| `REFL?` | Query reference level | Yes | None |
| `REF LEVEL {level}dBm` | Set reference level (full) | No | -90.0 to 20.0 dBm |
| `REFLP{level}` | Set reference level (pW) | No | 1.00-999 pW |
| `REFLN{level}` | Set reference level (nW) | No | 1.00-999 nW |
| `REFLU{level}` | Set reference level (µW) | No | 1.00-999 µW |
| `REFLM{level}` | Set reference level (mW) | No | 1.00-100 mW |
| `REFERENCE LEVEL {level}{unit}` | Set reference level (full) | No | Various units |
| `LSCL{scale}` | Set level scale | Yes | 0.1-10.0 dB/DIV or 0 (linear) |
| `LSCL?` | Query level scale | Yes | None |
| `LSCL0` | Set linear scale | No | None |
| `LEVEL SCALE {scale}dB/D` | Set level scale (full) | No | 0.1-10.0 dB/DIV |
| `LEVEL SCALE 0` | Set linear scale (full) | No | None |
| `BASL{level}` | Set base level | Yes | 0 to REF × 0.9 |
| `BASL?` | Query base level | Yes | None |
| `BASE LEVEL {level}` | Set base level (full) | No | 0 to REF × 0.9 |
| `REF=P` | Set peak to reference level | No | None |
| `ATREF{mode}` | Auto reference level | Yes | 1 (ON) or 0 (OFF) |
| `ATREF?` | Query auto reference level | Yes | None |
| `LOFST{offset}` | Set level offset | Yes | -99.9 to 99.9 dB |
| `LOFST?` | Query level offset | Yes | None |
| `SCALEMODE0` | Scale mode: Linear | No | None |
| `SCALEMODE1` | Scale mode: Log | No | None |
| `SCALEMODE` | Set scale mode | No | 0 or 1 |

---

## Resolution/Sensitivity Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `RESLN{resolution}` | Set resolution | Yes | 0.01-2.0 nm |
| `RESOLN?` | Query resolution | Yes | None |
| `RESOLUTION WL {resolution}nm` | Set resolution (full) | No | 0.01-2.0 nm |
| `RESOLUTION FREQ {resolution}GHz` | Set frequency resolution | No | 2, 4, 10, 20, 40, 100, 200, 400 GHz |
| `SNHD` | Sensitivity: Normal Range Hold | No | None |
| `SNAT` | Sensitivity: Normal Range Auto | No | None |
| `SMID` | Sensitivity: MID | No | None |
| `SHI1` | Sensitivity: HIGH 1 | No | None |
| `SHI2` | Sensitivity: HIGH 2 | No | None |
| `SHI3` | Sensitivity: HIGH 3 | No | None |
| `SENS?` | Query sensitivity mode | Yes | None |
| `SENS NORMAL RANGE HOLD` | Sensitivity: Normal Range Hold (full) | No | None |
| `SENS NORMAL RANGE AUTO` | Sensitivity: Normal Range Auto (full) | No | None |
| `SENS {sensitivity}` | Set sensitivity | No | Mode string |
| `AVERAGE TIMES {times}` | Set average times | No | 1-1000 |
| `SAMPLING POINT {points}` | Set sampling points | No | 11-20001 |
| `SMPL0` | Auto sampling | No | None |
| `SMPL{points}` | Set sampling points | No | 11-20001 |
| `ARES?` | Query resolution ability | Yes | None |

---

## Trace Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `TRACE A` | Set trace A active | No | None |
| `TRACE B` | Set trace B active | No | None |
| `TRACE C` | Set trace C active | No | None |
| `ACTIVE TRACE {trace}` | Set active trace | No | A, B, or C |
| `WRTA` | Trace A: Write | No | None |
| `WRITE A` | Trace A: Write (full) | No | None |
| `WRITE {trace}` | Set trace to write | No | A, B, or C |
| `FIXA` | Trace A: Fix | No | None |
| `FIX A` | Trace A: Fix (full) | No | None |
| `FIX {trace}` | Set trace to fix | No | A, B, or C |
| `MAXA` | Trace A: Max hold | No | None |
| `MAX HOLD A` | Trace A: Max hold (full) | No | None |
| `MAX HOLD {trace}` | Set trace to max hold | No | A, B, or C |
| `MINB` | Trace B: Min hold | No | None |
| `MIN HOLD B` | Trace B: Min hold (full) | No | None |
| `MIN HOLD {trace}` | Set trace to min hold | No | A, B, or C |
| `RAVA{times}` | Trace A: Roll average | No | 2-100 times |
| `RAVB{times}` | Trace B: Roll average | No | 2-100 times |
| `ROLL AVG {trace} {times}` | Set trace to roll average | No | A/B/C, 2-100 |
| `DSPA` | Trace A: Display | No | None |
| `DSPB` | Trace B: Display | No | None |
| `DSPC` | Trace C: Display | No | None |
| `DISPLAY {trace}` | Set trace to display | No | A, B, or C |
| `BLKA` | Trace A: Blank | No | None |
| `BLKB` | Trace B: Blank | No | None |
| `BLKC` | Trace C: Blank | No | None |
| `BLANK {trace}` | Set trace to blank | No | A, B, or C |
| `B=A` | Copy trace B to A | No | None |
| `C=A` | Copy trace C to A | No | None |
| `A=B` | Copy trace A to B | No | None |
| `C=B` | Copy trace C to B | No | None |
| `A=C` | Copy trace A to C | No | None |
| `B=C` | Copy trace B to C | No | None |
| `TRACE {source}→{dest}` | Copy trace | No | A/B/C → A/B/C |
| `A-B→C` | Trace C = A - B | No | None |
| `B-A→C` | Trace C = B - A | No | None |
| `A-BCL` | Trace C = A - B (log) | No | None |
| `B-ACL` | Trace C = B - A (log) | No | None |
| `A+BCL` | Trace C = A + B (log) | No | None |
| `A+B(LIN)→C` | Trace C = A + B (linear) | No | None |
| `NORMC` | Normalize trace C | No | None |
| `CVFTC{limit}` | Curve fit trace C | No | Limit value |
| `CVPKC{limit}` | Curve peak trace C | No | Limit value |

---

## Marker Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `WMKR{wavelength}` | Set marker to wavelength | No | 0.000-2350.000 nm |
| `FMKR{frequency}` | Set marker to frequency | No | 1.0000-674.5000 THz |
| `MARKER {wavelength}nm` | Set marker wavelength (full) | No | 0.000-2350.000 nm |
| `MARKER {frequency}THz` | Set marker frequency (full) | No | 1.0000-674.5000 THz |
| `MKR{number}` | Set marker number | No | 1-10 |
| `MCLR{number}` | Clear marker | No | 1-10 |
| `MKCL` | Clear all markers | No | None |
| `ALL MARKER CLEAR` | Clear all markers (full) | No | None |
| `CTR=M` | Set center to marker | No | None |
| `REF=M` | Set reference to marker | No | None |
| `L1MK{wavelength}` | Set line marker 1 wavelength | No | 0.000-2350.000 nm |
| `L1FMK{frequency}` | Set line marker 1 frequency | No | 1.0000-674.5000 THz |
| `L2MK{wavelength}` | Set line marker 2 wavelength | No | 0.000-2350.000 nm |
| `L2FMK{frequency}` | Set line marker 2 frequency | No | 1.0000-674.5000 THz |
| `LINE MARKER1 {wavelength}nm` | Set line marker 1 (full) | No | 0.000-2350.000 nm |
| `LINE MARKER2 {wavelength}nm` | Set line marker 2 (full) | No | 0.000-2350.000 nm |
| `L3DBM{level}` | Set line marker 3 (dBm) | No | -150.00 to 40.00 dBm |
| `L3DB{level}` | Set line marker 3 (dB) | No | -139.900 to 139.900 dB |
| `L3LN{level}` | Set line marker 3 (linear) | No | Linear value |
| `LINE MARKER3 {level}dB` | Set line marker 3 (full) | No | -139.900 to 139.900 dB |
| `LINE MARKER3 {level}dBm` | Set line marker 3 dBm (full) | No | -150.00 to 40.00 dBm |
| `L4DBM{level}` | Set line marker 4 (dBm) | No | -150.00 to 40.00 dBm |
| `L4DB{level}` | Set line marker 4 (dB) | No | -139.900 to 139.900 dB |
| `L4LN{level}` | Set line marker 4 (linear) | No | Linear value |
| `SP=LM` | Set span to line markers | No | None |
| `SRLMK` | Search line markers | No | None |
| `LMKCL` | Clear line markers | No | None |
| `MLTMKR` | Multi marker | No | None |
| `MKROS` | Marker on/off | No | None |
| `FIG` | Figure marker | No | None |
| `MKRPRT` | Marker print | No | None |
| `MKRUP` | Marker update | No | None |
| `MKUNT` | Marker unit | No | None |
| `MKR?` | Query marker position | Yes | None |

---

## Peak Search Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `PEAK SEARCH` | Perform peak search | No | None |
| `PKSR` | Peak search (short) | No | None |
| `PKWL?` | Query peak wavelength | Yes | None |
| `PKLVL?` | Query peak level | Yes | None |
| `BTSR` | Bottom search | No | None |
| `NSR` | Next search | No | None |
| `NSRR` | Next search reverse | No | None |
| `MSRL` | Marker search | No | None |
| `ATSR{on_off}` | Auto search | No | 1 (ON) or 0 (OFF) |
| `MODIF{difference}` | Mode difference | No | Difference value |

---

## Analysis Commands

### Spectral Width Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `SWENV` | Spectral width: Envelope | No | None |
| `SWENY` | Spectral width: Envelope (alternative) | No | None |
| `ENVT1{threshold}` | Envelope threshold 1 | No | 0.01-50.00 dB |
| `ENVT2{threshold}` | Envelope threshold 2 | No | 0.01-50.00 dB |
| `ENVK{coefficient}` | Envelope coefficient | No | Coefficient value |
| `SWTHR` | Spectral width: Threshold | No | None |
| `THRTH{threshold}` | Threshold value | No | 0.01-50.00 dB |
| `THRK{coefficient}` | Threshold coefficient | No | Coefficient value |
| `SWRMS` | Spectral width: RMS | No | None |
| `RMSTH{threshold}` | RMS threshold | No | 0.01-50.00 dB |
| `RMSK{coefficient}` | RMS coefficient | No | Coefficient value |
| `SWPRM` | Spectral width: Peak RMS | No | None |
| `PRMTH{threshold}` | Peak RMS threshold | No | 0.01-50.00 dB |
| `PRMK{coefficient}` | Peak RMS coefficient | No | Coefficient value |
| `NCHTH{threshold}` | Notch threshold | No | 0.01-50.00 dB |
| `NCHMOD{mode}` | Notch mode | No | Mode value |
| `SPEC WD ENV {threshold}dB` | Spectral width envelope (full) | No | 0.01-50.00 dB |
| `SPEC WD THRESH {threshold}dB` | Spectral width threshold (full) | No | 0.01-50.00 dB |
| `SPEC WD RMS {threshold}dB` | Spectral width RMS (full) | No | 0.01-50.00 dB |
| `SPEC WD PK RMS {threshold}dB` | Spectral width peak RMS (full) | No | 0.01-50.00 dB |
| `SPEC WD SEARCH` | Spectral width search | No | None |
| `SPWD?` | Query spectral width | Yes | None |
| `MODFT` | Mode filter | No | None |

### SMSR Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `SMSR{ref}` | SMSR reference | No | 1-10 |
| `SSMSK{mask}` | SMSR mask | No | ±0.00-99.99 nm |
| `SMSR MASK ±{range}nm` | SMSR mask (full) | No | ±0.00-99.99 nm |

### Power Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `POWER` | Power measurement | No | None |
| `POFS{offset}` | Power offset | No | -10.00 to 10.00 dB |
| `PARAM POWER OFST {offset}dB` | Power offset (full) | No | -10.00 to 10.00 dB |

### Laser Diode Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `FPAN` | FP-LD analysis | No | None |
| `DFBAN` | DFB-LD analysis | No | None |
| `DFBLD0;1;0;20.00` | DFB-LD parameters | No | Parameters |
| `LEDAN` | LED analysis | No | None |
| `LED0;1;0;10.00` | LED parameters | No | Parameters |

### PMD Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `PMD` | PMD analysis | No | None |
| `PMDTH{threshold}` | PMD threshold | No | Threshold value |

### EDFA Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `EDNF` | EDFA noise figure | No | None |
| `OFIN{offset}` | Input offset | No | -99.99 to 99.99 dB |
| `OFOUT{offset}` | Output offset | No | -99.99 to 99.99 dB |
| `EDFA NF TRACE A OFST {offset}dB` | EDFA NF trace A offset (full) | No | -99.99 to 99.99 dB |
| `EDFA NF TRACE B OFST {offset}dB` | EDFA NF trace B offset (full) | No | -99.99 to 99.99 dB |
| `PLMSK` | Power level mask | No | None |
| `MIMSK` | Mask input | No | None |
| `EDFCVF{type}` | EDFA curve fit | No | Type value |
| `EDFTH{threshold}` | EDFA threshold | No | Threshold value |

### WDM Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `WDM` | WDM analysis | No | None |
| `WDMAN` | WDM analysis (alternative) | No | None |
| `WDMOS` | WDM on/off | No | None |
| `WDMRH` | WDM reference | No | None |
| `WDMRN` | WDM reference number | No | None |
| `WDMDISP` | WDM display | No | None |
| `WDMREF` | WDM reference | No | None |
| `WDMMR` | WDM marker | No | None |
| `WDMREFDAT` | WDM reference data | No | None |
| `WDMCHAUT` | WDM channel auto | No | None |
| `WDMMAX{max}` | WDM max channels | No | 1-200 |
| `WDM MAX NUMBER {max}` | WDM max channels (full) | No | 1-200 |
| `WDMTH{threshold}` | WDM threshold | No | 0.1-50.0 dB |
| `WDM THRESH {threshold}dB` | WDM threshold (full) | No | 0.1-50.0 dB |
| `WDMDIF{difference}` | WDM difference | No | Difference value |
| `DUTCH{channel}` | DUT channel | No | Channel number |
| `DUTCHF{frequency}` | DUT channel frequency | No | Frequency value |
| `WDMCHSW` | WDM channel switch | No | None |
| `WDMUNT` | WDM unit | No | None |
| `WDMTCOPY` | WDM trace copy | No | None |
| `WDMNOI` | WDM noise | No | None |
| `WDMNOIP` | WDM noise power | No | None |
| `WDMNOIBW` | WDM noise bandwidth | No | None |
| `DUTLEV` | DUT level | No | None |
| `DUTSNR` | DUT SNR | No | None |
| `WDMDSPMSK` | WDM display mask | No | None |
| `WDMDUAL` | WDM dual | No | None |
| `WDMSLOPE` | WDM slope | No | None |
| `WNFAN` | WDM NF analysis | No | None |
| `WNFNP` | WDM NF number | No | None |
| `WNFOFI` | WDM NF input | No | None |
| `WNFOFO` | WDM NF output | No | None |

### Filter Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `FILPKAN` | Filter peak analysis | No | None |
| `FILBTMAN` | Filter bottom analysis | No | None |

### Auto Analysis

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `ATANA{on_off}` | Auto analysis | No | 1 (ON) or 0 (OFF) |
| `AUTO` | Auto (in analysis context) | No | None |
| `AUTO OFF` | Auto off | No | None |

---

## Display Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `NORMD` | Normal display | No | None |
| `NORMAL DISPLAY` | Normal display (full) | No | None |
| `SPLIT` | Split display | No | None |
| `SPLIT DISPLAY` | Split display (full) | No | None |
| `3D` | 3D display | No | None |
| `3D DISPLAY` | 3D display (full) | No | None |
| `ULTRA` | Upper trace A | No | None |
| `ULTRB` | Upper trace B | No | None |
| `ULTRC` | Upper trace C | No | None |
| `UHLD` | Upper hold | No | None |
| `LHLD` | Lower hold | No | None |
| `ANGL{angle}` | 3D angle | No | -50 to +50 degrees |
| `3D ANGLE {angle}` | 3D angle (full) | No | -50 to +50 degrees |
| `3DRCL` | 3D recall | No | None |
| `ZSCL{scale}` | 3D Z-scale | No | 3-16 |
| `3D Z-SCALE {scale}` | 3D Z-scale (full) | No | 3-16 |
| `MEM` | Memory | No | None |
| `LBL` | Label input | No | None |
| `LBLCL` | Label clear | No | None |
| `NMSK` | Noise mask | No | None |
| `MSKL` | Mask level | No | None |
| `CLR` | Clear traces | No | None |

---

## Memory Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `SAVEA{address}` | Save trace A to memory | No | 0-31 |
| `SAVEB{address}` | Save trace B to memory | No | 0-31 |
| `SAVEC{address}` | Save trace C to memory | No | 0-31 |
| `SAVE {trace} → MEM {slot}` | Save trace to memory (full) | No | A/B/C, 0-31 |
| `RCLA{address}` | Recall memory to trace A | No | 0-31 |
| `RCLB{address}` | Recall memory to trace B | No | 0-31 |
| `RCLC{address}` | Recall memory to trace C | No | 0-31 |
| `RECALL MEM {slot} → {trace}` | Recall memory (full) | No | 0-31, A/B/C |

---

## Measurement Mode Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `CLMES` | CW measurement mode | No | None |
| `PLMES` | Pulse measurement mode | No | None |
| `ANA?` | Query analysis mode | Yes | None |

---

## Pulse Measurement Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `PULSE LIGHT MEASURE LPF MODE` | Pulse: LPF mode | No | None |
| `PULSE LIGHT MEASURE PEAK HOLD MODE {times}` | Pulse: Peak hold mode | No | 1-9999 times |
| `PULSE LIGHT MEASURE EXT TRG MODE` | Pulse: External trigger mode | No | None |
| `EXTRG` | External trigger | No | None |

---

## Power Meter Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `PMPRT` | Power meter repeat | No | None |
| `PMSGL` | Power meter single | No | None |
| `PMSTP` | Power meter stop | No | None |
| `AREA` | Power meter area | No | None |
| `REL` | Power meter relative | No | None |
| `PMRST` | Power meter reset | No | None |
| `PMUNT` | Power meter unit | No | None |

---

## Analog Output Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| (Commands implemented in AnalogOutputController) | | | |

---

## Program Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `EXEC{program_number}` | Execute program | No | 1-20 |
| `EXECUTE KEY {program_number}` | Execute program (full) | No | 1-20 |
| `PROGRAM EXECUTE` | Program execute | No | None |
| `PROGRAM EDIT` | Program edit | No | None |
| `PREXT` | Program exit/pause | No | None |
| `PRDEL` | Delete program | No | None |

---

## Floppy Disk Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `WR A'{filename}'` | Write trace A to FD | No | Filename |
| `WR B'{filename}'` | Write trace B to FD | No | Filename |
| `WR C'{filename}'` | Write trace C to FD | No | Filename |
| `WRMEM{address}'{filename}'` | Write memory to FD | No | 0-31, filename |
| `WR3D'{filename}'` | Write 3D data to FD | No | Filename |
| `WRPRG{number}'{filename}'` | Write program to FD | No | 1-20, filename |
| `RD A'{filename}'` | Read trace A from FD | No | Filename |
| `RD B'{filename}'` | Read trace B from FD | No | Filename |
| `RD C'{filename}'` | Read trace C from FD | No | Filename |
| `RDMEM{address}'{filename}'` | Read memory from FD | No | 0-31, filename |
| `RD3D'{filename}'` | Read 3D data from FD | No | Filename |
| `RDPRG{number}'{filename}'` | Read program from FD | No | 1-20, filename |
| `WRDT'{filename}'` | Write data to FD | No | Filename |
| `RDDT'{filename}'` | Read data from FD | No | Filename |
| `WRSET'{filename}'` | Write settings to FD | No | Filename |
| `RDSET'{filename}'` | Read settings from FD | No | Filename |
| `DEL'{filename}'` | Delete file | No | Filename |
| `DSKIN` | Initialize disk | No | None |
| `FLOPPYWRITE` | Floppy write | No | None |
| `TRFMT` | Trace format | No | None |
| `GRCOL` | Graphic color | No | None |
| `GRFMT` | Graphic format | No | None |
| `D&TDT` | Date/time data | No | None |
| `LBLDT` | Label data | No | None |
| `DTARA` | Data area | No | None |
| `CNDDT` | Condition data | No | None |

---

## Data Output Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `LDATA` | Level data trace A | Yes | None |
| `LDATA?` | Query level data trace A | Yes | None |
| `LDATB` | Level data trace B | Yes | None |
| `LDATB?` | Query level data trace B | Yes | None |
| `LDATC` | Level data trace C | Yes | None |
| `LDATC?` | Query level data trace C | Yes | None |
| `LDATA R{start}-R{end}` | Level data range | Yes | Range |
| `LDATB R{start}-R{end}` | Level data range B | Yes | Range |
| `LDATC R{start}-R{end}` | Level data range C | Yes | Range |
| `WDATA` | Wavelength data trace A | Yes | None |
| `WDATA?` | Query wavelength data trace A | Yes | None |
| `WDATB` | Wavelength data trace B | Yes | None |
| `WDATB?` | Query wavelength data trace B | Yes | None |
| `WDATC` | Wavelength data trace C | Yes | None |
| `WDATC?` | Query wavelength data trace C | Yes | None |
| `WDATA R{start}-R{end}` | Wavelength data range | Yes | Range |
| `WDATB R{start}-R{end}` | Wavelength data range B | Yes | Range |
| `WDATC R{start}-R{end}` | Wavelength data range C | Yes | Range |
| `LMEM{address}` | Memory level data | Yes | 0-31 |
| `WMEM{address}` | Memory wavelength data | Yes | 0-31 |
| `DTNUM` | Data number | Yes | None |
| `DTNUM?` | Query data number | Yes | None |
| `LDTDIG` | Log data digit | No | None |
| `DIR` | Directory | Yes | None |
| `DIR?` | Query directory | Yes | None |
| `FNAME` | Filename | Yes | None |
| `FNAME?` | Query filename | Yes | None |
| `WARN` | Warning errors | Yes | None |
| `WARN?` | Query warning errors | Yes | None |
| `ARES?` | Query resolution ability | Yes | None |
| `LTALM` | Long term alarm | Yes | None |
| `LTALM?` | Query long term alarm | Yes | None |
| `LTALMDT` | Long term alarm data | Yes | None |
| `LTALMDT?` | Query long term alarm data | Yes | None |
| `WAVELENGTH {trace}?` | Query wavelength (alternative) | Yes | A/B/C |
| `POWER {trace}?` | Query power (alternative) | Yes | A/B/C |
| `TRACE {trace}?` | Query trace (alternative) | Yes | A/B/C |

---

## Advanced/Long Term Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `LTSWP` | Long term sweep start/stop | No | None |
| `LTINTVL{interval}` | Long term interval | No | Interval value |
| `LTINTVL {interval}` | Long term interval (full) | No | Interval value |
| `LTTIME{times}` | Long term repeat times | No | Times value |
| `LTWL` | Long term wavelength display | No | None |
| `LTL` | Long term level display | No | None |
| `LTSNR` | Long term SNR display | No | None |
| `LTCH{channel}` | Long term channel | No | Channel number |
| `LTCHCUR` | Long term channel cursor | No | None |
| `LTREFSET` | Long term reference set | No | None |
| `LTREFINI` | Long term reference initialize | No | None |
| `LTWLLIM` | Long term wavelength limit | No | None |
| `LTLLOW` | Long term level low | No | None |
| `LTLHI` | Long term level high | No | None |
| `LTSNRLIM` | Long term SNR limit | No | None |
| `LTATSCL` | Long term auto scale | No | None |
| `LTWLCTR` | Long term wavelength center | No | None |
| `LTWLSPAN` | Long term wavelength span | No | None |
| `LTLVLCTR` | Long term level center | No | None |
| `LTLVLSCL` | Long term level scale | No | None |
| `LTDAT?{data_number}` | Query long term data | Yes | Data number |
| `LTST?` | Query long term status | Yes | None |

---

## Copy/Output Commands

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `COPY` | Printer/plotter output | No | None |
| `PRFED{lines}` | Paper feed | No | 1-10 lines |
| `HELP` | Explanatory statement display | No | None |
| `CRS` | Coarse key of rotary knob | No | None |
| `SD0` | String delimiter: Comma | No | None |
| `SD1` | String delimiter: Space | No | None |
| `BD0` | Block delimiter: CRLF+EOI | No | None |
| `BD1` | Block delimiter: EOI only | No | None |
| `SRQ` | Service request | No | None |
| `SRMSK` | Service request mask | No | None |

---

## Panel Switch Commands

These are high-level commands that map to panel switch operations:

| Command | Description | Parameters |
|---------|-------------|------------|
| `AUTO` | Auto sweep | None |
| `REPEAT` | Repeat sweep | None |
| `SINGLE` | Single sweep | None |
| `STOP` | Stop sweep | None |
| `SEGMENT MEASURE` | Segment measure | None |
| `CENTER WL {wavelength}nm` | Center wavelength | 600.00-1750.00 nm |
| `CENTER FREQ {frequency}THz` | Center frequency | 171.500-499.500 THz |
| `SPAN WL {span}nm` | Wavelength span | 0, 0.5-1200.0 nm |
| `SPAN FREQ {span}THz` | Frequency span | 0, 0.10-350.00 THz |
| `START WL {wavelength}nm` | Start wavelength | 0.00-1750.00 nm |
| `STOP WL {wavelength}nm` | Stop wavelength | 600.00-2350.00 nm |
| `REF LEVEL {level}dBm` | Reference level | -90.0 to 20.0 dBm |
| `LEVEL SCALE {scale}dB/D` | Level scale | 0.1-10.0 dB/DIV |
| `BASE LEVEL {level}` | Base level | 0 to REF × 0.9 |
| `RESOLUTION WL {resolution}nm` | Resolution | 0.01-2.0 nm |
| `RESOLUTION FREQ {resolution}GHz` | Frequency resolution | 2, 4, 10, 20, 40, 100, 200, 400 GHz |
| `SENS NORMAL RANGE HOLD` | Sensitivity: Normal Range Hold | None |
| `SENS NORMAL RANGE AUTO` | Sensitivity: Normal Range Auto | None |
| `AVERAGE TIMES {times}` | Average times | 1-1000 |
| `SAMPLING POINT {points}` | Sampling points | 11-20001 |

---

## IEEE-488.2 and common OSA queries (used by software)

| Command | Description | Query | Parameters |
|---------|-------------|-------|------------|
| `*OPC?` | Operation complete (IEEE 488.2) | Yes | None |
| `SMSR?` | Side-mode suppression ratio (dB) | Yes | None |
| `ANAR?` | Analysis result (full response string) | Yes | None |
| `SMPL?` | Sampling points | Yes | None |

---

## Notes

1. **Query Commands**: Commands marked with `?` are query commands that return data. Use `query()` method instead of `write_command()`.

2. **Parameter Formats**: 
   - Wavelengths: typically in nm (nanometers)
   - Frequencies: typically in THz (terahertz)
   - Levels: typically in dBm (decibel milliwatts)
   - Times: typically in seconds

3. **Command Variations**: Many commands have both short and full forms. Both are listed where applicable.

4. **Range Validation**: Always validate parameters before sending commands. Ranges are specified in the Parameters column.

5. **Response Parsing**: Query responses may need parsing. Check controller implementation for response format details.

---

## Total Command Count

- **System Commands**: ~30
- **Sweep Commands**: ~15
- **Wavelength/Span Commands**: ~15
- **Level Commands**: ~20
- **Resolution/Sensitivity Commands**: ~15
- **Trace Commands**: ~30
- **Marker Commands**: ~30
- **Peak Search Commands**: ~10
- **Analysis Commands**: ~100+
- **Display Commands**: ~20
- **Memory Commands**: ~10
- **Measurement Mode Commands**: ~5
- **Pulse Measurement Commands**: ~5
- **Power Meter Commands**: ~7
- **Program Commands**: ~5
- **Floppy Disk Commands**: ~25
- **Data Output Commands**: ~30
- **Advanced/Long Term Commands**: ~20
- **Copy/Output Commands**: ~10
- **Panel Switch Commands**: ~20

**Total: 400+ individual GP-IB commands**

---

*Last Updated: Based on Ando AQ6317B GP-IB Commands Reference*
*Source: Ando AQ6317B GP-IB Manual and Controller Implementation*
