#!/usr/bin/env python3
"""Calibração do robô de toque usando os próprios toques lidos via adb.

  python -m tools.calibrate run      # calibração completa (jog -> detecta Z -> grade -> salva)
  python -m tools.calibrate verify   # toca pontos aleatórios e mede o erro
  python -m tools.calibrate jog      # só movimenta manualmente (diagnóstico)

Pré-requisitos: P1S já "homed" com a MESA VAZIA, gabarito e celular montados,
tela ligada/desbloqueada (ative "Permanecer ativo" nas opções do desenvolvedor),
depuração USB autorizada, nenhum cabo atrapalhando o caminho da ponteira.
"""
import argparse
import math
import random
import re
import sys
import time
from pathlib import Path

import numpy as np

from taprobot import BambuLink, Calibration, RobotTap, load_config
from taprobot.adb import AdbClient
from taprobot.touch_reader import TouchReader, find_touch_device, get_wm_size

EXPECTED_PX_PER_MM = 10.25  # Moto G06: ~720 px / 70,25 mm de largura útil

INTRO = """
CHECKLIST DE SEGURANÇA
  1. A P1S foi homed (G28) com a mesa VAZIA e continua ligada desde então.
  2. O gabarito e o celular estão fixos na mesa; a tela está acesa e desbloqueada.
  3. A ponteira está firme no cabeçote e a ponta passa ABAIXO do bico.
  4. motion.z_floor no config.yaml está correto (a mesa nunca sobe além dele).
  5. Sua mão fica perto do botão de energia da impressora durante a calibração.
"""

HELP = """
Comandos do jog (a ponteira anda em milímetros):
  x+ / x- / y+ / y- [mm]   move no eixo (sem número usa o passo atual)
  z-  [mm]                 DESCE a ponteira (diminui Z, a mesa sobe)
  z+  [mm]                 SOBE a ponteira
  step N                   define o passo (mm). Em Z o passo padrão é no máx. 1 mm
  pos                      mostra a posição
  ok                       terminei: a ponteira está sobre a tela (pode estar alta)
  q                        cancela
Objetivo: deixar a ponteira em cima da TELA, perto do centro (±8 mm em X, ±15 mm em Y).
Dica: aproxime em Z devagar (z- 10, z- 5...) deixando uns 3 mm antes do contato.
"""


def open_session(cfg, with_cal):
    p = cfg["printer"]
    link = BambuLink(p["ip"], p["serial"], p["access_code"])
    link.connect()
    cal_path = Path(cfg.get("_dir", ".")) / cfg["calibration_file"]
    cal = Calibration.load(cal_path) if with_cal else None
    robot = RobotTap(cfg, link, cal)

    adb = AdbClient(cfg["adb"]["serial"], cfg["adb"]["path"])
    try:
        w, h = get_wm_size(adb)
    except Exception as exc:  # noqa: BLE001
        w, h = cfg["screen"]["width_px"], cfg["screen"]["height_px"]
        print(f"Aviso: não li o tamanho da tela via adb ({exc}); usando {w}x{h} do config.")
    dev = find_touch_device(adb)
    print(f"Touchscreen: {dev['name']} ({dev['path']}), raw máx {dev['max_x']}x{dev['max_y']}; tela {w}x{h}")
    reader = TouchReader(adb, dev, w, h)
    reader.start()
    return robot, reader, (w, h), cal_path, link


def safe_lift(robot):
    try:
        if robot.pos:
            robot.move_abs(z=robot.m["z_start"])
    except Exception as exc:  # noqa: BLE001
        print("Aviso: não consegui subir a ponteira:", exc)


def jog(robot, reader):
    step = 5.0
    print(HELP)
    while True:
        line = input("jog> ").strip().lower()
        if not line:
            continue
        if line in ("ok", "fim"):
            return
        if line in ("q", "quit", "sair"):
            raise SystemExit("cancelado")
        parts = line.split()
        if parts[0] == "pos":
            print("posição (X, Y, Z):", robot.pos)
            continue
        if parts[0] == "step" and len(parts) > 1:
            step = float(parts[1])
            print("passo =", step)
            continue
        m = re.fullmatch(r"([xyz])([+-])", parts[0])
        if not m:
            print("comando não reconhecido (digite ok, pos, step N, x+ ...)")
            continue
        axis, sign = m.groups()
        dist = float(parts[1]) if len(parts) > 1 else (min(step, 1.0) if axis == "z" else step)
        delta = dist if sign == "+" else -dist
        x, y, z = robot.pos
        try:
            if axis == "x":
                robot.move_abs(x=x + delta, y=y)
            elif axis == "y":
                robot.move_abs(x=x, y=y + delta)
            else:
                robot.move_abs(z=z + delta, feed=robot.m["feed_z_touch"] if delta < 0 else None)
        except ValueError as exc:
            print("BLOQUEADO:", exc)
            continue
        print("posição (X, Y, Z): %.2f, %.2f, %.2f" % robot.pos, "  [celular sentindo toque]" if reader.in_contact else "")


def auto_descend(robot, reader, step):
    floor = robot.m["z_floor"]
    z = robot.pos[2]
    downs = reader.down_count
    print(f"Descendo de {z:.2f} em passos de {step} mm até o celular sentir o toque (limite {floor})...")
    while True:
        z -= step
        if z < floor:
            raise RuntimeError(
                "cheguei no z_floor sem detectar toque. Possíveis causas: ponteira fora da tela, "
                "ponteira sem contato elétrico (tente aterrar a espuma/borracha condutiva), "
                "ou z_floor alto demais."
            )
        robot.move_abs(z=z, feed=robot.m["feed_z_touch"])
        time.sleep(0.15)
        if reader.down_count > downs:
            return z


def tap_and_read(robot, reader, x, y):
    n = len(reader.contacts)
    robot.tap_mm(x, y)
    q = reader.wait_contact(n, timeout=3.0)
    if q is None:
        raise RuntimeError(
            f"toque não detectado em X={x:.1f} Y={y:.1f} mm. A ponteira provavelmente saiu da tela; "
            "refaça a calibração começando mais perto do centro."
        )
    return q


def cmd_jog(args):
    cfg = load_config(args.config)
    robot, reader, _, _, link = open_session(cfg, False)
    try:
        print(INTRO)
        input("Enter para continuar (Ctrl+C cancela)... ")
        m = robot.m
        robot.move_abs(z=m["z_start"])
        robot.move_abs(x=(m["x_min"] + m["x_max"]) / 2, y=(m["y_min"] + m["y_max"]) / 2)
        jog(robot, reader)
    finally:
        safe_lift(robot)
        reader.stop()
        link.close()


def cmd_run(args):
    cfg = load_config(args.config)
    robot, reader, (W, H), cal_path, link = open_session(cfg, False)
    try:
        print(INTRO)
        input("Enter para continuar (Ctrl+C cancela)... ")
        m = robot.m
        sx = args.start_x if args.start_x is not None else (m["x_min"] + m["x_max"]) / 2
        sy = args.start_y if args.start_y is not None else (m["y_min"] + m["y_max"]) / 2
        robot.move_abs(z=m["z_start"])
        robot.move_abs(x=sx, y=sy)

        print("PASSO 1: posicione a ponteira sobre a tela.")
        jog(robot, reader)

        n0 = len(reader.contacts)
        zc = auto_descend(robot, reader, args.z_step)
        x0, y0, _ = robot.pos
        robot.move_abs(z=zc + 3.0)
        q0 = reader.wait_contact(n0)
        if q0 is None:
            raise RuntimeError("o celular não concluiu o toque inicial (ele foi detectado mas não liberado?)")
        robot.set_z_contact(zc)
        print(f"PASSO 2: Z de contato = {zc:.2f} mm; primeiro toque em ({q0[0]:.0f}, {q0[1]:.0f}) px")

        mm_pts, px_pts = [(x0, y0)], [q0]
        print("PASSO 3: toques de sondagem para descobrir orientação e escala...")
        for dx, dy in ((10.0, 0.0), (0.0, 10.0)):
            q = tap_and_read(robot, reader, x0 + dx, y0 + dy)
            mm_pts.append((x0 + dx, y0 + dy))
            px_pts.append(q)

        d1 = (np.array(px_pts[1]) - np.array(px_pts[0])) / 10.0
        d2 = (np.array(px_pts[2]) - np.array(px_pts[0])) / 10.0
        J = np.column_stack([d1, d2])  # px por mm
        scale = [float(np.linalg.norm(d1)), float(np.linalg.norm(d2))]
        print(f"  escala medida: {scale[0]:.1f} e {scale[1]:.1f} px/mm (esperado ~{EXPECTED_PX_PER_MM})")
        if abs(np.linalg.det(J)) < 1.0:
            raise RuntimeError("sondagem degenerada (os dois toques caíram no mesmo ponto?)")
        if not all(0.6 * EXPECTED_PX_PER_MM < s < 1.6 * EXPECTED_PX_PER_MM for s in scale):
            print("  AVISO: escala bem diferente do esperado; confira o movimento da ponteira.")
        Jinv = np.linalg.inv(J)
        p0 = np.array([x0, y0])
        q0a = np.array(px_pts[0])

        print("PASSO 4: grade 3x3 sobre a tela...")
        for fy in (0.08, 0.5, 0.92):
            for fx in (0.12, 0.5, 0.88):
                target = np.array([fx * W, fy * H])
                p = p0 + Jinv @ (target - q0a)
                try:
                    q = tap_and_read(robot, reader, float(p[0]), float(p[1]))
                except ValueError as exc:
                    raise RuntimeError(f"ponto da grade fora dos limites do robô: {exc}") from exc
                mm_pts.append((float(p[0]), float(p[1])))
                px_pts.append(q)
                print(f"  alvo ({target[0]:.0f},{target[1]:.0f}) px -> leu ({q[0]:.0f},{q[1]:.0f}) px")

        cal = Calibration.from_pairs(px_pts, mm_pts, zc, W, H)
        cal.save(cal_path)
        robot.set_calibration(cal)
        print(f"\nCalibração salva em {cal_path}")
        print(f"Erro máximo do ajuste: {cal.fit_error_mm:.2f} mm (bom: < 0,5 mm)")
        if cal.fit_error_mm > 0.5:
            print("AVISO: erro alto. Verifique se o celular está firme no gabarito e repita.")
        robot.park()
        print("Agora rode: python -m tools.calibrate verify")
    finally:
        safe_lift(robot)
        reader.stop()
        link.close()


def cmd_verify(args):
    cfg = load_config(args.config)
    robot, reader, (W, H), _, link = open_session(cfg, True)
    try:
        cal = robot.cal
        mm_per_px = math.sqrt(abs(np.linalg.det(np.array(cal.affine)[:, :2])))
        rng = random.Random(7)
        pts = [(0.1 * W, 0.1 * H), (0.9 * W, 0.1 * H), (0.1 * W, 0.9 * H), (0.9 * W, 0.9 * H), (0.5 * W, 0.5 * H)]
        pts += [(rng.uniform(0.15, 0.85) * W, rng.uniform(0.15, 0.85) * H) for _ in range(5)]
        errs = []
        for x, y in pts:
            n = len(reader.contacts)
            robot.tap_px(x, y)
            q = reader.wait_contact(n, timeout=3.0)
            if q is None:
                print(f"alvo ({x:.0f},{y:.0f}) px -> SEM TOQUE")
                errs.append(float("inf"))
                continue
            e_px = math.hypot(q[0] - x, q[1] - y)
            errs.append(e_px * mm_per_px)
            print(f"alvo ({x:4.0f},{y:4.0f}) px -> leu ({q[0]:4.0f},{q[1]:4.0f}) px | erro {e_px:5.1f} px = {e_px * mm_per_px:.2f} mm")
        worst = max(errs)
        print(f"\nPior erro: {worst:.2f} mm. " + ("OK para botões >= 4 mm." if worst < 1.0 else "Acima de 1 mm: recalibre."))
        robot.park()
    finally:
        safe_lift(robot)
        reader.stop()
        link.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["run", "verify", "jog"])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--z-step", type=float, default=0.1, help="passo da descida automática (mm)")
    ap.add_argument("--start-x", type=float, default=None, help="X inicial do bico (mm)")
    ap.add_argument("--start-y", type=float, default=None, help="Y inicial do bico (mm)")
    args = ap.parse_args()
    try:
        {"run": cmd_run, "verify": cmd_verify, "jog": cmd_jog}[args.command](args)
    except KeyboardInterrupt:
        sys.exit("\ninterrompido")
    except (RuntimeError, ValueError) as exc:
        sys.exit(f"ERRO: {exc}")


if __name__ == "__main__":
    main()
