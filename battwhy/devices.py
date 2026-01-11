"""Detect active power-hungry devices (Wi-Fi, GPU, USB)."""

from pathlib import Path
from typing import List, Dict, Optional


class ActiveDevice:
    """Represents an active power-consuming device."""

    def __init__(self, device_type: str, name: str, status: str, details: Optional[str] = None):
        self.device_type = device_type
        self.name = name
        self.status = status
        self.details = details

    def __repr__(self):
        if self.details:
            return f"{self.device_type}: {self.name} ({self.status}) - {self.details}"
        return f"{self.device_type}: {self.name} ({self.status})"

    def to_dict(self):
        """Convert to dictionary for JSON output."""
        result = {
            "type": self.device_type,
            "name": self.name,
            "status": self.status,
        }
        if self.details:
            result["details"] = self.details
        return result


def check_wifi_interfaces() -> List[ActiveDevice]:
    """
    Check for active Wi-Fi interfaces.

    Returns:
        List of active Wi-Fi devices.
    """
    active_wifi = []
    net_dir = Path("/sys/class/net")

    if not net_dir.exists():
        return active_wifi

    for interface_dir in net_dir.iterdir():
        interface_name = interface_dir.name

        # Skip loopback and virtual interfaces that aren't wireless
        if interface_name.startswith("lo") or interface_name.startswith("docker") or \
           interface_name.startswith("br-") or interface_name.startswith("veth"):
            continue

        # Check if it's a wireless interface
        # Look for wireless directory or check if name starts with wl (wlan, wlp, etc.)
        wireless_dir = interface_dir / "wireless"
        is_wireless = wireless_dir.exists() or interface_name.startswith("wl") or \
                     interface_name.startswith("wlp") or interface_name.startswith("wlan")

        if not is_wireless:
            continue

        # Check operational state
        operstate_file = interface_dir / "operstate"
        if operstate_file.exists():
            try:
                operstate = operstate_file.read_text().strip()
                if operstate == "up":
                    # Check if connected (carrier is up)
                    carrier_file = interface_dir / "carrier"
                    carrier = "connected" if carrier_file.exists() and carrier_file.read_text().strip() == "1" else "disconnected"
                    active_wifi.append(ActiveDevice(
                        device_type="Wi-Fi",
                        name=interface_name,
                        status="UP",
                        details=f"operstate: {operstate}, carrier: {carrier}"
                    ))
            except (OSError, IOError):
                pass

    return active_wifi


def check_dedicated_gpu() -> List[ActiveDevice]:
    """
    Check for active dedicated GPU.

    Returns:
        List containing the dedicated GPU if active, empty list otherwise.
    """
    gpu_devices = []
    drm_dir = Path("/sys/class/drm")

    if not drm_dir.exists():
        return gpu_devices

    # Check each DRM card
    for card_dir in drm_dir.iterdir():
        if not card_dir.name.startswith("card"):
            continue

        # Check if this is a discrete GPU (not integrated)
        # Usually discrete GPUs have a device directory with power_state
        device_dir = card_dir / "device"
        if not device_dir.exists():
            continue

        # Check power state
        power_state_file = device_dir / "power_state"
        if power_state_file.exists():
            try:
                power_state = power_state_file.read_text().strip()
                # Common states: D0 (fully on), D1-D3 (various sleep states)
                if power_state.startswith("D0") or power_state == "unknown":
                    # Check vendor/device info
                    vendor_file = device_dir / "vendor"
                    device_file = device_dir / "device"
                    vendor_id = None
                    device_id = None

                    if vendor_file.exists():
                        try:
                            vendor_id = vendor_file.read_text().strip()
                        except (OSError, IOError):
                            pass

                    if device_file.exists():
                        try:
                            device_id = device_file.read_text().strip()
                        except (OSError, IOError):
                            pass

                    details = f"power_state: {power_state}"
                    if vendor_id and device_id:
                        details += f", vendor: {vendor_id}, device: {device_id}"

                    gpu_devices.append(ActiveDevice(
                        device_type="Dedicated GPU",
                        name=card_dir.name,
                        status="active",
                        details=details
                    ))
            except (OSError, IOError):
                pass

        # Alternative: check runtime PM status
        runtime_status_file = device_dir / "power" / "runtime_status"
        if runtime_status_file.exists():
            try:
                runtime_status = runtime_status_file.read_text().strip()
                if runtime_status == "active":
                    # Only add if not already added via power_state check
                    if not gpu_devices:
                        gpu_devices.append(ActiveDevice(
                            device_type="Dedicated GPU",
                            name=card_dir.name,
                            status="active",
                            details=f"runtime_status: {runtime_status}"
                        ))
            except (OSError, IOError):
                pass

    return gpu_devices


def check_usb_devices() -> List[ActiveDevice]:
    """
    Check for active USB devices.

    Returns:
        List of active USB devices that are not in power-saving mode.
    """
    active_usb = []
    usb_bus_dir = Path("/sys/bus/usb/devices")

    if not usb_bus_dir.exists():
        return active_usb

    for usb_device_dir in usb_bus_dir.iterdir():
        device_name = usb_device_dir.name

        # Skip bus controllers and hubs (they're always active)
        if device_name.startswith("usb") and len(device_name) == 5:
            continue

        # Check power control and runtime status
        power_dir = usb_device_dir / "power"
        if not power_dir.exists():
            continue

        control_file = power_dir / "control"
        runtime_status_file = power_dir / "runtime_status"

        control = None
        runtime_status = None

        if control_file.exists():
            try:
                control = control_file.read_text().strip()
            except (OSError, IOError):
                pass

        if runtime_status_file.exists():
            try:
                runtime_status = runtime_status_file.read_text().strip()
            except (OSError, IOError):
                pass

        # Device is active if runtime_status is "active" or control is "on"
        is_active = False
        if runtime_status == "active":
            is_active = True
        elif control == "on":
            is_active = True

        if is_active:
            # Try to get product name
            product_file = usb_device_dir / "product"
            product_name = None
            if product_file.exists():
                try:
                    product_name = product_file.read_text().strip()
                except (OSError, IOError):
                    pass

            device_display_name = product_name if product_name else device_name

            details = f"runtime_status: {runtime_status or 'unknown'}"
            if control:
                details += f", control: {control}"

            active_usb.append(ActiveDevice(
                device_type="USB",
                name=device_display_name,
                status="active",
                details=details
            ))

    return active_usb


def check_bluetooth() -> List[ActiveDevice]:
    """
    Check for active Bluetooth adapter.

    Returns:
        List containing Bluetooth adapter if active, empty list otherwise.
    """
    bluetooth_devices = []

    # Check for Bluetooth devices in /sys/class/bluetooth
    bt_dir = Path("/sys/class/bluetooth")
    if bt_dir.exists():
        for bt_device_dir in bt_dir.iterdir():
            if bt_device_dir.is_dir():
                bluetooth_devices.append(ActiveDevice(
                    device_type="Bluetooth",
                    name=bt_device_dir.name,
                    status="present",
                    details="Bluetooth adapter detected"
                ))

    # Alternative: check via rfkill
    rfkill_dir = Path("/sys/class/rfkill")
    if rfkill_dir.exists():
        for rfkill_dir_item in rfkill_dir.iterdir():
            if not rfkill_dir_item.is_dir():
                continue

            name_file = rfkill_dir_item / "name"
            type_file = rfkill_dir_item / "type"
            state_file = rfkill_dir_item / "state"

            try:
                if type_file.exists() and name_file.exists() and state_file.exists():
                    device_type = type_file.read_text().strip()
                    if device_type == "bluetooth":
                        name = name_file.read_text().strip()
                        state = int(state_file.read_text().strip())
                        # state 0 = soft-blocked or hard-blocked, 1 = unblocked
                        if state == 1:
                            bluetooth_devices.append(ActiveDevice(
                                device_type="Bluetooth",
                                name=name,
                                status="unblocked",
                                details="Bluetooth is not blocked"
                            ))
            except (OSError, IOError, ValueError):
                pass

    return bluetooth_devices


def get_active_devices() -> List[ActiveDevice]:
    """
    Get all active power-consuming devices.

    Returns:
        List of all active devices.
    """
    all_devices = []

    # Check Wi-Fi
    all_devices.extend(check_wifi_interfaces())

    # Check dedicated GPU
    all_devices.extend(check_dedicated_gpu())

    # Check USB devices (limit to avoid too much noise)
    usb_devices = check_usb_devices()
    if len(usb_devices) <= 10:  # Only show if reasonable number
        all_devices.extend(usb_devices)

    # Check Bluetooth
    all_devices.extend(check_bluetooth())

    return all_devices
