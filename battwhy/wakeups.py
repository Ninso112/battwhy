"""Simple wakeup rate detection from /proc/stat and /proc/interrupts."""

import time
from pathlib import Path
from typing import Dict, Optional, Tuple


def read_context_switches() -> Optional[int]:
    """Read number of context switches from /proc/stat."""
    stat_file = Path("/proc/stat")
    if not stat_file.exists():
        return None

    try:
        with stat_file.open() as f:
            for line in f:
                if line.startswith("ctxt "):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except (OSError, IOError, ValueError):
        pass

    return None


def read_interrupts_total() -> Optional[int]:
    """Read total interrupt count from /proc/interrupts (sum of all interrupts)."""
    interrupts_file = Path("/proc/interrupts")
    if not interrupts_file.exists():
        return None

    try:
        total = 0
        with interrupts_file.open() as f:
            for line in f:
                # Skip header lines
                if line.strip().startswith("CPU") or not line.strip():
                    continue

                # Parse interrupt counts (first number after CPU columns)
                parts = line.split()
                if parts:
                    # Sum all CPU columns (skip the interrupt name at the end)
                    # Format: 0: 12345 0 0 ...  irq_name
                    for part in parts:
                        # Stop at non-numeric (reached interrupt name)
                        try:
                            total += int(part)
                        except ValueError:
                            break
    except (OSError, IOError, ValueError):
        return None

    return total if total > 0 else None


def sample_wakeup_rate(duration: float = 2.0) -> Optional[float]:
    """
    Sample wakeup rate over a duration.

    Uses context switches as a proxy for wakeup rate.

    Args:
        duration: Sampling duration in seconds.

    Returns:
        Wakeup rate (context switches per second) or None if unavailable.
    """
    start_switches = read_context_switches()
    if start_switches is None:
        return None

    time.sleep(duration)

    end_switches = read_context_switches()
    if end_switches is None:
        return None

    if end_switches <= start_switches:
        return None

    wakeup_rate = (end_switches - start_switches) / duration
    return wakeup_rate


def sample_interrupt_rate(duration: float = 2.0) -> Optional[float]:
    """
    Sample interrupt rate over a duration.

    Args:
        duration: Sampling duration in seconds.

    Returns:
        Interrupt rate (interrupts per second) or None if unavailable.
    """
    start_interrupts = read_interrupts_total()
    if start_interrupts is None:
        return None

    time.sleep(duration)

    end_interrupts = read_interrupts_total()
    if end_interrupts is None:
        return None

    if end_interrupts <= start_interrupts:
        return None

    interrupt_rate = (end_interrupts - start_interrupts) / duration
    return interrupt_rate


def get_wakeup_info(duration: float = 2.0) -> Dict:
    """
    Get wakeup information (context switches and interrupts).

    Args:
        duration: Sampling duration in seconds.

    Returns:
        Dictionary with wakeup information.
    """
    wakeup_rate = sample_wakeup_rate(duration)
    interrupt_rate = sample_interrupt_rate(duration)

    # Heuristic: high wakeup/interrupt rate indicates frequent wakeups
    # Thresholds are rough estimates:
    # - > 5000 context switches/sec: high
    # - > 10000 interrupts/sec: high
    wakeup_level = "unknown"
    if wakeup_rate is not None:
        if wakeup_rate > 5000:
            wakeup_level = "high"
        elif wakeup_rate > 1000:
            wakeup_level = "moderate"
        else:
            wakeup_level = "low"

    return {
        "context_switches_per_sec": wakeup_rate,
        "interrupts_per_sec": interrupt_rate,
        "wakeup_level": wakeup_level,
    }
