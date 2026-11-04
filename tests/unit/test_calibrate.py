"""Fluxo completo da calibração com impressora e celular simulados."""
import argparse
import re
from pathlib import Path

import pytest

from taprobot import Calibration, RobotTap, simulated_robot
from tools import calibrate

Z_CONTATO = 20.0
PX_POR_MM = 10.25


def mm_para_px(x, y):
    """Montagem fictícia: tela sobre a mesa, com o eixo Y invertido em relação à impressora."""
    return (x - 92.5) * PX_POR_MM, (207.5 - y) * PX_POR_MM


class FakeReader:
    def __init__(self):
        self.contacts, self.down_count, self.in_contact = [], 0, False

    def stop(self):
        pass

    def wait_contact(self, count_before, timeout=4.0):
        return self.contacts[-1] if len(self.contacts) > count_before else None


class FakePrinter:
    """Executa o G-code: o celular "sente" o toque quando Z chega à altura da tela."""

    def __init__(self, reader):
        self.reader = reader
        self.x = self.y = None
        self.z = 99.0

    def send_gcode(self, gcode, wait_ack=True):
        for line in gcode.splitlines():
            if not line.startswith("G1"):
                continue
            for axis, value in re.findall(r"([XYZ])(-?[\d.]+)", line):
                setattr(self, axis.lower(), float(value))
            if self.z <= Z_CONTATO and not self.reader.in_contact:
                self.reader.in_contact = True
                self.reader.down_count += 1
                self.touch_at = (self.x, self.y)
            elif self.z > Z_CONTATO and self.reader.in_contact:
                self.reader.in_contact = False
                self.reader.contacts.append(mm_para_px(*self.touch_at))

    def close(self):
        pass


@pytest.fixture
def args(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        "printer: {ip: 192.0.2.1, serial: S, access_code: C}\nmotion: {z_floor: 14.0}\n",
        encoding="utf-8",
    )
    reader = FakeReader()
    printer = FakePrinter(reader)

    def open_session(cfg, with_cal):
        cal_path = Path(cfg["_dir"]) / cfg["calibration_file"]
        cal = Calibration.load(cal_path) if with_cal else None
        return RobotTap(cfg, printer, cal, sleep=lambda s: None), reader, (720, 1640), cal_path, printer

    monkeypatch.setattr(calibrate, "open_session", open_session)
    monkeypatch.setattr(calibrate.time, "sleep", lambda s: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "ok" if "jog" in prompt else "")
    return argparse.Namespace(config=str(config), z_step=0.1, start_x=None, start_y=None)


def test_calibracao_completa_acha_o_contato_e_a_orientacao(args, tmp_path, capsys):
    calibrate.cmd_run(args)
    cal = Calibration.load(tmp_path / "calibration.json")
    assert cal.z_contact == pytest.approx(Z_CONTATO, abs=0.11)
    assert cal.fit_error_mm < 0.01
    assert mm_para_px(*cal.px_to_mm(100, 1500)) == pytest.approx((100, 1500), abs=0.5)

    calibrate.cmd_verify(args)
    assert "Pior erro: 0.0" in capsys.readouterr().out


def test_jog_antes_de_conhecer_toda_a_posicao(args):
    calibrate.cmd_jog(args)  # sobe só em Z e depois anda em XY: a posição começa incompleta


@pytest.mark.parametrize("primeiro, segundo", [
    (dict(z=30.0), dict(x=100.0, y=100.0)),
    (dict(x=100.0, y=100.0), dict(z=30.0)),
])
def test_movimento_com_posicao_parcial(primeiro, segundo):
    robot = simulated_robot(on_send=None)
    robot.move_abs(**primeiro)
    robot.move_abs(**segundo)
    assert None not in robot.pos


def test_toque_depois_de_estacionar_sem_posicao_conhecida():
    robot = simulated_robot(on_send=None)
    robot.park()
    robot.tap_px(360, 800)
