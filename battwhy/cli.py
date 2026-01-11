"""Command-line interface for battwhy."""

import argparse
import json
import sys
from typing import Dict, Optional

from battwhy.battery import get_battery_info, BatteryNotFoundError
from battwhy.cpu import get_top_processes
from battwhy.devices import get_active_devices
from battwhy.wakeups import get_wakeup_info
from battwhy.diagnosis import generate_diagnosis


def format_battery_status(battery_data: Dict) -> str:
    """Format battery status for human-readable output."""
    lines = []
    status = battery_data.get("status", "Unknown")
    capacity = battery_data.get("capacity")

    status_line = f"Battery Status: {status}"
    if capacity is not None:
        status_line += f" ({capacity}%)"
    lines.append(status_line)

    power_watts = battery_data.get("power_watts")
    if power_watts is not None:
        if battery_data["status"] == "Discharging":
            lines.append(f"Current Power Draw: ~{power_watts:.2f}W")
        elif battery_data["status"] == "Charging":
            lines.append(f"Current Power Input: ~{power_watts:.2f}W")

    remaining_hours = battery_data.get("estimated_remaining_hours")
    if remaining_hours is not None and battery_data["status"] == "Discharging":
        if remaining_hours < 24:
            lines.append(f"Estimated Remaining: ~{remaining_hours:.1f} hours")
        else:
            days = remaining_hours / 24
            lines.append(f"Estimated Remaining: ~{days:.1f} days")

    return "\n".join(lines)


def format_cpu_info(overall_cpu: float, processes) -> str:
    """Format CPU information for human-readable output."""
    lines = []
    lines.append(f"Overall CPU Usage: {overall_cpu:.1f}%")
    lines.append("")
    lines.append("Top CPU Processes:")
    if not processes:
        lines.append("  (no processes using significant CPU)")
    else:
        for i, proc in enumerate(processes, 1):
            lines.append(f"  {i}. {proc.name} (PID {proc.pid}) - {proc.cpu_percent:.1f}%")
    return "\n".join(lines)


def format_devices(devices) -> str:
    """Format device information for human-readable output."""
    lines = []
    lines.append("Active Devices:")
    if not devices:
        lines.append("  (no active power-hungry devices detected)")
    else:
        for device in devices:
            details = f" - {device.name}"
            if device.details:
                details += f" ({device.details})"
            lines.append(details)
    return "\n".join(lines)


def format_wakeups(wakeup_info: Optional[Dict]) -> str:
    """Format wakeup information for human-readable output."""
    if not wakeup_info:
        return "Wakeup Rate: (unavailable)"

    lines = []
    ctx_switches = wakeup_info.get("context_switches_per_sec")
    interrupts = wakeup_info.get("interrupts_per_sec")
    level = wakeup_info.get("wakeup_level", "unknown")

    if ctx_switches is not None:
        lines.append(f"Context Switches: {ctx_switches:.0f}/sec")
    if interrupts is not None:
        lines.append(f"Interrupts: {interrupts:.0f}/sec")
    lines.append(f"Wakeup Level: {level}")

    return "Wakeup Info: " + ", ".join(lines)


def format_output(
    battery_data: Dict,
    overall_cpu: float,
    processes,
    devices,
    wakeup_info: Optional[Dict],
    diagnosis,
    no_color: bool = False,
) -> str:
    """Format complete output for human-readable display."""
    lines = []
    lines.append("=" * 60)
    lines.append("BATTERY DRAIN DIAGNOSIS")
    lines.append("=" * 60)
    lines.append("")

    # Battery status
    lines.append(format_battery_status(battery_data))
    lines.append("")

    # CPU info
    lines.append(format_cpu_info(overall_cpu, processes))
    lines.append("")

    # Devices
    lines.append(format_devices(devices))
    lines.append("")

    # Wakeups (optional)
    if wakeup_info:
        lines.append(format_wakeups(wakeup_info))
        lines.append("")

    # Diagnosis
    lines.append("-" * 60)
    lines.append("DIAGNOSIS")
    lines.append("-" * 60)
    lines.append("")
    lines.append(diagnosis.to_text())

    return "\n".join(lines)


def output_json(
    battery_data: Dict,
    overall_cpu: float,
    processes,
    devices,
    wakeup_info: Optional[Dict],
    diagnosis,
) -> str:
    """Output data as JSON."""
    output = {
        "battery": battery_data,
        "cpu": {
            "overall_percent": overall_cpu,
            "top_processes": [
                {"pid": p.pid, "name": p.name, "cpu_percent": p.cpu_percent}
                for p in processes
            ],
        },
        "devices": [d.to_dict() for d in devices],
        "wakeups": wakeup_info,
        "diagnosis": diagnosis.to_dict(),
    }
    return json.dumps(output, indent=2)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Diagnose laptop battery drain on Linux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  battwhy                    # Quick diagnosis
  battwhy --duration 10      # Longer CPU sampling
  battwhy --top 10           # Show top 10 CPU processes
  battwhy --json             # Output as JSON
  battwhy --no-color         # Disable colored output
        """,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="CPU sampling duration in seconds (default: 2.0)",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top CPU processes to show (default: 5)",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )

    args = parser.parse_args()

    # Collect data
    try:
        battery_data = get_battery_info()
    except BatteryNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading battery information: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        overall_cpu, top_processes = get_top_processes(duration=args.duration, top_n=args.top)
    except Exception as e:
        print(f"Warning: Could not sample CPU usage: {e}", file=sys.stderr)
        overall_cpu = 0.0
        top_processes = []

    try:
        active_devices = get_active_devices()
    except Exception as e:
        print(f"Warning: Could not check devices: {e}", file=sys.stderr)
        active_devices = []

    wakeup_info = None
    try:
        # Sample wakeups using the same duration as CPU
        wakeup_info = get_wakeup_info(duration=args.duration)
    except Exception as e:
        # Wakeups are optional, so we don't fail if they can't be read
        pass

    # Generate diagnosis
    try:
        diagnosis = generate_diagnosis(
            battery_data=battery_data,
            overall_cpu_percent=overall_cpu,
            top_processes=top_processes,
            active_devices=active_devices,
            wakeup_info=wakeup_info,
        )
    except Exception as e:
        print(f"Warning: Could not generate diagnosis: {e}", file=sys.stderr)
        # Create a minimal diagnosis
        from battwhy.diagnosis import Diagnosis
        diagnosis = Diagnosis()
        diagnosis.add_issue(f"Error generating diagnosis: {e}", severity="low")

    # Output results
    if args.json:
        print(output_json(
            battery_data=battery_data,
            overall_cpu=overall_cpu,
            processes=top_processes,
            devices=active_devices,
            wakeup_info=wakeup_info,
            diagnosis=diagnosis,
        ))
    else:
        print(format_output(
            battery_data=battery_data,
            overall_cpu=overall_cpu,
            processes=top_processes,
            devices=active_devices,
            wakeup_info=wakeup_info,
            diagnosis=diagnosis,
            no_color=args.no_color,
        ))


if __name__ == "__main__":
    main()
