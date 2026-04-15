# Temperature Stability Process

## Parameters

| Name | Value | Notes |
|---|---|---|
| Initial Temp | 25.0 °C | Start of cold→hot sweep |
| Max Temp | 35.0 °C | End of cold→hot sweep |
| Min Temp | 25.0 °C | TEC resets here after every hot→cold |
| Step | 0.1 °C | Increment per point |
| DegOfStability | 5.0 °C | Required consecutive stable span |
| Min stability span | 0.7 °C | Min stable gap between two exceeds |
| FWHM threshold | 0.3 nm | Max FWHM for a point to be "stable" |
| Max retries | 3 | Attempts per point before declaring exceed |

---

## Process overview

```
 SETUP → SWEEP UP → found 5 °C stable? → SWEEP DOWN to verify
                                              │
                               ┌──────────────┼──────────────┐
                              ALL             ANY            
                             stable?         failed?         
                               │               │             
                          TEC → min        TEC → min         
                               │               │             
                            ████████       resume UP         
                             PASS          from where        
                            ████████       you paused        
                                               │             
                                          found another      
                                          5 °C stable?       
                                           │          │      
                                          YES         NO     
                                           │          │      
                                      SWEEP DOWN   ████████  
                                      again         FAIL     
                                                   ████████  
```

---

## Step by step

### 1. Setup

```
Check instruments → Laser ON → TEC → 25.0 °C → Ando peak-find → Apply recipe
```

### 2. Sweep UP (cold → hot, 0.1 °C steps)

Measure at each point: **25.0, 25.1, 25.2, ... up to 35.0 °C**

At every point, check:
- FWHM ≤ 0.3 nm?
- All enabled hard limits pass?
- Up to 3 retries if it fails

Result: **STABLE** or **EXCEED**

### 3. Two rules during sweep up

---

#### RULE 1 — DegOfStability: exceed resets the window

The window needs **5.0 °C of consecutive stable points** (50 points at 0.1 step).
One single exceed **resets the window to zero**.

```
25.0  25.1  25.2  ...  27.4  27.5  27.6  ...  32.6
 ✔     ✔     ✔    ✔    ✔     ✘     ✔    ✔     ✔
 ├─────────────────────┘     │     ├────────────┘
 window = 2.4 °C             │     window = 5.0 °C → FOUND!
 (thrown away)                │
                         EXCEED → resets window to zero
                               new window starts at 27.6
```

**As soon as 5.0 °C consecutive stable is found → PAUSE the sweep, go to step 4.**

---

#### RULE 2 — Min stability span: two exceeds too close = FAIL

After an exceed, must have **0.7 °C stable** (7 points) before next exceed is allowed.

**OK — 0.7 °C between exceeds:**

```
27.5  27.6  27.7  27.8  27.9  28.0  28.1  28.2  28.3
 ✘     ✔     ✔     ✔     ✔     ✔     ✔     ✔     ✘
 │     ├─────────────────────────────┘     │
 │              0.7 °C (7 points)          │
EXCEED          min stab span MET        EXCEED #2
 #1             → allowed                (OK)
```

**FAIL — only 0.3 °C between exceeds:**

```
27.5  27.6  27.7  27.8  27.9
 ✘     ✔     ✔     ✔     ✘
 │     ├─────────────┘    │
 │     only 0.3 °C        │
EXCEED (3 points)       EXCEED #2 → HARD FAIL!
 #1    needed 0.7 °C      test stops immediately
```

---

### 4. Sweep DOWN (hot → cold, verify the window)

Sweep downward through the qualifying window, same 0.1 °C steps.
**Every point must be stable.**

```
Example: window was 27.6 → 32.6 °C

Verify: 32.6 → 32.5 → 32.4 → ... → 27.8 → 27.7 → 27.6
         ✔      ✔      ✔     ✔      ✔      ✔      ✔
         All stable → VERIFICATION PASSED ✔
```

If **any** point fails → verification FAILED, stop the down-sweep.

### 5. Reset TEC to min

**Always** after the down-sweep (pass or fail):

```
TEC → 25.0 °C (min)
Wait for settle
```

### 6. What happens next

**If verification PASSED → TEST PASSES. Done.**

**If verification FAILED:**

```
Resume sweep UP from where you paused (next point after top of window)

Example: window was 27.6 → 32.6, verification failed
         → resume from 32.7 °C upward
         → keep looking for another 5.0 °C stable window
         → if found → sweep down again → verify
         → if reached 35.0 °C without finding one → FAIL
```

---

## Full walkthrough example

```
Step = 0.1 °C, DegOfStability = 5.0 °C, Min stab span = 0.7 °C
Range: 25.0 → 35.0 °C
```

### Round 1: Sweep UP

```
25.0  ✔ ─┐
25.1  ✔  │
 ...  ✔  │ 2.5 °C of stable points
27.4  ✔  │
27.5  ✘ ─┘ EXCEED! Window resets.
27.6  ✔ ─┐
27.7  ✔  │
 ...  ✔  │  need 0.7 °C before next exceed allowed
28.2  ✔  │  28.2 − 27.5 = 0.7 °C → min stab span met ✔
 ...  ✔  │
32.5  ✔  │  window [27.6 → 32.5] = 4.9 °C (not yet)
32.6  ✔ ─┘  window [27.6 → 32.6] = 5.0 °C → FOUND! PAUSE HERE.
```

### Round 1: Sweep DOWN (verify 32.6 → 27.6)

```
32.6  ✔
32.5  ✔
 ...  ✔
30.1  ✔
30.0  ✘  ← FAIL! Verification failed at 30.0 °C.
         Stop sweep down.
```

### Reset

```
TEC → 25.0 °C, wait for settle.
```

### Round 2: Resume sweep UP from 32.7

```
32.7  ✔ ─┐
32.8  ✔  │
 ...  ✔  │ only 2.3 °C left (32.7 → 35.0)
35.0  ✔ ─┘ span = 2.3 °C < 5.0 °C needed

Not enough range left for another 5.0 °C window.
→ TEST RESULT: ████ FAIL ████
  TEC → 25.0 °C
```

---

## Full walkthrough — PASS scenario

### Round 1: Sweep UP

```
25.0  ✔ ─┐
25.1  ✔  │
 ...  ✔  │ all stable, no exceeds
29.9  ✔  │
30.0  ✔ ─┘ window [25.0 → 30.0] = 5.0 °C → FOUND! PAUSE.
```

### Round 1: Sweep DOWN (verify 30.0 → 25.0)

```
30.0  ✔
29.9  ✔
 ...  ✔
25.1  ✔
25.0  ✔  ← all 51 points stable

VERIFICATION PASSED ✔
```

### Reset + result

```
TEC → 25.0 °C
→ TEST RESULT: ████ PASS ████
```

---

## Full walkthrough — Min stability span HARD FAIL

### Sweep UP

```
25.0  ✔ ─┐
 ...  ✔  │
26.8  ✔  │
26.9  ✘ ─┘ EXCEED #1. Need 0.7 °C stable before next exceed.
27.0  ✔     recovery: 0.1 °C
27.1  ✔     recovery: 0.2 °C
27.2  ✔     recovery: 0.3 °C
27.3  ✘     EXCEED #2! Only 0.4 °C from last exceed.
            0.4 < 0.7 (min stability span)
            → ████ HARD FAIL ████
            Test stops immediately.
            TEC → 25.0 °C
```

---

## Full walkthrough — verification fails, second window passes

### Round 1: Sweep UP

```
25.0  ✔ ─┐
 ...  ✔  │ all stable
30.0  ✔ ─┘ window [25.0 → 30.0] = 5.0 °C → FOUND! PAUSE.
```

### Round 1: Sweep DOWN (verify 30.0 → 25.0)

```
30.0  ✔
 ...  ✔
27.5  ✘  ← FAIL! Stop down-sweep.
```

### Reset

```
TEC → 25.0 °C
```

### Round 2: Resume sweep UP from 30.1

```
30.1  ✔ ─┐
30.2  ✔  │
 ...  ✔  │ all stable
35.0  ✔ ─┘ window [30.1 → 35.0] = 4.9 °C < 5.0 °C

Not enough! 4.9 < 5.0
→ ████ FAIL ████
  TEC → 25.0 °C
```

If max temp were 36.0 instead:

```
30.1  ✔ ─┐
 ...  ✔  │
35.1  ✔ ─┘ window [30.1 → 35.1] = 5.0 °C → FOUND!

Sweep DOWN: 35.1 → 30.1, all stable ✔
TEC → 25.0 °C
→ ████ PASS ████
```

---

## Quick reference

```
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│  1. Sweep UP in 0.1 °C steps                                 │
│                                                               │
│  2. At each point: measure, check FWHM + limits              │
│     - STABLE → add to window                                 │
│     - EXCEED → window resets to zero                          │
│                check min stability span (0.7 °C)              │
│                if another exceed within 0.7 °C → HARD FAIL   │
│                                                               │
│  3. Window reaches 5.0 °C consecutive stable → PAUSE         │
│                                                               │
│  4. Sweep DOWN through the window (verify)                   │
│     - All stable → PASS                                      │
│     - Any fail  → resume UP from where you paused            │
│                                                               │
│  5. After every down-sweep: TEC → min temp (25.0 °C)         │
│                                                               │
│  6. If no 5.0 °C window found before max temp → FAIL         │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## Glossary

| Term | Meaning |
|---|---|
| **DegOfStability** | Required consecutive stable span. Any exceed resets to zero. |
| **Min stability span** | Min gap between two exceeds. Less than this = HARD FAIL. Code: `RecoveryStep_C` |
| **Exceed** | Point where all retries failed. Breaks the stability window. |
| **Qualifying window** | Consecutive stable points spanning ≥ DegOfStability |
| **Verification** | Hot→cold sweep rechecking every point in the window |
| **HARD FAIL** | Two exceeds within Min stability span. Test stops immediately. |
