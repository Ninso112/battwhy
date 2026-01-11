"""Generate diagnostic summary from collected battery, CPU, device, and wakeup data."""

from typing import List, Dict, Optional
from battwhy.cpu import ProcessCPUUsage
from battwhy.devices import ActiveDevice


class Diagnosis:
    """Battery drain diagnosis with issues and recommendations."""

    def __init__(self):
        self.issues = []
        self.recommendations = []
        self.severity = "unknown"

    def add_issue(self, issue: str, severity: str = "medium"):
        """Add an issue to the diagnosis."""
        self.issues.append({"text": issue, "severity": severity})

    def add_recommendation(self, recommendation: str):
        """Add a recommendation to the diagnosis."""
        self.recommendations.append(recommendation)

    def set_severity(self, severity: str):
        """Set overall severity: low, medium, high."""
        self.severity = severity

    def to_dict(self):
        """Convert to dictionary for JSON output."""
        return {
            "severity": self.severity,
            "issues": self.issues,
            "recommendations": self.recommendations,
        }

    def to_text(self) -> str:
        """Convert to plain text summary."""
        lines = []

        if not self.issues:
            lines.append("No significant battery drain issues detected.")
            return "\n".join(lines)

        # Determine overall summary
        if self.severity == "high":
            lines.append("Battery drain is HIGH. Multiple issues detected:")
        elif self.severity == "medium":
            lines.append("Battery drain is MODERATE. Some issues detected:")
        else:
            lines.append("Battery drain appears LOW, but some minor issues detected:")

        lines.append("")

        # List issues
        for issue in self.issues:
            severity_marker = "[HIGH] " if issue["severity"] == "high" else "• "
            lines.append(f"{severity_marker}{issue['text']}")

        # Add recommendations if any
        if self.recommendations:
            lines.append("")
            lines.append("Recommendations:")
            for rec in self.recommendations:
                lines.append(f"  - {rec}")

        return "\n".join(lines)


def generate_diagnosis(
    battery_data: Dict,
    overall_cpu_percent: float,
    top_processes: List[ProcessCPUUsage],
    active_devices: List[ActiveDevice],
    wakeup_info: Optional[Dict] = None,
) -> Diagnosis:
    """
    Generate diagnostic summary from collected data.

    Args:
        battery_data: Battery information from battery module.
        overall_cpu_percent: Overall CPU usage percentage.
        top_processes: List of top CPU-consuming processes.
        active_devices: List of active power-consuming devices.
        wakeup_info: Optional wakeup information.

    Returns:
        Diagnosis object with issues and recommendations.
    """
    diagnosis = Diagnosis()

    # Check battery status
    battery_status = battery_data.get("status", "").lower()
    is_discharging = battery_status == "discharging"
    power_watts = battery_data.get("power_watts")

    if not is_discharging:
        diagnosis.add_issue("Battery is not discharging (charging or full)", severity="low")
        diagnosis.set_severity("low")
        return diagnosis

    # Check power draw
    if power_watts is not None:
        if power_watts > 20:
            diagnosis.add_issue(f"Very high power draw: ~{power_watts:.1f}W", severity="high")
            diagnosis.set_severity("high")
        elif power_watts > 15:
            diagnosis.add_issue(f"High power draw: ~{power_watts:.1f}W", severity="medium")
            if diagnosis.severity != "high":
                diagnosis.set_severity("medium")
        elif power_watts < 5:
            diagnosis.add_issue(f"Low power draw: ~{power_watts:.1f}W (good)", severity="low")
            if diagnosis.severity == "unknown":
                diagnosis.set_severity("low")

    # Check CPU usage
    high_cpu_processes = [p for p in top_processes if p.cpu_percent > 10.0]
    if overall_cpu_percent > 50:
        diagnosis.add_issue(f"Very high overall CPU usage: {overall_cpu_percent:.1f}%", severity="high")
        diagnosis.set_severity("high")
    elif overall_cpu_percent > 30:
        diagnosis.add_issue(f"High overall CPU usage: {overall_cpu_percent:.1f}%", severity="medium")
        if diagnosis.severity != "high":
            diagnosis.set_severity("medium")

    if high_cpu_processes:
        process_names = [p.name for p in high_cpu_processes[:3]]  # Top 3
        if len(high_cpu_processes) == 1:
            p = high_cpu_processes[0]
            diagnosis.add_issue(
                f"High CPU usage by process '{p.name}' ({p.cpu_percent:.1f}%)",
                severity="high" if p.cpu_percent > 20 else "medium"
            )
        else:
            names_str = "', '".join(process_names)
            if len(high_cpu_processes) > 3:
                names_str += f" and {len(high_cpu_processes) - 3} more"
            diagnosis.add_issue(
                f"High CPU usage by processes: '{names_str}'",
                severity="high" if any(p.cpu_percent > 20 for p in high_cpu_processes) else "medium"
            )

        if diagnosis.severity != "high" and any(p.cpu_percent > 20 for p in high_cpu_processes):
            diagnosis.set_severity("high")
        elif diagnosis.severity == "unknown" and any(p.cpu_percent > 10 for p in high_cpu_processes):
            diagnosis.set_severity("medium")

    # Check active devices
    wifi_devices = [d for d in active_devices if d.device_type == "Wi-Fi"]
    gpu_devices = [d for d in active_devices if d.device_type == "Dedicated GPU"]
    usb_devices = [d for d in active_devices if d.device_type == "USB"]
    bluetooth_devices = [d for d in active_devices if d.device_type == "Bluetooth"]

    device_issues = []
    if wifi_devices:
        device_issues.append(f"Wi-Fi interface{'s' if len(wifi_devices) > 1 else ''} active ({', '.join(d.name for d in wifi_devices)})")
    if gpu_devices:
        device_issues.append(f"Dedicated GPU active ({', '.join(d.name for d in gpu_devices)})")
    if bluetooth_devices:
        device_issues.append(f"Bluetooth adapter active ({', '.join(d.name for d in bluetooth_devices)})")
    if len(usb_devices) > 3:  # Only report if many USB devices
        device_issues.append(f"Many active USB devices ({len(usb_devices)})")

    if device_issues:
        # Combine device issues
        if gpu_devices:
            # dGPU is usually a big power consumer
            diagnosis.add_issue("Dedicated GPU is active while on battery", severity="high")
            diagnosis.set_severity("high")
        elif wifi_devices or bluetooth_devices:
            diagnosis.add_issue(" and ".join(device_issues) + " while on battery", severity="medium")
            if diagnosis.severity != "high":
                diagnosis.set_severity("medium")

    # Check wakeups
    if wakeup_info:
        wakeup_level = wakeup_info.get("wakeup_level")
        if wakeup_level == "high":
            diagnosis.add_issue("High system wakeup rate (frequent context switches/interrupts)", severity="medium")
            if diagnosis.severity == "unknown":
                diagnosis.set_severity("medium")

    # Generate recommendations
    if high_cpu_processes:
        top_process = high_cpu_processes[0]
        diagnosis.add_recommendation(f"Consider closing or reducing activity of '{top_process.name}'")

    if gpu_devices:
        diagnosis.add_recommendation("Consider switching to integrated graphics or using GPU power-saving mode")

    if wifi_devices and not is_discharging:
        # Only recommend if there are other issues
        if diagnosis.severity in ("high", "medium"):
            diagnosis.add_recommendation("Consider disabling Wi-Fi if not needed")

    if bluetooth_devices and diagnosis.severity in ("high", "medium"):
        diagnosis.add_recommendation("Consider disabling Bluetooth if not needed")

    if power_watts and power_watts > 15:
        diagnosis.add_recommendation("Check for background processes and reduce system activity")

    # Set default severity if still unknown
    if diagnosis.severity == "unknown":
        diagnosis.set_severity("low")

    return diagnosis
