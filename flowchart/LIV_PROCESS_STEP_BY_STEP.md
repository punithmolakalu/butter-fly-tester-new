# LIV Process — Step-by-Step (Clear)

This document explains the **LIV process** in order, one step at a time.  
**LIV** = **L**ight (power), **I** (current), **V** (voltage).

---

## Before the process starts (test sequence)

1. User starts the test sequence and the recipe includes **LIV**.
2. A **popup** appears: *"Connect fiber to power meter. Click OK to open LIV window and start."*
3. User clicks **OK**.
4. The **LIV window** opens on the other monitor: **left** = recipe (RCP) values, **right** = live graph.
5. The LIV process **starts** (Phase 1 below).

---

## Phase 1 — Start and prepare laser

| Step | What happens | Instrument |
|------|----------------|------------|
| **1** | Process starts. Check: is the device **fiber coupled**? | — |
| **2a** | If **No** (not fiber coupled): Move **actuator A** in front of the beam. | Actuator |
| **2b** | Wait for actuator to reach position (timeout from recipe). | Actuator |
| **2c** | If **Yes** (fiber coupled): Emit message for user to connect fiber to power meter (no action yet). | — |
| **3** | **Turn on laser.** | Arroyo |
| **4a** | Check: is laser **ON**? | Arroyo |
| **4b** | If **No**: Show "Laser failed" prompt, home actuator (if used), turn laser off, set result FAILED, **EXIT**. | Arroyo, Actuator |
| **4c** | If **Yes**: Continue. | — |
| **5** | **Set temperature** to the value from recipe (e.g. 25 °C). | Arroyo |
| **6** | **Wait for temperature** to stabilize within ±0.5 °C (timeout from recipe). | Arroyo |

After Phase 1 the laser is on and at the correct temperature.

---

## Phase 2 — LIV test (sweep: current → power, voltage, PD)

| Step | What happens | Instrument |
|------|----------------|------------|
| **7** | **Clear** the LIV plot (ready for new curve). | — |
| **8** | Set **max current** and **min current** on the laser from recipe (if Arroyo supports it). Compute **number of steps** = (Max − Min) ÷ Increment + 1. | Arroyo |
| **9** | **For each current step** (from min to max): | |
| **9a** | Set **current** = min + (step × increment). Send this current to the laser. | Arroyo |
| **9b** | **Wait** for the delay from recipe (e.g. 100 ms). | — |
| **10** | At this current, take **10 power readings**: | |
| **10a** | Read power from **Gentec** power meter. | Gentec |
| **10b** | Convert to mW (×1000) and add to a temporary list. | — |
| **10c** | Repeat until you have **10 readings**, then take the **average** = mean power for this step. | Gentec |
| **11** | Read **one** laser **voltage** and **one** **PD** (photodiode) value at this current. | Arroyo |
| **12** | **Store** this step: append (mean power, voltage, PD, current) to the main arrays. **Plot** this point on the live graph (Power, Voltage, PD vs Current). | — |
| **13** | If more steps remain → go back to **Step 9a** (next current). If all steps are done → **final power** = last power value. Phase 2 ends. | — |

After Phase 2 you have: **current array**, **power array**, **voltage array**, **PD array**, and **final power**.

---

## Phase 3 — After sweep: fiber, alignment, Thorlabs

| Step | What happens | Instrument |
|------|----------------|------------|
| **14** | Check again: is the device **fiber coupled**? | — |
| **15a** | If **No**: **Home** actuator A and wait for position. Then go to **Step 18** (Thorlabs). | Actuator |
| **15b** | If **Yes**: Continue with Steps 16–17 (alignment). | — |
| **16** | **Turn off laser** (so user can connect fiber safely). | Arroyo |
| **17** | Show **popup**: *"Connect fiber to power meter. Click OK to open alignment window."* | — |
| **18** | User clicks **OK**. Send to alignment window: **min current**, **max current**, **temperature** from recipe. **Open alignment window.** | — |
| **19** | **Turn laser on** again. **Turn Ando on** (OSA repeat sweep) so the user can align using the spectrum. | Arroyo, Ando |
| **20** | **Wait** until the user presses **OK** in the alignment window (user aligns fiber, then confirms). No Thorlabs readings yet. | — |
| **21a** | If user presses **Cancel**: Turn Ando off, turn laser off, set result FAILED, **EXIT**. | Ando, Arroyo |
| **21b** | If user presses **OK**: **Turn Ando off**. Continue. | Ando |
| **22** | Take **10 power readings** from the **Thorlabs** power meter (one by one, small delay between). | Thorlabs |
| **23** | **Average** the 10 Thorlabs readings. Convert to mW (×1000). Save as **Thorlabs average power**. | — |

After Phase 3 you have the **Thorlabs average power** (mW) for calibration.

---

## Phase 4 — Calibration and pass/fail

| Step | What happens | Instrument |
|------|----------------|------------|
| **24** | **Calibration factor** = (final power from LIV test) ÷ (Thorlabs average power). If Thorlabs average is 0, use factor = 1.0. | — |
| **25** | **Power at rated current**: From the power vs current curve, find the power at the recipe "rated current" (interpolation). | — |
| **26** | **Current at rated power**: From the curve, find the current needed to reach the recipe "rated power" (interpolation). | — |
| **27** | **Threshold current** and **slope efficiency**: Fit a line in the low-power region of the curve; threshold = where the line crosses zero power; slope = slope of the line. | — |
| **28** | **Pass/fail**: Compare the calculated values to the recipe limits (e.g. power at rated current min/max, current at rated power min/max, threshold min/max). If any limit is failed → result **FAILED** and add reason; else **PASSED**. | — |

After Phase 4 you have: calibration factor, power at rated current, current at rated power, threshold, slope efficiency, and **PASS** or **FAIL**.

---

## Phase 5 — Save and exit

| Step | What happens | Instrument |
|------|----------------|------------|
| **29** | **Save** all LIV data to the database (arrays, results, pass/fail). | — |
| **30** | **Turn laser off.** | Arroyo |
| **31** | Set state to **COMPLETED** (or FAILED/ABORTED if something went wrong earlier). Emit result to GUI. **EXIT.** | — |

---

## Summary in one line per phase

- **Phase 1:** Check fiber/actuator → laser on → set temperature → wait for stable temp.  
- **Phase 2:** Step current from min to max; at each step: 10× Gentec power (average), 1× Arroyo voltage, 1× Arroyo PD → store and plot.  
- **Phase 3:** Fiber path: laser off → prompt → alignment window (laser + Ando on) → user OK → Ando off → 10× Thorlabs power → average.  
- **Phase 4:** Calibration factor, power at rated current, current at rated power, threshold, slope → pass/fail vs recipe limits.  
- **Phase 5:** Save to DB → laser off → EXIT.

---

## Instruments used (quick reference)

| Instrument | Used in LIV for |
|------------|------------------|
| **Arroyo** | Temperature set/wait, current set/limits, voltage, PD, laser on/off. |
| **Gentec** | Power **only during** the LIV sweep (10 samples per current step). |
| **Thorlabs** | Power **only after** alignment (10 readings → average for calibration). |
| **Ando** | On during alignment window (repeat sweep); off when user clicks OK. |
| **Actuator** | Move to beam / home (when not fiber coupled). |
