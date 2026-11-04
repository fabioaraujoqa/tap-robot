"""Palavras-chave do robô de toque físico (Bambu Lab P1S) para o Robot Framework.

Envolve o `taprobot.RobotTap`: o Appium localiza o elemento, o robô toca o centro dele
com a ponteira. As coordenadas são PIXELS da tela, as mesmas do Appium.

    Library    ../libraries/TapRobotLibrary.py    simulado=${SIMULADO}

Com `simulado=True` nada é enviado à impressora: o G-code de cada toque vai para o log
do Robot, e a calibração é fictícia. Serve para validar os testes sem hardware.

Com o robô real, todo gesto só passa se o celular sentir o contato (via `getevent`). Isso
não olha o app: garante que a ponteira encostou. No modo simulado não há essa confirmação.
"""
from __future__ import annotations

from pathlib import Path

from robot.api import logger
from robot.api.deco import keyword, library
from robot.libraries.BuiltIn import BuiltIn

from taprobot import BambuLink, Calibration, RobotTap, load_config, simulated_robot
from taprobot.adb import AdbClient
from taprobot.device import DEFAULT_SERIAL, resolve_udid
from taprobot.touch_reader import TouchReader, find_touch_device, get_wm_size

ROOT = Path(__file__).resolve().parents[3]
TOUCH_TIMEOUT_S = 3.0  # folga: o robô só estima quando o movimento termina


def _bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "sim", "yes", "on")
    return bool(value)


@library(scope="GLOBAL", auto_keywords=False)
class TapRobotLibrary:
    def __init__(self, config: str = str(ROOT / "config.yaml"), simulado=False):
        self.config_path = config
        self.simulated = _bool(simulado)
        self.robot: RobotTap | None = None
        self.reader: TouchReader | None = None

    # ------------------------------------------------------------ conexão
    @keyword("Conectar Robô")
    def connect(self, udid=None):
        """Conecta na P1S, carrega a calibração e passa a ler os toques do celular (ou simula)."""
        if self.robot is not None:
            return
        if self.simulated:
            self.robot = simulated_robot(on_send=lambda g: logger.debug("G-code simulado:\n" + g.rstrip()))
            logger.warn("Robô em modo SIMULADO: os toques não são reais.")
            return
        cfg = load_config(self.config_path)
        cal_path = Path(cfg["_dir"]) / cfg["calibration_file"]
        if not cal_path.exists():
            raise RuntimeError(f"{cal_path.name} não encontrado: rode `python -m tools.calibrate run`")
        cal = Calibration.load(cal_path)
        adb_path = cfg["adb"]["path"]
        adb = AdbClient(udid or cfg["adb"]["serial"] or resolve_udid(adb=adb_path), adb_path)
        width, height = get_wm_size(adb)
        reader = TouchReader(adb, find_touch_device(adb), width, height)
        p = cfg["printer"]
        link = BambuLink(p["ip"], p["serial"], p["access_code"])
        link.connect()
        self.robot = RobotTap(cfg, link, cal)
        reader.start()
        self.reader = reader
        logger.info(f"Robô conectado (erro de calibração {cal.fit_error_mm:.2f} mm).")

    @keyword("Desconectar Robô")
    def disconnect(self):
        """Estaciona a ponteira e fecha a conexão. Seguro chamar mais de uma vez."""
        if self.robot is None:
            return
        try:
            self.robot.park()
        finally:
            self.robot.link.close()
            self.robot = None
            if self.reader is not None:
                self.reader.stop()
                self.reader = None

    @keyword("Robô Está Simulado")
    def is_simulated(self) -> bool:
        return self.simulated

    def _robot(self) -> RobotTap:
        if self.robot is None:
            raise RuntimeError("robô não conectado: chame `Conectar Robô` antes")
        return self.robot

    def _gesture(self, action):
        """Executa o gesto e, com o robô real, exige que o celular tenha sentido o contato."""
        before = len(self.reader.contacts) if self.reader else 0
        action(self._robot())
        if self.reader and self.reader.wait_contact(before, timeout=TOUCH_TIMEOUT_S) is None:
            raise RuntimeError(f"o celular não sentiu o toque em {TOUCH_TIMEOUT_S:.0f} s (ponteira não encostou?)")

    # ------------------------------------------------------------ gestos por elemento
    def _center(self, locator):
        appium = BuiltIn().get_library_instance("AppiumLibrary")
        r = appium.get_element_rect(locator)
        x, y = r["x"] + r["width"] / 2, r["y"] + r["height"] / 2
        return x, y

    @keyword("Toque Físico No Elemento")
    def tap_element(self, locator, dwell_ms=None):
        """Toca fisicamente o centro do elemento encontrado pelo Appium."""
        x, y = self._center(locator)
        logger.info(f"Toque físico em '{locator}' ({x:.0f}, {y:.0f}) px")
        self._gesture(lambda r: r.tap_px(x, y, dwell_ms=int(dwell_ms) if dwell_ms is not None else None))

    @keyword("Toque Longo Físico No Elemento")
    def long_press_element(self, locator, segundos=1.0):
        x, y = self._center(locator)
        logger.info(f"Toque longo físico em '{locator}' ({x:.0f}, {y:.0f}) px por {segundos}s")
        self._gesture(lambda r: r.long_press_px(x, y, seconds=float(segundos)))

    @keyword("Arraste Físico Entre Elementos")
    def drag_elements(self, origem, destino, duracao=0.8, espera=0.6):
        """Encosta no centro de `origem`, espera `espera` s e arrasta até o centro de `destino`."""
        x1, y1 = self._center(origem)
        x2, y2 = self._center(destino)
        logger.info(f"Arraste físico de '{origem}' para '{destino}'")
        self._gesture(lambda r: r.swipe_px(x1, y1, x2, y2, duration_s=float(duracao), hold_s=float(espera)))

    # ------------------------------------------------------------ gestos por coordenada
    @keyword("Toque Físico Em Coordenada")
    def tap_xy(self, x, y, dwell_ms=None):
        self._gesture(lambda r: r.tap_px(float(x), float(y), dwell_ms=int(dwell_ms) if dwell_ms is not None else None))

    @keyword("Toque Longo Físico Em Coordenada")
    def long_press_xy(self, x, y, segundos=1.0):
        self._gesture(lambda r: r.long_press_px(float(x), float(y), seconds=float(segundos)))

    @keyword("Arraste Físico")
    def swipe(self, x1, y1, x2, y2, duracao=0.35, espera=0):
        """Arrasta de (x1, y1) até (x2, y2) px em `duracao` s, depois de `espera` s encostado."""
        self._gesture(lambda r: r.swipe_px(float(x1), float(y1), float(x2), float(y2),
                                           duration_s=float(duracao), hold_s=float(espera)))

    @keyword("Estacionar Ponteira")
    def park(self):
        self._robot().park()

    # ------------------------------------------------------------ celular
    @keyword("Descobrir Celular")
    def find_device(self, serial=DEFAULT_SERIAL) -> str:
        """Devolve o UDID do celular: o serial no USB ou IP:porta no Wi-Fi (conecta sozinho)."""
        udid = resolve_udid(serial)
        logger.info(f"Celular {serial}: {udid}")
        return udid
