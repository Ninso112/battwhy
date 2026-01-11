# battwhy

battwhy is a small Linux command-line tool that explains why your laptop battery is draining fast. It inspects power and activity indicators (CPU load, wakeups, devices, power_supply stats) and summarizes which components likely cause high power usage.

## Features

- **Battery Status**: Reads battery information from `/sys/class/power_supply/*`, including:
  - Current power draw/input
  - Battery capacity and status
  - Estimated remaining time

- **CPU Analysis**: Samples CPU usage over a configurable duration to identify:
  - Overall CPU load
  - Top CPU-consuming processes

- **Device Detection**: Identifies active power-hungry devices:
  - Wi-Fi interfaces
  - Dedicated GPUs
  - USB devices
  - Bluetooth adapters

- **Wakeup Analysis**: Detects system wakeup rates (context switches and interrupts)

- **Diagnostic Summary**: Provides plain-English explanations and recommendations

## Requirements

- Python 3.6 or later
- Linux (primarily designed for laptops)
- Standard library only (no external dependencies)

## Installation

battwhy can be run directly from the source directory:

```bash
# Clone or download the repository
cd battwhy

# Run directly
python3 -m battwhy

# Or make it executable and add to PATH
chmod +x battwhy/__main__.py
```

For system-wide installation, you can create a wrapper script:

```bash
#!/bin/bash
python3 -m battwhy "$@"
```

Save it as `/usr/local/bin/battwhy` (or similar) and make it executable.

## Usage

### Quick Diagnosis

Run battwhy without arguments for a quick diagnosis:

```bash
battwhy
```

This will:
- Read battery status
- Sample CPU usage for 2 seconds
- Check for active devices
- Generate a diagnostic summary

### Longer CPU Sampling

For more accurate CPU measurements, use a longer sampling duration:

```bash
battwhy --duration 10
```

This samples CPU usage for 10 seconds instead of the default 2 seconds.

### Show More CPU Processes

Display the top 10 CPU processes instead of the default 5:

```bash
battwhy --top 10
```

### JSON Output

Get machine-readable JSON output for scripting or automation:

```bash
battwhy --json
```

### Disable Colors

Disable colored output (currently not implemented, but option is available):

```bash
battwhy --no-color
```

### Combined Options

```bash
battwhy --duration 5 --top 10 --json
```

## Examples

### Example Output

```
============================================================
BATTERY DRAIN DIAGNOSIS
============================================================

Battery Status: Discharging (45%)
Current Power Draw: ~12.5W
Estimated Remaining: ~3.2 hours

Overall CPU Usage: 35.2%

Top CPU Processes:
  1. firefox (PID 12345) - 15.2%
  2. chrome (PID 12346) - 8.5%
  3. python3 (PID 12347) - 3.1%

Active Devices:
 - wlan0 (operstate: up, carrier: connected)
 - Dedicated GPU active (card0)

------------------------------------------------------------
DIAGNOSIS
------------------------------------------------------------

Battery drain is MODERATE. Some issues detected:

• High overall CPU usage: 35.2%
• High CPU usage by processes: 'firefox', 'chrome'
• Dedicated GPU active while on battery
• Wi-Fi interface active while on battery

Recommendations:
  - Consider closing or reducing activity of 'firefox'
  - Consider switching to integrated graphics or using GPU power-saving mode
```

## How It Works

battwhy uses heuristics and best-effort guesses to diagnose battery drain. It is not a precise power measurement tool, but rather a helpful diagnostic aid.

### Heuristics

1. **Power Draw Analysis**: 
   - High power draw (>20W): Very high severity
   - Medium power draw (15-20W): Medium severity
   - Low power draw (<5W): Low severity (good)

2. **CPU Usage**:
   - Processes using >20% CPU: High severity
   - Processes using >10% CPU: Medium severity
   - Overall CPU >50%: Very high severity
   - Overall CPU >30%: High severity

3. **Device Impact**:
   - Dedicated GPU active: High severity (significant power consumer)
   - Wi-Fi/Bluetooth active: Medium severity (moderate power consumer)
   - Many USB devices: Medium severity (if >3 devices)

4. **Wakeup Rate**:
   - High context switches (>5000/sec): High wakeup level
   - Moderate (1000-5000/sec): Moderate wakeup level
   - Low (<1000/sec): Low wakeup level

### Data Sources

- **Battery**: `/sys/class/power_supply/*/`
  - Reads `status`, `capacity`, `power_now`, `current_now`, `voltage_now`, `energy_now`, etc.

- **CPU**: `/proc/stat` and `/proc/[pid]/stat`
  - Samples CPU time before and after a duration
  - Calculates per-process CPU usage

- **Devices**: 
  - Wi-Fi: `/sys/class/net/*/operstate`, `/sys/class/net/*/wireless`
  - GPU: `/sys/class/drm/card*/device/power_state`
  - USB: `/sys/bus/usb/devices/*/power/runtime_status`
  - Bluetooth: `/sys/class/bluetooth/*`, `/sys/class/rfkill/*`

- **Wakeups**: `/proc/stat` (ctxt), `/proc/interrupts`

## Limitations

1. **Accuracy**: This tool provides best-effort guesses based on available system information. It does not perform exact power measurements. Actual power consumption may vary.

2. **Hardware Dependencies**: 
   - Battery information depends on what your laptop's ACPI/sysfs provides
   - Some fields may be missing or unavailable on certain hardware
   - GPU detection works best with standard DRM drivers

3. **Platform**: Designed for Linux laptops. Desktop systems will report "No battery found".

4. **Sampling Duration**: CPU sampling requires a short wait time (default 2 seconds). For more accurate results, use longer durations with `--duration`.

5. **Process Identification**: Process names are read from `/proc/[pid]/comm` or `/proc/[pid]/stat`. Some system processes may not have readable names.

6. **Permissions**: Some information may require root access, but battwhy tries to work with standard user permissions where possible.

7. **Wakeup Detection**: Wakeup rate detection is simplified and may not capture all wakeup sources.

## License

This project is licensed under the GNU General Public License v3.0 (GPLv3). See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Disclaimer

This tool is provided as-is without warranty. Use at your own risk. Battery drain diagnosis is inherently imprecise and depends on many factors including hardware, software configuration, and usage patterns.
