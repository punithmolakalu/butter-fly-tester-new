# PER Overview Algorithm

## Explanation in English

The **PER (Polarization Extinction Ratio) algorithm** runs a laser PER test. The steps run in sequence with no branches.

---

### Step-by-step sequence

1. **Set the laser temperature to RCP value** – Set temperature from the RCP (Remote Control Panel) before turning the laser on.
2. **Move PER actuator in front of Thorlabs powermeter** – Position the PER actuator so the beam is in front of the Thorlabs power meter for measurement.
3. **Ramp laser current to RCP value and turn laser on** – Bring the laser current to the RCP value and turn the laser on.
4. **Conduct PER test** – Run the PER measurement (polarization extinction ratio).
5. **Turn laser off** – Turn the laser off after the test.
6. **Upload PER results to DB** – Save the PER results to the database.
7. **Home PER actuator so it is not in the beam path** – Return the PER actuator to home so it is out of the beam path.

---

## PER Overview flowchart (ASCII)

```text
+------------------------------------------------------------------+
| 1. Set the laser temperature to RCP value                        |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 2. Move PER actuator in front of Thorlabs powermeter              |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 3. Ramp laser current to RCP value and turn laser on              |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 4. Conduct PER test                                               |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 5. Turn laser off                                                 |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 6. Upload PER results to DB                                       |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| 7. Home PER actuator so it is not in the beam path                |
+------------------------------------------------------------------+
                                |
                                v
                            +-------+
                            |  END  |
                            +-------+
```

---

## Summary

PER Overview is a linear 7-step process: set temperature → move PER actuator to Thorlabs powermeter → ramp current and turn laser on → conduct PER test → turn laser off → upload results to DB → home PER actuator → END.

---

## Reference

For the **full merged process** (Overview + **Conduct PER test** expanded into the detailed PER Test), see **`PER_PROCESS.md`**.
