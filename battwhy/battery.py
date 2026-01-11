"""Read battery information from /sys/class/power_supply."""

import os
from pathlib import Path
from typing import Dict, Optional, List


class BatteryNotFoundError(Exception):
    """Raised when no battery is found on the system."""


def read_sysfs_value(path: Path) -> Optional[str]:
    """Read a value from sysfs, returning None if file doesn't exist or can't be read."""
    try:
        if path.exists() and path.is_file():
            return path.read_text().strip()
    except (OSError, IOError, PermissionError):
        pass
    return None


def parse_int_value(value: Optional[str], scale: int = 1) -> Optional[int]:
    """Parse an integer value from sysfs, applying scale factor."""
    if value is None:
        return None
    try:
        return int(value) // scale
    except (ValueError, TypeError):
        return None


def find_batteries() -> List[Path]:
    """Find all battery devices in /sys/class/power_supply."""
    power_supply_dir = Path("/sys/class/power_supply")
    if not power_supply_dir.exists():
        return []

    batteries = []
    for device_dir in power_supply_dir.iterdir():
        type_file = device_dir / "type"
        device_type = read_sysfs_value(type_file)
        if device_type == "Battery":
            batteries.append(device_dir)

    return batteries


def read_battery_data(battery_path: Path) -> Dict:
    """Read battery data from a single battery device."""
    data = {
        "name": battery_path.name,
        "status": None,
        "capacity": None,
        "capacity_level": None,
        "power_now": None,
        "current_now": None,
        "voltage_now": None,
        "energy_now": None,
        "energy_full": None,
        "energy_full_design": None,
        "voltage_min_design": None,
    }

    # Status (Charging, Discharging, Full, Not charging, etc.)
    data["status"] = read_sysfs_value(battery_path / "status")

    # Capacity (percentage)
    data["capacity"] = parse_int_value(read_sysfs_value(battery_path / "capacity"))

    # Capacity level (Normal, Low, Critical, etc.)
    data["capacity_level"] = read_sysfs_value(battery_path / "capacity_level")

    # Power/Current/Voltage values are in micro-units (μW, μA, μV)
    power_now = read_sysfs_value(battery_path / "power_now")
    if power_now is None:
        # Fallback: try current_now * voltage_now
        current = parse_int_value(read_sysfs_value(battery_path / "current_now"), scale=1000)  # μA to mA
        voltage = parse_int_value(read_sysfs_value(battery_path / "voltage_now"), scale=1000)  # μV to mV
        if current is not None and voltage is not None:
            # Power in mW
            data["power_now"] = (current * voltage) // 1000  # Convert to mW, then to W equivalent
            data["power_now"] = data["power_now"] * 1000  # Keep in μW for consistency
        else:
            data["power_now"] = None
    else:
        data["power_now"] = parse_int_value(power_now)

    # Current (microamperes)
    data["current_now"] = parse_int_value(read_sysfs_value(battery_path / "current_now"))

    # Voltage (microvolts)
    data["voltage_now"] = parse_int_value(read_sysfs_value(battery_path / "voltage_now"))

    # Energy (micro-Watt-hours)
    data["energy_now"] = parse_int_value(read_sysfs_value(battery_path / "energy_now"))
    data["energy_full"] = parse_int_value(read_sysfs_value(battery_path / "energy_full"))
    data["energy_full_design"] = parse_int_value(read_sysfs_value(battery_path / "energy_full_design"))

    # Voltage min design (microvolts)
    data["voltage_min_design"] = parse_int_value(read_sysfs_value(battery_path / "voltage_min_design"))

    return data


def get_battery_info() -> Dict:
    """
    Get battery information from the system.

    Returns:
        Dictionary with battery data. If no battery is found, raises BatteryNotFoundError.

    Raises:
        BatteryNotFoundError: If no battery is found on the system.
    """
    batteries = find_batteries()

    if not batteries:
        raise BatteryNotFoundError("No battery found on this system. This tool is designed for laptops.")

    # Use the first battery (most laptops have one)
    # TODO: Support multiple batteries if needed
    battery_data = read_battery_data(batteries[0])

    # Calculate estimated power draw in watts
    power_watts = None
    if battery_data["power_now"] is not None:
        power_watts = battery_data["power_now"] / 1_000_000.0  # μW to W
    elif battery_data["current_now"] is not None and battery_data["voltage_now"] is not None:
        # Estimate: current (A) * voltage (V) = power (W)
        current_amps = battery_data["current_now"] / 1_000_000.0  # μA to A
        voltage_volts = battery_data["voltage_now"] / 1_000_000.0  # μV to V
        power_watts = current_amps * voltage_volts

    battery_data["power_watts"] = power_watts

    # Estimate remaining capacity if energy_now and energy_full are available
    remaining_hours = None
    if battery_data["energy_now"] is not None and battery_data["energy_full"] is not None:
        energy_remaining_wh = battery_data["energy_now"] / 1_000_000.0  # μWh to Wh
        if power_watts is not None and power_watts > 0:
            remaining_hours = energy_remaining_wh / power_watts

    battery_data["estimated_remaining_hours"] = remaining_hours

    return battery_data
