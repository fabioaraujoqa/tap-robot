"""Leitura e validação da configuração."""
from __future__ import annotations

from pathlib import Path

import yaml


class ConfigError(ValueError):
    pass


DEFAULT_MOTION = dict(
    z_floor=None,
    z_start=40.0,
    z_max=80.0,
    x_min=10.0,
    x_max=245.0,
    y_min=10.0,
    y_max=245.0,
    hover_mm=2.0,
    press_mm=0.4,
    tap_dwell_ms=60,
    feed_xy=6000,
    feed_z=1200,
    feed_z_touch=300,
    max_feed_swipe=9000,
    settle_s=0.15,
    home_wait_s=90,
    park=None,
)

DEFAULT_SCREEN = dict(width_px=720, height_px=1640, margin_px=4)


def normalize_config(raw: dict, require_printer: bool = True) -> dict:
    """Aplica defaults e valida. Aceita dict cru (útil em testes)."""
    raw = raw or {}
    printer = dict(raw.get("printer") or {})
    if require_printer:
        for key in ("ip", "serial", "access_code"):
            value = str(printer.get(key) or "")
            if not value or value.startswith("COLOQUE"):
                raise ConfigError(f"printer.{key} não configurado em config.yaml")

    motion = {**DEFAULT_MOTION, **(raw.get("motion") or {})}
    if motion["z_floor"] is None:
        raise ConfigError(
            "motion.z_floor é obrigatório (Z mínimo permitido). "
            "Veja o comentário em config.example.yaml."
        )
    motion["z_floor"] = float(motion["z_floor"])
    if motion["x_min"] >= motion["x_max"] or motion["y_min"] >= motion["y_max"]:
        raise ConfigError("limites XY inválidos (min >= max)")
    if motion["z_floor"] >= motion["z_max"]:
        raise ConfigError("z_floor deve ser menor que z_max")

    return {
        "printer": printer,
        "motion": motion,
        "screen": {**DEFAULT_SCREEN, **(raw.get("screen") or {})},
        "adb": {"path": "adb", "serial": None, **(raw.get("adb") or {})},
        "calibration_file": raw.get("calibration_file", "calibration.json"),
    }


def load_config(path: str | Path = "config.yaml", require_printer: bool = True) -> dict:
    p = Path(path)
    if not p.exists():
        raise ConfigError(
            f"{p} não encontrado. Copie config.example.yaml para config.yaml e edite."
        )
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cfg = normalize_config(raw, require_printer=require_printer)
    cfg["_dir"] = str(p.resolve().parent)
    return cfg
