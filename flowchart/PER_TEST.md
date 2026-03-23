# PER Test

## What is PER?

**PER** stands for **Polarization Extinction Ratio**. It measures how well a laser keeps one polarization and suppresses the other. A higher PER (in dB) means better polarization purity, which matters for fiber optics and many laser applications.

The **PER Test** is the procedure that runs this measurement: the laser beam passes through a rotating polarizer (or the measurement setup rotates). As the angle changes, the power seen by the power meter goes up and down. The test finds the **maximum** and **minimum** power over a full rotation, then computes:

**PER (dB) = 10 × log₁₀(max power / min power)**

---

## Clear explanation of the PER Test

The test has three parts: **setup**, a **measurement loop**, and **finish**.

### 1. Setup (steps 1–5, run once)

- **Clear the PER display** so the graph starts fresh.
- **Set motor speed and acceleration** from the RCP (Remote Control Panel) so the rotation is safe and consistent.
- **Wait for the motor to finish** applying those settings.
- **Move the motor to the starting angle** from the RCP (e.g. 0° or a defined start).
- **Start rotating the motor** so the polarizer (or setup) rotates in front of the beam.

### 2. Measurement loop (steps 6–19, repeat while motor is busy)

While the motor is rotating, the test repeatedly:

1. **Reads power** from the power meter (e.g. Thorlabs).
2. **Converts to mW** (multiply by 1000 if the meter gives watts).
3. **Stores the value** in a power array.
4. From the power array so far, gets the **maximum** and **minimum** power.
5. Computes **max ÷ min**, then **log₁₀** of that, then **× 10** → this is the **running PER** in dB.
6. **Reads the motor position** (angle) and appends it to a position array.
7. **Updates the graph**: power vs angle (running power vs running position).
8. Finds the **index of the maximum power** in the power array and uses it to get the **angle where power is maximum** (max angle).
9. Asks: **Is the motor still busy?**
   - **Yes** → go back to step 6 and take another power measurement (next angle).
   - **No** → motor has stopped; leave the loop and go to finish.

So the loop keeps adding one power and one angle at a time, updating the running PER and the graph, until the motor stops.

### 3. Finish (steps 20–22, run once)

- **Rotate the motor back** to the starting position so the system is ready for the next test.
- **Wait until the motor is not busy** so the move is complete.
- **Return** the final **max power**, **min power**, **PER** (dB), and **max angle** to the caller (e.g. for display, pass/fail, or database).

---

### Step-by-step sequence (reference)

**Setup (once)**  
1. **Clear the PER display**  
2. **Set the motor maximum speed and acceleration based on RCP**  
3. **Wait for motor to finish setting**  
4. **Move motor to starting angle based on RCP**  
5. **Start rotating motor**  

**Measurement loop (repeats while motor is busy)**  
6. **Get power measurement**  
7. **Multiply power by 1000 for mW**  
8. **Append to power array**  
9. **Get maximum value from power array**  
10. **Get minimum value from power array**  
11. **Divide the maximum by the minimum**  
12. **Take the log_10 of max/min**  
13. **Multiply the result from log_10 by 10 for the running PER value**  
14. **Get the position of the motor**  
15. **Append polled position to running position array**  
16. **Graph running power vs running position**  
17. **Get index of max power from running power array**  
18. **Use index of max power to get the maximum angle**  
19. **Is the motor busy?**  
    - **Yes** → go back to step 6 (Get power measurement).  
    - **No** → continue.  

**Finish (once motor is not busy)**  
20. **Rotate the motor back to the starting position**  
21. **Wait until the motor is not busy**  
22. **Return max power, min power, PER, max angle** (end).

---

## PER Test flowchart (ASCII)

```text
+------------------------------------------------------------------+
| 1. Clear the PER display                                         |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 2. Set the motor maximum speed and acceleration based on RCP      |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 3. Wait for motor to finish setting                              |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 4. Move motor to starting angle based on RCP                      |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 5. Start rotating motor                                          |
+------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
    +--->| 6. Get power measurement                                        |
    |    +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 7. Multiply power by 1000 for mW                               |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 8. Append to power array                                        |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 9. Get maximum value from power array                            |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 10. Get minimum value from power array                           |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 11. Divide the maximum by the minimum                            |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 12. Take the log_10 of max/min                                   |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 13. Multiply the result from log_10 by 10 for the running       |
        |     PER value                                                    |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 14. Get the position of the motor                                |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 15. Append polled position to running position array             |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 16. Graph running power vs running position                      |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 17. Get index of max power from running power array              |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 18. Use index of max power to get the maximum angle              |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | 19. Is the motor busy?                                           |
        +---------------------------+--------------------------------------+
                |                                   |
               Yes                                  No
                \                                   |
                 \                                  v
                  \                 +------------------------------------------------------------------+
                   \                | 20. Rotate the motor back to the starting position               |
                    \               +------------------------------------------------------------------+
                     \                                  |
                      \                                 v
                       \               +------------------------------------------------------------------+
                        \              | 21. Wait until the motor is not busy                             |
                         \             +------------------------------------------------------------------+
                          \                                |
                           \                               v
                            \              +------------------------------------------------------------------+
                             \             | 22. Return max power, min power, PER, max angle                   |
                              \            +------------------------------------------------------------------+
                               \                               |
                                \                              v
                                 \                         +-------+
                                  \                        |  END  |
                                   \                       +-------+
                                    +
                                    |
                                    +=========> (loop back to step 6)
```

---

## Loop back (detail)

The **Yes** branch of **Is the motor busy?** returns to step **6. Get power measurement** in the PER Test:

```text
    ... Is the motor busy? ...
                |
               Yes
                |
                +===============>  (back to)  6. Get power measurement
```

So the block from step 6 through step 19 repeats until the motor is no longer busy; then steps 20–22 run once and the PER Test ends.

---

## Summary

**PER Test** = setup (clear display, set speed/accel, move to start, start rotating) → **loop**: get power → mW → append → max/min → divide → log₁₀ × 10 (PER) → position → append position → graph → index of max → max angle → **motor busy?** (Yes → repeat from get power; No → rotate back, wait, return max power, min power, PER, max angle → END).

---

## Reference

For **PER Overview** wrapped around this test (steps before and after **Conduct PER test**), see **`PER_PROCESS.md`** and **`PER_OVERVIEW.md`**.
