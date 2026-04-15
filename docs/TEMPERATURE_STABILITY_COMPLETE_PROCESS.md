# Complete Temperature Stability Process

1. Read all values from RCP

Take all required settings from RCP.

Arroyo values
Min temperature
Max temperature
Increment
Wait time
Set current
Initial temperature
ANDO values
Span
Sampling
Continuous scan enabled or not
Offset 1
Offset 2
Stability values
Degree of stability
Recovery steps
Min stability span
Limits

Check only enabled limits, such as:

FWHM
SMSR
Peak wavelength
Power
2. Configure instruments
2.1 Configure Arroyo

Send to Arroyo:

Max temperature
Initial temperature
Set current

This means controller is loaded with the test settings.

2.2 Configure ANDO

Send to ANDO:

Span
Sampling
Offset 1
Offset 2
Continuous scan mode if enabled

So ANDO is ready for spectral acquisition.

3. Turn ON outputs

After device settings are sent:

3.1 Turn ON TEC

Enable TEC output on Arroyo.

This allows temperature control to begin.

3.2 Turn ON Laser

Enable laser output.

This allows optical readings to be measured by ANDO and Thorlabs power meter.

4. Move to starting temperature

Now move to the starting temperature.

Starting point for first stage

The first stage starts from minimum temperature.

So:

Set Arroyo set temperature = Min temperature
Wait until temperature reaches setpoint
Wait additional configured wait time

Now the test is ready to begin.

5. Test has two directions

The temperature stability test has two parts:

Stage 1: Cold → Hot
Start from Min temperature
Increase to Max temperature using increment
Stage 2: Hot → Cold
After a stable range is found in Cold → Hot
Start from top stable point
Move downward and verify stability in reverse direction
6. What happens at each temperature point

At every temperature point, the same actions happen.

Example points:

20.0
20.1
20.2
20.3
...

For each point:

6.1 Set the temperature

Send current temperature step to Arroyo.

6.2 Wait for temperature stabilization

Wait until actual temperature reaches and stabilizes.

6.3 Wait configured delay

Apply the RCP wait time.

6.4 Perform spectrum scan
If continuous scan is enabled, use continuous scanning
Otherwise perform a single scan
6.5 Read measurements

At this temperature read:

FWHM from ANDO
SMSR from ANDO
Peak wavelength from ANDO
Power from Thorlabs meter
6.6 Plot live

Plot all readings in the Temperature Stability window.

7. Check enabled limits

Now check only the limits enabled in RCP.

Example:

FWHM upper limit enabled = 0.1

Then:

If FWHM is within limit → pass
If FWHM is outside limit → fail

If multiple parameters are enabled, all enabled checks must pass for that temperature point to be considered pass.

8. Retry logic at same temperature

If a temperature point fails:

Do not move to next temperature immediately.

Instead:

Stay at the same temperature
Re-measure up to 5 times total
Stop early if pass happens
Case A: Pass during retry

Example:

1st read fail
2nd read fail
3rd read pass

Then:

stop retry immediately
mark this temperature point as pass
continue to next temperature
Case B: All 5 fail

Example:

5 reads all fail

Then:

mark this temperature point as fail
take the last reading as the final plotted value
continue to next temperature

So one failed point does not stop the test immediately.

9. Consecutive fail logic

Track how many temperature points failed consecutively.

Example:

Recovery steps = 2

That means:

1 fail is allowed
2 consecutive fails are allowed
3 consecutive fails means test fail

Because it exceeded the allowed recovery steps.

Example
20.3 fail
20.4 fail
20.5 fail

Now consecutive fail count = 3
So test fails.

If a point passes

If a later point passes:

reset consecutive fail count to 0
10. Min stability span logic

This is different from consecutive fail count.

Example:

Min stability span = 0.7°C

Meaning:

After a failed point, the next failed point must not happen too close.

There must be at least 0.7°C of acceptable region before another fail can occur without breaking stability tracking.

Example

Fail at 20.3

Then next fail should not happen before:

20.3 + 0.7 = 21.0
Good case
first fail at 20.3
next fail at 21.1

Distance = 0.8
This is acceptable

Bad case
first fail at 20.3
next fail at 20.6

Distance = 0.3
This is too close

Then the stability tracking resets.

Important:
This reset is for stability span tracking, not necessarily for whole test restart.

11. Degree of stability logic

This is the main success target.

Example:

Degree of stability = 3°C

You must find a passing region of 3°C.

For example:

23.0 to 26.0

That means over this full 3°C range, the test remained stable according to the rules.

If a fail occurs inside this region in a way that breaks the logic, that region is no longer valid and stability tracking restarts from a later point.

12. Full Cold → Hot process

Now let’s describe it from beginning to end.

Stage 1: Cold → Hot
Step 1

Load RCP values.

Step 2

Configure Arroyo:

Max temp
Initial temp
Set current
Step 3

Configure ANDO:

Span
Sampling
Offset 1
Offset 2
Continuous scan if enabled
Step 4

Turn ON TEC.

Step 5

Turn ON laser.

Step 6

Move set temperature to Min temperature.

Step 7

Wait until temperature reaches and stabilizes.

Step 8

Wait configured wait time.

Step 9

Start stepping from Min → Max using increment.

At each temperature:

Set temperature
Wait for stability
Wait configured delay
Scan
Read FWHM, SMSR, Peak WL, Power
Plot live
Check enabled limits
Step 10

If current point fails:

retry same temperature up to 5 times
if pass occurs in retry, stop retry and mark pass
if all 5 fail, mark fail and continue
Step 11

Update tracking:

consecutive fail count
min stability span logic
current passing span
Step 12

If consecutive failed points exceed allowed count:

test fails
Step 13

If stable passing range reaches Degree of Stability:

Cold → Hot stage success
note the top stable temperature
begin Hot → Cold verification
13. Example of Cold → Hot

Example:

Min = 20
Max = 35
Increment = 0.1
Degree = 3
Min stability span = 0.7
Recovery steps = 2
Sample
20.0 pass
20.2 initial fail, retry pass
20.3 fail after 5 tries
20.4 fail after 5 tries
20.5 pass → reset consecutive fail count
continue
from 23.0 to 26.0 all acceptable

Now:

stable span = 3°C
Cold → Hot success at 26.0 top point

Now move to reverse stage.

14. Full Hot → Cold process

Hot → Cold does not start from Max temperature automatically in your logic.

It starts from the top point of the stable range found in Cold → Hot.

Example:

stable range found = 23.0 to 26.0

Then reverse starts from:

26.0

Now move downward.

Stage 2: Hot → Cold

At each temperature while going down:

Set temperature
Wait for stabilization
Wait configured time
Scan
Read values
Plot live
Check limits
Retry same temp up to 5 times if failed
update fail count and stability logic
Goal

Verify that the same stability behavior is maintained in reverse direction.

15. If Hot → Cold passes

If reverse direction also satisfies the stability requirement:

Final result = PASS
Test ends
16. If Hot → Cold fails

If reverse fails before completing the required stable range:

Do not restart from Min temperature.

Do not restart whole test.

Instead:

go back to the last top stable point found in forward direction
continue searching upward for a new stable range
Example

You found:

stable range = 23 to 26

Then reverse:

26 pass
25.5 pass
25 fail

So reverse verification failed.

Now:

continue forward again from 26 upward
search 26 → 35 for another valid 3°C stable range

For example:

maybe 26 to 29 becomes a new stable region

Then again do reverse from 29 downward.

17. Why continue from top stable point

Because:

the earlier lower range was already checked
the system is now trying to find a better stable region at a higher temperature
restarting from Min temperature would repeat already-tested points unnecessarily

So “continue test” means:

resume from the last top stable point
move upward again
18. Final fail cases

The test finally fails in either of these conditions:

Case 1: Too many consecutive fails

Example:

Recovery steps = 2
3 consecutive failed points occur

Then final fail.

Case 2: No room left to achieve stability span

Example:

Degree required = 3°C
current search starts at 34
max temp = 35

Only 1°C range remains, so 3°C stable region is impossible

Then final fail.

Case 3: Reverse verification never succeeds before temperature range ends

If repeated forward search and reverse verification cannot produce a valid stable region before max limit is exhausted, final result is fail.

19. Min stability span explained clearly with process

Let’s isolate this clearly.

Suppose:

Min stability span = 0.7°C

And a fail happens at:

20.3

Now for stability evaluation:

another fail should not happen before 21.0

If another fail happens at:

20.4
or 20.5
or 20.8

Then this means the system did not hold a long enough good region after the previous fail.

So the current stability accumulation is broken.

You reset the stability tracking start point and continue looking for a new valid region.

This does not always mean the whole test is failed immediately.
It only means the current potential stable span is not valid.

20. Complete flow in compact form
1. Read RCP values
2. Configure Arroyo
3. Configure ANDO
4. Turn ON TEC
5. Turn ON Laser
6. Move to Min temperature
7. Wait for stabilization
8. Start Cold → Hot sweep

For each temperature point:
    a. Set temperature
    b. Wait for stabilization
    c. Wait configured delay
    d. Scan
    e. Read FWHM/SMSR/Peak WL/Power
    f. Plot live
    g. Check enabled limits

If fail:
    - Retry same temperature up to 5 times
    - Stop early if pass
    - If all 5 fail, mark final fail for that point

Track:
    - consecutive failed points
    - min stability span spacing
    - degree of stability passing region

If consecutive fail count exceeds recovery rule:
    - FAIL

If required degree span is achieved:
    - Start Hot → Cold verification from top stable point

During Hot → Cold:
    - apply same checks again

If reverse passes:
    - PASS

If reverse fails:
    - continue forward from last top stable point
    - search for new stable region

If no remaining temperature range can satisfy required span:
    - FAIL
21. One simple summary
Cold → Hot is used to find a stable temperature region.
Hot → Cold is used to verify that the region is stable in reverse.
Retry up to 5 times is only for the same temperature point.
Recovery steps checks consecutive failed points.
Min stability span checks how far apart failed points are.
Degree of stability is the total passing temperature range required.
If reverse fails, continue forward from the last top stable point, not from the beginning.

If you want, I can turn this into a clean ASCII flowchart with Cold→Hot and Hot→Cold branches together.

For each temperature:

1. Set temperature
2. Wait for stabilization
3. Wait configured delay
4. Perform scan:

   * Continuous OR Single
5. Read:

   * FWHM
   * SMSR
   * Peak Wavelength
   * Power
6. Plot values live
7. Check limits

---

## 7. Limit Check Logic

If limits enabled:

* If value within limits → PASS
* If value outside limits → FAIL

All enabled parameters must pass.

---

## 8. Retry Logic (Same Temperature)

If FAIL:

* Retry up to **5 times**
* Stop early if PASS occurs

### Case A: Pass during retry

* Stop retry
* Mark PASS

### Case B: All 5 fail

* Mark FAIL
* Use last reading
* Continue to next temperature

---

## 9. Recovery Steps Logic

Tracks **consecutive failed temperature points**

* Recovery Steps = N
* Test fails when **N + 1** consecutive fails occur (e.g. N = 2 → third consecutive fail ends the test)

### Example (Recovery = 2)

```
Fail → Fail → Fail → TEST FAIL
```

If PASS occurs:

* Reset fail count

---

## 10. Min Stability Span

Defines minimum gap between failures.

### Rule:

After a fail, the next fail must be at least:

```
Fail Temp + Min Stability Span
```

### Example:

* Fail at 20.3
* Min Span = 0.7

Next fail must be ≥ 21.0

### If violated:

* Stability tracking (degree-of-stability window) **resets** — the run continues unless recovery-step or range rules fail

---

## 11. Degree of Stability

Target: continuous PASS region

### Example:

* Degree = 3°C
* Need continuous valid region of 3°C

Example:

```
23 → 26 = 3°C → VALID
```

If fail occurs in between:

* Restart stability tracking

---

## 12. Cold → Hot Process

1. Start from Min Temp
2. Move upward using increment
3. At each step:

   * Measure
   * Retry if needed
   * Track:

     * Fail count
     * Stability span
4. If consecutive fails exceed limit → FAIL
5. If stable span achieved → proceed to reverse

---

## 13. Example (Cold → Hot)

```
20.0 → PASS
20.2 → FAIL → Retry → PASS
20.3 → FAIL (5 times)
20.4 → FAIL (5 times)
20.5 → PASS → reset fail count

23 → 26 → continuous PASS → 3°C achieved
```

---

## 14. Hot → Cold Process

Start from **top of stable range**

Example:

```
Stable: 23 → 26
Start reverse from 26 → 20
```

At each step:

* Same logic:

  * Measurement
  * Retry
  * Limits
  * Stability rules

---

## 15. Reverse Result

### Case A: Reverse PASS

* Final result = PASS

### Case B: Reverse FAIL

* Do NOT restart from Min
* Continue from **top stable point**

---

## 16. Continue Test Logic

If reverse fails:

```
Stable range = 23 → 26
Reverse fails at 25
```

Then:

* Restart from 26
* Continue upward (26 → 35)
* Search new stable region

---

## 17. New Stability Search

Example:

```
26 → 29 = 3°C → New stable region
```

Then:

* Perform reverse check again

---

## 18. Final Fail Conditions

### Case 1: Too many consecutive fails

```
Exceeds recovery steps (N + 1 consecutive fails when Recovery Steps = N)
```

### Case 2: No room for stability span

```
Need 3°C but only 1°C left → FAIL
```

### Case 3: Reverse never passes

* After multiple attempts
* No valid region found

---

## 19. Min Stability Span Example

### Good:

```
Fail at 20.3
Next fail at 21.1 → OK
```

### Bad:

```
Fail at 20.3
Next fail at 20.6 → RESET (stability window tracking)
```

---

## 20. Full Flow Summary

```
1. Load RCP
2. Configure Arroyo + ANDO
3. Turn ON TEC + Laser
4. Move to Min Temp
5. Start Cold → Hot

For each temperature:
    - Measure
    - Retry if needed
    - Check limits

Track:
    - Consecutive fails
    - Min stability span
    - Degree span

If degree achieved:
    → Reverse (Hot → Cold)

If reverse passes:
    → PASS

If reverse fails:
    → Continue from top point

If no valid span possible:
    → FAIL
```

---

## 21. Key Concepts

* Retry = same temperature (max 5)
* Recovery = consecutive fails (fail at N + 1 when Recovery Steps = N)
* Min Stability Span = spacing between fails (too close → reset stability window)
* Degree of Stability = required pass range
* Reverse check = validation
* Continue = resume from top stable point

---

## Implementation notes (software)

* The cold→hot sweep uses **Min Temperature** → **Max Temperature** from the recipe.
* **Raw data**: every measurement attempt (including retries) is stored in `raw_measurement_rows` and in the optional CSV trace; the main plot uses **final** points per setpoint only (retries omitted from the summary plot).
* Session JSON (`ts1.json` / `ts2.json`) includes full arrays plus `raw_measurement_rows`.
