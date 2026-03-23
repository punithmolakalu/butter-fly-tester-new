# Thorlabs Power Meter SCPI Command List

## IEEE-488.2 Common Commands

### Identification and Status
- `*IDN?` - Query manufacturer, model, serial number, firmware
- `*RST` - Reset instrument to default state
- `*CLS` - Clear status registers and error queue
- `*OPC` - Set operation complete bit when commands finish
- `*OPC?` - Return "1" when all operations are complete
- `*TST?` - Run self-test, return result (0 = pass)
- `*WAI` - Wait until all previous commands complete

### Event and Status Registers
- `*ESE <value>` - Set standard event enable register
- `*ESE?` - Query standard event enable register
- `*ESR?` - Query and clear standard event status register
- `*SRE <value>` - Set service request enable register
- `*SRE?` - Query service request enable register
- `*STB?` - Query status byte register

## SYSTEM Subsystem

- `SYST:ERR?` - Read last error code and message
- `SYST:VERS?` - Query supported SCPI version
- `SYST:LFREQ <50|60>` - Set line frequency (50 or 60 Hz)
- `SYST:LFREQ?` - Query line frequency
- `SYST:SENS:IDN?` - Query connected sensor info (type, SN, flags)

## STATUS Subsystem

### Measurement Status
- `STAT:MEAS:EVEN?` - Read measurement event register
- `STAT:MEAS:COND?` - Read measurement condition register
- `STAT:MEAS:PTR <value>` - Set positive transition filter
- `STAT:MEAS:NTR <value>` - Set negative transition filter
- `STAT:MEAS:ENAB <value>` - Enable measurement event reporting

### Operation Status
- `STAT:OPER:EVEN?` - Read operation event register
- `STAT:OPER:COND?` - Read operation condition register
- `STAT:OPER:PTR <value>` - Set operation positive transition filter
- `STAT:OPER:NTR <value>` - Set operation negative transition filter
- `STAT:OPER:ENAB <value>` - Enable operation event reporting

### Questionable Status
- `STAT:QUES:EVEN?` - Read questionable event register
- `STAT:QUES:COND?` - Read questionable condition register
- `STAT:QUES:PTR <value>` - Set questionable positive transition filter
- `STAT:QUES:NTR <value>` - Set questionable negative transition filter
- `STAT:QUES:ENAB <value>` - Enable questionable event reporting

### Status Preset
- `STAT:PRESET` - Reset all status registers to default

## CALIBRATION Subsystem

- `CAL:STR?` - Read human-readable calibration string

## SENSE Subsystem (Measurement Settings)

### Averaging
- `SENS:AVER <value>` - Set averaging count
- `SENS:AVER?` - Query averaging count

### Correction/Attenuation
- `SENS:CORR:LOSS <value>` - Set user attenuation factor (dB)
- `SENS:CORR:LOSS?` - Query attenuation factor

### Zero Adjustment
- `SENS:COLL:ZERO:INIT` - Start zero adjustment
- `SENS:COLL:ZERO:ABOR` - Abort zero adjustment
- `SENS:COLL:ZERO:STAT?` - Query zeroing status
- `SENS:COLL:ZERO:MAGN?` - Query zero offset value

### Beam and Wavelength
- `SENS:BEAM <value>` - Set beam diameter (mm)
- `SENS:BEAM?` - Query beam diameter
- `SENS:WAV <value>` - Set operating wavelength (nm)
- `SENS:WAV?` - Query operating wavelength

### Sensor Response Configuration
- `SENS:POW:RESP <value>` - Set photodiode responsivity (A/W)
- `SENS:POW:RESP?` - Query photodiode responsivity
- `SENS:THERM:RESP <value>` - Set thermopile responsivity (V/W)
- `SENS:THERM:RESP?` - Query thermopile responsivity
- `SENS:ENER:PYRO:RESP <value>` - Set pyroelectric responsivity (V/J)
- `SENS:ENER:PYRO:RESP?` - Query pyroelectric responsivity

## CURRENT Measurement

- `CURR:RANG:AUTO ON|OFF` - Enable/disable auto-ranging
- `CURR:RANG:AUTO?` - Query auto-ranging state
- `CURR:RANG <value>` - Set current range (A)
- `CURR:RANG?` - Query current range
- `CURR:REF <value>` - Set delta reference current
- `CURR:REF?` - Query delta reference
- `CURR:STAT ON|OFF` - Enable/disable delta mode
- `CURR:STAT?` - Query delta mode state

## POWER Measurement

- `POW:RANG:AUTO ON|OFF` - Enable/disable auto-ranging
- `POW:RANG:AUTO?` - Query auto-ranging
- `POW:RANG <value>` - Set power range (W)
- `POW:RANG?` - Query power range
- `POW:REF <value>` - Set delta reference power
- `POW:REF?` - Query delta reference
- `POW:STAT ON|OFF` - Enable/disable delta mode
- `POW:STAT?` - Query delta mode
- `POW:UNIT W|DBM` - Set power unit
- `POW:UNIT?` - Query power unit

## VOLTAGE Measurement

- `VOLT:RANG:AUTO ON|OFF` - Enable/disable auto-ranging
- `VOLT:RANG:AUTO?` - Query auto-ranging
- `VOLT:RANG <value>` - Set voltage range (V)
- `VOLT:RANG?` - Query voltage range
- `VOLT:REF <value>` - Set delta reference voltage
- `VOLT:REF?` - Query delta reference
- `VOLT:STAT ON|OFF` - Enable/disable delta mode
- `VOLT:STAT?` - Query delta mode

## INPUT Subsystem

### Photodiode Filter
- `INP:PDI:FILT:STAT ON|OFF` - Enable/disable photodiode low-pass filter
- `INP:PDI:FILT:STAT?` - Query photodiode filter state

### Thermopile Settings
- `INP:THERM:ACC:STAT ON|OFF` - Enable thermopile acceleration
- `INP:THERM:ACC:STAT?` - Query thermopile acceleration state
- `INP:THERM:ACC:AUTO ON|OFF` - Enable thermopile auto acceleration
- `INP:THERM:ACC:AUTO?` - Query auto acceleration
- `INP:THERM:TAU <value>` - Set thermopile time constant (s)
- `INP:THERM:TAU?` - Query thermopile time constant

### Adapter Type
- `INP:ADAP:TYPE PHOT|THERM|PYRO` - Set default adapter type
- `INP:ADAP:TYPE?` - Query adapter type

## Measurement Control

### Configuration
- `CONF:POW` - Configure for power measurement
- `CONF:CURR` - Configure for current measurement
- `CONF:VOLT` - Configure for voltage measurement
- `CONF:ENER` - Configure for energy measurement
- `CONF:FREQ` - Configure for frequency measurement
- `CONF:PDEN` - Configure for power density
- `CONF:EDEN` - Configure for energy density
- `CONF:RES` - Configure for sensor resistance
- `CONF:TEMP` - Configure for sensor temperature
- `CONF?` - Query current configuration

### Measurement Execution
- `INIT` - Start measurement
- `ABOR` - Abort measurement

### Measurement Queries
- `MEAS:POW?` - Perform power measurement
- `MEAS:CURR?` - Perform current measurement
- `MEAS:VOLT?` - Perform voltage measurement
- `MEAS:ENER?` - Perform energy measurement
- `MEAS:FREQ?` - Perform frequency measurement
- `MEAS:PDEN?` - Perform power density measurement
- `MEAS:EDEN?` - Perform energy density measurement
- `MEAS:RES?` - Perform resistance measurement
- `MEAS:TEMP?` - Perform temperature measurement

### Reading Results
- `READ?` - Start new measurement and read result
- `FETC?` - Read last measured value


