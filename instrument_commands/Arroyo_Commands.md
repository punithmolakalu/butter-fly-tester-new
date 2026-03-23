# Arroyo Instrument Commands Reference

This document lists all unique commands used in `serial_interface.py`, grouped by TEC and Laser controllers.

## Common Commands

| Command | Description | Type |
|---------|-------------|------|
| `*IDN?` | Device identification | Query |

---

## TEC Controller Commands

### Temperature Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:T?` | Read actual temperature | Query | `read_temp()` |
| `TEC:SET:T?` | Read temperature setpoint | Query | `read_set_temp()` |
| `TEC:T <value>` | Set temperature setpoint | Write | `set_temp()` |
| `TEC:LIM:THI?` | Read temperature high limit | Query | `read_THI_limit()` |
| `TEC:LIM:THI <value>` | Set temperature high limit | Write | `set_THI_limit()` |
| `TEC:LIM:TLO?` | Read temperature low limit | Query | `read_TLO_limit()` |
| `TEC:LIM:TLO <value>` | Set temperature low limit | Write | `set_TLO_limit()` |

### Mode Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:MODE?` | Read operation mode (T/R/ITE) | Query | `read_mode()` |
| `TEC:MODE:<mode>` | Set operation mode | Write | `set_mode()` |

### Output Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:OUT?` | Read output status (ON/OFF) | Query | `read_output()` |
| `TEC:OUT <value>` | Set output (1=ON, 0=OFF) | Write | `set_output()` |

### Current Control (ITE Mode)

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:ITE?` | Read actual current | Query | `read_current()` |
| `TEC:SET:ITE?` | Read current setpoint | Query | `read_set_current()` |
| `TEC:ITE <value>` | Set current setpoint | Write | `set_current()` |
| `TEC:LIM:ITE?` | Read current limit | Query | `read_current_limit()` |
| `TEC:LIM:ITE <value>` | Set current limit | Write | `set_current_limit()` |

### Voltage Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:V?` | Read actual voltage | Query | `read_voltage()` |
| `TEC:VBULK?` | Read supply voltage | Query | `vbulk()` |
| `TEC:LIM:V?` | Read voltage limit (v3.X+) | Query | `read_voltage_limit()` |
| `TEC:LIM:V <value>` | Set voltage limit (v3.X+) | Write | `set_voltage_limit()` |

### Control Parameters

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:GAIN?` | Read control loop gain | Query | `read_gain()` |
| `TEC:GAIN <value>` | Set control loop gain | Write | `set_gain()` |
| `TEC:PID?` | Read PID values (P,I,D) | Query | `read_PID()` |
| `TEC:PID <P>,<I>,<D>` | Set PID values | Write | `set_PID()` |
| `TEC:TOL?` | Read tolerance criteria | Query | `read_tolerance()` |
| `TEC:TOL <tolerance>,<time>` | Set tolerance criteria | Write | `set_tolerance()` |

### Sensor Configuration

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:CONST?` | Read sensor constants (A,B,C) | Query | `sensor_constants()` |
| `TEC:CONST <A>,<B>,<C>` | Set sensor constants | Write | `set_sensor_constants()` |

### Heat/Cool Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:HEATCOOL?` | Read heat/cool mode | Query | `read_heatcool()` |
| `TEC:HEATCOOL <mode>` | Set heat/cool mode | Write | `set_heatcool()` |

### Fan Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:FAN?` | Read fan settings | Query | `read_fan()` |
| `TEC:FAN <speed>,<mode>[,<delay>]` | Set fan settings | Write | `set_fan()` |

### AutoTune

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TEC:AUTOTUNE?` | Read autotune status | Query | `read_autotune()` |
| `TEC:AUTOTUNE <temp>` | Start autotune process | Write | `autotune()` |

### System Information

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `TIME?` | Read unit run time | Query | `run_time()` |
| `BEEP 1` | Make beep sound | Write | `beep()` |

---

## Laser Controller Commands

### Laser Current Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:LDI?` | Read laser diode current | Query | `laser_read_current()` |
| `LASER:I?` | Read laser current (alternative) | Query | `laser_read_current()` |
| `LASER:SET:LDI?` | Read laser current setpoint | Query | `laser_read_set_current()` |
| `LASER:SET:I?` | Read laser current setpoint (alt) | Query | `laser_read_set_current()` |
| `LASER:LDI <value>` | Set laser current setpoint | Write | `laser_set_current()` |
| `LASER:LIMIT:LDI?` | Read laser current limit | Query | `laser_read_current_limit()` |
| `LASER:LIMIT:LDI <value>` | Set laser current limit | Write | `laser_set_current_limit()` |

### Laser Voltage Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:LDV?` | Read laser diode voltage | Query | `laser_read_voltage()` |
| `LASER:SET:LDV?` | Read laser voltage setpoint | Query | `laser_read_set_voltage()` |
| `LASER:LDV <value>` | Set laser voltage setpoint | Write | `laser_set_voltage()` |
| `LASER:LIMIT:LDV?` | Read laser voltage limit | Query | `laser_read_voltage_limit()` |
| `LASER:LIMIT:LDV <value>` | Set laser voltage limit | Write | `laser_set_voltage_limit()` |

### Laser Output Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:OUTPUT?` | Read laser output status | Query | `laser_read_output()` |
| `LASER:OUTPUT <value>` | Set laser output (1=ON, 0=OFF) | Write | `laser_set_output()` |

### Laser Mode Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:MODE?` | Read laser operation mode | Query | `laser_read_mode()` |
| `LASER:MODE:<mode>` | Set laser operation mode | Write | `laser_set_mode()` |

### Monitor Diode Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:MDI?` | Read monitor diode current | Query | `laser_read_monitor_diode_current()` |
| `LASER:IPD?` | Read monitor diode current (alt) | Query | `laser_read_monitor_diode_current()` |
| `LASER:SET:MDI?` | Read monitor diode current setpoint | Query | `laser_read_set_monitor_diode_current()` |
| `LASER:SET:IPD?` | Read monitor diode current setpoint (alt) | Query | `laser_read_set_monitor_diode_current()` |
| `LASER:MDI <value>` | Set monitor diode current | Write | `laser_set_monitor_diode_current()` |
| `LASER:MDP?` | Read monitor diode power | Query | `laser_read_monitor_diode_power()` |
| `LASER:SET:MDP?` | Read monitor diode power setpoint | Query | `laser_read_set_monitor_diode_power()` |
| `LASER:MDP <value>` | Set monitor diode power | Write | `laser_set_monitor_diode_power()` |
| `LASER:LIMIT:MDP?` | Read monitor diode power limit | Query | `laser_read_monitor_diode_power_limit()` |
| `LASER:LIMIT:MDP <value>` | Set monitor diode power limit | Write | `laser_set_monitor_diode_power_limit()` |

### Laser Temperature Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:T?` | Read laser temperature | Query | `laser_read_temperature()` |
| `LASER:LIMIT:THIGH?` | Read temperature high limit | Query | `laser_read_temperature_high_limit()` |
| `LASER:LIMIT:THIGH <value>` | Set temperature high limit | Write | `laser_set_temperature_high_limit()` |
| `LASER:LIMIT:TLOW?` | Read temperature low limit | Query | `laser_read_temperature_low_limit()` |
| `LASER:LIMIT:TLOW <value>` | Set temperature low limit | Write | `laser_set_temperature_low_limit()` |

### Laser Pulse Control

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:F?` | Read laser frequency | Query | `laser_read_frequency()` |
| `LASER:F <value>` | Set laser frequency | Write | `laser_set_frequency()` |
| `LASER:PW?` | Read pulse width | Query | `laser_read_pulse_width()` |
| `LASER:PW <value>` | Set pulse width | Write | `laser_set_pulse_width()` |

### Laser Tolerance

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:TOLERANCE?` | Read laser tolerance criteria | Query | `laser_read_tolerance()` |
| `LASER:TOLERANCE <tolerance>,<time>` | Set laser tolerance | Write | `laser_set_tolerance()` |

### Laser Sensor Configuration

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:CONST?` | Read laser sensor constants | Query | `laser_read_constants()` |
| `LASER:CONST <A>,<B>,<C>` | Set laser sensor constants | Write | `laser_set_constants()` |

### Laser Other Parameters

| Command | Description | Type | Method |
|---------|-------------|------|--------|
| `LASER:R?` | Read laser resistance | Query | `laser_read_resistance()` |
| `LASER:PDBIAS?` | Read photodiode bias | Query | `laser_read_photodiode_bias()` |
| `LASER:PDBIAS <value>` | Set photodiode bias | Write | `laser_set_photodiode_bias()` |
| `LASER:RANGE?` | Read laser current range | Query | `laser_read_range()` |
| `LASER:RANGE <value>` | Set laser current range | Write | `laser_set_range()` |

---

## Summary Statistics

### TEC Commands
- **Total Unique Commands**: 35
- **Query Commands**: 19
- **Write Commands**: 16

### Laser Commands
- **Total Unique Commands**: 38
- **Query Commands**: 22
- **Write Commands**: 16

### Common Commands
- **Total**: 1 (`*IDN?`)

### Grand Total
- **Total Unique Commands**: 74

---

## Notes

1. **Command Format**: All commands end with `\r\n` (carriage return + line feed)
2. **Response Format**: Responses typically end with `\r\n` which is stripped during parsing
3. **Timeout**: Default response timeout is 0.1 seconds (100ms) in `write_command()`
4. **Retries**: Commands retry up to 3 times on failure
5. **Alternative Commands**: Some laser commands have alternative formats (e.g., `LASER:LDI?` vs `LASER:I?`)
6. **Firmware Versions**: Some commands (like `TEC:LIM:V?`) are only available in v3.X+ firmware

---

## Commands Used in Timeout-Critical Operations

Based on the execution flowchart, these commands are called frequently and cause slowdowns:

### Status Update Loop (every 1-2 seconds):
- `TEC:T?` - Read temperature
- `LASER:LDI?` or `LASER:I?` - Read laser current  
- `LASER:MDP?` - Read laser power (monitor diode)

### Test Execution:
- `TEC:MODE?` - Check mode
- `TEC:MODE:T` - Set temperature mode
- `TEC:T <value>` - Set temperature
- `LASER:LDI <value>` - Set laser current

These commands are the primary contributors to performance slowdowns when connected to real hardware.

