# Stability Overview

## Explanation in English

The **Stability Overview** flow runs a laser stability test. It ramps the laser current to the value set in the RCP and checks whether the laser is on. If **False**, it notifies the user and skips the test. If **True**, it sets the TEC to the MinTemp from the RCP and waits until the read temperature matches the set temperature or a timeout is reached. If there is a **timeout**, it notifies the user and skips the test. If **no timeout**, it waits 2 seconds, sets Ando settings from the Spectrum RCP, and starts a single Ando sweep. It then loops: get Ando WL and LVL data, and check if the sweep has stopped. If **No**, it loops back to get WL/LVL again. If **Yes**, it grabs the peak WL from the WL data, sets the Ando center wavelength to that peak, sets the Ando span and sampling from the Stability RCP, runs the stability test, runs the pass/fail algorithm, saves data to the DB, and turns off the laser.

---

## Stability Overview flowchart (ASCII)

```text
+--------------------------------------+
| Ramp Laser Current to Current Set    |
| in RCP                               |
+------------------+-------------------+
                   |
                   v
          +---------------------+
          | Check Laser is ON   |
          +---------+-----------+
                    |
          +---------+---------+
          |                   |
        False               True
          |                   |
          v                   v
+----------------------+   +---------------------------+
| Notify user of error |   | Set TEC to MinTemp set    |
| and skip the test    |   | in RCP                    |
+----------------------+   +------------+--------------+
                                         |
                                         v
                       +--------------------------------------+
                       | Wait until read temp matches set     |
                       | temp OR timeout is reached           |
                       +------------------+-------------------+
                                          |
                                          v
                               +---------------------+
                               | Check if timeout    |
                               +----------+----------+
                                          |
                               +----------+----------+
                               |                     |
                             True                  False
                               |                     |
                               v                     v
                +--------------------------+   +------------------+
                | Notify user of error     |   | Wait 2 seconds   |
                | and skip the test        |   +--------+---------+
                +--------------------------+            |
                                                       v
                                +------------------------------------+
                                | Set Ando settings based on         |
                                | Spectrum RCP                       |
                                +------------------+-----------------+
                                                   |
                                                   v
                                +------------------------------------+
                                | Start a single sweep from Ando     |
                                +------------------+-----------------+
                                                   |
                                                   v
                                +------------------------------------+
                                | Get ando WL and LVL data           |
                                +------------------+-----------------+
                                                   |
                                                   v
                                +--------------------------+
                                | Check if sweep stopped   |
                                +----------+---------------+
                                           |
                                 +---------+---------+
                                 |                   |
                                No                  Yes
                                 |                   |
                                 v                   v
                  (loop back to Get WL/LVL)   +---------------------------+
                                              | Grab peak WL from WL Data |
                                              +-------------+-------------+
                                                            |
                                                            v
                                              +-----------------------------+
                                              | Set ando center WL to peak  |
                                              +-------------+---------------+
                                                            |
                                                            v
                                              +-----------------------------+
                                              | Set ando span to value set  |
                                              | in Stability RCP            |
                                              +-------------+---------------+
                                                            |
                                                            v
                                              +-----------------------------+
                                              | Set ando sampling to value  |
                                              | specified in Stability RCP  |
                                              +-------------+---------------+
                                                            |
                                                            v
                                              +---------------------+
                                              | Run Stability test  |
                                              +----------+----------+
                                                         |
                                                         v
                                              +--------------------------+
                                              | Run Pass/Fail algorithm  |
                                              +----------+---------------+
                                                         |
                                                         v
                                              +----------------------+
                                              | Save data to DB      |
                                              +----------+-----------+
                                                         |
                                                         v
                                              +----------------------+
                                              | Turn off laser       |
                                              +----------------------+
```

---

## Summary (high-level)

**Stability Overview** = Ramp laser current to RCP → **Laser ON?** (False → notify and skip; True → Set TEC to MinTemp from RCP → wait for temp or timeout → **Timeout?** (True → notify and skip; False → wait 2 s → set Ando from Spectrum RCP → start single sweep → **loop**: get Ando WL/LVL → **Sweep stopped?** (No → loop back; Yes → grab peak WL → set Ando center/span/sampling from Stability RCP → run stability test → pass/fail → save to DB → turn off laser → end))).

---

# Part B — Temperature stability test (detailed pass/fail)

This section describes the **measurement and decision logic** inside the stability test (FWHM recovery, retries, consecutive exceeds, optional limits). It complements the high-level **Stability Overview** flow above.

---

## B.1 Test setup (from recipe)

The recipe supplies:

| Concept | Role |
|--------|------|
| **Initial temperature** | Start/end anchor for the TEC sweep |
| **Maximum temperature** | Other end of the sweep range |
| **Temperature increment** | Step size between setpoints |
| **FWHM recovery threshold** | e.g. 0.3 nm — “good enough” FWHM for a temperature to count as *within limit* |
| **FWHM lower / upper limit** | Optional hard limits (when enabled) |
| **SMSR lower / upper limit** | Optional hard limits (when enabled) |
| **Delta WL per °C limits** | Optional — checked **at end of test** (when enabled) |

The test runs **two sweeps**:

1. **Cold → Hot:** from initial temperature to maximum temperature  
2. **Hot → Cold:** from maximum temperature back to initial temperature  

---

## B.2 What happens at each temperature

At **every** temperature setpoint:

1. Measure **FWHM**, **SMSR**, and **peak wavelength**.
2. Compare **FWHM** to the **recovery threshold**.

### FWHM ≤ threshold (within recovery limit)

- That temperature is treated as **within limit** for the consecutive-exceed logic.
- The **consecutive-above** counter is **reset to zero**.
- Move to the **next** temperature.

### FWHM > threshold (above recovery limit)

- **Stay** at the same temperature.
- Take up to **5** additional measurements.
- If **any** of those measurements has FWHM **≤ threshold**: use that measurement; treat the point as **within limit** (same as above — reset consecutive exceed, next temperature).
- If **all 5** measurements remain **> threshold**: use the **last** measurement and treat this setpoint as an **exceed**.

---

## B.3 Consecutive exceed rule

- **At most 2 consecutive** “exceed” temperatures are allowed.
- **1 or 2** consecutive exceeds → test **continues**.
- **3** consecutive exceeds → test **fails immediately** and **stops**.

---

## B.4 Other criteria (when enabled)

### FWHM lower / upper (LL / UL)

If **FWHM** is **below** the lower limit or **above** the upper limit → **fail immediately** and **stop**.

### SMSR lower / upper (LL / UL)

If **SMSR** is **below** the lower limit or **above** the upper limit → **fail immediately** and **stop**.

### Delta WL per °C

Evaluated **at the end** of the test (after both sweeps). If the derived slope is **outside** the recipe limits → **fail**.

---

## B.5 Pass condition

The test **passes** only if:

- There are **no more than 2 consecutive exceed** temperatures anywhere in the run (per B.3).
- All **FWHM / SMSR** window limits (when enabled) are satisfied at every measured point.
- **Delta WL per °C** (when enabled) is within limits at the final evaluation.

The run must complete **all temperatures in both sweeps** before final pass/fail, except when an **immediate** failure (B.4 or B.3) stops the test early.

---

## B.6 When the test fails

The test **fails** (and typically **stops** so remaining setpoints are **not** measured) if **any** of these occur:

| Condition | When |
|-----------|------|
| **3+ consecutive exceeds** | FWHM above recovery threshold at 3 consecutive temperatures (after the retry logic in B.2). |
| **FWHM out of band** | FWHM outside recipe LL/UL when those limits are enabled. |
| **SMSR out of band** | SMSR outside recipe LL/UL when those limits are enabled. |
| **Delta WL per °C** | Outside recipe limits when enabled (checked at end). |

---

## B.7 How everything fits together (short)

- **Recovery threshold + retries:** If FWHM is bad, you get up to **5** tries at the **same** temperature; one good reading clears the point.  
- **Consecutive exceed:** You may tolerate **1–2** bad temperatures in a row; the **3rd** consecutive bad point **fails** the test.  
- **Hard FWHM/SMSR bands** (when on): any violation at a point **fails** immediately.  
- **Delta WL/°C** (when on): checked **after** the sweeps finish.  
- **Stop on fail:** On immediate failure, the test does **not** continue through remaining temperatures.

---

## B.8 Flow sketch (logic only)

```text
For each sweep (Cold→Hot, then Hot→Cold):
  For each temperature setpoint:
      Measure FWHM, SMSR, peak WL
      If enabled limits: FWHM or SMSR outside LL/UL → FAIL STOP
      If FWHM ≤ recovery threshold → OK, reset consecutive exceed, next T
      Else (FWHM > threshold):
          Retry up to 5 times at same T
          If any retry OK → OK, reset consecutive exceed, next T
          Else → count as EXCEED for this T
              If 3 consecutive EXCEEDs → FAIL STOP
      Next setpoint
After all setpoints (if still running):
      If delta WL/°C enabled and out of range → FAIL
      Else PASS
```

---

## See also

- **`stability_test.md`** — additional ASCII flowcharts for the detailed logic (per-temperature, retries, consecutive exceed, delta WL).

---

*Keep this file in sync when the implementation or product definition changes.*
