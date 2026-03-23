# LIV Overview Algorithm

## Explanation in English

The **LIV (Light–Current–Voltage) algorithm** runs a laser test and calibration. Here is what each part does, in order.

---

### 1. Start and fiber check
- **START** → **Check if fiber coupled?**
- If **No**: **Move actuator A in front of beam**, then **Wait for actuator A to be in position**. The two branches then meet again.
- If **Yes**: **Prompt user to connect fiber to power meter** (shown twice in the flow; both paths later merge).

---

### 2. Turn on laser and check
- After the merge: **Turn on laser** → **Check if laser is ON**.
- If **No**: **Prompt user: laser couldn't turn on** → **User presses OK** → **Move actuator A to home, Exit** (test stops).
- If **Yes**: **Set temperature to LIV RCP temperature** → **Wait for temperature to stabilize within ±0.5** → **Conduct LIV test**.

---

### 3. After LIV test – fiber check again
- **Check if fiber coupled?** again.
- If **No**: **Move actuator A to home, Wait for position** (then flow continues).
- If **Yes**: **Turn off laser** → **Turn on laser** → **Prompt user to connect fiber to power meter**. Both paths merge.

---

### 4. Thorlabs power meter loop (calibration)
- **Take Thorlabs power meter measurement** → **Append to array** → **I == 10?**
- If **No**: Go back to **Take Thorlabs power meter measurement** (repeat until 10 readings).
- If **Yes**: Continue to **AVERAGE POWER ARRAY**.

---

### 5. Calibration and power in mW
- **AVERAGE POWER ARRAY** (average of the 10 readings).
- **Multiply average power by 1000 for mW** (convert to milliwatts).
- **Divide final power from LIV test by average power** to get the **Thorlabs calibration factor**.

---

### 6. Calculations and pass/fail
- **Calculate power at rated current**  
- **Calculate current at rated power**  
- **Calculate threshold current**  
- **Check if LIV passed or failed** using **RCP parameters**.

---

### 7. Save and shutdown
- **Save LIV data to database**
- **Turn laser off**
- **EXIT**

---

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
                | Exit                         |    | Conduct LIV test            |
                +------------------------------+    +-------------+---------------+
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
