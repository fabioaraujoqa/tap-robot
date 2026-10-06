"""Executor: roda o cenário em laço, coleta amostras e obedece ao guardião."""
from __future__ import annotations

import json
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .collector import Collector, EventLog
from .guardian import Abort, Guardian
from .scenario import Player, Scenario, Step, WearCounter


class RunDone(Exception):
    """Fim normal: duração ou número de iterações atingido."""


class Runner:
    def __init__(self, sc: Scenario, robot, adb, run_dir: Path, *, wear: WearCounter,
                 probe=None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, echo=print, meta_extra: Optional[dict] = None):
        self.sc, self.robot, self.adb = sc, robot, adb
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.clock, self._sleep, self.echo = clock, sleep, echo
        self.wear = wear
        self.t0 = clock()
        self.events = EventLog(self.run_dir / "events.jsonl", clock, self.t0, echo=echo)
        self.col = Collector(adb, sc.package, self.run_dir, self.events, clock=clock, t0=self.t0)
        self.guard = Guardian(sc, self.col, adb, robot, self.events, clock=clock, probe=probe)
        self.player = Player(sc, robot, adb, sleep=self.idle, clock=clock, on_touch=self._on_touch)
        s = sc.sampling
        self.every = {
            "heartbeat": float(s.get("heartbeat_s", 10)),
            "sample": float(s.get("interval_s", 60)),
            "screenshot": float(s.get("screenshot_every_min", 10)) * 60,
            "calibration": float((sc.calibration_check or {}).get("every_min", 0)) * 60,
        }
        self.next = {k: self.t0 + v for k, v in self.every.items()}
        self.next["heartbeat"] = self.t0  # checa já no começo
        self.meta = {
            "name": sc.name, "package": sc.package, "mode": sc.mode, "seed": self.player.seed,
            "started": datetime.now().isoformat(timespec="seconds"), "scenario": sc.to_dict(),
            **(meta_extra or {}),
        }
        self.adb_ok = True

    # ------------------------------------------------------------ contadores
    def _on_touch(self, step: Step):
        if self.wear.add(1):
            self.events.add("wear_warning", f"a ponteira passou de {self.wear.warn_at} toques acumulados: "
                                             "confira a borracha e o fuso Z")

    @property
    def touches(self) -> int:
        return self.player.touches + len(self.guard.calibration_errors_px)

    def elapsed(self) -> float:
        return self.clock() - self.t0

    # ------------------------------------------------------------ laço
    def tick(self):
        """Checagens periódicas. Enquanto o adb estiver fora, espera aqui (sem tocar)."""
        while True:
            self.guard.check_stop()
            now = self.clock()
            if now >= self.next["heartbeat"]:
                self.next["heartbeat"] = now + self.every["heartbeat"]
                self.adb_ok = self.guard.heartbeat()
            if self.adb_ok:
                break
            self._sleep(min(2.0, self.every["heartbeat"]))

        now = self.clock()
        if now >= self.next["sample"]:
            self.next["sample"] = now + self.every["sample"]
            self._sample()
        if self.every["screenshot"] and now >= self.next["screenshot"]:
            self.next["screenshot"] = now + self.every["screenshot"]
            self.col.screenshot()
        if self.every["calibration"] and self.guard.probe and now >= self.next["calibration"]:
            self.next["calibration"] = now + self.every["calibration"]
            self.guard.robot_call(self.guard.calibration_check)
            self.wear.add(1)
        self.guard.check_touches(self.touches)

    def _sample(self):
        from .adb import AdbError
        try:
            row = self.col.sample(touches=self.touches)
        except AdbError as exc:
            self.events.add("collector_warning", f"amostra perdida: {exc}")
            return
        self.guard.check_sample(row)

    def idle(self, seconds: float):
        """Espera em pedaços de até 1 s, sem parar as checagens."""
        end = self.clock() + seconds
        while True:
            self.tick()
            left = end - self.clock()
            if left <= 0:
                return
            self._sleep(min(1.0, left))

    def _before_step(self, step: Step):
        sc = self.sc
        if sc.duration_min and self.elapsed() >= sc.duration_min * 60:
            raise RunDone(f"duração de {sc.duration_min} min concluída")
        self.tick()

    # ------------------------------------------------------------ execução
    def run(self) -> dict:
        status, reason, kind = "completed", "", ""
        old_handlers = {}

        def on_signal(signum, _frame):
            self.guard.request_stop(f"interrompido por {signal.Signals(signum).name}")

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                old_handlers[sig] = signal.signal(sig, on_signal)
            except ValueError:  # fora da thread principal (ex.: testes)
                pass
        try:
            self.meta["device"] = self.guard.preflight()
            self.events.add("run_start", f"{self.sc.name} [{self.sc.mode}] semente {self.player.seed}")
            self.col.start_logcat(on_event=self.guard.on_event)
            self._sample()
            self.col.screenshot("inicio")
            while True:
                if self.sc.iterations and self.player.iteration >= self.sc.iterations:
                    raise RunDone(f"{self.sc.iterations} iterações concluídas")
                self.player.run_iteration(before_step=self._before_step, call=self.guard.robot_call)
        except RunDone as done:
            reason = str(done)
        except Abort as ab:
            status, reason, kind = ("interrupted" if ab.kind == "user" else "aborted"), ab.reason, ab.kind
            self.events.add("abort" if status == "aborted" else "stopped", ab.reason, kind=ab.kind)
        except Exception as exc:  # noqa: BLE001  bug ou falha inesperada: ainda assim estaciona
            status, reason, kind = "aborted", f"{type(exc).__name__}: {exc}", "error"
            self.events.add("abort", reason, kind="error")
        finally:
            self.guard.safe_park()
            for sig, h in old_handlers.items():
                signal.signal(sig, h)
            self._finish(status, reason, kind)
        return self.meta

    def _finish(self, status, reason, kind):
        try:
            if kind != "adb":  # amostra final direto do coletor, sem o guardião reagir
                self.col.sample(touches=self.touches)
                self.col.screenshot("fim")
        except Exception as exc:  # noqa: BLE001
            self.events.add("collector_warning", f"amostra final: {exc}")
        self.col.stop()
        self.wear.save()
        self.events.add("run_end", reason or status)
        self.meta.update({
            "ended": datetime.now().isoformat(timespec="seconds"),
            "duration_s": round(self.elapsed(), 1),
            "status": status, "reason": reason, "abort_kind": kind,
            "iterations": self.player.iteration, "touches": self.touches,
            "app_restarts": self.guard.restarts, "wear_total_touches": self.wear.total,
            "calibration_errors_px": [round(e, 1) for e in self.guard.calibration_errors_px],
        })
        (self.run_dir / "meta.json").write_text(json.dumps(self.meta, indent=2, ensure_ascii=False), encoding="utf-8")
