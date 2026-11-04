"""Cenário: validação do YAML, variação reproduzível, intervalo mínimo e contagem de toques."""
from pathlib import Path

import pytest

from soak.fake import FakeAdb
from soak.scenario import Player, ScenarioError, WearCounter, load_scenario

ROOT = Path(__file__).resolve().parents[1]
PKG = "io.appium.android.apis"


def base(**kw):
    raw = {"package": PKG, "duration_min": 1, "steps": [{"tap": [360, 800]}]}
    raw.update(kw)
    return raw


class FakeRobot:
    def __init__(self):
        self.calls = []

    def tap_px(self, x, y, dwell_ms=None):
        self.calls.append(("tap", x, y))

    def long_press_px(self, x, y, seconds=1.0):
        self.calls.append(("long_press", x, y, seconds))

    def swipe_px(self, x1, y1, x2, y2, duration_s=0.35):
        self.calls.append(("swipe", x1, y1, x2, y2, duration_s))


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.t += s


def test_exemplos_carregam():
    for name in ("apidemos_soak.yaml", "apidemos_consumo.yaml"):
        sc = load_scenario(ROOT / "soak" / "examples" / name)
        assert sc.package == PKG and sc.steps
    assert load_scenario(ROOT / "soak/examples/apidemos_consumo.yaml").mode == "consumo"


def test_padroes_e_mescla_de_limites():
    sc = load_scenario(base(limits={"max_touches": 10}))
    assert sc.limits["max_touches"] == 10
    assert sc.limits["app_restarts_max"] == 3  # padrão mantido
    assert sc.sampling["interval_s"] == 60 and sc.mode == "soak"


@pytest.mark.parametrize("raw, msg", [
    ({"duration_min": 1, "steps": [{"tap": [1, 1]}]}, "package"),
    (base(duration_min=None), "duration_min ou iterations"),
    (base(steps=[{"wait": 1}]), "nenhum toque"),
    (base(steps=[{"tap": [360]}]), "esperava 2"),
    (base(steps=[{"tap": [1, 1], "swipe": [1, 1, 2, 2]}]), "exatamente uma"),
    (base(steps=[{"tap": [900, 100]}]), "fora da tela"),
    (base(steps=[{"tap": [1, 1]}, {"wait": [3, 1]}]), "tempo inválido"),
    (base(steps=[{"tap": [1, 1]}, {"key": "BACK; rm -rf /"}]), "tecla inválido"),
    (base(mode="turbo"), "mode"),
    (base(calibration_check={"x": 1}), "calibration_check"),
    (base(desconhecido=1), "desconhecidos"),
])
def test_validacao(raw, msg):
    with pytest.raises(ScenarioError, match=msg):
        load_scenario(raw)


def test_jitter_reproduzivel_e_dentro_da_tela():
    sc = load_scenario(base(seed=5, jitter_px=50, steps=[{"tap": [2, 1638]}, {"swipe": [360, 1200, 360, 400]}]))
    runs = []
    for _ in range(2):
        robot, clock = FakeRobot(), Clock()
        p = Player(sc, robot, None, clock.sleep, clock)
        for _ in range(5):
            p.run_iteration()
        runs.append(robot.calls)
        for call in robot.calls:
            for x in (call[1], call[3]) if call[0] == "swipe" else (call[1],):
                assert 4 <= x <= 716
            for y in (call[2], call[4]) if call[0] == "swipe" else (call[2],):
                assert 4 <= y <= 1636
    assert runs[0] == runs[1]  # mesma semente, mesmos toques
    assert any(c[1] != 2 for c in runs[0] if c[0] == "tap")


def test_intervalo_minimo_entre_toques():
    sc = load_scenario(base(min_interval_s=2.0, steps=[{"tap": [100, 100]}, {"wait": 0.5}, {"tap": [200, 200]}]))
    robot, clock = FakeRobot(), Clock()
    Player(sc, robot, None, clock.sleep, clock).run_iteration()
    assert clock.slept == [0.5, 1.5]


def test_acoes_contagem_tecla_e_pausa():
    sc = load_scenario(base(
        steps=[{"tap": [10, 10]}, {"long_press": [20, 20], "seconds": 2}, {"swipe": [1, 2, 3, 4], "duration_s": 0.5},
               {"key": "back"}, {"wait": [1, 2]}],
        pause={"every_iterations": 2, "seconds": 30}, min_interval_s=0,
    ))
    robot, clock, adb = FakeRobot(), Clock(), FakeAdb(PKG)
    touched = []
    p = Player(sc, robot, adb, clock.sleep, clock, on_touch=touched.append)
    p.run_iteration()
    p.run_iteration()
    assert [c[0] for c in robot.calls] == ["tap", "long_press", "swipe"] * 2
    assert robot.calls[1][3] == 2.0 and robot.calls[2][5] == 0.5
    assert p.touches == 6 and len(touched) == 6
    assert 30.0 in clock.slept and p.iteration == 2


def test_wear_counter_acumula_e_avisa_uma_vez(tmp_path):
    path = tmp_path / "wear.json"
    w = WearCounter(path, warn_at=3)
    assert [w.add() for _ in range(4)] == [False, False, True, False]
    w.save()
    w2 = WearCounter(path, warn_at=3)
    assert w2.total == 4 and w2.warned
