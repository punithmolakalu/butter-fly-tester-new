# Gentec INTEGRA Power Meter Command List

## Identification / Interface
- `*VER` - Query instrument version/identification
  - Returns: Version string (e.g., "Integra...")
  - Used for: Connection testing and device identification
  - Format: Text command, no CR/LF needed; response ends with CR/LF

## Measurement / Reading
- `*CVU` - Get Current Value (Current displayed value)
  - Returns: Current power reading with unit (e.g., "1.234 W" or "1234.5 mW")
  - Used for: Reading the current power measurement displayed on the device
  - Format: Text command, no CR/LF needed; response ends with CR/LF
  - Response parsing: Extract numeric value using regex pattern `[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?`
  - Unit detection: Response may contain "W", "mW", "µW", "nW" or similar indicators

## Connection Settings
- **Baud Rate**: 115200 (default for RS-232), USB ignores baud rate
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **Timeout**: 0.3-0.5 seconds (recommended)
- **DTR/RTS**: Set to True (may help with some devices)

## Communication Protocol
- Commands are ASCII text starting with '*'
- No CR/LF needed when sending commands
- Responses end with CR/LF
- Commands should be sent as bytes: `cmd.encode("ascii", errors="ignore")`
- Responses should be decoded: `response.decode("ascii", errors="ignore").strip()`

## Auto-Detection
- Probe ports using `*VER` command
- Prioritize ports with descriptions containing: "integra", "usb-meter", "meter", "opto", "gentec"
- Try multiple baud rates if default fails: 115200, 9600, 19200, 38400, 57600, 230400








