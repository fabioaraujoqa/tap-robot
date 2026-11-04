"""Comandos e métricas da suíte não funcional, sempre pelo driver UiAutomator2.

Tudo passa por `driver.execute_script("mobile: ...")`. Os comandos de shell (dumpsys,
am start -W, getevent) exigem o servidor Appium com:

    appium --allow-insecure=uiautomator2:adb_shell

A interpretação das saídas do Android reaproveita `soak.parsers`.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

import numpy as np
from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn
from selenium.common.exceptions import WebDriverException

from soak.parsers import (
    cpu_percent,
    parse_battery,
    parse_gfxinfo,
    parse_keyguard,
    parse_meminfo,
    parse_pidof,
    parse_proc_pid_stat,
    parse_proc_stat_total,
    parse_resumed_package,
    parse_thermal,
)
from taprobot.touch_reader import parse_getevent_lp

ROOT = Path(__file__).resolve().parents[4]
RESULTADOS = ROOT / "results" / "nfr"
FLAG_ADB_SHELL = (
    "este teste precisa de comandos de shell, e o servidor Appium não os permite. Suba com: "
    "appium --port 4725 --allow-insecure=uiautomator2:adb_shell "
    "e rode com -v APPIUM_URL:http://127.0.0.1:4725"
)
GETEVENT_LOG = "/data/local/tmp/nfr_getevent.log"


# ---------------------------------------------------------------- cálculos
def percentil(valores, p) -> float:
    """Percentil p (0 a 100), com interpolação linear."""
    numeros = [float(v) for v in valores]
    if not numeros:
        raise ValueError("sem amostras para calcular o percentil")
    return float(np.percentile(numeros, float(p)))


def inclinacao_por_hora(horas, valores) -> float:
    """Inclinação da reta de regressão linear: unidades por hora."""
    x, y = [float(v) for v in horas], [float(v) for v in valores]
    if len(x) < 3:
        raise ValueError(f"regressão precisa de ao menos 3 amostras; há {len(x)}")
    if max(x) == min(x):
        raise ValueError("regressão precisa de amostras em horários diferentes")
    return float(np.polyfit(x, y, 1)[0])


def inclinacao_memoria(amostras, aquecimento=0) -> dict:
    """MB/h no trecho mais longo do mesmo processo, sem os primeiros ciclos de aquecimento.

    Depois de um crash a memória recomeça do zero. Misturar processos faria a queda parecer
    melhora e esconderia um vazamento, então cada processo vira um trecho separado.
    """
    trechos: list[list[dict]] = []
    for amostra in amostras:
        if amostra.get("pss_mb") in (None, "") or amostra.get("pid") in (None, ""):
            continue
        if trechos and trechos[-1][-1]["pid"] == amostra["pid"]:
            trechos[-1].append(amostra)
        else:
            trechos.append([amostra])
    if not trechos:
        raise ValueError("nenhuma amostra de memória válida")
    trecho = max(trechos, key=len)[int(aquecimento):]
    return {
        "mb_por_hora": inclinacao_por_hora(
            [a["horas"] for a in trecho], [a["pss_mb"] for a in trecho]
        ),
        "amostras": len(trecho),
        "trechos": len(trechos),
        "horas": float(trecho[-1]["horas"]) - float(trecho[0]["horas"]),
    }


def parse_am_start(texto: str) -> dict:
    """Saída de `am start -W` -> TotalTime, WaitTime e LaunchState."""
    def numero(campo):
        m = re.search(rf"^\s*{campo}:\s*(\d+)", texto, re.M)
        return int(m.group(1)) if m else None

    estado = re.search(r"^\s*LaunchState:\s*(\w+)", texto, re.M)
    return {
        "total_ms": numero("TotalTime"),
        "wait_ms": numero("WaitTime"),
        "estado": estado.group(1) if estado else None,
    }


def parse_ultima_posicao(texto: str):
    """`dumpsys location` -> latitude e longitude da última posição do provedor gps."""
    m = re.search(r"last location=Location\[gps (-?[\d.]+),(-?[\d.]+)", texto)
    return {"latitude": float(m.group(1)), "longitude": float(m.group(2))} if m else None


def parse_threads(texto: str):
    """`Threads:` de /proc/<pid>/status."""
    m = re.search(r"^Threads:\s*(\d+)", texto, re.M)
    return int(m.group(1)) if m else None


def parse_ultimo_toque(texto: str):
    """Saída de `getevent -lt` -> horário (s, relógio monotônico) do último BTN_TOUCH DOWN."""
    ultimo = None
    for m in re.finditer(r"\[\s*([\d.]+)\]\s+\S*\s*EV_KEY\s+BTN_TOUCH\s+DOWN", texto):
        ultimo = float(m.group(1))
    return ultimo


def parse_quadros(texto: str) -> list:
    """`dumpsys gfxinfo <pacote> framestats` -> FrameCompleted (s) dos quadros válidos."""
    quadros: list[float] = []
    for bloco in re.findall(r"---PROFILEDATA---\s*\n(.*?)---PROFILEDATA---", texto, re.S):
        linhas = [linha.strip() for linha in bloco.strip().splitlines() if linha.strip()]
        if len(linhas) < 2:
            continue
        colunas = linhas[0].rstrip(",").split(",")
        flags, fim = colunas.index("Flags"), colunas.index("FrameCompleted")
        for linha in linhas[1:]:
            campos = linha.rstrip(",").split(",")
            if len(campos) > max(flags, fim) and campos[flags] == "0":
                quadros.append(int(campos[fim]) / 1e9)
    return sorted(quadros)


def latencia_toque_ms(toque_s: float, quadros) -> float:
    """Tempo do toque até o primeiro quadro concluído depois dele."""
    for quadro in quadros:
        if quadro > toque_s:
            return (quadro - toque_s) * 1000
    raise RuntimeError("nenhum quadro foi desenhado depois do toque: a tela não mudou")


def _numero_ou_vazio(valor):
    return "" if valor is None else valor


class nfr_appium:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self):
        self._csv: dict[str, Path] = {}
        self._colunas: dict[str, list] = {}
        self._cpu_anterior = None
        self._ultimo_pid = None
        self._getevent_pid = None

    # ------------------------------------------------------------ driver
    def _driver(self):
        return BuiltIn().get_library_instance("AppiumLibrary")._current_application()

    def _mobile(self, comando: str, **args):
        return self._driver().execute_script(f"mobile: {comando}", args)

    def adb_shell(self, command, timeout_ms=30000) -> str:
        """Roda um comando no aparelho (`mobile: shell`) e devolve a saída."""
        try:
            saida = self._mobile("shell", command=command, timeout=int(timeout_ms))
        except WebDriverException as exc:
            if "adb_shell" in str(exc):
                raise RuntimeError(FLAG_ADB_SHELL) from exc
            raise
        return saida if isinstance(saida, str) else str(saida.get("stdout", ""))

    def get_performance_data(self, package, data_type):
        return self._mobile("getPerformanceData", packageName=package, dataType=data_type)

    def set_sensor(self, sensor_type, value):
        self._mobile("sensorSet", sensorType=sensor_type, value=str(value))

    def set_connectivity(self, wifi=None, data=None, airplane_mode=None):
        args = {"wifi": wifi, "data": data, "airplaneMode": airplane_mode}
        args = {k: BuiltIn().convert_to_boolean(v) for k, v in args.items() if v is not None}
        self._mobile("setConnectivity", **args)

    def set_network_speed(self, speed):
        self._mobile("networkSpeed", speed=speed)

    def gsm_call(self, phone_number, action):
        self._mobile("gsmCall", phoneNumber=str(phone_number), action=action)

    def send_sms(self, phone_number, message):
        self._mobile("sendSms", phoneNumber=str(phone_number), message=message)

    def set_geolocation(self, latitude, longitude):
        self._mobile("setGeolocation", latitude=float(latitude), longitude=float(longitude))

    def obter_ultima_posicao(self) -> dict:
        """Última posição do provedor GPS em `dumpsys location`."""
        posicao = parse_ultima_posicao(self.adb_shell("dumpsys location"))
        if posicao is None:
            raise RuntimeError("`dumpsys location` não informou nenhuma posição de GPS")
        return posicao

    def reset_geolocation(self):
        self._mobile("resetGeolocation")

    # ------------------------------------------------------------ inicialização
    def medir_inicio(self, package, activity, modo) -> dict:
        """`am start -W` frio (mata o processo) ou morno (mantém o processo, recria a activity).

        O Android decide o estado real, que volta em `estado`: COLD, WARM ou HOT.
        """
        componente = f"{package}/{activity}"
        if modo == "frio":
            saida = self.adb_shell(f"am start -W -S -n {componente}")
        elif modo == "morno":
            self.adb_shell("input keyevent HOME")
            # FLAG_ACTIVITY_NEW_TASK | FLAG_ACTIVITY_CLEAR_TASK: destrói a activity, não o processo
            saida = self.adb_shell(f"am start -W -f 0x10008000 -n {componente}")
        else:
            raise ValueError(f"modo de início desconhecido: {modo}")
        medida = parse_am_start(saida)
        if medida["total_ms"] is None:
            raise RuntimeError(f"`am start -W` não informou TotalTime:\n{saida}")
        return medida

    def abrir_activity(self, package, activity):
        saida = self.adb_shell(f"am start -W -n {package}/{activity}")
        if "Error" in saida or "Exception" in saida:
            raise RuntimeError(f"não abriu {activity}:\n{saida}")

    # ------------------------------------------------------------ métricas
    def obter_pid(self, package):
        return parse_pidof(self.adb_shell(f"pidof {package} || true"))

    def obter_pss_mb(self, package):
        return parse_meminfo(self.adb_shell(f"dumpsys meminfo {package}")).get("pss_mb")

    def zerar_gfxinfo(self, package):
        self.adb_shell(f"dumpsys gfxinfo {package} reset")

    def obter_jank(self, package) -> dict:
        return parse_gfxinfo(self.adb_shell(f"dumpsys gfxinfo {package}"))

    def obter_threads(self, pid):
        return parse_threads(self.adb_shell(f"cat /proc/{pid}/status || true"))

    def obter_bateria(self) -> dict:
        return parse_battery(self.adb_shell("dumpsys battery"))

    def obter_pacote_em_foco(self):
        return parse_resumed_package(self.adb_shell("dumpsys activity activities"))

    def tela_bloqueada(self):
        return parse_keyguard(self.adb_shell("dumpsys window"))

    def contar_crashes(self, package) -> int:
        """Crashes do pacote no buffer de crash do logcat (compare antes e depois)."""
        saida = self.adb_shell(f"logcat -d -b crash | grep -c 'Process: {package}' || true")
        return int(saida.strip() or 0)

    def _ler_cpu(self, pid):
        proc = parse_proc_pid_stat(self.adb_shell(f"cat /proc/{pid}/stat || true"))
        total = parse_proc_stat_total(self.adb_shell("cat /proc/stat"))
        return (proc, total)

    def coletar_amostra(self, package) -> dict:
        """Memória, CPU, threads, bateria e temperatura. O PID vazio indica que o app não roda."""
        pid = self.obter_pid(package)
        amostra = {
            "pid": pid, "pss_mb": None, "java_heap_mb": None, "native_heap_mb": None,
            "cpu_pct": None, "threads": None,
        }
        if pid is not None:
            amostra.update(parse_meminfo(self.adb_shell(f"dumpsys meminfo {package}")))
            amostra["threads"] = self.obter_threads(pid)
            atual = self._ler_cpu(pid)
            # a CPU sai da diferença entre leituras do mesmo processo
            anterior = self._cpu_anterior if self._ultimo_pid == pid else None
            amostra["cpu_pct"] = cpu_percent(anterior, atual)
            self._cpu_anterior, self._ultimo_pid = atual, pid
        bateria = self.obter_bateria()
        termica = parse_thermal(self.adb_shell("dumpsys thermalservice || true"))
        temperatura = termica.get("temp_skin_c") or termica.get("temp_cpu_c")
        amostra.update(
            bateria_pct=bateria["battery_pct"],
            carregando=bateria["charging"],
            temperatura_c=temperatura if temperatura is not None else bateria["battery_temp_c"],
        )
        return amostra

    # ------------------------------------------------------------ latência do toque
    def obter_touchscreen(self) -> str:
        dispositivos = parse_getevent_lp(self.adb_shell("getevent -lp"))
        if not dispositivos:
            raise RuntimeError("nenhum touchscreen encontrado em `getevent -lp`")
        return dispositivos[0]["path"]

    def iniciar_getevent(self, dispositivo):
        """Deixa o `getevent -lt` rodando no aparelho, gravando em arquivo.

        `mobile: shell` espera o comando terminar, então o getevent fica em segundo plano
        e o arquivo é lido depois de cada toque.
        """
        self.adb_shell(f"rm -f {GETEVENT_LOG}")
        saida = self.adb_shell(
            f"nohup getevent -lt {dispositivo} > {GETEVENT_LOG} 2>&1 < /dev/null & echo $!"
        )
        self._getevent_pid = int(saida.strip())

    def parar_getevent(self):
        """Encerra só o getevent deste teste: o robô real tem o próprio leitor de toques."""
        if self._getevent_pid is not None:
            self.adb_shell(f"kill {self._getevent_pid} || true")
            self._getevent_pid = None
        self.adb_shell(f"rm -f {GETEVENT_LOG}")

    def medir_latencia_toque(self, package, toque_anterior=None) -> dict:
        """Latência do último toque físico até o primeiro quadro depois dele.

        O `getevent` e o `framestats` usam o relógio monotônico do aparelho, então não é
        preciso sincronizar relógios entre o computador e o celular.
        """
        toque = parse_ultimo_toque(self.adb_shell(f"cat {GETEVENT_LOG}"))
        if toque is None or (toque_anterior is not None and toque <= float(toque_anterior)):
            raise RuntimeError(
                "o `getevent` não registrou um toque novo. Só toque físico aparece aqui: "
                "clique por software e robô simulado não geram esse evento"
            )
        quadros = parse_quadros(self.adb_shell(f"dumpsys gfxinfo {package} framestats"))
        return {"toque_s": toque, "latencia_ms": latencia_toque_ms(toque, quadros)}

    # ------------------------------------------------------------ CSV
    def gravar_csv(self, tipo, **campos) -> str:
        """Acrescenta uma linha em results/nfr/<tipo>_<data-hora>.csv (grava já, sobrevive a falhas)."""
        if tipo not in self._csv:
            RESULTADOS.mkdir(parents=True, exist_ok=True)
            carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self._csv[tipo] = RESULTADOS / f"{tipo}_{carimbo}.csv"
            self._colunas[tipo] = ["data_hora"] + list(campos)
            with self._csv[tipo].open("w", newline="", encoding="utf-8") as arquivo:
                csv.writer(arquivo).writerow(self._colunas[tipo])
            logger.info(f"CSV: {self._csv[tipo]}", also_console=True)
        linha = {"data_hora": datetime.now().isoformat(timespec="seconds"), **campos}
        with self._csv[tipo].open("a", newline="", encoding="utf-8") as arquivo:
            csv.writer(arquivo).writerow(
                [_numero_ou_vazio(linha.get(coluna)) for coluna in self._colunas[tipo]]
            )
        return str(self._csv[tipo])

    # ------------------------------------------------------------ cálculos como keywords
    def calcular_percentil(self, valores, p):
        return percentil(valores, p)

    def calcular_inclinacao_memoria(self, amostras, aquecimento=0):
        return inclinacao_memoria(amostras, aquecimento)

    def calcular_inclinacao_por_hora(self, horas, valores):
        return inclinacao_por_hora(horas, valores)
