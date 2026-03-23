# Butterfly Tester — GUI Overview

This document explains how the **Butterfly Tester** GUI works from startup to test run.

---

## 1. Startup (`main.py`)

```
main()
  → QApplication (Fusion style + dark palette)
  → MainViewModel()           ← holds instrument state and workers
  → app.aboutToQuit → viewmodel.shutdown
  → MainWindow(viewmodel)      ← the main UI
  → window.showMaximized()
  → app.exec_()
```

- **MainViewModel**: owns all instrument **workers** (threads), connection state, and timers. It does **not** create widgets.
- **MainWindow**: builds all tabs and widgets, and **binds** to the viewmodel via Qt signals/slots.
- Workers start with the viewmodel; instruments stay **disconnected** until the user connects on the **Connection** tab.

---

## 2. Main window structure

The main window is a **tabbed** interface. Tabs are created in `MainWindow.__init__`:

| Tab | Purpose |
|-----|--------|
| **Main** | Laser/TEC readbacks, Status Log, **Start** (Start New, New Recipe, Run, Stop, Align), Part Details, Pass/Fail |
| **Manual Control** | Arroyo (current, temp, laser/TEC buttons), Actuator A/B, PRM, Ando, Wavemeter — direct control of instruments |
| **Recipe** | Load recipe file (browse), shows loaded recipe path |
| **LIV** | LIV graph (power/voltage/PD) — updated when LIV runs |
| **PER** | PER graph |
| **Spectrum** | Spectrum graph |
| **Temperature Stability** | Stability graph |
| **Summary** | Summary values |
| **Result** | Placeholder |
| **Connection** | **Scan All**, **Connect All**, Save; per-instrument scan/connect/disconnect (Arroyo, Actuator, Ando, Wavemeter, PRM, Gentec, Thorlabs) |

- **Footer**: connection status (green/gray circles per instrument), **Disconnect All**, **Reconnect**.
- **Menu**: File (Exit), Help (About).

All widgets are **view only**; they call viewmodel methods or react to viewmodel signals (e.g. `connection_state_changed`, `arroyo_readings_updated`).

---

## 3. How instruments connect (Connection tab)

1. User runs **Scan All** → discovers COM ports, GPIB, VISA, PRM serials; results go to status log and dropdowns.
2. User selects addresses in the dropdowns and clicks **Connect All** (or per-instrument Connect).
3. Each instrument has a **worker** (e.g. `ArroyoWorker`) running in a **QThread**. Connect is done by emitting a signal to that worker; the worker connects on its thread and emits back `connection_state_changed` or `connection_result`.
4. **MainViewModel** updates internal flags (`_arroyo_connected`, etc.) and emits **connection_state_changed(state)**.
5. **MainWindow** slot `_on_connection_state_changed` updates the footer (circles) and enables/disables controls.

So: **Connection tab** → viewmodel connect methods → workers → viewmodel state → **MainWindow** updates UI.

---

## 4. Manual Control tab

- **Arroyo**: Set current, set temp, max current/temp, **Laser ON/OFF**, **TEC ON/OFF**. Values are sent to the Arroyo worker via viewmodel (e.g. `viewmodel.set_arroyo_current(value)`).
- **Actuator**: Move A/B, Home A/B, Home Both — same idea via viewmodel.
- **PRM**: Speed, Move, Home, quick angles, Stop — viewmodel talks to PRM worker/connection.
- **Ando**: Center WL, span, ref level, sweep mode, etc. — viewmodel → Ando worker.
- **Wavemeter**: Apply range — viewmodel.

Readbacks (e.g. laser current, TEC temp) come from **viewmodel signals** (e.g. `arroyo_readings_updated`) and are shown in **Main** tab (Laser Details, TEC Details) and in Manual Control where applicable.

---

## 5. Recipe and “Start New”

- **Recipe** tab: user browses and loads a **recipe file** (e.g. JSON). Loaded data is stored as `_current_recipe_data` / `_current_recipe_path` and the Recipe tab shows the path.
- **Start New** button opens **TestInformationDialog**: operator name, serial, part number, recipe path, wavelength, comments. On **Start Test** (OK), the dialog’s recipe path is used to load the recipe again and apply it (e.g. wavemeter range from wavelength). So “Start New” = set part info + (re)load recipe.
- **New Recipe** button opens **RecipeWindow** (separate window, often on second monitor) for editing recipes.

---

## 6. Run (test sequence)

When the user clicks **Run**:

1. **MainWindow._on_run_clicked** checks that a recipe is loaded and that the recipe has a **TEST_SEQUENCE** (e.g. `["LIV", "PER"]`).
2. It creates **TestSequenceExecutor** and **TestSequenceThread**:
   - `TestSequenceExecutor` is given the test sequence, recipe, and **SequenceInstrumentBridge(viewmodel)** so tests use the **same** instrument instances the GUI connected (Arroyo, Gentec, etc.).
   - `TestSequenceThread` runs the executor in a **worker thread** so the UI stays responsive.
3. Main window connects executor signals to its slots:
   - **log_message** → status log
   - **sequence_completed** / **sequence_stopped** → update status (Done/Stopped) and pass/fail
   - **liv_test_result** → `_on_liv_result` (update LIV tab and LIV window)
   - **liv_process_window_requested** → open **LIV Process** window (after laser is on)
   - **liv_pre_start_prompt_requested** → show a message box; when user clicks OK, the executor is **acknowledged** so the LIV thread can continue (e.g. “Connect fiber to Thorlabs meter”).
   - **alignment_window_requested** → open **Alignment** window (same as Align button) for LIV alignment step.
   - Similarly for PER, Spectrum, Stability results and test windows if present.

4. **TestSequenceThread.start()** is called. The thread runs the executor’s **run** (or `run_blocking_in_worker_thread` in a full implementation), which runs each test in sequence (e.g. LIV, then PER). For **LIV**, the executor uses **SequenceInstrumentBridge** to get Arroyo, Gentec, Thorlabs, Actuator, Ando and passes them into the LIV process (`liv_core.LIVMain`). During LIV, the bridge **pauses** viewmodel polling timers so the LIV thread has exclusive use of serial/VISA.

**Stop** button sets a flag so the executor stops after the current step.

---

## 7. LIV flow in the GUI

1. Executor runs the **LIV** test step and calls `LIVMain.run(params, executor=self)`.
2. **LIV** turns on the laser, stabilizes temperature, then emits **liv_process_window_requested(params)** so the GUI opens the **LIV Process** window (recipe params on left, live graph on right, often on second monitor).
3. Main window’s **liv_plot_clear** / **liv_plot_update** are connected to the LIV window so the plot updates live during the sweep (each **liv_plot_update** carries current, Gentec power, Arroyo voltage `LAS:LDV`, and monitor diode `LAS:MDI` raw).
4. When LIV needs user input (e.g. “Connect fiber to Thorlabs meter”), it uses the executor’s **liv_pre_start_prompt_requested**; the main window shows a **QMessageBox**; when the user clicks OK, the main window calls the executor’s **ack** so the LIV thread’s `_wait_prompt` returns.
5. When LIV needs alignment, it emits **alignment_window_requested**; the main window opens the **Alignment** window. User aligns and presses **OK** (or Cancel). The Alignment window emits **alignment_confirmed** (or **alignment_cancelled**), which is wired to the executor’s LIV object so **continue_after_alignment()** or **alignment_cancelled()** is called and the LIV thread continues or aborts.
6. When LIV finishes, the executor emits **liv_test_result(result)**. Main window’s `_on_liv_result` updates the LIV tab and the LIV Process window with final results (P@Ir, I@Pr, Ith, pass/fail, etc.).

So: **LIV logic** lives in **liv_core**; **GUI** only opens windows, shows prompts, and forwards plot/result updates via the executor’s signals.

---

## 8. Alignment window

- Opened from **Align** button or during LIV (**alignment_window_requested**).
- **Align** tab: wavelength, laser settings, Ando details, **Laser On** / **Ando On**, power meters, **OK** / **Cancel**.
- **ANDO SETTINGS** tab: Ando-specific settings.
- Laser readbacks in the alignment window come from the **same** viewmodel (main window is bound to Arroyo); alignment window connects to **gentec_reading_updated** / **thorlabs_reading_updated** to show power.
- **OK** emits **alignment_confirmed** → LIV continues. **Cancel** emits **alignment_cancelled** → LIV aborts.

---

## 9. LIV Process window (`LivTestSequenceWindow`)

- Shown when the executor emits **liv_process_window_requested** (after laser is on).
- **Left**: LIV recipe parameters (min/max current, temp, etc.) and, after run, Phase‑4 results (calibration, P@Ir, I@Pr, Ith, slope efficiency, pass/fail).
- **Right**: Live **pyqtgraph** plot (power, voltage, PD) and overlays (threshold, rated I/P, slope-fit segment).
- Receives **liv_plot_clear**, **liv_plot_update** (four floats: I, P, V, PD) from the executor during the sweep, and final result in **liv_test_result**.

---

## 10. Data flow summary

```
User (Connection tab)     → ViewModel (connect/disconnect) → Workers (threads) → Hardware
User (Manual Control)     → ViewModel (set current, etc.)  → Workers           → Hardware
Workers                   → ViewModel (readings, state)     → Signals           → MainWindow (update labels, footer, graphs)

User (Run)                → MainWindow creates Executor + Thread
                          → Executor uses Bridge(viewmodel) to get instruments
                          → Executor runs LIV (liv_core) in thread
LIV                       → Emits liv_process_window_requested → MainWindow opens LIV window
LIV                       → Emits liv_plot_update etc.        → MainWindow forwards to LIV window
LIV                       → Emits liv_pre_start_prompt       → MainWindow shows message box → acks executor
LIV                       → Emits alignment_window_requested → MainWindow opens Alignment → user OK/Cancel → LIV continues/aborts
Executor                  → Emits liv_test_result            → MainWindow updates LIV tab + LIV window
Executor                  → Emits sequence_completed         → MainWindow sets status Done, pass/fail
```

---

## 11. Important files

| File | Role |
|------|------|
| **main.py** | Entry point; creates app, viewmodel, main window; starts workers on timer. |
| **viewmodel/main_viewmodel.py** | Instrument workers, connection state, timers, signals; no UI. |
| **view/main_window.py** | All tabs, footer, menu; connects to viewmodel and executor signals. |
| **viewmodel/sequence_instrument_bridge.py** | Gives executor access to viewmodel’s instruments (get_arroyo, get_instrument); pause/resume polling for LIV. |
| **operations/test_sequence_executor.py** | Runs TEST_SEQUENCE (e.g. LIV, PER); uses bridge to get instruments; emits liv_* and result signals. |
| **operations/LIV/liv_core.py** | LIV logic (sweep, Thorlabs, alignment prompts, pass/fail). |
| **view/liv_test_window.py** | LIV Process window (params + live graph + results). |
| **view/alignment_window.py** | Alignment window (OK/Cancel for LIV). |

This is how the GUI is **designed** to work. If your current `test_sequence_executor.py` is a shorter version without `liv_process_window_requested` / `liv_pre_start_prompt_requested` / alignment, the main window’s connections for those signals will fail until the full executor (with `_run_liv`, bridge, and those signals) is restored.
