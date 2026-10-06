"""Cenário do teste: passos em YAML, variação aleatória reproduzível e contagem de toques."""
from __future__ import annotations

import copy
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import yaml

ACTIONS = ("tap", "swipe", "long_press", "wait", "key")
TOUCH_ACTIONS = ("tap", "swipe", "long_press")

DEFAULTS = {
    "mode": "soak",
    "seed": None,
    "duration_min": None,
    "iterations": None,
    "min_interval_s": 1.0,
    "jitter_px": 0,
    "screen": [720, 1640],
    "pause": {"every_iterations": 0, "seconds": 0},
    "sampling": {"interval_s": 60, "heartbeat_s": 10, "screenshot_every_min": 10},
    "calibration_check": None,
    "limits": {
        "max_touches": 20000,          # por execução
        "app_restarts_max": 3,         # reinícios do app antes de abortar
        "adb_offline_max_s": 120,
        "robot_errors_max": 3,         # erros seguidos do robô/MQTT
        "battery_temp_max_c": 45.0,
        "wear_warn_touches": 50000,    # acumulado da ponteira (todas as execuções)
    },
    "verdict": {
        "mem_slope_warn_mb_h": 5.0,
        "mem_slope_fail_mb_h": 20.0,
        "janky_warn_pct": 10.0,
        "janky_fail_pct": 25.0,
        "temp_warn_c": 40.0,
        "cpu_warn_pct": 30.0,
        "drain_warn_pct_h": 15.0,
    },
}


class ScenarioError(ValueError):
    pass


@dataclass
class Step:
    kind: str
    args: list
    opts: dict = field(default_factory=dict)

    @property
    def touches(self) -> int:
        return 1 if self.kind in TOUCH_ACTIONS else 0


@dataclass
class Scenario:
    name: str
    package: str
    steps: list
    activity: Optional[str] = None
    mode: str = "soak"
    seed: Optional[int] = None
    duration_min: Optional[float] = None
    iterations: Optional[int] = None
    min_interval_s: float = 1.0
    jitter_px: float = 0
    screen: list = field(default_factory=lambda: [720, 1640])
    pause: dict = field(default_factory=dict)
    sampling: dict = field(default_factory=dict)
    calibration_check: Optional[dict] = None
    limits: dict = field(default_factory=dict)
    verdict: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = copy.deepcopy(self.__dict__)
        d["steps"] = [{s.kind: s.args, **s.opts} for s in self.steps]
        return d


def _merge(base: dict, over: Optional[dict]) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _nums(value, n, what) -> list:
    vals = value if isinstance(value, list) else [value]
    if len(vals) != n or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        raise ScenarioError(f"{what}: esperava {n} número(s), veio {value!r}")
    return [float(v) for v in vals]


def parse_step(raw: dict, i: int) -> Step:
    if not isinstance(raw, dict):
        raise ScenarioError(f"passo {i + 1}: deve ser um mapa (ex.: {{tap: [360, 800]}})")
    kinds = [k for k in raw if k in ACTIONS]
    if len(kinds) != 1:
        raise ScenarioError(f"passo {i + 1}: use exatamente uma ação entre {', '.join(ACTIONS)}")
    kind = kinds[0]
    value = raw[kind]
    opts = {k: v for k, v in raw.items() if k != kind}
    where = f"passo {i + 1} ({kind})"
    if kind == "tap":
        args = _nums(value, 2, where)
    elif kind == "long_press":
        args = _nums(value, 2, where)
        opts.setdefault("seconds", 1.0)
    elif kind == "swipe":
        args = _nums(value, 4, where)
        opts.setdefault("duration_s", 0.35)
    elif kind == "wait":
        args = _nums(value, 2 if isinstance(value, list) else 1, where)  # s ou [mín, máx]
        if any(a < 0 for a in args) or (len(args) == 2 and args[0] > args[1]):
            raise ScenarioError(f"{where}: tempo inválido {value!r}")
    else:  # key: tecla via adb (BACK, HOME...). Não é toque físico.
        if not isinstance(value, str) or not value.replace("_", "").isalnum():
            raise ScenarioError(f"{where}: nome de tecla inválido {value!r}")
        args = [value.upper()]
    return Step(kind, args, opts)


def load_scenario(source) -> Scenario:
    """Lê de um caminho YAML ou de um dict, aplica os padrões e valida."""
    raw = source if isinstance(source, dict) else yaml.safe_load(Path(source).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ScenarioError("o cenário deve ser um mapa YAML")
    for key in ("package", "steps"):
        if not raw.get(key):
            raise ScenarioError(f"campo obrigatório ausente: {key}")
    data = _merge(DEFAULTS, {k: v for k, v in raw.items() if k != "steps"})
    data["steps"] = [parse_step(s, i) for i, s in enumerate(raw["steps"])]
    data.setdefault("name", raw["package"])
    unknown = set(data) - set(Scenario.__dataclass_fields__)
    if unknown:
        raise ScenarioError(f"campos desconhecidos: {', '.join(sorted(unknown))}")

    sc = Scenario(**data)
    if sc.mode not in ("soak", "consumo"):
        raise ScenarioError("mode deve ser 'soak' (carregador) ou 'consumo' (bateria)")
    if not sc.duration_min and not sc.iterations:
        raise ScenarioError("defina duration_min ou iterations")
    if not any(s.touches for s in sc.steps):
        raise ScenarioError("o cenário não tem nenhum toque (tap, swipe ou long_press)")
    if sc.min_interval_s < 0 or sc.jitter_px < 0:
        raise ScenarioError("min_interval_s e jitter_px não podem ser negativos")
    if sc.calibration_check is not None:
        cc = {"every_min": 15, "tolerance_px": 30, **sc.calibration_check}
        _nums([cc.get("x"), cc.get("y")], 2, "calibration_check (x, y)")
        sc.calibration_check = cc
    w, h = _nums(sc.screen, 2, "screen")
    for s in sc.steps:
        pts = s.args if s.kind in ("tap", "long_press") else s.args if s.kind == "swipe" else []
        for x, y in zip(pts[0::2], pts[1::2]):
            if not (0 <= x <= w and 0 <= y <= h):
                raise ScenarioError(f"ponto ({x:.0f}, {y:.0f}) fora da tela {w:.0f}x{h:.0f}")
    return sc


class WearCounter:
    """Total acumulado de toques da ponteira, entre execuções (borracha e fuso Z)."""

    def __init__(self, path: Path, warn_at: int):
        self.path = Path(path)
        self.warn_at = int(warn_at)
        try:
            self.total = int(json.loads(self.path.read_text())["touches"])
        except (OSError, ValueError, KeyError):
            self.total = 0
        self.warned = self.total >= self.warn_at

    def add(self, n: int = 1) -> bool:
        """Soma toques. Devolve True na primeira vez que passar do limite de aviso."""
        self.total += n
        if self.total % 50 == 0:
            self.save()
        if not self.warned and self.total >= self.warn_at:
            self.warned = True
            return True
        return False

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"touches": self.total}))


class Player:
    """Executa os passos com variação aleatória (semente fixa = execução reproduzível).

    `sleep` é chamado para toda espera: o executor usa isso para checar o guardião e
    coletar amostras durante as pausas.
    """

    def __init__(self, sc: Scenario, robot, adb, sleep: Callable[[float], None],
                 clock: Callable[[], float] = time.monotonic, on_touch: Callable[[Step], None] = lambda s: None):
        self.sc, self.robot, self.adb = sc, robot, adb
        self.sleep, self.clock, self.on_touch = sleep, clock, on_touch
        self.seed = sc.seed if sc.seed is not None else random.SystemRandom().randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.margin = 4
        self.iteration = 0
        self.touches = 0
        self._last_touch: Optional[float] = None

    def _jitter(self, x, y, step: Step):
        j = float(step.opts.get("jitter_px", self.sc.jitter_px))
        w, h = self.sc.screen
        x = min(max(x + self.rng.uniform(-j, j), self.margin), w - self.margin)
        y = min(max(y + self.rng.uniform(-j, j), self.margin), h - self.margin)
        return round(x, 1), round(y, 1)

    def _respect_interval(self):
        if self._last_touch is not None:
            left = self.sc.min_interval_s - (self.clock() - self._last_touch)
            if left > 0:
                self.sleep(left)

    def run_step(self, step: Step):
        if step.kind == "wait":
            secs = step.args[0] if len(step.args) == 1 else self.rng.uniform(*step.args)
            self.sleep(secs)
            return
        if step.kind == "key":
            try:
                self.adb.shell(f"input keyevent KEYCODE_{step.args[0]}")
            except Exception:  # noqa: BLE001  adb fora: o heartbeat do guardião trata
                pass
            return
        self._respect_interval()
        if step.kind == "tap":
            self.robot.tap_px(*self._jitter(*step.args, step))
        elif step.kind == "long_press":
            self.robot.long_press_px(*self._jitter(*step.args, step), seconds=float(step.opts["seconds"]))
        else:
            x1, y1 = self._jitter(*step.args[:2], step)
            x2, y2 = self._jitter(*step.args[2:], step)
            self.robot.swipe_px(x1, y1, x2, y2, duration_s=float(step.opts["duration_s"]))
        self._last_touch = self.clock()
        self.touches += 1
        self.on_touch(step)

    def run_iteration(self, before_step: Callable[[Step], None] = lambda s: None,
                      call: Callable[[Callable[[], None]], None] = lambda fn: fn()):
        """`before_step` roda antes de cada passo (checagens); `call` envolve os gestos físicos (erros do robô)."""
        for step in self.sc.steps:
            before_step(step)
            if step.touches:
                call(lambda: self.run_step(step))
            else:
                self.run_step(step)
        self.iteration += 1
        p = self.sc.pause
        if p.get("every_iterations") and p.get("seconds") and self.iteration % int(p["every_iterations"]) == 0:
            self.sleep(float(p["seconds"]))
