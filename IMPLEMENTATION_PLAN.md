# Implementation Plan: Instrument Connect Verification (*IDN*) & Reliable Disconnect UI

This plan ties **SCPI command references**, **driver `connect()` behavior**, and **GUI “Connected / Disconnected”** so every instrument proves it is the expected device after open, and the footer always reflects a real disconnect.

---

## 1. Command reference inventory (source of truth)

| Instrument | Markdown command reference (repo) | Primary Python module |
|------------|-----------------------------------|------------------------|
| Arroyo TEC/Laser | `instrument_commands/Arroyo_Commands.md` | `instruments/arroyo.py` |
| ANDO OSA | `instrument_commands/Ando_Commands.md` | `instruments/ando.py` |
| Wavemeter | `instrument_commands/Wavemeter_Commands.md` | `instruments/wavemeter.py` |
| Gentec INTEGRA | `instrument_commands/Gentec_Powermeter_Commands.md` | `instruments/gentec_powermeter.py` |
| Thorlabs PM | `instrument_commands/thorlabs_powermetr_commands.md` | `instruments/thorlabs_powermeter.py` |
| Actuator | `instrument_commands/Actuator_Commands.md` | `instruments/actuator.py` |
| PRM (Kinesis) | `instrument_commands/PRM_Commands.md` | `instruments/prm.py` |

**Action (documentation):** When changing connect logic, update the matching markdown row if a new query or timeout is introduced.

---

## 2. Current behavior audit (connect + “who am I”)

| Instrument | Connect path | Post-open verification today | Notes |
|------------|--------------|--------------------------------|--------|
| **Arroyo** | `ArroyoConnection.connect()` | `read_temp()` (not `*IDN?`) | `identify()` → `*IDN?` exists but is **not** required on connect. |
| **ANDO** | `AndoConnection.connect()` | `*IDN?` then `REMOTE` + read-buffer flush | **Good:** VISA session is exercised immediately. |
| **Wavemeter** | `WavemeterInstrument` + `WavemeterConnection.connect()` | VISA open + optional `D1`/`K0` prime only | Many heads **do not** document `*IDN?`; verify with **`E` + read** or `*IDN?` if supported. |
| **Thorlabs PM** | `ThorlabsPowermeterConnection.connect()` | `*IDN?` required (non-empty) | **Good.** |
| **Gentec** | `GentecConnection.connect()` | `*VER` / `*CVU` handshake (not IEEE `*IDN?`) | **Accept as “IDN-equivalent”** per vendor doc. |
| **Actuator** | `ActuatorConnection.connect()` | Serial open + sleeps; **no** command response check | Risk: wrong device on COM still shows “connected”. |
| **PRM** | `PRMConnection.connect()` | Kinesis `BuildDeviceList` + `CreateKCubeDCServo` + enable/polling | Not SCPI; **serial-in-list + motor object** is the identity check. |

---

## 3. Target behavior (requirements)

### 3.1 On connect (all instruments)

1. **VISA / SCPI-class devices (ANDO, Thorlabs, Wavemeter if applicable)**  
   - After `open_resource`, run **`*IDN?`** when the instrument supports it (ANDO, Thorlabs: **mandatory**).  
   - **Wavemeter:** try `*IDN?` inside `try/except`; if unsupported, fall back to one **documented** transaction (e.g. `K0` + `W0`/`W1` + `E` + read) with timeout and **non-empty numeric** reply → treat as verified.  
   - Store last **IDN string** (or short hash) on the connection object for logging / status tooltip (optional UI later).

2. **Serial SCPI-class (Arroyo)**  
   - After open, require **`*IDN?`** (via existing `identify()`) **or** keep `read_temp()` **plus** one `*IDN?` if firmware always responds — pick one path and document it in `Arroyo_Commands.md`.  
   - Goal: distinguish “COM opens” from “Arroyo answers”.

3. **Gentec**  
   - Keep **`*VER` / `*CVU`** as the handshake; optionally log parsed model string.

4. **Actuator**  
   - Define **one** minimal query from `Actuator_Commands.md` that returns a known pattern (or wait for a banner line) after connect; fail connect if no response in N ms.  
   - Avoid generic `*IDN?` unless firmware documents it.

5. **PRM**  
   - After `EnableDevice()`, read **device ID / serial** from API (if available) and compare to selected SN; log mismatch.

### 3.2 On disconnect (footer must show **Disconnected**)

1. **Every worker** (`workers/workers.py`): `do_disconnect` must:  
   - Close hardware / release VISA.  
   - Set internal handle to `None`.  
   - **`connection_state_changed.emit({ "<Name>": False })`** — already pattern for Arroyo/Ando/Wavemeter; ensure **Gentec, Thorlabs, Actuator, PRM** do the same consistently (no missing keys).

2. **MainViewModel** (`viewmodel/main_viewmodel.py`): each `_on_*_connection_changed` must set the corresponding `self._*_connected` flag and call **`_emit_connection_state_if_changed()`** so the footer updates even when disconnect does not change other instruments.

3. **Failure during poll** (e.g. `do_ping`, wavemeter read): already emits disconnect on some paths — **audit** that every failure path clears `connected` and emits **False** once (avoid double-emit loops unless idempotent).

4. **UI** (`view/main_window.py`): footer labels read `get_connection_state()` — no change needed if emits are correct; optionally show last **IDN** substring in status log on connect success.

### 3.3 Continuous background health checks (must **not** block the GUI)

**Goal:** Instruments are checked **all the time in the background** so cable unplug, power-off, VISA errors, or serial loss are detected quickly. The **main GUI must never freeze**: no long `connect()`, `query()`, or `read()` on the Qt main thread.

#### Architecture rules

1. **All blocking I/O stays off the GUI thread**  
   - Keep the existing pattern: **one `QThread` per instrument family** (`workers/workers.py` — `ArroyoWorker`, `AndoWorker`, `WavemeterWorker`, …) and drive hardware only from slots running on those threads.  
   - **Never** call `instrument.connect()`, `*IDN?`, `query()`, serial `read()`, or Kinesis API from `MainWindow` / main-thread button handlers beyond **emitting** `request_connect` / `request_disconnect` / `trigger_read` / `trigger_ping`.

2. **Use short timers + signals for “always on” checks**  
   - `MainViewModel` already uses `QTimer` (e.g. `_ando_poll_timer`, `_wavemeter_poll_timer`, …) to **request** reads/pings on workers — keep intervals **reasonable** (hundreds of ms to a few s) and **stagger** heavy devices (ANDO vs wavemeter on GPIB) to avoid bus pile-up.  
   - Worker slots must **finish quickly** or use **bounded timeouts** on VISA/serial so a dead device does not hang the worker thread for minutes.

3. **Results back to UI only via Qt signals**  
   - Workers emit `connection_state_changed`, `readings_ready`, etc.; `MainViewModel` updates `self._*_connected` and emits aggregated `connection_state_changed` for the footer.  
   - **Never** block the main thread waiting for a worker (`wait()` on thread from GUI) except where Qt already uses `BlockingQueuedConnection` in a controlled, short path — prefer **async** emit + UI update.

4. **Whenever status is lost → show Disconnected**  
   - **User clicks Disconnect** → worker `do_disconnect` → emit `{ "<Instrument>": False }` → footer **Disconnected** immediately.  
   - **Poll / read / ping fails** (timeout, exception, empty `*IDN?`, invalid session) → worker must **close** the session if needed, set internal `connected` / handle to disconnected state, and emit **`False`** for that instrument so the footer matches reality.  
   - **No “ghost Connected”**: if `is_connected()` is false, the ViewModel flag and footer must both show **Disconnected**.

5. **Interaction with long-running tests**  
   - Reuse existing **`SequenceInstrumentBridge.pause_for_liv` / `pause_for_temperature_stability`**: during LIV or Temperature Stability, pause **poll timers** that would contend with the test thread, then **`resume_after_liv`** — so background checks do not break tests **and** tests do not starve health checks longer than necessary.

6. **Optional future: unified health service**  
   - If timers proliferate, consolidate into one “health tick” per second that **schedules** one lightweight check per instrument round-robin — still only **signals** into workers, never blocking GUI.

---

## 4. Implementation phases (recommended order)

### Phase A — Inventory & tests (1–2 sessions)

- [ ] Walk through each `instrument_commands/*.md` and list the **minimum** query for “alive + identity”.  
- [ ] Add a short **“Connect verification”** subsection to each markdown (1 paragraph + example command).  
- [ ] Manual test matrix: Connect → read one value → Disconnect → confirm footer **Disconnected** for each instrument.

### Phase B — Arroyo (high impact)

- [ ] In `ArroyoConnection.connect()`, after serial open, call **`identify()` / `*IDN?`** (with existing `\r` framing) before `read_temp()`, or in addition to it.  
- [ ] On failure: `disconnect()`, `connected = False`, return `False`.  
- [ ] Update `Arroyo_Commands.md` with the exact sequence.

### Phase C — Wavemeter (GPIB + optional IDN)

- [ ] In `WavemeterConnection.connect()` (after `WavemeterInstrument` construction):  
  - [ ] Try `*IDN?` with short timeout; if OK, store string.  
  - [ ] Else run **fallback** from `Wavemeter_Commands.md` (`K0`, range `W0`/`W1`, `E`, read).  
- [ ] Do **not** fail connect on optional prime alone; fail only if **both** IDN (if tried) and fallback fail.  
- [ ] Document behavior in `Wavemeter_Commands.md`.

### Phase D — Actuator

- [ ] Read `Actuator_Commands.md` and pick **one** handshake command.  
- [ ] Implement in `ActuatorConnection.connect()` after serial open.  
- [ ] On timeout → close port, `connected = False`, return `False`.

### Phase E — PRM / Gentec / Thorlabs / ANDO (polish)

- [ ] **ANDO / Thorlabs:** already IDN-based; add **cached `last_idn`** property for logging only.  
- [ ] **Gentec:** log first line of `*VER` on success.  
- [ ] **PRM:** after connect, assert `serial_number` still in `GetDeviceList()` post-`EnableDevice()` (defensive).

### Phase F — Disconnect consistency pass

- [ ] Grep all `disconnect()` and worker `do_disconnect` for `emit({... False})`.  
- [ ] Ensure **no** code path leaves `is_connected() == True` after `disconnect()`.  
- [ ] Run “Disconnect All” and verify footer row for each instrument turns **Disconnected** (red/off) within one UI tick.

### Phase G — Background monitoring & GUI responsiveness (non-blocking)

- [ ] Audit **every** code path that touches hardware from `view/main_window.py` / recipe windows — move any remaining synchronous `connect`/`query` to worker emits.  
- [ ] Document per-instrument **max poll duration** (VISA timeout, serial read timeout) so no single poll blocks the worker thread beyond e.g. 2–5 s.  
- [ ] Verify each worker’s **failure** path (ping, read wavelength, Ando `identify`, etc.) emits **`connection_state_changed` → False** and clears handles.  
- [ ] Verify **stagger** between ANDO ping and wavemeter read when both use GPIB (timer offsets or shared lock only around `open`, not around every poll).  
- [ ] Manual test: run UI, drag/resize windows, open menus — no freeze while instruments are polled; unplug device — footer goes **Disconnected** within one or two poll cycles.

---

## 5. Acceptance criteria

1. Connecting to a **wrong** VISA resource (wrong `*IDN?`) → **connect fails**, footer **Disconnected**, user sees reason in log where available.  
2. Connecting to correct hardware → log line includes **IDN substring** (or Gentec `*VER` / wavemeter fallback success).  
3. **Disconnect** (button or worker) → within 500 ms footer shows **Disconnected** for that instrument; no stale “Connected”.  
4. No regression: LIV / Spectrum / Temperature Stability still use the same worker instances after connect.  
5. **GUI never blocks** on instrument I/O: main thread stays responsive during continuous background checks; unplug or instrument error updates footer to **Disconnected** without requiring a manual refresh.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Wavemeter has no `*IDN?` | Use documented `E`/read fallback only. |
| `*IDN?` slows startup | Run IDN with existing timeouts; cache result for session. |
| Double-connect from UI | Workers already replace session; optional debounce in viewmodel. |
| GPIB contention | Keep shared `pyvisa_open_lock` around **open** only (already in `visa_safe.py`). |
| Health poll hogs worker | Stagger timers; shorten timeouts; round-robin optional “Phase G” service. |
| GUI freeze from main thread | Code review: no `connect`/`query` on UI thread; only signals to workers. |

---

## 7. File checklist (implementation touch list)

- `instruments/arroyo.py` — add `*IDN?` on connect.  
- `instruments/wavemeter.py` — IDN try + documented fallback in `WavemeterConnection.connect()` or `WavemeterInstrument`.  
- `instruments/actuator.py` — response-based connect verify.  
- `instruments/prm.py` — optional post-enable sanity check.  
- `workers/workers.py` — verify every `do_disconnect` emits `False`.  
- `viewmodel/main_viewmodel.py` — ensure all `_on_*_connection_changed` update flags + `_emit_connection_state_if_changed()`; audit **`QTimer`** poll intervals and **pause/resume** with test sequence (`SequenceInstrumentBridge`).  
- `view/main_window.py` — ensure footer reads only from ViewModel state (no blocking calls in paint/resize).  
- `instrument_commands/*.md` — document verify sequence per device.

---

*End of plan. Implement phases **B→F** first, then **G** (background monitoring / GUI) in parallel with any connect-IDN hardening. If a specific instrument blocks testing, fix that instrument before expanding poll frequency.*
