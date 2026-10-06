"""Testes da lógica pura (sem impressora e sem celular). Rode: python -m pytest tests -q"""
import math
import sys

import numpy as np
import pytest

from taprobot import Calibration, ConfigError, DryRunLink, RobotTap, fit_affine, normalize_config, simulated_robot
from taprobot.touch_reader import TouchReader, parse_getevent_lp


def make_cfg(**motion):
    raw = {
        "printer": {"ip": "1.2.3.4", "serial": "X", "access_code": "1"},
        "motion": {"z_floor": 14.0, **motion},
    }
    return normalize_config(raw)


class Recorder(DryRunLink):
    def __init__(self):
        self.sent = []

    def send_gcode(self, gcode, wait_ack=True):
        self.sent.append(gcode)


def make_cal():
    # Celular girado 90° e deslocado: mm = R @ px * 0.0976 + t
    th = math.radians(90)
    s = 0.0976
    A = s * np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    t = np.array([200.0, 40.0])
    px = [(60, 100), (660, 100), (60, 1500), (660, 1500), (360, 800), (200, 300)]
    mm = [tuple(A @ np.array(p) + t) for p in px]
    return Calibration.from_pairs(px, mm, z_contact=15.0, screen_w=720, screen_h=1640), A, t


def test_fit_recovers_transform():
    cal, A, t = make_cal()
    assert cal.fit_error_mm < 1e-6
    x, y = cal.px_to_mm(100, 200)
    assert np.allclose([x, y], A @ np.array([100, 200]) + t)
    px = cal.mm_to_px(x, y)
    assert np.allclose(px, [100, 200])


def test_collinear_rejected():
    with pytest.raises(ValueError):
        fit_affine([(0, 0), (1, 1), (2, 2)], [(0, 0), (1, 1), (2, 2)])


def test_save_load_roundtrip(tmp_path):
    cal, _, _ = make_cal()
    f = tmp_path / "c.json"
    cal.save(f)
    again = Calibration.load(f)
    assert again.affine == cal.affine and again.z_contact == 15.0


def test_simulated_calibration_reaches_whole_screen():
    cfg = make_cfg()
    cal = Calibration.simulated(cfg)
    link = Recorder()
    robot = RobotTap(cfg, link, cal, sleep=lambda s: None)
    w, h = cal.screen_w, cal.screen_h
    for x, y in [(4, 4), (w - 4, 4), (4, h - 4), (w - 4, h - 4), (w / 2, h / 2)]:
        robot.tap_px(x, y)  # não pode estourar limites XY nem z_floor
    assert len(link.sent) == 5


def test_z_floor_required():
    with pytest.raises(ConfigError):
        normalize_config({"printer": {"ip": "1", "serial": "2", "access_code": "3"}})


def test_tap_gcode_and_limits():
    cal, _, _ = make_cal()
    link = Recorder()
    robot = RobotTap(make_cfg(), link, cal, sleep=lambda s: None)
    robot.tap_px(360, 800)
    g = link.sent[0].splitlines()
    assert g[0] == "G90" and g[-1] == "M400"
    zs = [float(l.split("Z")[1].split()[0]) for l in g if l.startswith("G1 Z")]
    assert max(zs) == pytest.approx(17.0)      # hover = contato + 2
    assert min(zs) == pytest.approx(14.6)      # toque = contato - 0.4
    assert min(zs) >= 14.0                     # nunca abaixo do z_floor


def test_blocks_below_floor():
    cal, _, _ = make_cal()
    robot = RobotTap(make_cfg(z_floor=14.8), Recorder(), cal, sleep=lambda s: None)
    with pytest.raises(ValueError):
        robot.tap_px(360, 800)  # toque seria 14.6 < 14.8
    with pytest.raises(ValueError):
        robot.move_abs(z=10.0)


def test_blocks_outside_xy_and_screen():
    cal, _, _ = make_cal()
    robot = RobotTap(make_cfg(x_max=100), Recorder(), cal, sleep=lambda s: None)
    with pytest.raises(ValueError):
        robot.tap_px(360, 800)   # cai em X>100
    robot2 = RobotTap(make_cfg(), Recorder(), cal, sleep=lambda s: None)
    with pytest.raises(ValueError):
        robot2.tap_px(2000, 10)  # fora da tela


def test_swipe_feed_clamped():
    cal, _, _ = make_cal()
    link = Recorder()
    robot = RobotTap(make_cfg(), link, cal, sleep=lambda s: None)
    robot.swipe_px(360, 1400, 360, 300, duration_s=0.01)
    feeds = [int(l.split("F")[1]) for l in link.sent[0].splitlines() if l.startswith("G1 X")]
    assert max(feeds) <= 9000


def test_home_requires_confirmation():
    robot = RobotTap(make_cfg(), Recorder(), None, sleep=lambda s: None)
    with pytest.raises(RuntimeError):
        robot.home()


def test_parse_getevent_lp():
    text = (
        'add device 1: /dev/input/event3\n'
        '  name:     "mtk-tpd"\n'
        '  events:\n'
        '    ABS (0003): ABS_MT_POSITION_X  : value 0, min 0, max 719, fuzz 0, flat 0, resolution 0\n'
        '                ABS_MT_POSITION_Y  : value 0, min 0, max 1639, fuzz 0, flat 0, resolution 0\n'
        'add device 2: /dev/input/event0\n'
        '  name:     "gpio-keys"\n'
    )
    devs = parse_getevent_lp(text)
    assert len(devs) == 1 and devs[0]["path"] == "/dev/input/event3"
    assert (devs[0]["max_x"], devs[0]["max_y"]) == (719, 1639)


def test_touch_reader_state_machine():
    class FakeAdb:
        base = ["adb"]

    r = TouchReader(FakeAdb(), {"path": "p", "max_x": 719, "max_y": 1639}, 720, 1640)
    lines = [
        "EV_ABS       ABS_MT_TRACKING_ID   00000010",
        "EV_ABS       ABS_MT_POSITION_X    000000c8",   # 200
        "EV_ABS       ABS_MT_POSITION_Y    00000190",   # 400
        "EV_KEY       BTN_TOUCH            DOWN",
        "EV_SYN       SYN_REPORT           00000000",
        "EV_ABS       ABS_MT_POSITION_X    000000ca",   # 202
        "EV_SYN       SYN_REPORT           00000000",
        "EV_ABS       ABS_MT_TRACKING_ID   ffffffff",
        "EV_KEY       BTN_TOUCH            UP",
        "EV_SYN       SYN_REPORT           00000000",
    ]
    for l in lines:
        r.handle_line(l)
    assert r.down_count == 1 and not r.in_contact
    assert len(r.contacts) == 1
    x, y = r.contacts[0]
    assert x == pytest.approx(201, abs=1) and y == pytest.approx(400, abs=1)



def test_robo_simulado_entrega_o_gcode_e_respeita_as_travas():
    sent = []
    robot = simulated_robot(on_send=sent.append)
    robot.tap_px(360, 820)
    robot.park()
    assert len(sent) == 2 and robot.link.sent == 2
    assert "G4 P" in sent[0]
    with pytest.raises(ValueError):
        robot.tap_px(9999, 1)  # fora da tela continua bloqueado
    quiet = simulated_robot(on_send=None)
    quiet.tap_px(10, 10)
    assert quiet.link.sent == 1

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
