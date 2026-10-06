"""Lê os toques reais do celular via `adb shell getevent`.

É o "sensor" da calibração: o robô toca, o celular informa em que pixel sentiu o
toque. Assim a calibração não depende de marcações visuais.
"""
from __future__ import annotations

import re
import statistics
import subprocess
import threading
import time

from .adb import AdbClient


def parse_getevent_lp(text: str):
    """Extrai dispositivos com ABS_MT_POSITION_X/Y de `getevent -lp`."""
    devices, cur = [], None
    for line in text.splitlines():
        m = re.match(r"add device \d+:\s+(\S+)", line)
        if m:
            cur = {"path": m.group(1), "name": "", "max_x": None, "max_y": None}
            devices.append(cur)
            continue
        if cur is None:
            continue
        m = re.search(r'name:\s+"(.*)"', line)
        if m:
            cur["name"] = m.group(1)
        m = re.search(r"ABS_MT_POSITION_X\s*:.*?max (\d+)", line)
        if m:
            cur["max_x"] = int(m.group(1))
        m = re.search(r"ABS_MT_POSITION_Y\s*:.*?max (\d+)", line)
        if m:
            cur["max_y"] = int(m.group(1))
    return [d for d in devices if d["max_x"] and d["max_y"]]


def find_touch_device(adb: AdbClient):
    devices = parse_getevent_lp(adb.shell("getevent", "-lp"))
    if not devices:
        raise RuntimeError(
            "nenhum touchscreen encontrado em `adb shell getevent -lp` "
            "(o celular está conectado e com depuração USB autorizada?)"
        )
    return devices[0]


def get_wm_size(adb: AdbClient):
    """Tamanho físico da tela em px, ex.: (720, 1640)."""
    out = adb.shell("wm", "size")
    sizes = re.findall(r"(\d+)x(\d+)", out)
    if not sizes:
        raise RuntimeError(f"não consegui ler `wm size`: {out!r}")
    w, h = sizes[-1]  # "Override size" (se houver) vem por último
    return int(w), int(h)


_LINE = re.compile(r"(EV_\w+)\s+(\w+)\s+(\w+)")


class TouchReader:
    """Acompanha os toques do celular em segundo plano."""

    def __init__(self, adb: AdbClient, device: dict, screen_w: int, screen_h: int):
        self.adb = adb
        self.device = device
        self.sx = (screen_w - 1) / device["max_x"]
        self.sy = (screen_h - 1) / device["max_y"]
        self.contacts: list[tuple[float, float]] = []  # toques concluídos (px)
        self.down_count = 0
        self.in_contact = False
        self._x = self._y = None
        self._samples: list[tuple[int, int]] = []
        self._proc = None
        self._thread = None

    def start(self):
        self._proc = subprocess.Popen(
            self.adb.base + ["shell", "getevent", "-l", self.device["path"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        time.sleep(0.5)

    def stop(self):
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None

    def _loop(self):
        for line in self._proc.stdout:
            self.handle_line(line)

    def handle_line(self, line: str):
        m = _LINE.search(line)
        if not m:
            return
        ev, name, val = m.groups()
        if ev == "EV_ABS":
            if name == "ABS_MT_POSITION_X":
                self._x = int(val, 16)
            elif name == "ABS_MT_POSITION_Y":
                self._y = int(val, 16)
            elif name == "ABS_MT_TRACKING_ID":
                self._up() if val.lower() == "ffffffff" else self._down()
        elif ev == "EV_KEY" and name == "BTN_TOUCH":
            self._down() if val == "DOWN" else self._up()
        elif ev == "EV_SYN" and name == "SYN_REPORT":
            if self.in_contact and self._x is not None and self._y is not None:
                self._samples.append((self._x, self._y))

    def _down(self):
        if not self.in_contact:
            self.in_contact = True
            self.down_count += 1
            self._samples = []

    def _up(self):
        if self.in_contact:
            self.in_contact = False
            if self._samples:
                rx = statistics.median(s[0] for s in self._samples)
                ry = statistics.median(s[1] for s in self._samples)
                self.contacts.append((rx * self.sx, ry * self.sy))

    def wait_contact(self, count_before: int, timeout: float = 4.0):
        """Espera um novo toque CONCLUÍDO e devolve (x_px, y_px)."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if len(self.contacts) > count_before:
                return self.contacts[-1]
            time.sleep(0.02)
        return None
