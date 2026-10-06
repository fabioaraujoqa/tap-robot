"""Busca do celular (taprobot.device) e biblioteca do Robot Framework em modo simulado."""

import pytest

from taprobot import device

import TapRobotLibrary as lib_module  # robot/libraries está no pythonpath do pytest


def test_parse_mdns_acha_o_serial_certo():
    text = (
        "List of discovered mdns services\n"
        "adb-OUTRO123-aaaa\t_adb-tls-connect._tcp\t192.168.15.30:5555\n"
        "adb-ZF525PMHVF-iQtco6\t_adb-tls-pairing._tcp\t0.0.0.0:38429\n"
        "adb-ZF525PMHVF-iQtco6\t_adb-tls-connect._tcp\t192.168.15.20:41983\n"
    )
    assert device.parse_mdns(text, "ZF525PMHVF") == "192.168.15.20:41983"
    assert device.parse_mdns(text, "NAOEXISTE") is None


def fake_adb(responses):
    """Substitui o _adb: responde pelo início dos argumentos e registra as chamadas."""
    calls = []

    def run(*args, adb="adb", timeout=15):
        calls.append(args)
        for prefix, out in responses.items():
            if args[: len(prefix)] == prefix:
                return out
        return ""
    return run, calls


def test_resolve_prefere_usb(monkeypatch):
    run, _ = fake_adb({("devices",): "List of devices attached\nZF525PMHVF\tdevice\n"})
    monkeypatch.setattr(device, "_adb", run)
    assert device.resolve_udid("ZF525PMHVF") == "ZF525PMHVF"


def test_resolve_reconhece_wifi_ja_conectado(monkeypatch):
    run, calls = fake_adb({
        ("devices",): "List of devices attached\nRQ8R709VAVR\tdevice\n192.168.15.20:41983\tdevice\n",
        ("-s", "192.168.15.20:41983", "shell"): "ZF525PMHVF\n",
    })
    monkeypatch.setattr(device, "_adb", run)
    assert device.resolve_udid("ZF525PMHVF") == "192.168.15.20:41983"
    assert not any(c[0] == "connect" for c in calls)


def test_resolve_conecta_pelo_mdns_e_limpa_offline(monkeypatch):
    run, calls = fake_adb({
        ("devices",): "List of devices attached\n192.168.15.24:40935\toffline\n",
        ("mdns",): "adb-ZF525PMHVF-x\t_adb-tls-connect._tcp\t192.168.15.20:41983\n",
        ("connect",): "connected to 192.168.15.20:41983\n",
    })
    monkeypatch.setattr(device, "_adb", run)
    assert device.resolve_udid("ZF525PMHVF") == "192.168.15.20:41983"
    assert ("disconnect", "192.168.15.24:40935") in calls


def test_resolve_sem_celular(monkeypatch):
    run, _ = fake_adb({("devices",): "List of devices attached\n"})
    monkeypatch.setattr(device, "_adb", run)
    monkeypatch.setattr(device.time, "sleep", lambda s: None)
    with pytest.raises(device.DeviceNotFound, match="Depuração por Wi-Fi"):
        device.resolve_udid("ZF525PMHVF")


# ---------------------------------------------------------------- biblioteca do Robot
@pytest.fixture
def lib():
    lib = lib_module.TapRobotLibrary(simulado="True")
    lib.connect()
    yield lib
    lib.disconnect()


def test_biblioteca_simulada_registra_os_gestos(lib, monkeypatch):
    sent = []
    monkeypatch.setattr(lib.robot.link, "send_gcode", lambda g, wait_ack=True: sent.append(g))
    lib.tap_xy("360", "800")
    lib.long_press_xy(360, 800, "1.5")
    lib.swipe(360, 1300, 360, 400, "0.4")
    assert len(sent) == 3 and "G4 P1500" in sent[1]
    assert lib.is_simulated()


def test_toque_no_elemento_usa_o_centro_do_rect(lib, monkeypatch):
    class FakeAppium:
        def get_element_rect(self, locator):
            assert locator == "accessibility_id=Views"
            return {"x": 100, "y": 1000, "width": 200, "height": 60}

    class FakeBuiltIn:
        def get_library_instance(self, name):
            return FakeAppium()

    monkeypatch.setattr(lib_module, "BuiltIn", FakeBuiltIn)
    taps = []
    monkeypatch.setattr(lib.robot, "tap_px", lambda x, y, dwell_ms=None: taps.append((x, y)))
    lib.tap_element("accessibility_id=Views")
    assert taps == [(200, 1030)]


def test_toque_fora_da_tela_e_bloqueado(lib):
    with pytest.raises(ValueError, match="fora da tela"):
        lib.tap_xy(5000, 100)


def test_gesto_sem_conectar_da_erro_claro():
    with pytest.raises(RuntimeError, match="Conectar Robô"):
        lib_module.TapRobotLibrary(simulado=True).tap_xy(1, 1)


def test_desconectar_duas_vezes_e_seguro(lib):
    lib.disconnect()
    lib.disconnect()
