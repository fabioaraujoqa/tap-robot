"""Controle do "dedo" robótico: tap, swipe e long press via G-code na P1S.

Convenção de Z da Bambu: Z = distância entre o bico e a mesa. Z MAIOR = mesa mais
baixa (ponteira mais longe da tela). Para tocar, o Z DIMINUI.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Optional

from .calibration import Calibration
from .config import ConfigError

log = logging.getLogger("taprobot")


class DryRunLink:
    """Imprime o G-code em vez de enviar. Bom para testar sem a impressora."""

    def connect(self, *a, **k):
        pass

    def close(self):
        pass

    def send_gcode(self, gcode, wait_ack=True):
        print("[dry-run] G-code:\n  " + gcode.rstrip().replace("\n", "\n  "))
        return None


class RobotTap:
    def __init__(self, cfg: dict, link, calibration: Optional[Calibration] = None, sleep=time.sleep):
        self.cfg = cfg
        self.m = cfg["motion"]
        self.screen = cfg["screen"]
        self.link = link
        self.cal = calibration
        self._z_contact = calibration.z_contact if calibration else None
        self._sleep = sleep
        self._pos = None  # (x, y, z) conhecido após o último movimento

    # ------------------------------------------------------------------ estado
    @property
    def pos(self):
        return self._pos

    @property
    def z_contact(self) -> float:
        if self._z_contact is None:
            raise ConfigError("z_contact desconhecido: rode `python -m tools.calibrate run`")
        return self._z_contact

    def set_z_contact(self, z: float):
        self._z_contact = float(z)

    def set_calibration(self, cal: Calibration):
        self.cal = cal
        self._z_contact = cal.z_contact

    def _need_cal(self) -> Calibration:
        if self.cal is None:
            raise ConfigError("sem calibração: rode `python -m tools.calibrate run`")
        return self.cal

    # ------------------------------------------------------------------ segurança
    def _check_xy(self, x, y):
        m = self.m
        if not (m["x_min"] <= x <= m["x_max"] and m["y_min"] <= y <= m["y_max"]):
            raise ValueError(
                f"ponto X={x:.1f} Y={y:.1f} mm fora dos limites configurados "
                f"(X {m['x_min']}..{m['x_max']}, Y {m['y_min']}..{m['y_max']})"
            )

    def _check_z(self, z):
        m = self.m
        if z < m["z_floor"] - 1e-9:
            raise ValueError(f"Z={z:.2f} abaixo do z_floor ({m['z_floor']}); movimento bloqueado")
        if z > m["z_max"] + 1e-9:
            raise ValueError(f"Z={z:.2f} acima do z_max ({m['z_max']})")

    def _z_levels(self):
        hover = self.z_contact + self.m["hover_mm"]
        touch = self.z_contact - self.m["press_mm"]
        self._check_z(touch)
        self._check_z(hover)
        return hover, touch

    # ------------------------------------------------------------------ tempo
    @staticmethod
    def _t(dist, feed):
        if dist <= 1e-6:
            return 0.0
        return dist / (feed / 60.0) + 0.05  # +50 ms de aceleração

    def _xy_dist(self, x, y):
        if self._pos is None:
            return 250.0  # desconhecido: estima o pior caso
        return math.hypot(x - self._pos[0], y - self._pos[1])

    def _z_dist(self, z):
        if self._pos is None:
            return 60.0
        return abs(z - self._pos[2])

    def _exec(self, lines, est_s):
        self.link.send_gcode("\n".join(["G90", *lines, "M400"]))
        self._sleep(est_s + self.m["settle_s"])

    # ------------------------------------------------------------------ movimento livre
    def move_abs(self, x=None, y=None, z=None, feed=None):
        """Movimento livre validado (usado na calibração e em jogging)."""
        if z is not None:
            self._check_z(z)
        if (x is None) != (y is None):
            raise ValueError("informe x e y juntos")
        if x is not None:
            self._check_xy(x, y)

        px, py, pz = self._pos if self._pos else (None, None, None)
        est = 0.0
        parts = []
        if x is not None:
            parts.append(f"X{x:.3f} Y{y:.3f}")
            est += self._t(self._xy_dist(x, y), feed or self.m["feed_xy"])
        if z is not None:
            parts.append(f"Z{z:.3f}")
            est += self._t(self._z_dist(z), feed or self.m["feed_z"])
        if not parts:
            return
        f = feed or (self.m["feed_xy"] if x is not None else self.m["feed_z"])
        self._exec([f"G1 {' '.join(parts)} F{int(f)}"], est)
        self._pos = (
            x if x is not None else px,
            y if y is not None else py,
            z if z is not None else pz,
        )

    # ------------------------------------------------------------------ gestos (mm)
    def tap_mm(self, x, y, dwell_ms=None):
        hover, touch = self._z_levels()
        self._check_xy(x, y)
        m = self.m
        dwell = int(m["tap_dwell_ms"] if dwell_ms is None else dwell_ms)

        est = (
            self._t(self._z_dist(hover), m["feed_z"])
            + self._t(self._xy_dist(x, y), m["feed_xy"])
            + self._t(hover - touch, m["feed_z_touch"])
            + dwell / 1000.0
            + self._t(hover - touch, m["feed_z"])
        )
        self._exec(
            [
                f"G1 Z{hover:.3f} F{int(m['feed_z'])}",
                f"G1 X{x:.3f} Y{y:.3f} F{int(m['feed_xy'])}",
                f"G1 Z{touch:.3f} F{int(m['feed_z_touch'])}",
                f"G4 P{dwell}",
                f"G1 Z{hover:.3f} F{int(m['feed_z'])}",
            ],
            est,
        )
        self._pos = (x, y, hover)

    def swipe_mm(self, x1, y1, x2, y2, duration_s=0.35):
        if duration_s <= 0:
            raise ValueError("duration_s deve ser > 0")
        hover, touch = self._z_levels()
        self._check_xy(x1, y1)
        self._check_xy(x2, y2)
        m = self.m
        dist = math.hypot(x2 - x1, y2 - y1)
        feed = min(max(dist / duration_s * 60.0, 300.0), float(m["max_feed_swipe"]))

        est = (
            self._t(self._z_dist(hover), m["feed_z"])
            + self._t(self._xy_dist(x1, y1), m["feed_xy"])
            + self._t(hover - touch, m["feed_z_touch"])
            + self._t(dist, feed)
            + self._t(hover - touch, m["feed_z"])
        )
        self._exec(
            [
                f"G1 Z{hover:.3f} F{int(m['feed_z'])}",
                f"G1 X{x1:.3f} Y{y1:.3f} F{int(m['feed_xy'])}",
                f"G1 Z{touch:.3f} F{int(m['feed_z_touch'])}",
                f"G1 X{x2:.3f} Y{y2:.3f} F{int(feed)}",
                f"G1 Z{hover:.3f} F{int(m['feed_z'])}",
            ],
            est,
        )
        self._pos = (x2, y2, hover)

    # ------------------------------------------------------------------ gestos (pixels)
    def _check_px(self, x, y):
        cal = self._need_cal()
        margin = self.screen.get("margin_px", 0)
        if not (margin <= x <= cal.screen_w - margin and margin <= y <= cal.screen_h - margin):
            raise ValueError(
                f"ponto ({x:.0f},{y:.0f}) px fora da tela {cal.screen_w}x{cal.screen_h}"
            )

    def tap_px(self, x, y, dwell_ms=None):
        self._check_px(x, y)
        mx, my = self._need_cal().px_to_mm(x, y)
        self.tap_mm(mx, my, dwell_ms=dwell_ms)

    def long_press_px(self, x, y, seconds=1.0):
        self.tap_px(x, y, dwell_ms=int(seconds * 1000))

    def swipe_px(self, x1, y1, x2, y2, duration_s=0.35):
        self._check_px(x1, y1)
        self._check_px(x2, y2)
        cal = self._need_cal()
        ax, ay = cal.px_to_mm(x1, y1)
        bx, by = cal.px_to_mm(x2, y2)
        self.swipe_mm(ax, ay, bx, by, duration_s)

    def tap_element(self, element, **kw):
        """Toca o centro de um WebElement do Appium."""
        r = element.rect
        self.tap_px(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2, **kw)

    # ------------------------------------------------------------------ utilidades
    def home(self, bed_empty: bool = False):
        """G28. Em alguns modelos o homing em Z encosta o bico na mesa: faça com a mesa VAZIA."""
        if not bed_empty:
            raise RuntimeError(
                "home() move a mesa e o cabeçote. Remova gabarito e celular e chame "
                "home(bed_empty=True)."
            )
        self.link.send_gcode("G28")
        self._sleep(self.m["home_wait_s"])
        self._pos = None

    def raise_pen(self):
        hover = self.z_contact + self.m["hover_mm"]
        self.move_abs(z=hover)

    def park(self):
        self.raise_pen()
        park = self.m.get("park")
        if park:
            self.move_abs(x=float(park[0]), y=float(park[1]))

    def close(self):
        try:
            if self._z_contact is not None and self._pos is not None:
                self.raise_pen()
        finally:
            self.link.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
