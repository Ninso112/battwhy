"""CPU load sampling from /proc/stat and process statistics."""

import os
import time
from pathlib import Path
from typing import Dict, List, Tuple


class CPUStat:
    """CPU statistics from /proc/stat."""

    def __init__(self, user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice):
        self.user = user
        self.nice = nice
        self.system = system
        self.idle = idle
        self.iowait = iowait
        self.irq = irq
        self.softirq = softirq
        self.steal = steal
        self.guest = guest
        self.guest_nice = guest_nice

    @property
    def total_idle(self):
        """Total idle time including iowait."""
        return self.idle + self.iowait

    @property
    def total_active(self):
        """Total active CPU time."""
        return (self.user + self.nice + self.system + self.irq + self.softirq +
                self.steal + self.guest + self.guest_nice)

    @property
    def total(self):
        """Total CPU time."""
        return self.total_idle + self.total_active


def read_cpu_stat() -> CPUStat:
    """Read CPU statistics from /proc/stat."""
    stat_file = Path("/proc/stat")
    if not stat_file.exists():
        raise RuntimeError("/proc/stat not found")

    with stat_file.open() as f:
        line = f.readline()
        if not line.startswith("cpu "):
            raise RuntimeError("Invalid /proc/stat format")

    parts = line.split()
    # Format: cpu user nice system idle iowait irq softirq steal guest guest_nice
    # At least 4 fields are guaranteed (user, nice, system, idle)
    values = [int(x) for x in parts[1:]]

    # Extend with zeros if some fields are missing
    while len(values) < 10:
        values.append(0)

    return CPUStat(
        user=values[0],
        nice=values[1],
        system=values[2],
        idle=values[3],
        iowait=values[4] if len(values) > 4 else 0,
        irq=values[5] if len(values) > 5 else 0,
        softirq=values[6] if len(values) > 6 else 0,
        steal=values[7] if len(values) > 7 else 0,
        guest=values[8] if len(values) > 8 else 0,
        guest_nice=values[9] if len(values) > 9 else 0,
    )


def get_process_cpu_time(pid: int) -> Tuple[int, int]:
    """
    Get CPU time for a process from /proc/[pid]/stat.

    Returns:
        Tuple of (utime, stime) in clock ticks.
    """
    stat_file = Path(f"/proc/{pid}/stat")
    if not stat_file.exists():
        return (0, 0)

    try:
        with stat_file.open() as f:
            line = f.read()
    except (OSError, IOError, PermissionError):
        return (0, 0)

    # Format: pid comm state ppid ... utime stime ...
    # comm can contain spaces and parentheses, so we need to parse carefully
    parts = line.split()

    if len(parts) < 14:
        return (0, 0)

    try:
        # utime is at index 13, stime at index 14 (0-indexed after splitting)
        # But comm can have spaces, so we need to find utime and stime differently
        # They are fields 14 and 15 in the stat file (1-indexed)
        # After the comm field (which ends with ')'), the next fields are:
        # state, ppid, pgrp, session, tty_nr, tty_pgrp, flags, minflt, cminflt,
        # majflt, cmajflt, utime, stime

        # Find the closing paren of comm
        comm_end = line.rfind(')')
        if comm_end == -1:
            return (0, 0)

        # Parse from after comm
        rest_parts = line[comm_end + 1:].split()
        if len(rest_parts) < 13:
            return (0, 0)

        utime = int(rest_parts[11])  # utime
        stime = int(rest_parts[12])  # stime
        return (utime, stime)
    except (ValueError, IndexError):
        return (0, 0)


def get_process_name(pid: int) -> str:
    """Get process name from /proc/[pid]/comm."""
    comm_file = Path(f"/proc/{pid}/comm")
    if comm_file.exists():
        try:
            return comm_file.read_text().strip()
        except (OSError, IOError):
            pass

    # Fallback: try to get from stat
    stat_file = Path(f"/proc/{pid}/stat")
    if stat_file.exists():
        try:
            with stat_file.open() as f:
                line = f.read()
            # Find comm field (between first '(' and last ')')
            start = line.find('(')
            end = line.rfind(')')
            if start != -1 and end != -1 and start < end:
                return line[start + 1:end]
        except (OSError, IOError, PermissionError):
            pass

    return f"PID {pid}"


class ProcessCPUUsage:
    """CPU usage information for a process."""

    def __init__(self, pid: int, name: str, cpu_percent: float):
        self.pid = pid
        self.name = name
        self.cpu_percent = cpu_percent


def sample_cpu_usage(duration: float = 2.0) -> Tuple[float, List[ProcessCPUUsage]]:
    """
    Sample CPU usage over a duration.

    Args:
        duration: Sampling duration in seconds.

    Returns:
        Tuple of (overall_cpu_percent, list of top processes).
    """
    # Get initial CPU stats
    cpu_stat_start = read_cpu_stat()

    # Get initial process CPU times
    proc_dir = Path("/proc")
    process_times_start = {}
    clock_ticks = os.sysconf(os.sysconf_names.get('SC_CLK_TCK', 100))

    for pid_dir in proc_dir.iterdir():
        if not pid_dir.is_dir():
            continue

        try:
            pid = int(pid_dir.name)
        except ValueError:
            continue

        utime, stime = get_process_cpu_time(pid)
        if utime > 0 or stime > 0:
            process_times_start[pid] = (utime, stime)

    # Wait for sampling duration
    time.sleep(duration)

    # Get final CPU stats
    cpu_stat_end = read_cpu_stat()

    # Get final process CPU times
    process_times_end = {}
    for pid_dir in proc_dir.iterdir():
        if not pid_dir.is_dir():
            continue

        try:
            pid = int(pid_dir.name)
        except ValueError:
            continue

        utime, stime = get_process_cpu_time(pid)
        if utime > 0 or stime > 0:
            process_times_end[pid] = (utime, stime)

    # Calculate overall CPU usage
    total_start = cpu_stat_start.total
    total_end = cpu_stat_end.total
    active_start = cpu_stat_start.total_active
    active_end = cpu_stat_end.total_active

    if total_end > total_start:
        total_delta = total_end - total_start
        active_delta = active_end - active_start
        overall_cpu_percent = (active_delta / total_delta) * 100.0
    else:
        overall_cpu_percent = 0.0

    # Calculate per-process CPU usage
    process_usage = []
    all_pids = set(process_times_start.keys()) | set(process_times_end.keys())

    for pid in all_pids:
        start_times = process_times_start.get(pid, (0, 0))
        end_times = process_times_end.get(pid, (0, 0))

        start_total = start_times[0] + start_times[1]
        end_total = end_times[0] + end_times[1]
        cpu_ticks = end_total - start_total

        if cpu_ticks > 0 and total_end > total_start:
            # Calculate CPU percentage
            total_ticks_delta = total_end - total_start
            cpu_percent = (cpu_ticks / total_ticks_delta) * 100.0

            if cpu_percent > 0.1:  # Only include processes using > 0.1% CPU
                name = get_process_name(pid)
                process_usage.append(ProcessCPUUsage(pid, name, cpu_percent))

    # Sort by CPU usage (descending)
    process_usage.sort(key=lambda p: p.cpu_percent, reverse=True)

    return (overall_cpu_percent, process_usage)


def get_top_processes(duration: float = 2.0, top_n: int = 5) -> Tuple[float, List[ProcessCPUUsage]]:
    """
    Get top N CPU-consuming processes.

    Args:
        duration: Sampling duration in seconds.
        top_n: Number of top processes to return.

    Returns:
        Tuple of (overall_cpu_percent, list of top N processes).
    """
    overall_cpu, processes = sample_cpu_usage(duration)
    return (overall_cpu, processes[:top_n])
