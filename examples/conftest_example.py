"""Para testes pytest existentes: copie as fixtures abaixo para o seu conftest.py.

Com `autouse=True`, TODO element.click() dos seus testes passa a tocar de verdade,
sem mudar nenhum teste.
"""
import pytest

from taprobot import BambuLink, Calibration, RobotTap, load_config
from taprobot.appium_patch import physical_clicks


@pytest.fixture(scope="session")
def robot():
    cfg = load_config("config.yaml")
    cal = Calibration.load(cfg["calibration_file"])
    p = cfg["printer"]
    link = BambuLink(p["ip"], p["serial"], p["access_code"])
    link.connect()
    r = RobotTap(cfg, link, cal)
    yield r
    r.park()
    link.close()


@pytest.fixture(autouse=True)
def physical_touch(robot):
    with physical_clicks(robot):
        yield
