"""Guardião: decide quando o teste deve parar e garante que a ponteira seja estacionada.

Para (Abort) quando: o app cai mais vezes que o permitido, a tela apaga, o adb fica
fora tempo demais, o robô/MQTT erra seguidamente, a bateria esquenta demais, o
orçamento de toques estoura, a verificação de calibração falha ou chega SIGINT/SIGTERM.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Callable, Optional

from . import parsers
from .adb import AdbError

log = logging.getLogger("soak.guardian")


class Abort(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


class Guardian:
    def __init__(self, sc, collector, adb, robot, events, clock: Callable[[], float] = time.monotonic,
                 probe=None):
        self.sc, self.col, self.adb, self.robot, self.events = sc, collector, adb, robot, events
        self.clock = clock
        self.probe = probe
        self.lim = sc.limits
        self.restarts = 0
        self.robot_errors = 0
        self.adb_down_since: Optional[float] = None
        self.stop_reason: Optional[str] = None
        self.pending_restart: Optional[str] = None
        self.calibration_errors_px: list[float] = []

    # ------------------------------------------------------------ sinais e logcat
    def request_stop(self, reason: str):
        self.stop_reason = reason

    def on_event(self, ev: dict):
        """Chamado pela thread do logcat. Só marca; quem age é o laço principal."""
        if ev["type"] == "anr":
            self.pending_restart = "ANR"  # a janela de ANR bloquearia os toques

    def check_stop(self):
        if self.stop_reason:
            raise Abort("user", self.stop_reason)

    # ------------------------------------------------------------ antes de começar
    def preflight(self) -> dict:
        """Confere o aparelho e devolve informações para o relatório."""
        info = {}
        try:
            for key, cmd in (("model", "getprop ro.product.model"), ("android", "getprop ro.build.version.release"),
                             ("brightness", "settings get system screen_brightness"),
                             ("brightness_auto", "settings get system screen_brightness_mode"),
                             ("screen_off_timeout_ms", "settings get system screen_off_timeout"),
                             ("stay_on_while_plugged", "settings get global stay_on_while_plugged_in")):
                info[key] = self.adb.shell(cmd).strip()
            hb = self.col.heartbeat()
            keyguard = parsers.parse_keyguard(self.adb.shell("dumpsys window | grep -E 'isKeyguardShowing|mShowingLockscreen'"))
            battery = parsers.parse_battery(self.adb.shell("dumpsys battery"))
        except AdbError as exc:
            raise Abort("adb", f"celular não responde no adb: {exc}") from exc

        if hb["screen_on"] is False:
            raise Abort("screen", "a tela está apagada: acenda e desbloqueie o celular antes de começar")
        if keyguard:
            raise Abort("screen", "o celular está na tela de bloqueio: desbloqueie antes de começar")
        if self.sc.mode == "consumo" and battery["charging"]:
            raise Abort("power", "modo consumo com o celular carregando: tire o cabo (use adb pelo Wi-Fi)")
        if self.sc.mode == "soak" and not battery["charging"]:
            self.events.add("warning", "modo soak na bateria: o celular pode descarregar durante o teste")
        info["charging_at_start"] = battery["charging"]

        timeout_ms = parsers._int(info.get("screen_off_timeout_ms"))
        stay_on = parsers._int(info.get("stay_on_while_plugged")) or 0
        duration_ms = (self.sc.duration_min or 0) * 60_000
        if timeout_ms and timeout_ms < max(duration_ms, 120_000) and not (battery["charging"] and stay_on):
            self.events.add("warning", f"a tela apaga após {timeout_ms // 1000}s sem toque: o teste vai parar se ela apagar "
                                       "(ative 'Permanecer ativo' no carregador ou aumente o tempo de tela)")
        if info.get("brightness_auto") == "1" and self.sc.mode == "consumo":
            self.events.add("warning", "brilho automático ligado: a medida de consumo varia com a luz do ambiente")
        self.start_app("início do teste")
        return info

    # ------------------------------------------------------------ app
    def start_app(self, why: str):
        pkg = self.sc.package
        if self.sc.activity:
            act = self.sc.activity if "/" in self.sc.activity else f"{pkg}/{self.sc.activity}"
            self.adb.shell(f"am start -n {act}")
        else:
            self.adb.shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
        self.events.add("app_start", why)

    def restart_app(self, why: str):
        self.restarts += 1
        if self.restarts > int(self.lim["app_restarts_max"]):
            raise Abort("app", f"app caiu ou travou {self.restarts} vezes (limite {self.lim['app_restarts_max']}); último: {why}")
        self.events.add("app_restart", f"{why} (reinício {self.restarts}/{self.lim['app_restarts_max']})")
        if why == "ANR":
            self.adb.shell(f"am force-stop {self.sc.package}")
        self.start_app(why)

    # ------------------------------------------------------------ verificações periódicas
    def heartbeat(self) -> bool:
        """Checagem rápida. Devolve False se o adb está fora (não tocar enquanto isso)."""
        now = self.clock()
        try:
            hb = self.col.heartbeat()
        except AdbError as exc:
            if self.adb_down_since is None:
                self.adb_down_since = now
                self.events.add("adb_offline", str(exc))
            down = now - self.adb_down_since
            if down > float(self.lim["adb_offline_max_s"]):
                raise Abort("adb", f"adb fora há {down:.0f}s (limite {self.lim['adb_offline_max_s']}s)")
            return False
        if self.adb_down_since is not None:
            self.events.add("adb_online", f"voltou após {now - self.adb_down_since:.0f}s")
            self.adb_down_since = None

        if hb["screen_on"] is False:
            raise Abort("screen", "a tela apagou (bloqueio automático? queda de energia?)")
        if self.pending_restart:
            why, self.pending_restart = self.pending_restart, None
            self.restart_app(why)
        elif not hb["app_alive"]:
            self.restart_app("app não está rodando")
        return True

    def check_sample(self, row: dict):
        temp = row.get("battery_temp_c")
        if temp is not None and temp > float(self.lim["battery_temp_max_c"]):
            raise Abort("temperature", f"bateria a {temp:.1f} °C (limite {self.lim['battery_temp_max_c']} °C)")
        if self.sc.mode == "consumo" and row.get("charging"):
            raise Abort("power", "o celular começou a carregar no meio do teste de consumo")
        fg = row.get("foreground")
        if row.get("app_alive") and fg and fg != self.sc.package:
            self.restart_app(f"app saiu do primeiro plano (em primeiro plano: {fg})")

    def check_touches(self, touches: int):
        if touches >= int(self.lim["max_touches"]):
            raise Abort("budget", f"orçamento de {self.lim['max_touches']} toques atingido")

    # ------------------------------------------------------------ robô
    def robot_call(self, fn: Callable[[], None]):
        """Executa um gesto. Erros seguidos do robô/MQTT abortam; limite de segurança aborta na hora."""
        try:
            fn()
        except ValueError as exc:  # z_floor, limites XY, ponto fora da tela: cenário ou calibração errados
            raise Abort("robot", f"movimento bloqueado pela trava de segurança: {exc}") from exc
        except Abort:
            raise
        except Exception as exc:  # noqa: BLE001  rede, MQTT, impressora
            self.robot_errors += 1
            self.events.add("robot_error", f"{type(exc).__name__}: {exc}")
            if self.robot_errors >= int(self.lim["robot_errors_max"]):
                raise Abort("robot", f"{self.robot_errors} erros seguidos do robô; último: {exc}") from exc
            return
        self.robot_errors = 0

    def calibration_check(self):
        cc = self.sc.calibration_check
        if not cc or self.probe is None:
            return
        x, y = float(cc["x"]), float(cc["y"])
        got = self.probe(self.robot, x, y)
        if got is None:
            raise Abort("calibration", f"verificação de calibração: o celular não sentiu o toque em ({x:.0f}, {y:.0f}) px")
        err = math.hypot(got[0] - x, got[1] - y)
        self.calibration_errors_px.append(err)
        if err > float(cc["tolerance_px"]):
            raise Abort("calibration", f"verificação de calibração: erro de {err:.0f} px (tolerância {cc['tolerance_px']} px)")
        self.events.add("calibration_ok", f"erro {err:.1f} px", error_px=round(err, 1))

    # ------------------------------------------------------------ saída segura
    def safe_park(self):
        try:
            self.robot.park()
            self.events.add("robot_parked", "ponteira estacionada")
        except Exception as exc:  # noqa: BLE001
            self.events.add("robot_error", f"NÃO consegui estacionar a ponteira: {exc}")
