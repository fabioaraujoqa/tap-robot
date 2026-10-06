"""Celular e robô falsos para o --dry-run e para os testes (sem P1S e sem celular).

O FakeAdb responde aos mesmos comandos que o coletor usa, no formato real do Android,
com números que evoluem no tempo (vazamento de memória, bateria descendo, aquecimento).
Falhas podem ser programadas: crash, ANR, tela apagada, adb fora, superaquecimento.
"""
from __future__ import annotations

import queue
import random
import struct
import time
import zlib
from typing import Callable, Optional

from taprobot.adb import AdbError


def tiny_png(w: int = 36, h: int = 82, rgb=(40, 90, 160)) -> bytes:
    """PNG válido de cor sólida (o "screenshot" do dry-run)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakeAdb:
    def __init__(self, package: str, clock: Callable[[], float] = time.monotonic, charging: bool = True,
                 leak_mb_per_h: float = 6.0, drain_pct_per_h: float = 12.0, seed: int = 1):
        self.package = package
        self.clock = clock
        self.t0 = clock()
        self.rng = random.Random(seed)
        self.charging = charging
        self.leak_mb_per_h = leak_mb_per_h
        self.drain_pct_per_h = drain_pct_per_h
        self.pid: Optional[int] = 12831
        self.screen_on = True
        self.offline = False
        self.extra_temp_c = 0.0
        self.foreground = package
        self.proc_ticks, self.total_ticks = 500, 6_000_000
        self.started = 0  # quantas vezes o app foi (re)aberto
        self._log: "queue.Queue[str]" = queue.Queue()
        self._schedule: list = []  # (t_s, função)
        self._stopped = False

    # ------------------------------------------------------------ falhas programadas
    def at(self, t_s: float, action: Callable[["FakeAdb"], None]):
        self._schedule.append((t_s, action))
        self._schedule.sort(key=lambda x: x[0])

    def _tick(self):
        el = self.clock() - self.t0
        while self._schedule and self._schedule[0][0] <= el:
            self._schedule.pop(0)[1](self)

    def crash(self, kind: str = "java"):
        pid = self.pid or 0
        stamp = time.strftime("%m-%d %H:%M:%S.000")
        if kind == "anr":
            self._log.put(f"{stamp}  1812  1990 E ActivityManager: ANR in {self.package} ({self.package}/.Main)\n")
            return
        self._log.put(f"{stamp} {pid} {pid} E AndroidRuntime: FATAL EXCEPTION: main\n")
        self._log.put(f"{stamp} {pid} {pid} E AndroidRuntime: Process: {self.package}, PID: {pid}\n")
        self._log.put(f"{stamp} {pid} {pid} E AndroidRuntime: java.lang.IllegalStateException: falha simulada\n")
        self._log.put(f"{stamp}  1812  2385 I ActivityManager: Process {self.package} (pid {pid}) has died: fg  TOP\n")
        self.pid = None
        self.foreground = "com.motorola.launcher3"

    # ------------------------------------------------------------ adb
    def shell(self, cmd: str, timeout: float = 20) -> str:
        self._tick()
        if self.offline:
            raise AdbError(f"adb shell: device '{self.package}-fake' not found")
        el_h = (self.clock() - self.t0) / 3600
        if cmd.startswith("pidof"):
            return f"{self.pid}\n" if self.pid else ""
        if cmd.startswith("dumpsys power"):
            return f"  mWakefulness={'Awake' if self.screen_on else 'Asleep'}\n"
        if cmd.startswith("dumpsys activity"):
            return f"  ResumedActivity: ActivityRecord{{d9c30ee u0 {self.foreground}/.Main t107}}\n"
        if cmd.startswith("dumpsys battery"):
            level = 93 if self.charging else max(1, round(93 - self.drain_pct_per_h * el_h))
            temp = 300 + int(40 * min(el_h * 4, 1)) + int(self.extra_temp_c * 10)
            counter = int(4_800_000 * level / 93)
            return (f"Current Battery Service state:\n  AC powered: {str(self.charging).lower()}\n"
                    f"  USB powered: false\n  Charge counter: {counter}\n  status: {2 if self.charging else 3}\n"
                    f"  level: {level}\n  scale: 100\n  voltage: 4100\n  temperature: {temp}\n")
        if cmd.startswith("dumpsys thermalservice"):
            cpu = 38 + 6 * min(el_h * 4, 1) + self.extra_temp_c
            return (f"Thermal Status: {2 if self.extra_temp_c > 10 else 0}\nCurrent temperatures from HAL:\n"
                    f"\tTemperature{{mValue={cpu:.1f}, mType=0, mName=CPU, mStatus=0}}\n"
                    f"\tTemperature{{mValue={cpu - 8:.1f}, mType=3, mName=SKIN, mStatus=0}}\n"
                    "Current cooling devices from HAL:\n")
        if cmd.startswith("dumpsys meminfo"):
            if not self.pid:
                return "No process found for: " + self.package
            pss = 84_000 + int(self.leak_mb_per_h * 1024 * el_h) + self.rng.randint(-800, 800)
            java = 12_600 + int(self.leak_mb_per_h * 700 * el_h)
            return (f" App Summary\n           Java Heap:    {java}      28372\n"
                    f"         Native Heap:     6224       7576\n           TOTAL PSS:    {pss}\n")
        if cmd.startswith("dumpsys gfxinfo"):
            frames = self.rng.randint(300, 900) if self.screen_on else 0
            janky = int(frames * self.rng.uniform(0.02, 0.08 + 0.1 * min(el_h, 1)))
            return f"Total frames rendered: {frames}\nJanky frames: {janky} (x%)\n90th percentile: 14ms\n"
        if cmd.startswith("cat /proc/"):
            self.proc_ticks += self.rng.randint(40, 120)
            self.total_ticks += 6000
            return (f"{self.pid} (um.android.apis) S 804 804 0 0 -1 4194624 13343 0 3387 0 "
                    f"{self.proc_ticks} 72 0 0 20 0 34 0\ncpu  {self.total_ticks} 0 0 0 0 0 0 0 0 0\n")
        if cmd.startswith(("am start", "monkey")):
            self.pid = 20000 + self.started
            self.started += 1
            self.foreground = self.package
            return "Events injected: 1\n"
        if cmd.startswith(("settings get", "getprop")):
            return {
                "settings get system screen_brightness": "144",
                "settings get system screen_brightness_mode": "0",
                "settings get system screen_off_timeout": "1800000",
                "settings get global stay_on_while_plugged_in": "7",
                "getprop ro.product.model": "moto g06 (simulado)",
                "getprop ro.build.version.release": "15",
            }.get(cmd, "") + "\n"
        if cmd.startswith("input keyevent"):
            return ""
        return ""

    def exec_out(self, cmd: str, timeout: float = 30) -> bytes:
        self._tick()
        if self.offline:
            raise AdbError("adb exec-out: device offline")
        return tiny_png()

    def logcat_follow(self):
        self._stopped = False
        while not self._stopped:
            self._tick()
            if self.offline:
                raise AdbError("logcat: device offline")
            try:
                yield self._log.get(timeout=0.2)
            except queue.Empty:
                continue

    def stop_logcat(self):
        self._stopped = True


class FakeTouchProbe:
    """Simula o TouchReader na verificação de calibração: devolve o ponto tocado + erro."""

    def __init__(self, error_px: float = 3.0, seed: int = 2):
        self.error_px = error_px
        self.rng = random.Random(seed)
        self.miss = False

    def __call__(self, robot, x: float, y: float):
        robot.tap_px(x, y)
        if self.miss:
            return None
        return (x + self.rng.uniform(-self.error_px, self.error_px),
                y + self.rng.uniform(-self.error_px, self.error_px))
