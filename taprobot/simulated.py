"""Robô simulado: o mesmo RobotTap, sem impressora e sem calibração real.

Usado pelo --dry-run do servidor e do soak e pelo modo SIMULADO do Robot Framework.
As coordenadas em mm não correspondem a nenhuma montagem: nunca use com a P1S.
"""
from __future__ import annotations

from .calibration import Calibration
from .config import normalize_config
from .robot import DryRunLink, RobotTap, _print_gcode

SIMULATED_Z_FLOOR = 14.0  # só para a simulação; não move nada de verdade


def simulated_config() -> dict:
    return normalize_config({"motion": {"z_floor": SIMULATED_Z_FLOOR}}, require_printer=False)


def simulated_robot(on_send=_print_gcode, cfg: dict | None = None,
                    calibration: Calibration | None = None) -> RobotTap:
    """RobotTap que entrega cada G-code a `on_send` em vez de enviar (None = descarta)."""
    cfg = cfg or simulated_config()
    cal = calibration or Calibration.simulated(cfg)
    return RobotTap(cfg, DryRunLink(on_send), cal, sleep=lambda s: None)
