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

## Summary

**Stability Overview** = Ramp laser current to RCP → **Laser ON?** (False → notify and skip; True → Set TEC to MinTemp from RCP → wait for temp or timeout → **Timeout?** (True → notify and skip; False → wait 2 s → set Ando from Spectrum RCP → start single sweep → **loop**: get Ando WL/LVL → **Sweep stopped?** (No → loop back; Yes → grab peak WL → set Ando center/span/sampling from Stability RCP → run stability test → pass/fail → save to DB → turn off laser → end))).
`