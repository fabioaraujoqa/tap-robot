"""Gera os PNGs da palestra a partir dos CSVs em results/nfr/ (pega o mais recente de cada tipo).

    pip install -e .[graficos]
    python tests/robot/nao_funcionais/scripts/gerar_graficos.py
    python tests/robot/nao_funcionais/scripts/gerar_graficos.py --entrada results/nfr --saida slides/
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))
import nfr_limites as limites  # noqa: E402

SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
GRADE = "#e6e5e0"
SERIE = "#2a78d6"
JANELA_P95 = 10


def _ler(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def _mais_recente(pasta: Path, tipo: str):
    arquivos = sorted(pasta.glob(f"{tipo}_*.csv"))
    return arquivos[-1] if arquivos else None


def _serie(linhas, coluna_x, coluna_y):
    pares = [(float(l[coluna_x]), float(l[coluna_y])) for l in linhas if l.get(coluna_y) not in (None, "")]
    return [p[0] for p in pares], [p[1] for p in pares]


def _em_tempo(horas):
    """Minutos em ensaios curtos, horas nos longos."""
    if horas and max(horas) >= 2:
        return list(horas), "Tempo (h)"
    return [h * 60 for h in horas], "Tempo (min)"


def _figura(titulo, rotulo_x, rotulo_y):
    fig, eixo = plt.subplots(figsize=(8, 4.5), dpi=200, facecolor=SUPERFICIE)
    eixo.set_facecolor(SUPERFICIE)
    eixo.set_title(titulo, loc="left", fontsize=15, color=TEXTO, fontweight="bold", pad=14)
    eixo.set_xlabel(rotulo_x, fontsize=11, color=TEXTO_SECUNDARIO)
    eixo.set_ylabel(rotulo_y, fontsize=11, color=TEXTO_SECUNDARIO)
    eixo.tick_params(colors=TEXTO_SECUNDARIO, labelsize=10, length=0)
    eixo.grid(axis="y", color=GRADE, linewidth=0.8)
    eixo.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        eixo.spines[lado].set_visible(False)
    eixo.spines["bottom"].set_color(GRADE)
    return fig, eixo


def _linha_limite(eixo, valor, rotulo):
    eixo.axhline(valor, color=TEXTO_SECUNDARIO, linewidth=1.5, linestyle=(0, (5, 4)))
    eixo.annotate(
        rotulo, xy=(1, valor), xycoords=("axes fraction", "data"), xytext=(0, 5),
        textcoords="offset points", ha="right", fontsize=10, color=TEXTO_SECUNDARIO,
    )


def _salvar(fig, saida: Path, nome: str) -> Path:
    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / f"{nome}.png"
    fig.tight_layout()
    fig.savefig(destino, facecolor=SUPERFICIE)
    plt.close(fig)
    return destino


def grafico_memoria(linhas, saida: Path) -> Path:
    horas, pss = _serie(linhas, "horas", "pss_mb")
    x, rotulo_x = _em_tempo(horas)
    fig, eixo = _figura("Memória do app ao longo do soak", rotulo_x, "PSS (MB)")
    eixo.plot(x, pss, color=SERIE, linewidth=2)
    _linha_limite(eixo, limites.SOAK_PSS_MAX_MB, f"Limite: {limites.SOAK_PSS_MAX_MB} MB")
    fator = 1 if rotulo_x == "Tempo (h)" else 60
    crashes = [float(l["horas"]) * fator for l in linhas if l.get("evento") == "crash"]
    for indice, crash in enumerate(crashes):
        eixo.axvline(crash, color=TEXTO_SECUNDARIO, linewidth=1, linestyle=":")
        if indice == 0:
            eixo.annotate("crash", xy=(crash, 0), xycoords=("data", "axes fraction"), xytext=(4, 6),
                          textcoords="offset points", fontsize=10, color=TEXTO_SECUNDARIO)
    eixo.set_ylim(bottom=0)
    return _salvar(fig, saida, "memoria")


def grafico_latencia(linhas, saida: Path) -> Path:
    latencias = [float(l["latencia_ms"]) for l in linhas if l.get("latencia_ms") not in (None, "")]
    x = list(range(1, len(latencias) + 1))
    p95 = [float(np.percentile(latencias[max(0, i + 1 - JANELA_P95):i + 1], 95)) for i in range(len(latencias))]
    fig, eixo = _figura(f"p95 da latência do toque (últimos {JANELA_P95} toques)", "Toque", "Latência (ms)")
    eixo.plot(x, p95, color=SERIE, linewidth=2)
    _linha_limite(eixo, limites.LATENCIA_P95_MAX_MS, f"SLA: {limites.LATENCIA_P95_MAX_MS} ms")
    eixo.set_ylim(bottom=0)
    return _salvar(fig, saida, "latencia_p95")


def grafico_bateria(linhas, saida: Path) -> Path:
    horas, nivel = _serie(linhas, "horas", "bateria_pct")
    x, rotulo_x = _em_tempo(horas)
    fig, eixo = _figura("Nível da bateria com o app em uso", rotulo_x, "Bateria (%)")
    eixo.plot(x, nivel, color=SERIE, linewidth=2, marker="o", markersize=5,
              markeredgecolor=SUPERFICIE, markeredgewidth=1.5)
    eixo.set_ylim(0, 100)
    return _salvar(fig, saida, "bateria")


GRAFICOS = {"soak": grafico_memoria, "latencia": grafico_latencia, "bateria": grafico_bateria}


def gerar(entrada: Path, saida: Path) -> list[Path]:
    gerados = []
    for tipo, desenhar in GRAFICOS.items():
        caminho = _mais_recente(entrada, tipo)
        if caminho is None:
            print(f"{tipo}: nenhum CSV em {entrada}, pulando")
            continue
        destino = desenhar(_ler(caminho), saida)
        print(f"{tipo}: {caminho.name} -> {destino}")
        gerados.append(destino)
    return gerados


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--entrada", type=Path, default=ROOT / "results" / "nfr")
    args.add_argument("--saida", type=Path, default=ROOT / "results" / "nfr" / "graficos")
    opcoes = args.parse_args()
    if not gerar(opcoes.entrada, opcoes.saida):
        sys.exit(f"nenhum CSV encontrado em {opcoes.entrada}")
