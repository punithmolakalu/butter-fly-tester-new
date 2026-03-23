# LIV Test Algorithm

This flowchart describes the **LIV (Light–Current–Voltage) test**: how the system sweeps laser current, collects power/voltage/PD data at each step, and returns the arrays and final power.

---

## Explanation in English

The LIV test measures how the laser behaves as current is increased: **Light** (optical power), **Current** (drive current), and **Voltage** (laser voltage). The algorithm does this by stepping current from a minimum to a maximum, taking multiple power readings at each step, and recording voltage and photodiode (PD) values.

---

### 1. Initialization

- **Clear the LIV plot** – Start with a clean plot (remove any previous LIV curve).
- **Calculate current range from RCP** – Use the RCP (e.g. Remote Control Panel) settings: minimum current, maximum current, and current step size.
- **Compute NumIncrements** –  
  `NumIncrements = (MaxCurrent - MinCurrent) / Increment`  
  This is how many current steps the test will run (and how many times the main loop repeats).

---

### 2. Main loop: for each current step

For every current level from min to max:

- **Add increment to set current** – Set the next current value (start at min, then min+increment, then +increment, etc.).
- **Set the laser current** – Send this current to the laser.
- **Wait for time delay from RCP** – Wait for the laser and measurement to settle before reading.

---

### 3. Inner loop: 10 power readings per current step

At each current step, the algorithm takes **10 power samples** and then averages them:

- **Get Gentec powermeter power** – Read one power value from the Gentec power meter.
- **Multiply by 1000** – Convert to the desired unit (e.g. mW).
- **Append to array** – Store this reading in a temporary array.
- **I == 10?**
  - **No** → Go back to **Get Gentec powermeter power** and take another reading (until 10 are collected).
  - **Yes** → You have 10 readings; leave the inner loop.

---

### 4. After 10 power readings: process and store

- **Get mean of power array and plot it** – Average the 10 power values and add that point to the LIV power plot.
- **Get laser voltage and plot it** – Read laser voltage and plot it for this current step.
- **Get PD and plot it** – Read the photodiode signal and plot it.
- **Append to main arrays** – Save this step’s results: append mean power to the power array, voltage to the voltage array, and PD to the PD array (these are the main outputs of the test).

---

### 5. Main loop check: more current steps?

- **I == NumIncrements?**
  - **No** → Go back to **Add increment to set current** and run the next current step (main loop continues).
  - **Yes** → All current steps are done; leave the main loop.

---

### 6. Finalization

- **Get the final power from power array** – Take the last power value (typically at max current) from the power array.
- **Return** – Return to the caller:
  - **power array** – Power at each current step (e.g. in mW).
  - **PD array** – Photodiode reading at each step.
  - **voltage array** – Laser voltage at each step.
  - **final power** – The last power value (often used for calibration or pass/fail).

The flowchart then reaches **END**.

---

### Summary

- **Outer loop**: current steps (NumIncrements times).  
- **Inner loop**: 10 power readings per current step (Gentec, ×1000, append, then I==10?).  
- At each step: mean power, voltage, and PD are computed/plotted and appended to the main arrays.  
- When all steps are done, final power is taken from the power array and all arrays plus final power are returned.

---

## Step-by-step process (in order)

Follow this sequence from start to finish:

| Step | Action | What it does |
|------|--------|--------------|
| **1** | START | Begin the LIV test. |
| **2** | Clear the LIV plot | Erase any previous LIV curve so you start with a blank plot. |
| **3** | Calculate current range from RCP | Read MinCurrent, MaxCurrent, and Increment from the RCP (Remote Control Panel). |
| **4** | Compute NumIncrements | Use formula: **(MaxCurrent − MinCurrent) ÷ Increment**. This is the number of current steps (e.g. 100 steps). |
| **5** | Add increment to set current | Set the *next* current value. First time: use MinCurrent. Then: MinCurrent + Increment, then +Increment again, and so on. |
| **6** | Set the laser current | Send that current value to the laser so it runs at this level. |
| **7** | Wait for time delay from RCP | Pause for the settling time defined in RCP (so laser and meter are stable). |
| **8** | Get Gentec powermeter power | Read one power value from the Gentec power meter. |
| **9** | Multiply by 1000 | Convert the reading (e.g. to milliwatts, mW). |
| **10** | Append to array | Store this value in a temporary array for this current step. |
| **11** | Check: I == 10? | Have you collected 10 power readings at this current step? |
| **11a** | If **No** | Go back to **Step 8** (Get Gentec powermeter power) and repeat until you have 10 readings. |
| **11b** | If **Yes** | Continue to Step 12. |
| **12** | Get mean of power array and plot it | Average the 10 power values and plot this point on the LIV power curve. |
| **13** | Get laser voltage and plot it | Read the laser voltage at this current and plot it. |
| **14** | Get PD and plot it | Read the photodiode (PD) value and plot it. |
| **15** | Append to main arrays | Add this step’s results to the main lists: append mean power to power array, voltage to voltage array, PD to PD array. |
| **16** | Check: I == NumIncrements? | Have you completed all current steps (from min to max)? |
| **16a** | If **No** | Go back to **Step 5** (Add increment to set current) and run the next current step. |
| **16b** | If **Yes** | All steps are done; continue to Step 17. |
| **17** | Get the final power from power array | Take the last value in the power array (usually at maximum current). |
| **18** | Return power array, PD array, voltage array, and final power | Send these four outputs back to the caller. |
| **19** | END | LIV test is finished. |

**In short:**  
- Steps **1–4**: Setup (clear plot, get range, compute number of steps).  
- Steps **5–7**: Set one current level and wait.  
- Steps **8–11**: Take 10 power readings at that current (loop until I==10).  
- Steps **12–15**: Average power, read voltage and PD, plot and append to main arrays.  
- Step **16**: If more current steps remain, go back to Step 5; otherwise continue.  
- Steps **17–19**: Get final power, return all arrays and final power, then END.

---

## Flowchart

```text
                               +-------+
                               | START |
                               +-------+
                                   |
                                   v
                    +-----------------------------+
                    | Clear the LIV plot           |
                    +-------------+---------------+
                                  |
                                  v
                    +-----------------------------+
                    | Calculate current range:    |
                    | (MaxCurrent - MinCurrent)   |
                    | from RCP                    |
                    +-------------+---------------+
                                  |
                                  v
                    +-----------------------------+
                    | NumIncrements =             |
                    | (Max - Min) / Increment     |
                    +-------------+---------------+
                                  |
                                  v
              +-----------------------------------------------+
         +--->| Add increment to set current                   |
         |    | (start at min current)                         |
         |    +-------------+----------------------------------+
                            |
                            v
              +-----------------------------------------------+
              | Set the laser current                          |
              +-------------+----------------------------------+
                            |
                            v
              +-----------------------------------------------+
              | Wait for time delay from RCP                   |
              +-------------+----------------------------------+
                            |
                            v
              +-----------------------------------------------+
         +--->| Get Gentec powermeter power                    |
         |    +-------------+----------------------------------+
         |                  |
         |                  v
         |    +-----------------------------------------------+
         |    | Multiply by 1000                               |
         |    +-------------+----------------------------------+
         |                  |
         |                  v
         |    +-----------------------------------------------+
         |    | Append to array                                |
         |    +-------------+----------------------------------+
         |                  |
         |                  v
         |    +-----------------------------------------------+
         |    | I == 10 ?                                      |
         |    +------------------+-----------------------------+
         |                       |
         |          No           |           Yes
         |           \           |            |
         +------------+          |            v
         \                                    +-----------------------------+
         \                                    | Get mean of power array      |
         \                                    | and plot it                 |
         \                                    +-------------+----------------+
         \                                                    |
         \                                                    v
         \                                    +-----------------------------+
         \                                    | Get laser voltage and plot it|
         \                                    +-------------+----------------+
         \                                                    |
         \                                                    v
         \                                    +-----------------------------+
         \                                    | Get PD and plot it           |
         \                                    +-------------+----------------+
         \                                                    |
         \                                                    v
         \                                    +-----------------------------+
         \                                    | Append PD to PD array        |
         \                                    | Append voltage to voltage   |
         \                                    | array                        |
         \                                    | Append mean power to        |
         \                                    | power array                  |
         \                                    +-------------+----------------+
         \                                                    |
         \                                                    v
         \                                    +-----------------------------+
         \                                    | I == NumIncrements ?        |
         \                                    +-------+---------------------+
         \                                             |
         \                                        No   |   Yes
         \                                         \   |    |
         +---------------------------------------------+    v
         ^                                             |    +-----------------------------+
         |                                             |    | Get final power from        |
         |                                             |    | power array                 |
         |                                             |    +-------------+---------------+
         |                                             |                  |
         |                                             |                  v
                                                                          +-----------------------------+
                                                                          | Return power array,         |
                                                                          | PD array, voltage array,    |
                                                                          | and final power            |
                                                                          +-----------------------------+
                                                                                          |
                                                                                          v
                                                                          +-----------------------------+
                                                                          | END                          |
                                                                          +-----------------------------+
```
