"""Cálculos e erros da biblioteca não funcional, sem aparelho."""
import csv
from types import SimpleNamespace

import pytest
from selenium.common.exceptions import WebDriverException

import nfr_appium as nfr


def test_percentil_interpola():
    assert nfr.percentil([100, 200, 300, 400, 500], 50) == 300
    assert nfr.percentil([100, 200], 90) == pytest.approx(190)


def test_percentil_sem_amostras():
    with pytest.raises(ValueError, match="sem amostras"):
        nfr.percentil([], 50)


def test_inclinacao_recupera_reta_conhecida():
    assert nfr.inclinacao_por_hora([0, 1, 2, 3], [100, 110, 120, 130]) == pytest.approx(10)


def test_inclinacao_exige_tres_amostras():
    with pytest.raises(ValueError, match="ao menos 3"):
        nfr.inclinacao_por_hora([0, 1], [1, 2])


def _amostra(pid, horas, pss):
    return {"pid": pid, "horas": horas, "pss_mb": pss}


def test_memoria_nao_mistura_processos():
    """A queda no crash não pode esconder o vazamento de 10 MB/h."""
    antes = [_amostra(1, h, 100 + 10 * h) for h in range(5)]
    depois = [_amostra(2, h, 60 + 10 * (h - 5)) for h in range(5, 8)]
    r = nfr.inclinacao_memoria(antes + depois)
    assert r["mb_por_hora"] == pytest.approx(10)
    assert (r["trechos"], r["amostras"]) == (2, 5)


def test_memoria_descarta_aquecimento():
    amostras = [_amostra(1, 0, 10), _amostra(1, 1, 90)] + [
        _amostra(1, h, 100 + h) for h in range(2, 7)
    ]
    assert nfr.inclinacao_memoria(amostras, 2)["mb_por_hora"] == pytest.approx(1)


def test_memoria_ignora_amostra_sem_processo():
    amostras = [_amostra(1, h, 100 + h) for h in range(3)] + [_amostra(None, 3, None)]
    assert nfr.inclinacao_memoria(amostras)["amostras"] == 3


def test_parse_am_start():
    saida = "Status: ok\nLaunchState: COLD\nActivity: x\nTotalTime: 743\nWaitTime: 750\nComplete\n"
    assert nfr.parse_am_start(saida) == {"total_ms": 743, "wait_ms": 750, "estado": "COLD"}


def test_parse_ultima_posicao_usa_o_gps():
    saida = (
        "last location=null\n"
        "last location=Location[fused 1.0,2.0 hAcc=5.0]\n"
        "last location=Location[gps -23.550498,-46.633298 hAcc=5.0 et=+24m]\n"
    )
    assert nfr.parse_ultima_posicao(saida) == {"latitude": -23.550498, "longitude": -46.633298}
    assert nfr.parse_ultima_posicao("last location=null") is None


def test_parse_threads():
    assert nfr.parse_threads("Name:\tapp\nThreads:\t27\nSigQ:\t0/1\n") == 27
    assert nfr.parse_threads("") is None


def test_parse_ultimo_toque_pega_o_ultimo_down():
    saida = (
        "[   10.100000] EV_KEY       BTN_TOUCH            DOWN\n"
        "[   10.200000] EV_KEY       BTN_TOUCH            UP\n"
        "[   12.500000] /dev/input/event4: EV_KEY       BTN_TOUCH            DOWN\n"
    )
    assert nfr.parse_ultimo_toque(saida) == 12.5
    assert nfr.parse_ultimo_toque("") is None


FRAMESTATS = """Applications Graphics Acceleration Info:
---PROFILEDATA---
Flags,IntendedVsync,Vsync,FrameCompleted,
0,1000000000,1000000000,10050000000,
1,1000000000,1000000000,10090000000,
0,1000000000,1000000000,10100000000,
---PROFILEDATA---
"""


def test_parse_quadros_ignora_quadro_com_flag():
    assert nfr.parse_quadros(FRAMESTATS) == [10.05, 10.1]


def test_latencia_e_o_primeiro_quadro_depois_do_toque():
    assert nfr.latencia_toque_ms(10.06, [10.05, 10.1, 10.2]) == pytest.approx(40)


def test_latencia_sem_quadro_novo_falha():
    with pytest.raises(RuntimeError, match="a tela não mudou"):
        nfr.latencia_toque_ms(11, [10.05])


def _lib_com_driver(execute):
    lib = nfr.nfr_appium()
    lib._driver = lambda: SimpleNamespace(execute_script=execute)
    return lib


def test_shell_sem_flag_explica_como_subir_o_servidor():
    def execute(_comando, _args):
        raise WebDriverException("Potentially insecure feature 'adb_shell' has not been enabled")

    with pytest.raises(RuntimeError, match="--allow-insecure=uiautomator2:adb_shell"):
        _lib_com_driver(execute).adb_shell("true")


def test_outro_erro_do_shell_nao_vira_erro_de_flag():
    def execute(_comando, _args):
        raise WebDriverException("device offline")

    with pytest.raises(WebDriverException, match="offline"):
        _lib_com_driver(execute).adb_shell("true")


def test_shell_passa_pelo_comando_mobile():
    chamadas = []

    def execute(comando, args):
        chamadas.append((comando, args))
        return "ok\n"

    assert _lib_com_driver(execute).adb_shell("dumpsys battery") == "ok\n"
    assert chamadas == [("mobile: shell", {"command": "dumpsys battery", "timeout": 30000})]


def test_csv_tem_uma_coluna_por_campo_e_vazio_para_none(tmp_path, monkeypatch):
    monkeypatch.setattr(nfr, "RESULTADOS", tmp_path / "nfr")
    lib = nfr.nfr_appium()
    lib.gravar_csv("soak", pid=1, pss_mb=None)
    caminho = lib.gravar_csv("soak", pid=2, pss_mb=99.5)
    assert caminho.startswith(str(tmp_path / "nfr" / "soak_"))
    with open(caminho, encoding="utf-8") as f:
        linhas = list(csv.reader(f))
    assert linhas[0] == ["data_hora", "pid", "pss_mb"]
    assert linhas[1][1:] == ["1", ""]
    assert linhas[2][1:] == ["2", "99.5"]
