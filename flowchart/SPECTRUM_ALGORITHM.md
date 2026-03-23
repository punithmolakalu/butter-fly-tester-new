# Spectrum Algorithm

## Explanation in English

The **Spectrum Algorithm** runs a spectrum acquisition sequence: it sets the laser current (either I@RatedP from LIV if the RCP uses it, or the current from the RCP), turns the laser on, and checks if the laser is on. If not, it notifies that the laser could not turn on and stops. If the laser is on, it sets the TEC temperature from the RCP and checks for TEC timeout. If the TEC times out, it notifies and stops. If not, it sets wavemeter and Ando settings from the RCP, grabs the Ando spectrum and a wavemeter measurement, plots the spectrum, sets the Ando center wavelength to the peak from the Ando, changes the Ando span to 1 nm and sampling to 501, saves the spectrum to the database, and turns the laser off.

---

### Step-by-step summary

1. **Check if RCP is using I@RatedP from LIV**
   - **Yes** → Set laser to I@RatedP.
   - **No** → Set laser to current from RCP.
2. **Turn laser on** (paths merge).
3. **Is laser on?**
   - **No** → Notify: laser could not turn on → stop.
   - **Yes** → Set TEC temperature from RCP.
4. **Did TEC timeout?**
   - **Yes** → Notify: TEC has timed out → stop.
   - **No** → Set wavemeter settings from RCP → Update Ando settings from RCP.
5. **Grab Ando spectrum** → **Grab wavemeter measurement** → **Plot the Ando spectrum**.
6. **Set center WL to peak WL from Ando** → **Change Ando span to 1 nm** → **Set Ando sampling to 501**.
7. **Save spectrum to DB** → **Turn off the laser** → end.

---

## Spectrum Algorithm flowchart (ASCII)

```text
+----------------------------------------------+
| Check if RCP is using I@RatedP from LIV      |
+----------------------------------------------+
            | Yes                        | No
            v                            v
+-----------------------------+   +----------------------------------+
| Set laser to I@RatedP       |   | Set laser to current from RCP    |
+-----------------------------+   +----------------------------------+
            \___________________________/
                        |
                        v
               +-------------------+
               | Turn laser on     |
               +-------------------+
                        |
                        v
               +-------------------+
               | Is laser on?      |
               +-------------------+
                        |
                +-------+-------+
                |               |
               Yes             No
                |               |
                v               |
                |               v
                |     +--------------------------------------+
                |     | Notify: laser could not turn on       |
                |     +--------------------------------------+
                |                    (stop)
                |
                v
   +------------------------------+
   | Set TEC temperature from RCP  |
   +------------------------------+
                |
                v
        +---------------------------+
        | Did TEC timeout?          |
        +---------------------------+
                |
        +-------+-------+
        |               |
       No              Yes
        |               |
        v               v
        |               +--------------------------------------+
        |               | Notify: TEC has timed out             |
        |               +--------------------------------------+
        |                          (stop)
        |
        v
   +--------------------------------------+
   | Set wavemeter settings from RCP      |
   +--------------------------------------+
                |
                v
   +------------------------------------+
   | Update Ando settings from RCP     |
   +------------------------------------+
                |
                v
+------------------------------------+
| Grab Ando spectrum                |
+------------------------------------+
                |
                v
+------------------------------------+
| Grab wavemeter measurement        |
+------------------------------------+
                |
                v
+------------------------------------+
| Plot the Ando spectrum            |
+------------------------------------+
                |
                v
+----------------------------------------------+
| Set center WL to peak WL from Ando           |
+----------------------------------------------+
                |
                v
+------------------------------------+
| Change Ando span to 1 nm           |
+------------------------------------+
                |
                v
+------------------------------------+
| Set Ando sampling to 501           |
+------------------------------------+
                |
                v
+------------------------------------+
| Save spectrum to DB                |
+------------------------------------+
                |
                v
+-----------------------------+
| Turn off the laser          |
+-----------------------------+
```

---

## Summary

**Spectrum Algorithm** = Check RCP for I@RatedP from LIV → set laser current (I@RatedP or RCP current) → turn laser on → **Is laser on?** (No → notify laser could not turn on, stop; Yes → set TEC from RCP → **Did TEC timeout?** (Yes → notify TEC timed out, stop; No → set wavemeter and Ando from RCP → grab Ando spectrum → grab wavemeter → plot Ando spectrum → set center WL to peak from Ando → Ando span 1 nm, sampling 501 → save spectrum to DB → turn off laser → end)).
