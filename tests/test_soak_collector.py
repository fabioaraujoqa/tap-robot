"""Parsers (com saídas reais do Moto G06) e coletor (com o FakeAdb)."""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from soak import parsers
from soak.adb import AdbError
from soak.collector import COLUMNS, Collector, EventLog
from soak.fake import FakeAdb

FIX = Path(__file__).parent / "fixtures" / "moto_g06"
PKG = "io.appium.android.apis"


def fx(name):
    return (FIX / name).read_text(encoding="utf-8")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- parsers (saídas reais)
def test_meminfo_real():
    m = parsers.parse_meminfo(fx("meminfo.txt"))
    assert m["pss_mb"] == pytest.approx(83580 / 1024)
    assert m["java_heap_mb"] == pytest.approx(12656 / 1024)
    assert m["native_heap_mb"] == pytest.approx(6224 / 1024)


def test_meminfo_sem_app_summary_usa_tabela():
    text = "  Native Heap     6289     6224\n  Dalvik Heap     1945     1872\n        TOTAL    83580    56904\n"
    m = parsers.parse_meminfo(text)
    assert m == {"pss_mb": pytest.approx(83580 / 1024), "java_heap_mb": pytest.approx(1945 / 1024),
                 "native_heap_mb": pytest.approx(6289 / 1024)}


def test_meminfo_app_morto():
    assert parsers.parse_meminfo("No process found for: x") == {"pss_mb": None, "java_heap_mb": None, "native_heap_mb": None}


def test_gfxinfo_real():
    g = parsers.parse_gfxinfo(fx("gfxinfo_reset.txt"))
    assert g["frames"] == 1 and g["janky_frames"] == 1
    assert g["janky_pct"] == 100.0
    assert g["frame_p90_ms"] == 2750


def test_gfxinfo_sem_quadros():
    assert parsers.parse_gfxinfo("Total frames rendered: 0\nJanky frames: 0 (0.00%)")["janky_pct"] is None


def test_battery_real():
    b = parsers.parse_battery(fx("battery.txt"))
    assert b["battery_pct"] == 93
    assert b["battery_temp_c"] == 22.0
    assert b["charging"] is False
    assert b["charge_mah"] == pytest.approx(4796.103)
    assert b["voltage_mv"] == 4327


def test_battery_carregando_por_status():
    assert parsers.parse_battery("  status: 2\n  level: 50\n")["charging"] is True


def test_thermal_real_prefere_hal_atual():
    t = parsers.parse_thermal(fx("thermalservice.txt"))
    assert t == {"thermal_status": 0, "temp_cpu_c": 30.1, "temp_skin_c": 24.0}


def test_thermal_ausente():
    assert parsers.parse_thermal("Can't find service: thermalservice") == {
        "thermal_status": None, "temp_cpu_c": None, "temp_skin_c": None}


def test_cpu_real_e_percentual():
    proc = parsers.parse_proc_pid_stat(fx("proc_stat.txt"))
    total = parsers.parse_proc_stat_total(fx("proc_stat_total.txt"))
    assert proc == 475 + 72
    assert total == 108335 + 193631 + 392453 + 5839868 + 164476 + 52764 + 15425
    assert parsers.cpu_percent((100, 10_000), (150, 11_000)) == pytest.approx(5.0)
    assert parsers.cpu_percent(None, (1, 2)) is None
    assert parsers.cpu_percent((100, 10_000), (90, 11_000)) is None  # contador voltou: outro processo


def test_proc_stat_nome_com_espacos():
    assert parsers.parse_proc_pid_stat("1 (a b) c) S 1 1 0 0 -1 0 0 0 0 0 10 5 0 0") == 15


def test_estado_real():
    assert parsers.parse_pidof(fx("pidof.txt")) == 12831
    assert parsers.parse_pidof("") is None
    assert parsers.parse_screen_on(fx("power.txt")) is False  # Dozing = tela apagada
    assert parsers.parse_screen_on("  mWakefulness=Awake") is True
    assert parsers.parse_screen_on("Display Power: state=ON") is True
    assert parsers.parse_resumed_package(fx("activity.txt")) == PKG
    assert parsers.parse_resumed_package("  topResumedActivity=ActivityRecord{1 u0 com.x/.A t1}") == "com.x"


def test_logcat_crash_java_real_de_outro_pacote_e_ignorado():
    p = parsers.LogcatParser(PKG)
    assert [e for line in fx("logcat_crash.txt").splitlines() for e in p.feed(line)] == []
    p2 = parsers.LogcatParser("io.appium.settings")
    evs = [e for line in fx("logcat_crash.txt").splitlines() for e in p2.feed(line)]
    # o Appium Settings caiu, reiniciou e caiu de novo: 2 crashes reais
    assert [e["type"] for e in evs] == ["crash", "crash"]
    assert [e["pid"] for e in evs] == [14808, 14846]
    assert evs[0]["detail"].startswith("java.lang.RuntimeException")


def test_logcat_anr_crash_nativo_e_morte():
    p = parsers.LogcatParser(PKG)
    evs = [e for line in fx("logcat_anr_synthetic.txt").splitlines() for e in p.feed(line)]
    assert [e["type"] for e in evs] == ["anr", "native_crash", "process_died"]
    assert evs[1]["pid"] == 13990


def test_logcat_linhas_reais_do_sistema_nao_geram_evento():
    p = parsers.LogcatParser(PKG)
    assert [e for line in fx("logcat_am.txt").splitlines() for e in p.feed(line)] == []
    assert p.feed("lixo sem formato") == []


# ---------------------------------------------------------------- coletor
@pytest.fixture
def setup(tmp_path):
    clock = Clock()
    adb = FakeAdb(PKG, clock=clock, charging=False)
    events = EventLog(tmp_path / "events.jsonl", clock, clock(), echo=None)
    col = Collector(adb, PKG, tmp_path, events, clock=clock)
    return clock, adb, events, col, tmp_path


def test_coletor_grava_csv_com_todas_as_colunas(setup):
    clock, adb, events, col, d = setup
    col.sample(touches=0)
    clock.t += 3600
    row = col.sample(touches=10)
    assert row["app_alive"] and row["screen_on"] and row["foreground"] == PKG
    assert row["pss_mb"] > 85 and row["cpu_pct"] is not None
    assert row["charging"] is False and row["battery_pct"] < 93
    rows = list(csv.DictReader((d / "samples.csv").open()))
    assert len(rows) == 2 and list(rows[0].keys()) == COLUMNS
    assert rows[1]["touches"] == "10"


def test_coletor_app_morto_nao_quebra(setup):
    clock, adb, events, col, d = setup
    adb.pid = None
    row = col.sample()
    assert row["app_alive"] is False and row["pss_mb"] is None and row["cpu_pct"] is None


def test_coletor_adb_fora_lanca_erro(setup):
    clock, adb, events, col, d = setup
    adb.offline = True
    with pytest.raises(AdbError):
        col.heartbeat()


def test_screenshot_e_eventos(setup):
    clock, adb, events, col, d = setup
    path = col.screenshot("teste")
    assert path.read_bytes().startswith(b"\x89PNG")
    events.add("crash", "x", pid=1)
    assert json.loads((d / "events.jsonl").read_text().splitlines()[0])["type"] == "crash"
    assert events.count("crash", "anr") == 1


def test_logcat_em_segundo_plano_registra_crash(setup):
    import time
    clock, adb, events, col, d = setup
    got = []
    col.start_logcat(on_event=got.append)
    adb.crash()
    for _ in range(50):
        if any(e["type"] == "crash" for e in got):
            break
        time.sleep(0.05)
    col.stop()
    assert [e["type"] for e in got] == ["crash", "process_died"]
