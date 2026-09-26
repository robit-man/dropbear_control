#!/usr/bin/env python3
"""Small read-only desktop indicator for the Dropbear hardware dashboard."""

from __future__ import annotations

import json
import os
import queue
import threading
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Any

import tkinter as tk


API_URL = os.environ.get(
    "DROPBEAR_DEVICE_API", "http://127.0.0.1:8000/api/hardware/devices"
)
DASHBOARD_URL = os.environ.get("DROPBEAR_DASHBOARD_URL", "http://127.0.0.1:8000")
POLL_MS = 2000
REQUEST_TIMEOUT_SECONDS = 1.5

BACKGROUND = "#10151d"
PANEL = "#18212c"
TEXT = "#eef4fb"
MUTED = "#8fa2b7"
GREEN = "#42d392"
AMBER = "#ffbd59"
RED = "#ff667a"


@dataclass(frozen=True)
class DeviceStatus:
    label: str
    state: str
    detail: str
    color: str


def _bits(value: Any) -> int:
    try:
        return bin(int(value)).count("1")
    except (TypeError, ValueError):
        return 0


def _device_by_role(devices: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    return next((device for device in devices if device.get("role") == role), None)


def _leg_status(devices: list[dict[str, Any]], role: str, label: str) -> DeviceStatus:
    device = _device_by_role(devices, role)
    if not device or not device.get("connected"):
        return DeviceStatus(label, "OFFLINE", "USB controller not present", RED)

    firmware = device.get("firmware") or {}
    health = device.get("health") or {}
    serial_state = str(device.get("serialState") or "unknown")
    version = str(firmware.get("version") or "identity pending")
    version_prefix = "behemoth-observation-protocol-"
    if version.startswith(version_prefix):
        version = version[len(version_prefix):]
    if not health:
        return DeviceStatus(
            label,
            "CONNECTED",
            f"{device.get('tty', '?')} · {serial_state} · {version}",
            AMBER,
        )

    motors = _bits(health.get("motorFreshMask"))
    sensors = _bits(health.get("sensorFreshMask"))
    can_ready = bool(health.get("canReady"))
    runtime_ready = bool(health.get("runtimeReady"))
    if can_ready and runtime_ready and motors == 6:
        state, color = "ONLINE", GREEN
    elif can_ready and runtime_ready:
        state, color = "DEGRADED", AMBER
    else:
        state, color = "FAULT", RED
    detail = f"CAN motors {motors}/6 · AS5600 {sensors}/5 · {device.get('tty', '?')} · {version}"
    return DeviceStatus(label, state, detail, color)


def summarize(snapshot: dict[str, Any]) -> list[DeviceStatus]:
    devices = list(snapshot.get("devices") or [])
    rows = [
        _leg_status(devices, "right", "RIGHT LEG"),
        _leg_status(devices, "left", "LEFT LEG"),
    ]
    neck = _device_by_role(devices, "neck_candidate")
    if neck and neck.get("connected"):
        firmware = neck.get("firmware") or {}
        version = str(firmware.get("version") or "identity pending")
        rows.append(DeviceStatus(
            "HEAD / NECK",
            "CONNECTED",
            f"{neck.get('tty', '?')} · {neck.get('serialState', 'unknown')} · {version}",
            GREEN if version != "identity pending" else AMBER,
        ))
    else:
        rows.append(DeviceStatus("HEAD / NECK", "OFFLINE", "USB controller not present", RED))
    return rows


def fetch_snapshot() -> dict[str, Any]:
    request = urllib.request.Request(API_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.load(response)


class StatusWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Dropbear Robot Status")
        self.root.configure(bg=BACKGROUND)
        self.root.geometry("500x286-24+48")
        self.root.minsize(460, 260)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        heading = tk.Frame(self.root, bg=BACKGROUND)
        heading.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(
            heading,
            text="DROPBEAR · LIVE HARDWARE",
            bg=BACKGROUND,
            fg=TEXT,
            font=("Sans", 12, "bold"),
        ).pack(side="left")
        self.service_label = tk.Label(
            heading,
            text="CHECKING",
            bg=BACKGROUND,
            fg=AMBER,
            font=("Sans", 9, "bold"),
        )
        self.service_label.pack(side="right")

        self.rows: list[tuple[tk.Label, tk.Label]] = []
        for label in ("RIGHT LEG", "LEFT LEG", "HEAD / NECK"):
            frame = tk.Frame(self.root, bg=PANEL, padx=12, pady=9)
            frame.pack(fill="x", padx=16, pady=3)
            left = tk.Frame(frame, bg=PANEL)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(
                left, text=label, bg=PANEL, fg=TEXT, font=("Sans", 10, "bold")
            ).pack(anchor="w")
            detail = tk.Label(
                left, text="Waiting for dashboard API", bg=PANEL, fg=MUTED,
                font=("Sans", 9), anchor="w",
            )
            detail.pack(anchor="w")
            state = tk.Label(
                frame, text="WAIT", bg=PANEL, fg=AMBER, font=("Sans", 9, "bold")
            )
            state.pack(side="right", padx=(10, 0))
            self.rows.append((state, detail))

        footer = tk.Frame(self.root, bg=BACKGROUND)
        footer.pack(fill="x", padx=16, pady=(9, 12))
        self.updated_label = tk.Label(
            footer, text="", bg=BACKGROUND, fg=MUTED, font=("Sans", 8)
        )
        self.updated_label.pack(side="left")
        tk.Button(
            footer,
            text="OPEN DASHBOARD",
            command=lambda: webbrowser.open(DASHBOARD_URL),
            bg="#26384a",
            fg=TEXT,
            activebackground="#31506b",
            activeforeground=TEXT,
            relief="flat",
            padx=10,
            pady=4,
        ).pack(side="right")

        self.results: queue.Queue[tuple[list[DeviceStatus] | None, str]] = queue.Queue()
        self.poll_in_flight = False
        self.root.after(100, self._start_poll)
        self.root.after(100, self._consume_results)

    def _start_poll(self) -> None:
        if not self.poll_in_flight:
            self.poll_in_flight = True
            threading.Thread(target=self._poll, daemon=True).start()
        self.root.after(POLL_MS, self._start_poll)

    def _poll(self) -> None:
        try:
            self.results.put((summarize(fetch_snapshot()), ""))
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
            self.results.put((None, str(error)))

    def _consume_results(self) -> None:
        try:
            while True:
                statuses, error = self.results.get_nowait()
                self.poll_in_flight = False
                if statuses is None:
                    self.service_label.configure(text="API OFFLINE", fg=RED)
                    self.updated_label.configure(text=error[:72])
                    for state, detail in self.rows:
                        state.configure(text="UNKNOWN", fg=RED)
                        detail.configure(text="Dashboard service unavailable")
                    continue
                self.service_label.configure(text="API ONLINE", fg=GREEN)
                from datetime import datetime
                self.updated_label.configure(text=f"Updated {datetime.now().strftime('%H:%M:%S')}")
                for status, (state, detail) in zip(statuses, self.rows):
                    state.configure(text=status.state, fg=status.color)
                    detail.configure(text=status.detail)
        except queue.Empty:
            pass
        self.root.after(200, self._consume_results)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    StatusWindow().run()
