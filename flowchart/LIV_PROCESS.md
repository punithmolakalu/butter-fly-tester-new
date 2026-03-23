# LIV Process (Complete)

This document merges the **LIV Algorithm** and the **LIV Test** into one process. The **LIV Test** flow is placed inside the **Conduct LIV test** block of the algorithm, so the full sequence from start to exit is in a single flowchart.

---

## What this process does

1. **LIV Algorithm** (overall): fiber check → turn on laser → set temperature → **run the LIV test** → check fiber again → Thorlabs calibration → calculations → pass/fail → save → turn laser off → EXIT.
2. **LIV Test** (inside “Conduct LIV test”): clear plot → step current from min to max → at each step take 10 power readings (Gentec) → mean power, voltage, PD → append to arrays → when all steps done, return power/PD/voltage arrays and final power.
3. **After LIV test**: the returned “final power” and arrays are used for Thorlabs calibration (average power, multiply by 1000, divide for calib factor) and for the rest of the algorithm (power at rated current, current at rated power, threshold current, pass/fail, save, laser off, EXIT).

So: **LIV Process** = LIV Algorithm with the **LIV Test** flow expanded inside the **Conduct LIV test** block.

---

## LIV process explained step by step (in English)

Below is the full LIV process in order, from start to exit. **LIV** = Light (optical power), **I** (current), **V** (voltage). The process runs a laser test, collects power/voltage/PD data, then calibrates with a Thorlabs power meter and decides pass/fail.

---

### Phase 1: Start and fiber alignment

**Step 1 – START**  
The process begins.

**Step 2 – Check if fiber coupled?**  
- **No** → Move actuator A in front of the beam, then wait for actuator A to be in position. (This aligns the fiber with the laser.)  
- **Yes** → Prompt the user to connect the fiber to the power meter.  
Both paths then merge and continue.

**Step 3 – Turn on laser**  
The laser is turned on.

**Step 4 – Check if laser is ON?**  
- **No** → Prompt the user that the laser could not turn on. User presses OK. Move actuator A to home and **Exit** (process stops).  
- **Yes** → Continue.

**Step 5 – Set temperature to LIV RCP temperature**  
The laser temperature is set to the LIV value defined in the RCP (e.g. Remote Control Panel).

**Step 6 – Wait for temperature to stabilize within ±0.5**  
The system waits until the temperature is stable within ±0.5 of the set value.

---

### Phase 2: Conduct LIV test (data collection)

This is the **LIV test** itself: the laser current is stepped from minimum to maximum, and at each step power, voltage, and PD are measured and stored.

**Step 7 – Clear the LIV plot**  
Any existing LIV plot is cleared so the new test is drawn from scratch.

**Step 8 – Calculate current range and NumIncrements**  
- Get from RCP: minimum current, maximum current, and current step size (increment).  
- Compute: **NumIncrements = (MaxCurrent − MinCurrent) ÷ Increment**.  
This is how many current steps the test will run (e.g. 100 steps).

**Step 9 – Set the first (or next) current and wait**  
- **Add increment to set current** – Set the current to the next value (first time: minimum current; then min + increment, and so on).  
- **Set the laser current** – Apply this current to the laser.  
- **Wait for time delay from RCP** – Wait for the settling time from RCP before measuring.

**Step 10 – Take 10 power readings at this current (inner loop)**  
- **Get Gentec powermeter power** – Read one power value from the Gentec power meter.  
- **Multiply by 1000** – Convert to the desired unit (e.g. mW).  
- **Append to array** – Store this value in a temporary array.  
- **Check: I == 10?**  
  - **No** → Go back to **Get Gentec powermeter power** and repeat until you have 10 readings.  
  - **Yes** → You have 10 readings; leave the inner loop.

**Step 11 – Process and store this current step**  
- **Get mean of power array and plot it** – Average the 10 power values and add this point to the LIV power plot.  
- **Get laser voltage and plot it** – Read laser voltage at this current and plot it.  
- **Get PD and plot it** – Read the photodiode (PD) value and plot it.  
- **Append to main arrays** – Append this step’s mean power to the power array, voltage to the voltage array, and PD to the PD array.

**Step 12 – Check if all current steps are done (outer loop)**  
- **Check: I == NumIncrements?**  
  - **No** → Go back to **Step 9** (add increment to set current) and run the next current step.  
  - **Yes** → All current steps are done. **Get the final power from the power array** (e.g. the last value). **Return** the power array, PD array, voltage array, and final power. The LIV test is finished and the process continues with the next phase.

---

### Phase 3: After LIV test – fiber check and Thorlabs calibration

**Step 13 – Check if fiber coupled? (again)**  
- **No** → Move actuator A to home and wait for position. Then the flow continues.  
- **Yes** → Turn off laser, then turn on laser, then prompt the user to connect the fiber to the power meter.  
Both paths merge.

**Step 13a – User presses OK (pop message)**  
After the “connect fiber to power meter” prompt, the user presses OK on the pop-up.

**Step 13b – Open alignment window**  
The alignment window opens.

**Step 13c – Turn on Laser On and Ando On in alignment window**  
In the alignment window, the **Laser On** button and **Ando On** button are turned on (so the user can align).

**Step 13d – Wait until user presses OK in alignment window**  
The process waits. **Thorlabs power meter readings are not taken** until the user confirms alignment. The user aligns the fiber and presses OK in the alignment window when ready.

**Step 13e – User presses OK in alignment window**  
The user presses OK in the alignment window to confirm alignment is done.

**Step 13f – Turn off Ando On**  
Ando On is turned off. The process then continues to Thorlabs power meter measurement.

**Step 14 – Thorlabs power meter: 10 readings and average**  
- **Take Thorlabs power meter measurement** – Read one value from the Thorlabs power meter.  
- **Append to array** – Store it.  
- **Check: I == 10?**  
  - **No** → Go back to **Take Thorlabs power meter measurement** and repeat until 10 readings.  
  - **Yes** → Compute **average power array** (mean of the 10 Thorlabs readings).

**Step 15 – Calibration factor**  
- **Multiply average power by 1000 for mW** – Convert the Thorlabs average to mW.  
- **Divide final power from LIV test by average power** – This gives the **Thorlabs calibration factor** (LIV power vs. Thorlabs power).

---

### Phase 4: Calculations and pass/fail

**Step 16 – Calculate key parameters**  
- **Calculate power at rated current** – Power at the rated current (from RCP).  
- **Calculate current at rated power** – Current needed to reach the rated power.  
- **Calculate threshold current** – Laser threshold current from the data.

**Step 17 – Check if LIV passed or failed**  
Using the RCP parameters, the system decides whether the LIV test **passed** or **failed** based on the calculated values and limits.

---

### Phase 5: Save and exit

**Step 18 – Save LIV data to database**  
All LIV results (arrays, final power, calibration factor, pass/fail, etc.) are saved to the database.

**Step 19 – Turn laser off**  
The laser is turned off.

**Step 20 – EXIT**  
The LIV process ends.

---

### Summary in one paragraph

The LIV process starts by checking fiber coupling and turning on the laser; if the laser is on, it sets temperature and waits for stability. It then runs the **LIV test**: clear plot, step current from min to max, and at each step take 10 Gentec power readings, average them, and record voltage and PD; results are stored in power, voltage, and PD arrays. When all steps are done, it returns the arrays and final power. The process then checks fiber again (and may ask the user to connect fiber to the Thorlabs meter). After the user presses OK on that prompt, the **alignment window** opens; Laser On and Ando On are turned on in that window. The process **waits until the user presses OK in the alignment window** (no Thorlabs readings are taken until then). Once the user presses OK in alignment, Ando On is turned off and the process continues: it takes 10 Thorlabs power readings and averages them, multiplies by 1000 for mW, and divides the LIV final power by this average to get the Thorlabs calibration factor. It then computes power at rated current, current at rated power, and threshold current, checks pass/fail against RCP parameters, saves LIV data to the database, turns the laser off, and exits.

---

## Complete process flowchart

```text
                               +-------+
                               | START |
                               +-------+
                                   |
                                   v
                    +---------------------------+
                    | Check if fiber coupled?   |
                    +-----------+---------------+
                    +-----------+-----------+
                    |                       |
                   No                      Yes
                    |                       |
                    v                       v
      +-------------------------+   +-------------------------------+
      | Move actuator A in      |   | Prompt user to connect fiber  |
      | front of beam           |   | to power meter                |
      +-----------+-------------+   +---------------+---------------+
                  |                                 |
                  v                                 v
      +-------------------------+   +-------------------------------+
      | Wait for actuator A     |   | Prompt user to connect fiber  |
      | to be in position       |   | to power meter                |
      +-----------+-------------+   +---------------+---------------+
                  |                                 |
                  +-----------------+---------------+
                                    |
                                    v
                      +---------------------------+
                      | Turn on laser             |
                      +-------------+-------------+
                                    |
                                    v
                      +---------------------------+
                      | Check if laser is ON      |
                      +-------------+-------------+
                                 +---------------+---------------+
                                 |                               |
                                No                              Yes
                                 |                               |
                                 v                               v
                +------------------------------+    +-----------------------------+
                | Prompt user: laser couldn't  |    | Set temperature to LIV RCP  |
                | turn on                       |    | temperature                 |
                +---------------+--------------+    +-------------+---------------+
                                |                                   |
                                v                                   v
                +------------------------------+    +-----------------------------+
                | User presses OK              |    | Wait for temperature to     |
                +---------------+--------------+    | stabilize within +/- 0.5    |
                                |                   +-------------+---------------+
                                v                                 |
                +------------------------------+                  v
                | Move actuator A to home      |    +-----------------------------+
                | Exit                         |    | Clear the LIV plot           |
                +------------------------------+    +-------------+---------------+
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
                         |                  |
                         |                  v
                         |    +-----------------------------------------------+
                         |    | Set the laser current                          |
                         |    +-------------+----------------------------------+
                         |                  |
                         |                  v
                         |    +-----------------------------------------------+
                         |    | Wait for time delay from RCP                   |
                         |    +-------------+----------------------------------+
                         |                  |
                         |                  v
                         |    +-----------------------------------------------+
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
                                              +-----------------------------+
                                              | Get mean of power array      |
                                              | and plot it                  |
                                              +-------------+----------------+
                                                                  |
                                                                  v
                                              +-----------------------------+
                                              | Get laser voltage and plot it|
                                              +-------------+----------------+
                                                                  |
                                                                  v
                                              +-----------------------------+
                                              | Get PD and plot it           |
                                              +-------------+----------------+
                                                                  |
                                                                  v
                                              +-----------------------------+
                                              | Append PD to PD array        |
                                              | Append voltage to voltage    |
                                              | array                        |
                                              | Append mean power to         |
                                              | power array                  |
                                              +-------------+----------------+
                                                                  |
                                                                  v
                                              +-----------------------------+
                                              | I == NumIncrements ?         |
                                              +-------+---------------------+
                                                                  |
                                                             No   |   Yes
                                                              \   |    |
                                                               \  |    v
                                                                \ |    +-----------------------------+
                                                                 \|    | Get final power from         |
                                                                  |    | power array                  |
                                                                  |    +-------------+---------------+
                                                                  |                  |
                                                                  |                  v
                                                                  |    +-----------------------------+
                                                                  |    | Return power array,         |
                                                                  |    | PD array, voltage array,    |
                                                                  |    | and final power             |
                                                                  |    +-------------+---------------+
                                                                  |                  |
                                                                  |                  v
                                                                  |
                                                                  v
                                    +-----------------------------+-----------------------------+
                                    | Check if fiber coupled?                                   |
                                    +-------------+-----------------------------+---------------+
                                                  |                             |
                                                 No                            Yes
                                                  |                             |
                                                  v                             v
                                +-----------------------------+   +-----------------------------+
                                | Move actuator A to home     |   | Turn off laser              |
                                | Wait for position           |   +-------------+---------------+
                                +-------------+---------------+                   |
                                              |                                 v
                                              |                  +-----------------------------+
                                              |                  | Turn on laser               |
                                              |                  +-------------+---------------+
                                              |                                  |
                                              |                                  v
                                              |                  +-----------------------------+
                                              |                  | Prompt user to connect      |
                                              |                  | fiber to power meter        |
                                              |                  +-------------+---------------+
                                              |                                  |
                                              |                                  v
                                              |                  +-----------------------------+
                                              |                  | User presses OK (pop)       |
                                              |                  +-------------+---------------+
                                              |                                  |
                                              |                                  v
                                              |                  +-----------------------------+
                                              |                  | Open alignment window      |
                                              |                  +-------------+---------------+
                                              |                                  |
                                              |                                  v
                                              |                  +-----------------------------+
                                              |                  | Turn on Laser On and        |
                                              |                  | Ando On in alignment window |
                                              |                  +-------------+---------------+
                                              |                                  |
                                              |                                  v
                                              |                  +-----------------------------+
                                              |                  | Wait: user presses OK      |
                                              |                  | in alignment window         |
                                              |                  | (no Thorlabs until then)    |
                                              |                  +-------------+---------------+
                                              |                                  |
                                              |                                  v
                                              |                  +-----------------------------+
                                              |                  | User presses OK in          |
                                              |                  | alignment window            |
                                              |                  +-------------+---------------+
                                              |                                  |
                                              |                                  v
                                              |                  +-----------------------------+
                                              |                  | Turn off Ando On            |
                                              |                  +-------------+---------------+
                                              |                                  |
                                              +------------------+---------------+
                                                                 |
                                                                 v
                                              +------------------------------------------+
                                         +--->| take Thorlabs power meter measurement     |
                                         \    +------------------------------------------+
                                         \                         |
                                         \                         v
                                         \    +------------------------------------------+
                                         \    | Append to array                          |
                                         \    +------------------------------------------+
                                         \                         |
                                         \                         v
                                         \    +------------------------------------------+
                                         \    | I==10?                                   |
                                         \    +------------------+-----------------------+
                                         \       NO              |              YES
                                         \        \              |               |
                                          +--------+             |               v
                                                                     +----------------------+
                                                                     | AVERAGE POWER ARRAY   |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | Multiply average     |
                                                                     | power by 1000 for mW |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | Divide final power   |
                                                                     | from LIV test by     |
                                                                     | avg power for        |
                                                                     | Thorlabs calib factor |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | Calculate power at    |
                                                                     | rated current         |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | Calculate current at |
                                                                     | rated power           |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | Calculate threshold  |
                                                                     | current              |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | Check if LIV passed  |
                                                                     | or failed based on   |
                                                                     | RCP parameters       |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | Save LIV data to     |
                                                                     | database             |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | Turn laser off       |
                                                                     +----------------------+
                                                                                 |
                                                                                 v
                                                                     +----------------------+
                                                                     | EXIT                 |
                                                                     +----------------------+
```

---

## Step-by-step: complete LIV process

| Phase | Step | Action |
|-------|------|--------|
| **Algorithm** | 1 | START. |
| | 2 | Check if fiber coupled? No → move actuator A in front of beam, wait for position. Yes → prompt user to connect fiber to power meter. Merge. |
| | 3 | Turn on laser. |
| | 4 | Check if laser is ON? No → prompt user (laser couldn’t turn on), user OK, move actuator A to home, Exit. Yes → continue. |
| | 5 | Set temperature to LIV RCP temperature. |
| | 6 | Wait for temperature to stabilize within ±0.5. |
| **LIV Test** | 7 | Clear LIV plot. |
| | 8 | Calculate current range from RCP; NumIncrements = (Max − Min) / Increment. |
| | 9 | Add increment to set current (start at min). Set laser current. Wait for time delay from RCP. |
| | 10 | Get Gentec powermeter power → multiply by 1000 → append to array. I == 10? No → repeat from Get Gentec. Yes → continue. |
| | 11 | Get mean of power array and plot. Get laser voltage and plot. Get PD and plot. Append to PD, voltage, power arrays. |
| | 12 | I == NumIncrements? No → back to step 9. Yes → get final power from power array; return power array, PD array, voltage array, final power. |
| **Algorithm** | 13 | Check if fiber coupled? No → move actuator A to home, wait. Yes → turn off laser, turn on laser, prompt to connect fiber to power meter. Merge. |
| | 13a | User presses OK (pop). Open alignment window. Turn on Laser On and Ando On in alignment window. |
| | 13b | Wait until user presses OK in alignment window (no Thorlabs readings until then). User presses OK → turn off Ando On. |
| | 14 | Take Thorlabs power meter measurement → append to array. I==10? No → repeat. Yes → average power array. |
| | 15 | Multiply average power by 1000 for mW. Divide final power from LIV test by average power (Thorlabs calib factor). |
| | 16 | Calculate power at rated current. Calculate current at rated power. Calculate threshold current. |
| | 17 | Check if LIV passed or failed (RCP parameters). |
| | 18 | Save LIV data to database. Turn laser off. EXIT. |

---

## Reference

- **LIV Algorithm** (overall flow): `LIV_ALGORITHM.md`
- **LIV Test** (detailed flow inside “Conduct LIV test”): `LIV_TEST.md`
