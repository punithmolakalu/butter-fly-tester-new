# Stability test — ASCII flowcharts

Companion to [`STABILITY_OVERVIEW.md`](STABILITY_OVERVIEW.md): **Part A** there keeps the original high-level flow (ramp current → laser ON → TEC → Ando sweep → peak → stability → DB). **Part B** there spells out FWHM/recovery/consecutive-exceed rules. This file is **extra ASCII diagrams** for the detailed logic only.

---

## 1. Overall test (two sweeps)

```text
                              +------------------+
                              |  START TEST      |
                              +--------+---------+
                                       |
                                       v
                              +------------------+
                              | Load recipe:     |
                              | T_init, T_max,   |
                              | step, thresholds |
                              +--------+---------+
                                       |
                                       v
                              +------------------+
                              | consecutive_exceed|
                              |      = 0         |
                              +--------+---------+
                                       |
                                       v
+------------------+           +------------------+           +------------------+
|  SWEEP 1         |           |  Run all T from  |           |  SWEEP 2         |
|  Cold --> Hot    | --------> |  T_init to T_max | --------> |  Hot --> Cold    |
|                  |           |  (see diagram 2) |           |  T_max to T_init |
+------------------+           +--------+---------+           +---------+--------+
                                       |                                 |
                                       |                                 |
                                       v                                 v
                              +------------------+           +------------------+
                              | (same per-T      | <-------- | Same per-T logic |
                              |  logic each step)|           | for each setpoint|
                              +--------+---------+           +--------+---------+
                                       |                                 |
                                       +----------------+----------------+
                                                        |
                                                        v
                                       +-------------------------------+
                                       | All setpoints done without    |
                                       | immediate FAIL?               |
                                       +---------------+---------------+
                                                       |
                              +------------------------+------------------------+
                              |                                                 |
                              v                                                 v
                 +-------------------------+                       +-------------------------+
                 | Delta WL/°C enabled?    |                       | On any immediate fail |
                 +------------+------------+                       | (limits / 3 consec.)  |
                              |                                    +------------+------------+
              +---------------+---------------+                                |
              | NO                            | YES                            v
              v                               v                     +------------------+
 +------------------------+        +------------------------+        |  FAIL + STOP   |
 | PASS (if no other      |        | Compute slope vs       |        +------------------+
 |  failure)              |        | recipe limits          |
 +------------------------+        +------------+-----------+
                                               |
                              +----------------+----------------+
                              |                                 |
                              v                                 v
                 +------------------------+       +------------------------+
                 | Slope in limits?       |       | Slope outside limits?  |
                 +------------+-----------+       +------------+-----------+
                              |                                 |
                              v                                 v
                 +------------------------+       +------------------------+
                 | PASS                   |       | FAIL + STOP            |
                 +------------------------+       +------------------------+
```

---

## 2. One temperature setpoint (measure, retry, exceed count)

```text
                         +---------------------------+
                         |  Set TEC to T_set         |
                         |  Wait for thermal settle  |
                         +-------------+-------------+
                                       |
                                       v
                         +---------------------------+
                         |  Measure: FWHM, SMSR,     |
                         |  peak WL                  |
                         +-------------+-------------+
                                       |
                                       v
                         +---------------------------+
                         |  FWHM/SMSR limits         |
                         |  enabled in recipe?      |
                         +------+--------+-----------+
                                |        |
                     +----------+        +----------+
                     | YES                  | NO
                     v                      |
          +----------------------+         |
          | FWHM in [LL,UL]    |         |
          | AND SMSR in [LL,UL]|         |
          +----------+---------+         |
                     |                   |
                     v                   v
              +------+------+    +------+------+
              | No          |    | Continue    |
              | FAIL STOP   |    | (limits OK  |
              +-------------+    |  or disabled)|
                                   +------+------+
                                          |
                                          v
                         +---------------------------+
                         |  FWHM <= recovery         |
                         |  threshold?               |
                         +------+--------+-----------+
                                |        |
                     +----------+        +----------+
                     | YES                  | NO
                     v                      v
          +----------------------+   +---------------------------+
          | Point = WITHIN limit |   | Stay at same T;           |
          | consec_exceed = 0    |   | retry loop (diagram 3)   |
          +----------+-----------+   +-------------+-------------+
                     |                             |
                     |                             |
                     +-------------+---------------+
                                   |
                                   v
                         +---------------------------+
                         |  Next T in current sweep  |
                         |  (or end of sweep)        |
                         +---------------------------+
```

---

## 3. FWHM above recovery threshold — up to 5 retries

```text
                         +---------------------------+
                         |  FWHM > threshold         |
                         |  (first or last reading)  |
                         +-------------+-------------+
                                       |
                                       v
                         +---------------------------+
                         |  attempt = 1              |
                         +-------------+-------------+
                                       |
                                       v
                    +----------------------------------------+
                    |              LOOP                      |
                    |  +----------------------------------+  |
                    |  | Measure again (same T)           |  |
                    |  +----------------+----------------+  |
                    |                   |                 |  |
                    |                   v                 |  |
                    |  +-- FWHM <= threshold? ----------+  |  |
                    |  |     |              |          |  |  |
                    |  |    YES             NO         |  |  |
                    |  |     |              |          |  |  |
                    |  |     v              v          |  |  |
                    |  |  +--------+   +-----------+   |  |  |
                    |  |  | Point  |   | attempt++ |   |  |  |
                    |  |  | OK     |   |           |   |  |  |
                    |  |  | reset  |   +-----+-----+   |  |  |
                    |  |  | consec |         |       |   |  |  |
                    |  |  | EXIT   |         v       |   |  |  |
                    |  |  +--------+   +-----------+   |  |  |
                    |  |              | attempt>5? |   |  |  |
                    |  |              +-----+-----+   |  |  |
                    |  |                    |         |   |  |  |
                    |  |           +------+------+  |   |  |  |
                    |  |           | No: loop back |  |   |  |  |
                    |  |           | Yes: use last |  |   |  |  |
                    |  |           | reading; point|  |   |  |  |
                    |  |           | = EXCEED      |  |   |  |  |
                    |  |           +-------+-------+  |   |  |  |
                    |  +----------------------------------+  |
                    +----------------------------------------+
                                       |
                                       v
                         +---------------------------+
                         |  If EXCEED:               |
                         |  consec_exceed++          |
                         +-------------+-------------+
                                       |
                                       v
                         +---------------------------+
                         |  consec_exceed >= 3 ?     |
                         +------+--------+-----------+
                                |        |
                     +----------+        +----------+
                     | YES                  | NO
                     v                      v
          +----------------------+   +----------------------+
          | FAIL + STOP          |   | consec_exceed = 0  |
          +----------------------+   | (if point was OK)  |
                                     +----------+-----------+
                                                |
                                                v
                                     +----------------------+
                                     | Next temperature     |
                                     +----------------------+
```

---

## 4. Consecutive exceed (simplified)

```text
        WITHIN limit (FWHM ok after measure/retry)          EXCEED at this T
                    |                                              |
                    v                                              v
           +----------------+                           +-------------------+
           | consec_exceed  |                           | consec_exceed++   |
           |    = 0         |                           +---------+---------+
           +----------------+                                     |
                                                                  v
                                                         +-------------------+
                                                         | consec_exceed==3? |
                                                         +----+---------+----+
                                                              |         |
                                                             YES        NO
                                                              |         |
                                                              v         v
                                                     +------------+  +------------+
                                                     | FAIL STOP  |  | Continue   |
                                                     +------------+  +------------+
```

---

## 5. End of test — delta WL per °C (when enabled)

```text
                         +---------------------------+
                         |  Both sweeps finished     |
                         |  without FAIL STOP        |
                         +-------------+-------------+
                                       |
                                       v
                         +---------------------------+
                         |  Delta WL/°C enabled?     |
                         +------+--------+-----------+
                                |        |
                     +----------+        +----------+
                     | NO                  | YES
                     v                     v
          +------------------+   +----------------------+
          | PASS               |   | Compute d(WL)/d(T)   |
          +------------------+   +----------+-----------+
                                              |
                                              v
                                   +----------+-----------+
                                   | In recipe limits?    |
                                   +----+--------+--------+
                                        |        |
                                       YES       NO
                                        |        |
                                        v        v
                             +--------------+  +--------------+
                             | PASS         |  | FAIL         |
                             +--------------+  +--------------+
```

---

*Diagrams describe the intended logic; keep in sync with `STABILITY_OVERVIEW.md` and the implementation.*
