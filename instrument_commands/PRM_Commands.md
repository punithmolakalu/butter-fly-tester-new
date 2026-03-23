# PRM (Thorlabs PRM1-Z8 / KDC101) Commands

Reference for the Thorlabs Kinesis API used with the PRM1-Z8 rotation mount driven by the KCube DCServo (KDC101). These are the main device control commands.

## Command summary

| Function           | Command                               | Description                              |
| ------------------ | ------------------------------------- | ---------------------------------------- |
| Identify device    | `Identify()`                          | Blink LED to identify controller         |
| Home stage         | `Home()`                              | Move stage to reference zero position   |
| Move to position   | `MoveAbsolute(position)`             | Move to an exact angle                   |
| Move by offset     | `MoveRelative(distance)`              | Move relative to current position        |
| Jog forward/back   | `MoveJog(direction)`                  | Continuous small movement                |
| Stop immediately   | `StopImmediate()`                     | Emergency stop                           |
| Stop smoothly      | `StopProfiled()`                      | Stop with deceleration                   |
| Set speed          | `SetVelParams(minVel, accel, maxVel)` | Set velocity parameters                  |
| Get position       | `GetPosition()`                       | Read current angle                       |
| Enable motor       | `EnableDevice()`                      | Enable stage control                     |
| Disable motor      | `DisableDevice()`                     | Disable motor output                     |

---

## Details

### Identify device
- **Command:** `Identify()`
- **Description:** Blink the controller LED so you can identify which physical unit is connected.

### Home stage
- **Command:** `Home()` (with timeout)
- **Description:** Move the stage to the reference (zero) position. Typically called after connect before other moves.

### Move to position
- **Command:** `MoveAbsolute(position)` or `MoveTo(position, timeout)`
- **Description:** Move to an exact angle (degrees). Position is given as a value in the device units (e.g. degrees); Kinesis often uses `System.Decimal` for position.

### Move by offset
- **Command:** `MoveRelative(distance)`
- **Description:** Move by a relative distance from the current position (degrees).

### Jog forward/back
- **Command:** `MoveJog(direction)`
- **Description:** Start continuous small movement in the given direction. Stop with `StopImmediate()` or `StopProfiled()`.

### Stop immediately
- **Command:** `StopImmediate()`
- **Description:** Emergency stop; motion stops as fast as the hardware allows.

### Stop smoothly
- **Command:** `StopProfiled()`
- **Description:** Stop with deceleration for a controlled halt.

### Set speed
- **Command:** `SetVelParams(minVel, accel, maxVel)`
- **Description:** Set velocity parameters: minimum velocity, acceleration, and maximum velocity (e.g. deg/s). Used to control move speed.

### Get position
- **Command:** `GetPosition()` or read `DevicePosition` / `Position`
- **Description:** Read the current angle. Kinesis may return a `.NET Decimal`; convert to float for display (e.g. `float(str(value))`).

### Enable motor
- **Command:** `EnableDevice()`
- **Description:** Enable stage control so moves can be executed. Usually called after connect and polling start.

### Disable motor
- **Command:** `DisableDevice()`
- **Description:** Disable motor output. Often used before disconnect.

---

## Connection flow (typical)

1. `BuildDeviceList()` then get device list by serial.
2. Create device: `KCubeDCServo.CreateKCubeDCServo(serial)`.
3. `Connect(serial)`.
4. `WaitForSettingsInitialized()`, `LoadMotorConfiguration(serial)` (if needed).
5. `StartPolling(intervalMs)`.
6. `EnableDevice()`.
7. Use `Home()`, `MoveTo()` / `MoveAbsolute()`, `GetPosition()`, etc.
8. When done: `StopPolling()`, `DisableDevice()`, `Disconnect()`.

## Implementation reference

- **Instrument module:** `instruments/prm.py` (`PRMConnection`).
- **Kinesis assemblies:** `Thorlabs.MotionControl.DeviceManagerCLI`, `Thorlabs.MotionControl.KCube.DCServoCLI`.
