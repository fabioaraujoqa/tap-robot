"""Guardião + executor com relógio simulado: cada falha deve parar o teste e estacionar a ponteira."""
import json
import signal

import pytest

from soak.fake import FakeAdb, FakeTouchProbe
from soak.runner import Runner
from soak.scenario import WearCounter, load_scenario

PKG = "io.appium.android.apis"


class Clock:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.001)


class FakeRobot:
    def __init__(self, fail_with=None, fail_times=0):
        self.taps, self.parked = [], 0
        self.fail_with, self.fail_times = fail_with, fail_times

    def _gesture(self, *a):
        if self.fail_times:
            self.fail_times -= 1
            raise self.fail_with
        self.taps.append(a)

    def tap_px(self, x, y, dwell_ms=None):
        self._gesture("tap", x, y)

    def long_press_px(self, x, y, seconds=1.0):
        self._gesture("long", x, y)

    def swipe_px(self, *a, **k):
        self._gesture("swipe", *a)

    def park(self):
        self.parked += 1


def make(tmp_path, *, charging=True, robot=None, probe=None, **sc_over):
    raw = {
        "package": PKG, "activity": ".ApiDemos", "duration_min": 5, "seed": 1, "min_interval_s": 1,
        "sampling": {"interval_s": 30, "heartbeat_s": 5, "screenshot_every_min": 2},
        "steps": [{"tap": [360, 800]}, {"wait": 2}],
    }
    raw.update(sc_over)
    sc = load_scenario(raw)
    clock = Clock()
    adb = FakeAdb(PKG, clock=clock, charging=charging)
    robot = robot or FakeRobot()
    runner = Runner(sc, robot, adb, tmp_path / "run", wear=WearCounter(tmp_path / "wear.json", 10**9),
                    probe=probe, clock=clock, sleep=clock.sleep, echo=None)
    return runner, adb, robot, clock


def types(runner):
    return [e["type"] for e in runner.events.events]


def test_execucao_normal_completa(tmp_path):
    runner, adb, robot, clock = make(tmp_path)
    meta = runner.run()
    assert meta["status"] == "completed" and "duração" in meta["reason"]
    assert robot.parked == 1 and meta["touches"] == len(robot.taps) > 50
    d = tmp_path / "run"
    assert json.loads((d / "meta.json").read_text())["status"] == "completed"
    assert len((d / "samples.csv").read_text().splitlines()) >= 10
    assert list((d / "screenshots").glob("*.png"))


def test_crash_reinicia_app_e_continua(tmp_path):
    runner, adb, robot, clock = make(tmp_path)
    adb.at(60, lambda a: a.crash())
    meta = runner.run()
    assert meta["status"] == "completed" and meta["app_restarts"] == 1
    assert "app_restart" in types(runner) and robot.parked == 1


def test_crashes_demais_abortam(tmp_path):
    runner, adb, robot, clock = make(tmp_path, limits={"app_restarts_max": 2})
    for t in (30, 60, 90):
        adb.at(t, lambda a: a.crash())
    meta = runner.run()
    assert meta["status"] == "aborted" and meta["abort_kind"] == "app"
    assert robot.parked == 1


def test_anr_forca_reinicio(tmp_path):
    runner, adb, robot, clock = make(tmp_path)
    runner.guard.on_event({"type": "anr"})
    started_before = adb.started
    runner.run()
    assert any(e["type"] == "app_restart" and "ANR" in e["detail"] for e in runner.events.events)
    assert adb.started > started_before


def test_tela_apagada_aborta(tmp_path):
    runner, adb, robot, clock = make(tmp_path)
    adb.at(45, lambda a: setattr(a, "screen_on", False))
    meta = runner.run()
    assert meta["abort_kind"] == "screen" and robot.parked == 1
    assert meta["duration_s"] < 60


def test_adb_fora_por_muito_tempo_aborta_sem_tocar(tmp_path):
    runner, adb, robot, clock = make(tmp_path, limits={"adb_offline_max_s": 40})
    adb.at(30, lambda a: setattr(a, "offline", True))
    taps_at = []
    orig = robot.tap_px
    robot.tap_px = lambda x, y, dwell_ms=None: (taps_at.append(clock() - runner.t0), orig(x, y))
    meta = runner.run()
    assert meta["abort_kind"] == "adb" and robot.parked == 1
    assert max(taps_at) < 36  # nenhum toque depois que o adb caiu (+ 1 heartbeat)


def test_adb_volta_e_teste_segue(tmp_path):
    runner, adb, robot, clock = make(tmp_path)
    adb.at(30, lambda a: setattr(a, "offline", True))
    adb.at(50, lambda a: setattr(a, "offline", False))
    meta = runner.run()
    assert meta["status"] == "completed"
    assert "adb_offline" in types(runner) and "adb_online" in types(runner)


def test_bateria_quente_aborta(tmp_path):
    runner, adb, robot, clock = make(tmp_path, limits={"battery_temp_max_c": 40})
    adb.at(40, lambda a: setattr(a, "extra_temp_c", 15))
    meta = runner.run()
    assert meta["abort_kind"] == "temperature" and robot.parked == 1


def test_orcamento_de_toques(tmp_path):
    runner, adb, robot, clock = make(tmp_path, limits={"max_touches": 10})
    meta = runner.run()
    assert meta["abort_kind"] == "budget" and len(robot.taps) == 10 and robot.parked == 1


def test_sigint_interrompe_e_estaciona(tmp_path):
    runner, adb, robot, clock = make(tmp_path)
    adb.at(20, lambda a: signal.raise_signal(signal.SIGINT))
    meta = runner.run()
    assert meta["status"] == "interrupted" and robot.parked == 1
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler  # handler original restaurado


def test_erros_seguidos_do_robo_abortam(tmp_path):
    robot = FakeRobot(fail_with=ConnectionError("MQTT caiu"), fail_times=99)
    runner, adb, robot, clock = make(tmp_path, robot=robot)
    meta = runner.run()
    assert meta["abort_kind"] == "robot" and types(runner).count("robot_error") == 3
    assert robot.parked == 1


def test_erro_isolado_do_robo_nao_aborta(tmp_path):
    robot = FakeRobot(fail_with=ConnectionError("soluço"), fail_times=1)
    runner, adb, robot, clock = make(tmp_path, robot=robot)
    assert runner.run()["status"] == "completed"


def test_trava_de_seguranca_aborta_na_hora(tmp_path):
    robot = FakeRobot(fail_with=ValueError("Z abaixo do z_floor"), fail_times=1)
    runner, adb, robot, clock = make(tmp_path, robot=robot)
    meta = runner.run()
    assert meta["abort_kind"] == "robot" and "trava" in meta["reason"]


def test_verificacao_de_calibracao(tmp_path):
    probe = FakeTouchProbe(error_px=2)
    runner, adb, robot, clock = make(tmp_path, probe=probe,
                                     calibration_check={"x": 360, "y": 110, "every_min": 1, "tolerance_px": 20})
    meta = runner.run()
    assert meta["status"] == "completed" and len(meta["calibration_errors_px"]) >= 4
    assert types(runner).count("calibration_ok") >= 4


@pytest.mark.parametrize("miss, err, msg", [(True, 0, "não sentiu"), (False, 80, "erro de")])
def test_calibracao_ruim_aborta(tmp_path, miss, err, msg):
    probe = FakeTouchProbe(error_px=err)
    probe.miss = miss
    runner, adb, robot, clock = make(tmp_path, probe=probe,
                                     calibration_check={"x": 360, "y": 110, "every_min": 1, "tolerance_px": 20})
    meta = runner.run()
    assert meta["abort_kind"] == "calibration" and msg in meta["reason"] and robot.parked == 1


def test_consumo_exige_bateria(tmp_path):
    runner, adb, robot, clock = make(tmp_path, charging=True, mode="consumo")
    meta = runner.run()
    assert meta["abort_kind"] == "power" and robot.taps == [] and robot.parked == 1


def test_consumo_aborta_se_conectar_o_cabo(tmp_path):
    runner, adb, robot, clock = make(tmp_path, charging=False, mode="consumo")
    adb.at(70, lambda a: setattr(a, "charging", True))
    assert runner.run()["abort_kind"] == "power"


def test_tela_bloqueada_impede_inicio(tmp_path):
    runner, adb, robot, clock = make(tmp_path)
    orig = adb.shell
    adb.shell = lambda cmd, timeout=20: "    isKeyguardShowing=true\n" if cmd.startswith("dumpsys window") else orig(cmd, timeout)
    meta = runner.run()
    assert meta["abort_kind"] == "screen" and "bloqueio" in meta["reason"] and robot.taps == []


def test_avisa_quando_a_tela_apaga_antes_do_fim(tmp_path):
    # Como no Moto G06 de verdade: tela apaga em 60 s e "Permanecer ativo" desligado.
    runner, adb, robot, clock = make(tmp_path)
    orig = adb.shell
    fake = {"settings get system screen_off_timeout": "60000\n", "settings get global stay_on_while_plugged_in": "0\n"}
    adb.shell = lambda cmd, timeout=20: fake.get(cmd) or orig(cmd, timeout)
    runner.run()
    warnings = [e["detail"] for e in runner.events.events if e["type"] == "warning"]
    assert any("apaga após 60s" in w for w in warnings)
