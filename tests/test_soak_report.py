"""Relatório: regressão de memória, consumo, veredito e geração do HTML/CSV."""
import csv
import json

import pytest

from soak.report import analyze, build_report, slope_per_hour
from soak.runner import Runner
from soak.fake import FakeAdb
from soak.scenario import WearCounter, load_scenario

PKG = "io.appium.android.apis"


def rows_linear(n=13, step_s=300, pss0=80.0, mb_h=10.0, charging=True, drain_h=0.0, pid=1):
    out = []
    for i in range(n):
        t = i * step_s
        out.append({"t_s": t, "pid": pid, "pss_mb": pss0 + mb_h * t / 3600, "java_heap_mb": 12.0, "native_heap_mb": 6.0,
                    "frames": 600, "janky_frames": 30, "cpu_pct": 8.0, "battery_pct": 90 - drain_h * t / 3600,
                    "charge_mah": 4800 - 48 * drain_h * t / 3600, "battery_temp_c": 30.0, "temp_cpu_c": 40.0,
                    "temp_skin_c": 32.0, "thermal_status": 0, "charging": charging})
    return out


def meta(**kw):
    return {"status": "completed", "mode": "soak", "touches": 100, "scenario": {}, **kw}


def test_slope_por_hora():
    assert slope_per_hour([0, 1800, 3600], [10, 15, 20]) == pytest.approx(10)
    assert slope_per_hour([0, 60], [1, 2]) is None  # pouco tempo
    assert slope_per_hour([0, 400, 800], [1, None, 3]) is None  # só 2 pontos válidos


def test_ok_sem_problemas():
    s = analyze(meta(), rows_linear(mb_h=1.0), [])
    assert s["verdict"] == "OK" and s["reasons"] == []
    assert s["mem_slope_mb_h"] == pytest.approx(1.0)
    assert s["janky_pct"] == pytest.approx(5.0)


@pytest.mark.parametrize("mb_h, verdict", [(8, "ATENÇÃO"), (30, "FALHA")])
def test_vazamento_de_memoria(mb_h, verdict):
    s = analyze(meta(), rows_linear(mb_h=mb_h), [])
    assert s["verdict"] == verdict and "memória" in s["reasons"][0]["text"]


def test_memoria_usa_o_maior_trecho_do_mesmo_processo():
    rows = rows_linear(n=4, mb_h=500, pid=1) + [dict(r, t_s=r["t_s"] + 1200, pid=2) for r in rows_linear(n=10, mb_h=2)]
    assert analyze(meta(), rows, [])["mem_slope_mb_h"] == pytest.approx(2.0)


def test_crash_e_anr_falham():
    ev = [{"type": "crash", "t_s": 10}, {"type": "anr", "t_s": 20}, {"type": "app_restart", "t_s": 21}]
    s = analyze(meta(), rows_linear(mb_h=0), ev)
    assert s["verdict"] == "FALHA" and s["crashes"] == 1 and s["anrs"] == 1


def test_aborto_por_ambiente_e_atencao_mas_por_app_e_falha():
    assert analyze(meta(status="aborted", abort_kind="adb", reason="adb fora"), rows_linear(mb_h=0), [])["verdict"] == "ATENÇÃO"
    assert analyze(meta(status="aborted", abort_kind="temperature", reason="quente"), rows_linear(mb_h=0), [])["verdict"] == "FALHA"


def test_consumo_na_bateria():
    m = meta(mode="consumo", scenario={"verdict": {"drain_warn_pct_h": 15}})
    s = analyze(m, rows_linear(mb_h=0, charging=False, drain_h=20), [])
    assert s["power_mode"] == "bateria"
    assert s["drain_pct_h"] == pytest.approx(20) and s["drain_mah_h"] == pytest.approx(960)
    assert s["verdict"] == "ATENÇÃO" and "consumo" in s["reasons"][0]["text"]


def test_limites_do_cenario_sobrepoem_padrao():
    m = meta(scenario={"verdict": {"mem_slope_warn_mb_h": 50, "mem_slope_fail_mb_h": 100}})
    assert analyze(m, rows_linear(mb_h=30), [])["verdict"] == "OK"


def test_poucos_dados_viram_atencao():
    s = analyze(meta(), rows_linear(n=2), [])
    assert s["mem_slope_mb_h"] is None and s["verdict"] == "ATENÇÃO"


def test_relatorio_completo_de_uma_execucao_simulada(tmp_path):
    class Clock:
        t = 0.0
        def __call__(self): return self.t
        def sleep(self, s): self.t += max(s, 0.001)

    class Robot:
        def tap_px(self, *a, **k): pass
        def park(self): pass

    clock = Clock()
    sc = load_scenario({"package": PKG, "duration_min": 30, "seed": 3, "steps": [{"tap": [360, 800]}, {"wait": 5}],
                        "sampling": {"interval_s": 60, "heartbeat_s": 10, "screenshot_every_min": 5}})
    adb = FakeAdb(PKG, clock=clock, leak_mb_per_h=40)
    adb.at(600, lambda a: a.crash())
    run = tmp_path / "run"
    Runner(sc, Robot(), adb, run, wear=WearCounter(tmp_path / "w.json", 10**9), clock=clock, sleep=clock.sleep, echo=None).run()
    out = build_report(run)
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and "</html>" in page
    assert "http://" not in page.replace("http://www.w3.org/2000/svg", "")  # autocontido
    data = json.loads(page.split('id="data">', 1)[1].split("</script>", 1)[0])
    assert data["summary"]["verdict"] == "FALHA" and data["summary"]["crashes"] == 1
    assert data["shots"] and data["shots"][0]["src"].startswith("data:image/png;base64,")
    summary = dict(csv.reader((run / "summary.csv").open()))
    assert summary["verdict"] == "FALHA" and float(summary["mem_slope_mb_h"]) > 20


def test_nome_com_html_e_escapado(tmp_path):
    (tmp_path / "meta.json").write_text(json.dumps(meta(name="<script>alert(1)</script>")))
    (tmp_path / "samples.csv").write_text("t_s,pss_mb\n0,80\n")
    page = build_report(tmp_path).read_text()
    assert "<script>alert(1)" not in page
