"""Disk/drive detection, cross-platform, no external dependencies.

Windows: enumerates drive letters (A:\\ .. Z:\\) that exist.
Linux/macOS: parses mounted filesystems from /proc/mounts (Linux) or
falls back to a fixed set of common mount points, filtering out pseudo
filesystems (proc, sysfs, tmpfs, etc.) and using shutil.disk_usage.
"""
from __future__ import annotations

import os
import shutil
import string
import sys
from dataclasses import dataclass

PSEUDO_FS = {
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2",
    "pstore", "bpf", "tracefs", "debugfs", "mqueue", "hugetlbfs",
    "securityfs", "autofs", "configfs", "fusectl", "overlay", "squashfs",
    "binfmt_misc", "rpc_pipefs", "efivarfs",
}


@dataclass
class Disk:
    name: str       # display name, e.g. "C:\\" or "/" or "/home"
    path: str       # path to scan
    total: int
    used: int
    free: int


def list_disks() -> list[Disk]:
    if sys.platform.startswith("win"):
        return _list_disks_windows()
    return _list_disks_unix()


def _list_disks_windows() -> list[Disk]:
    disks = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            try:
                usage = shutil.disk_usage(drive)
            except OSError:
                continue
            disks.append(Disk(drive, drive, usage.total, usage.used, usage.free))
    return disks


def _list_disks_unix() -> list[Disk]:
    mounts: list[tuple[str, str]] = []  # (mount_point, fstype)
    seen_points = set()

    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                _dev, mount_point, fstype = parts[0], parts[1], parts[2]
                if fstype in PSEUDO_FS:
                    continue
                if mount_point in seen_points:
                    continue
                seen_points.add(mount_point)
                mounts.append((mount_point, fstype))
    except OSError:
        mounts = [("/", ""), (os.path.expanduser("~"), "")]

    disks = []
    seen_usage: dict[tuple[int, int, int], str] = {}
    for mount_point, _fstype in mounts:
        if not os.path.isdir(mount_point):
            continue  # skip file bind-mounts (e.g. /etc/resolv.conf)
        try:
            usage = shutil.disk_usage(mount_point)
        except OSError:
            continue
        if usage.total == 0:
            continue

        key = (usage.total, usage.used, usage.free)
        existing = seen_usage.get(key)
        if existing is not None and len(existing) <= len(mount_point):
            # same underlying filesystem already represented by a
            # shorter (more relevant) mount point, e.g. "/" vs "/opt/data"
            continue
        seen_usage[key] = mount_point

    for mount_point in seen_usage.values():
        usage = shutil.disk_usage(mount_point)
        disks.append(Disk(mount_point, mount_point, usage.total, usage.used, usage.free))

    # largest first is a reasonable default ordering
    disks.sort(key=lambda d: d.total, reverse=True)
    return disks
