# PER Process (Complete)

This document merges the **PER Overview** and the **PER Test** into one process. The **PER Test** flow is placed **inside** the **Conduct PER test** step of the overview, so the full sequence from preparation to exit is described in one place.

---

## What this process does

1. **PER Overview** (overall): set laser temperature from RCP → move PER actuator in front of Thorlabs powermeter → ramp current and turn laser on → **run the PER test** → turn laser off → upload PER results to DB → home PER actuator → END.
2. **PER Test** (inside “Conduct PER test”): clear PER display → configure motor from RCP → move to start angle → start rotating → **loop** while motor is busy: get power → mW → append to arrays → compute running PER (10×log₁₀(max/min)) → position → graph → max angle → **Is motor busy?** → when done: rotate motor home, wait, **return** max power, min power, PER, max angle.
3. **After PER test**: the overview continues with turn laser off, upload to DB, and home actuator.

So: **PER Process** = PER Overview with the **PER Test** expanded inside **Conduct PER test**.

**PER (dB)** = 10 × log₁₀(max power / min power) — computed during the PER Test from the power array built while the motor rotates.

---

## PER process explained step by step (in English)

### Phase 1: Before the PER test (Overview steps 1–3)

**Step 1 – Set the laser temperature to RCP value**  
Set temperature from the RCP before or as part of bringing the laser to test conditions.

**Step 2 – Move PER actuator in front of Thorlabs powermeter**  
Position the PER actuator so the beam is in front of the Thorlabs power meter for measurement.

**Step 3 – Ramp laser current to RCP value and turn laser on**  
Bring the laser current to the RCP value and turn the laser on.

---

### Phase 2: Conduct PER test (PER Test — steps 1–22)

This is the **PER Test** itself (see also `PER_TEST.md`).

**Setup (once)**  
1. Clear the PER display.  
2. Set motor maximum speed and acceleration from RCP.  
3. Wait for motor to finish setting.  
4. Move motor to starting angle from RCP.  
5. Start rotating motor.

**Measurement loop (repeat while motor is busy)**  
6. Get power measurement → 7. Multiply by 1000 for mW → 8. Append to power array → 9–10. Max and min from array → 11. Divide max by min → 12. log₁₀ → 13. ×10 for running PER (dB) → 14–15. Motor position → append to position array → 16. Graph power vs position → 17–18. Index of max power → maximum angle → 19. **Is motor busy?**  
- **Yes** → back to step 6.  
- **No** → exit loop.

**Finish (once)**  
20. Rotate motor back to starting position.  
21. Wait until motor is not busy.  
22. Return max power, min power, PER, max angle to the caller.

---

### Phase 3: After the PER test (Overview steps 5–7)

**Step 5 – Turn laser off**  
Turn the laser off after the measurement.

**Step 6 – Upload PER results to DB**  
Save PER results (and related data as defined by the application) to the database.

**Step 7 – Home PER actuator**  
Move the PER actuator to home so it is not in the beam path.

**END** — Process complete.

---

## Complete PER process flowchart (ASCII)

Overview steps **1–3**, then **Conduct PER test** expanded as the PER Test (steps **1–22**), then overview steps **5–7**.

```text
+------------------------------------------------------------------+
| Overview 1. Set the laser temperature to RCP value               |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| Overview 2. Move PER actuator in front of Thorlabs powermeter     |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| Overview 3. Ramp laser current to RCP value and turn laser on     |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| Overview 4. Conduct PER test  (expanded below)                  |
+------------------------------------------------------------------+
                                |
                                v
        ==========  PER TEST (inside step 4)  ==========
+------------------------------------------------------------------+
| PER Test 1. Clear the PER display                                 |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| PER Test 2. Set motor max speed and acceleration from RCP         |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| PER Test 3. Wait for motor to finish setting                     |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| PER Test 4. Move motor to starting angle from RCP                 |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| PER Test 5. Start rotating motor                                 |
+------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
    +--->| PER Test 6. Get power measurement                           |
    |    +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 7. Multiply power by 1000 for mW                    |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 8. Append to power array                             |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 9. Get maximum value from power array                 |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 10. Get minimum value from power array                |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 11. Divide maximum by minimum                       |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 12. Take log_10 of max/min                          |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 13. Multiply log result by 10 (running PER, dB)      |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 14. Get position of motor                            |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 15. Append position to running position array         |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 16. Graph running power vs running position           |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 17. Get index of max power from running power array   |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 18. Use index to get maximum angle                    |
        +------------------------------------------------------------------+
                                |
                                v
        +------------------------------------------------------------------+
        | PER Test 19. Is the motor busy?                                |
        +---------------------------+--------------------------------------+
                |                                   |
               Yes                                  No
                |                                   |
                |                                   v
                |               +------------------------------------------------------------------+
                |               | PER Test 20. Rotate motor back to starting position              |
                |               +------------------------------------------------------------------+
                |                                   |
                |                                   v
                |               +------------------------------------------------------------------+
                |               | PER Test 21. Wait until motor is not busy                        |
                |               +------------------------------------------------------------------+
                |                                   |
                |                                   v
                |               +------------------------------------------------------------------+
                |               | PER Test 22. Return max power, min power, PER, max angle         |
                |               +------------------------------------------------------------------+
                |                                   |
                |                                   v
        (Yes from step 19: loop back to PER Test 6)
                                                    |
                                                    v
        ==========  end PER TEST; continue OVERVIEW  ==========
+------------------------------------------------------------------+
| Overview 5. Turn laser off                                       |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| Overview 6. Upload PER results to DB                              |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| Overview 7. Home PER actuator (not in beam path)                 |
+------------------------------------------------------------------+
                                |
                                v
                            +-------+
                            |  END  |
                            +-------+
```

**Note:** In the diagram above, the **No** branch from “Is the motor busy?” goes to steps 20–22; the **Yes** branch loops back to PER Test 6. After step 22 returns, the flow continues to **Overview 5** (turn laser off), not through the loop marker again.

---

## Cleaner loop-only snippet (PER Test)

```text
        | PER Test 19. Is the motor busy? |
                Yes --> back to PER Test 6 (Get power measurement)
                No  --> PER Test 20 -> 21 -> 22 (return) --> Overview 5
```

---

## Summary

**PER Process** = **Overview 1–3** → **PER Test 1–22** (motor rotation loop until not busy; PER = 10×log₁₀(max/min)) → **Overview 5–7** (laser off, DB upload, home actuator) → END.

---

## Reference

- **High-level sequence only:** `PER_OVERVIEW.md`  
- **PER Test detail only:** `PER_TEST.md`  
- **Full merged process (this file):** `PER_PROCESS.md`
