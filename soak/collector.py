"""Coleta periódica das métricas do celular e registro de eventos."""
from __future__ import annotations

import csv
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from . import parsers
from .adb import AdbError

COLUMNS = [
    "t_s", "time", "pid", "app_alive", "foreground", "screen_on",
    "pss_mb", "java_heap_mb", "native_heap_mb",
    "frames", "janky_frames", "janky_pct", "frame_p90_ms",
    "cpu_pct",
    "battery_pct", "battery_temp_c", "charging", "charge_mah", "voltage_mv",
    "thermal_status", "temp_cpu_c", "temp_skin_c",
    "touches",
]


class EventLog:
    """events.jsonl: um evento por linha, com tempo desde o início (t_s)."""

    def __init__(self, path: Path, clock: Callable[[], float], t0: float, echo=print):
        self.path = Path(path)
        self.clock, self.t0, self.echo = clock, t0, echo
        self._lock = threading.Lock()
        self.events: list[dict] = []

    def add(self, type_: str, detail: str = "", **extra) -> dict:
        ev = {
            "t_s": round(self.clock() - self.t0, 1),
            "time": datetime.now().isoformat(timespec="seconds"),
            "type": type_,
            "detail": detail,
            **extra,
        }
        with self._lock:
            self.events.append(ev)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if self.echo:
            self.echo(f"[{ev['t_s']:>7.0f}s] {type_}: {detail}")
        return ev

    def count(self, *types) -> int:
        with self._lock:
            return sum(1 for e in self.events if e["type"] in types)


class Collector:
    def __init__(self, adb, package: str, run_dir: Path, events: EventLog,
                 clock: Callable[[], float] = time.monotonic, t0: Optional[float] = None):
        self.adb, self.package = adb, package
        self.run_dir = Path(run_dir)
        self.events = events
        self.clock = clock
        self.t0 = clock() if t0 is None else t0
        self.csv_path = self.run_dir / "samples.csv"
        self.shots_dir = self.run_dir / "screenshots"
        self._cpu_prev: Optional[tuple] = None
        self._cpu_pid: Optional[int] = None
        self._logcat_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.last_sample: Optional[dict] = None
        with self.csv_path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)

    # ------------------------------------------------------------ verificação rápida
    def heartbeat(self) -> dict:
        """Estado mínimo para o guardião (barato: ~2 comandos). Lança AdbError se offline."""
        pid = parsers.parse_pidof(self.adb.shell(f"pidof {self.package}"))
        screen = parsers.parse_screen_on(self.adb.shell("dumpsys power | grep -E 'mWakefulness=|Display Power'"))
        return {"pid": pid, "app_alive": pid is not None, "screen_on": screen}

    def foreground(self) -> Optional[str]:
        return parsers.parse_resumed_package(
            self.adb.shell("dumpsys activity activities | grep -E 'ResumedActivity'")
        )

    # ------------------------------------------------------------ amostra completa
    def sample(self, touches: int = 0) -> dict:
        """Uma linha do CSV. Lança AdbError se o aparelho não responder."""
        row = {c: None for c in COLUMNS}
        row["t_s"] = round(self.clock() - self.t0, 1)
        row["time"] = datetime.now().isoformat(timespec="seconds")
        row["touches"] = touches
        row.update(self.heartbeat())
        row["foreground"] = self.foreground()
        pid = row["pid"]

        row.update(parsers.parse_battery(self.adb.shell("dumpsys battery")))
        row.update(self._optional("thermal", lambda: parsers.parse_thermal(self.adb.shell("dumpsys thermalservice"))))
        if pid is not None:
            row.update(self._optional("meminfo", lambda: parsers.parse_meminfo(self.adb.shell(f"dumpsys meminfo {self.package}"))))
            # "reset" devolve os números e zera: cada amostra mede só o intervalo dela.
            row.update(self._optional("gfxinfo", lambda: parsers.parse_gfxinfo(self.adb.shell(f"dumpsys gfxinfo {self.package} reset"))))
            row["cpu_pct"] = self._cpu(pid)
        else:
            self._cpu_prev = None

        self._append(row)
        self.last_sample = row
        return row

    def _optional(self, name, fn) -> dict:
        try:
            return fn()
        except AdbError:
            raise
        except Exception as exc:  # noqa: BLE001  formato inesperado: segue sem essa métrica
            self.events.add("collector_warning", f"{name}: {exc}")
            return {}

    def _cpu(self, pid: int) -> Optional[float]:
        out = self.adb.shell(f"cat /proc/{pid}/stat; head -1 /proc/stat")
        cur = (parsers.parse_proc_pid_stat(out.splitlines()[0] if out else ""), parsers.parse_proc_stat_total(out))
        prev = self._cpu_prev if self._cpu_pid == pid else None
        self._cpu_prev, self._cpu_pid = cur, pid
        pct = parsers.cpu_percent(prev, cur)
        return round(pct, 2) if pct is not None else None

    def _append(self, row: dict):
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["" if row[c] is None else (round(row[c], 3) if isinstance(row[c], float) else row[c]) for c in COLUMNS])

    # ------------------------------------------------------------ evidências
    def screenshot(self, label: str = "") -> Optional[Path]:
        self.shots_dir.mkdir(exist_ok=True)
        t = int(self.clock() - self.t0)
        path = self.shots_dir / f"{t:06d}s{('_' + label) if label else ''}.png"
        try:
            data = self.adb.exec_out("screencap -p")
        except AdbError as exc:
            self.events.add("collector_warning", f"screenshot: {exc}")
            return None
        if not data.startswith(b"\x89PNG"):
            self.events.add("collector_warning", "screenshot: saída não é PNG")
            return None
        path.write_bytes(data)
        return path

    # ------------------------------------------------------------ logcat em segundo plano
    def start_logcat(self, on_event: Optional[Callable[[dict], None]] = None):
        """Acompanha o logcat e registra crash/ANR do app. Reinicia se o adb cair."""
        parser = parsers.LogcatParser(self.package)

        def loop():
            while not self._stop.is_set():
                try:
                    for line in self.adb.logcat_follow():
                        if self._stop.is_set():
                            break
                        for ev in parser.feed(line):
                            kind = ev.pop("type")
                            detail = ev.pop("detail", "")
                            rec = self.events.add(kind, detail, **ev)
                            if on_event:
                                on_event(rec)
                except Exception as exc:  # noqa: BLE001
                    if not self._stop.is_set():
                        self.events.add("collector_warning", f"logcat: {exc}")
                if not self._stop.wait(5):
                    continue  # o logcat terminou (adb caiu?): tenta de novo em 5 s

        self._logcat_thread = threading.Thread(target=loop, daemon=True, name="logcat")
        self._logcat_thread.start()

    def stop(self):
        self._stop.set()
        stop = getattr(self.adb, "stop_logcat", None)
        if stop:
            stop()
