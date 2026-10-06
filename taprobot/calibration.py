"""Conversão pixel (tela do celular) -> mm (coordenadas do bico da P1S).

Usa uma transformação afim (rotação, escala, cisalhamento e translação), que
absorve qualquer orientação do celular na base e o deslocamento da ponteira em
relação ao bico.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


def fit_affine(src_pts, dst_pts):
    """Ajusta dst = M @ [src, 1] por mínimos quadrados.

    Retorna (M 2x3, erro por ponto na unidade de dst).
    """
    src = np.asarray(src_pts, dtype=float)
    dst = np.asarray(dst_pts, dtype=float)
    if src.shape[0] < 3 or src.shape != dst.shape:
        raise ValueError("são necessários >= 3 pares de pontos (mesmo formato)")
    A = np.hstack([src, np.ones((src.shape[0], 1))])
    if np.linalg.matrix_rank(A) < 3:
        raise ValueError("pontos colineares: não dá para calibrar")
    sol, *_ = np.linalg.lstsq(A, dst, rcond=None)  # (3, 2)
    err = np.linalg.norm(A @ sol - dst, axis=1)
    return sol.T, err


@dataclass
class Calibration:
    affine: list  # 2x3, px -> mm
    z_contact: float
    screen_w: int
    screen_h: int
    fit_error_mm: float = 0.0
    points: list = field(default_factory=list)  # [{"px":[x,y], "mm":[x,y]}]

    def px_to_mm(self, x: float, y: float):
        a = self.affine
        return (
            a[0][0] * x + a[0][1] * y + a[0][2],
            a[1][0] * x + a[1][1] * y + a[1][2],
        )

    def mm_to_px(self, X: float, Y: float):
        m = np.asarray(self.affine, dtype=float)
        px = np.linalg.solve(m[:, :2], np.array([X, Y]) - m[:, 2])
        return float(px[0]), float(px[1])

    @classmethod
    def from_pairs(cls, px_pts, mm_pts, z_contact, screen_w, screen_h):
        m, err = fit_affine(px_pts, mm_pts)
        pts = [
            {"px": [float(p[0]), float(p[1])], "mm": [float(q[0]), float(q[1])]}
            for p, q in zip(px_pts, mm_pts)
        ]
        return cls(
            affine=m.tolist(),
            z_contact=float(z_contact),
            screen_w=int(screen_w),
            screen_h=int(screen_h),
            fit_error_mm=float(err.max()),
            points=pts,
        )

    @classmethod
    def simulated(cls, cfg, screen_mm=(70.0, 160.0)):
        """Calibração fictícia para dry-run: a tela vira um retângulo centrado nos limites XY.

        Não corresponde a nenhuma montagem real. Nunca use com a impressora.
        """
        m, s = cfg["motion"], cfg["screen"]
        w, h = int(s["width_px"]), int(s["height_px"])
        x0 = (m["x_min"] + m["x_max"] - screen_mm[0]) / 2
        y0 = (m["y_min"] + m["y_max"] - screen_mm[1]) / 2
        return cls(
            affine=[[screen_mm[0] / w, 0.0, x0], [0.0, screen_mm[1] / h, y0]],
            z_contact=m["z_floor"] + m["press_mm"] + 1.0,
            screen_w=w,
            screen_h=h,
        )

    def save(self, path):
        Path(path).write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)
