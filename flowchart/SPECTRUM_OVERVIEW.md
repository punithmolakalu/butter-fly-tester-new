# Spectrum Overview

## Explanation in English

The **Spectrum Overview** flow runs a single optical spectrum sweep using the Ando (optical spectrum analyzer). It clears the plot, starts the sweep, then loops: get wavelength (WL) and level (LVL) data from the Ando, convert LVL to linear, normalize, and poll sweep status. When the sweep has stopped, it gets wavemeter wavelength, converts to nm if needed, plots WL and normalized LVL, gets Ando DFLBD analysis data, laser current, and TEC temperature, saves a spectrum image, and saves data to the database.

---

## Spectrum Overview flowchart (ASCII)

```text
+-----------------------------+
| Clear the spectrum plot     |
+-----------------------------+
              |
              v
+-----------------------------+
| Start single sweep          |
+-----------------------------+
              |
              v
+---------------------------------------+
| Get WL and LVL data from Ando         |<-------------------+
+---------------------------------------+                    |
              |                                             |
              v                                             |
+-----------------------------+                             |
| Convert LVL data to linear  |                             |
+-----------------------------+                             |
              |                                             |
              v                                             |
+-----------------------------+                             |
| Normalize LVL data          |                             |
+-----------------------------+                             |
              |                                             |
              v                                             |
+-----------------------------+                             |
| Poll sweep status           |                             |
+-----------------------------+                             |
              |                                             |
              v                                             |
+-----------------------------+                             |
| Did sweep stop?             |---- No ---------------------+
+-----------------------------+
              |
             Yes
              |
              v
+-----------------------------+
| Get wavemeter WL            |
+-----------------------------+
              |
              v
+------------------------------------------+
| Convert wavemeter WL to nm if needed     |
+------------------------------------------+
              |
              v
+------------------------------------------+
| Plot WL data and normalized linear LVL   |
| data                                     |
+------------------------------------------+
              |
              v
+------------------------------------------+
| Get Ando analysis DFLBD data            |
+------------------------------------------+
              |
              v
+-----------------------------+
| Get laser current           |
+-----------------------------+
              |
              v
+-----------------------------+
| Get TEC temperature         |
+-----------------------------+
              |
              v
+------------------------------------------+
| Save an image of the spectrum            |
+------------------------------------------+
              |
              v
+-----------------------------+
| Save data to DB             |
+-----------------------------+
```

---

## Summary

**Spectrum Overview** = clear plot → start single sweep → **loop** (get WL and LVL from Ando → convert LVL to linear → normalize LVL → poll sweep status → **Did sweep stop?** No → back to get WL and LVL; Yes → get wavemeter WL → convert to nm if needed → plot WL and normalized LVL → get Ando DFLBD → get laser current → get TEC temperature → save spectrum image → save data to DB → end.
