"""Linha de comando do teste de resistência.

  python -m soak run cenario.yaml [--serial IP:porta] [--duration-min N] [--yes]
  python -m soak run cenario.yaml --dry-run          # sem P1S e sem celular (dados falsos)
  python -m soak report runs/<pasta>                 # (re)gera o relatório
  python -m soak ui [--serial IP:porta]              # lista itens da tela com coordenadas
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from .adb import AdbClient, AdbError, pick_serial
from .report import build_report
from .scenario import ScenarioError, WearCounter, load_scenario

ROOT = Path(__file__).resolve().parents[1]

CHECKLIST = """
ATENÇÃO: a impressora vai se mover sozinha durante todo o teste.
  1. A P1S foi homed (G28) com a mesa VAZIA e não foi desligada desde então.
  2. calibration.json é desta montagem (`python calibrate.py verify` passou há pouco).
  3. motion.z_floor no config.yaml está correto para o celular na base.
  4. A base está presa na mesa e o celular firme nela; nenhum cabo no caminho da ponteira.
  5. Tela desbloqueada e configurada para não apagar durante o teste.
  6. Você vai acompanhar as primeiras execuções com a mão perto do botão de energia.
"""


class RobotLinkError(RuntimeError):
    pass


class AckLink:
    """Envolve o BambuLink: comando sem confirmação vira erro (o guardião conta e aborta)."""

    def __init__(self, inner):
        self.inner = inner

    def send_gcode(self, gcode, wait_ack=True):
        r = self.inner.send_gcode(gcode, wait_ack=wait_ack)
        if wait_ack and r is None:
            raise RobotLinkError("a impressora não confirmou o comando (MQTT caiu?)")
        return r

    def close(self):
        self.inner.close()


class CountingLink:
    """Link do dry-run: só conta os comandos (o DryRunLink imprimiria cada G-code)."""

    def __init__(self):
        self.sent = 0

    def send_gcode(self, gcode, wait_ack=True):
        self.sent += 1

    def close(self):
        pass


class TouchProbe:
    """Verificação de calibração real: toca e lê o pixel sentido pelo celular (getevent)."""

    def __init__(self, serial: str, adb_path: str = "adb"):
        from taprobot.touch_reader import Adb, TouchReader, find_touch_device, get_wm_size
        adb = Adb(adb_path, serial)
        w, h = get_wm_size(adb)
        self.reader = TouchReader(adb, find_touch_device(adb), w, h)
        self.reader.start()

    def __call__(self, robot, x, y):
        n = len(self.reader.contacts)
        robot.tap_px(x, y)
        return self.reader.wait_contact(n, timeout=3.0)

    def stop(self):
        self.reader.stop()


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "run"


def apply_overrides(sc, args):
    if args.duration_min is not None:
        sc.duration_min, sc.iterations = args.duration_min, None
    if args.sample_s is not None:
        sc.sampling["interval_s"] = args.sample_s
    if args.dry_run:  # escala de tempo curta para validar o fluxo em ~2 min
        if args.duration_min is None:
            sc.duration_min, sc.iterations = 2, None
        if args.sample_s is None:
            sc.sampling["interval_s"] = 10
        sc.sampling["heartbeat_s"] = min(sc.sampling.get("heartbeat_s", 10), 3)
        sc.sampling["screenshot_every_min"] = 0.5
        if sc.calibration_check:
            sc.calibration_check["every_min"] = 0.5
    return sc


def cmd_run(args) -> int:
    from taprobot import BambuLink, Calibration, RobotTap, load_config, normalize_config
    from .runner import Runner

    sc = apply_overrides(load_scenario(args.scenario), args)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) / f"{stamp}-{_slug(sc.name)}{'-dryrun' if args.dry_run else ''}"
    probe, link = None, None

    if args.dry_run:
        from .fake import FakeAdb, FakeTouchProbe
        cfg = normalize_config({"motion": {"z_floor": 14.0}}, require_printer=False)
        robot = RobotTap(cfg, CountingLink(), Calibration.simulated(cfg), sleep=lambda s: None)
        adb = FakeAdb(sc.package, charging=sc.mode == "soak", leak_mb_per_h=6.0, drain_pct_per_h=40.0)
        if args.simulate_crash:
            adb.at(45, lambda a: a.crash())
        probe = FakeTouchProbe() if sc.calibration_check else None
        serial = "falso"
        wear_path = Path(args.out) / "wear-dryrun.json"
        print(f"[dry-run] sem P1S e sem celular: dados simulados, {sc.duration_min} min.")
    else:
        cfg = load_config(args.config)
        cal_path = Path(cfg["_dir"]) / cfg["calibration_file"]
        if not cal_path.exists():
            print(f"ERRO: {cal_path.name} não existe. Calibre antes: python calibrate.py run")
            return 2
        serial = args.serial or cfg["adb"].get("serial") or pick_serial(cfg["adb"]["path"])
        adb = AdbClient(serial, cfg["adb"]["path"])
        print(CHECKLIST)
        if not args.yes and input("Digite 'sim' para começar: ").strip().lower() != "sim":
            print("cancelado")
            return 1
        p = cfg["printer"]
        link = BambuLink(p["ip"], p["serial"], p["access_code"])
        link.connect()
        robot = RobotTap(cfg, AckLink(link), Calibration.load(cal_path))
        if sc.calibration_check:
            probe = TouchProbe(serial, cfg["adb"]["path"])
        else:
            print("Aviso: sem calibration_check no cenário, a calibração não será verificada durante o teste.")
        wear_path = Path(args.out) / "wear.json"

    wear = WearCounter(wear_path, sc.limits["wear_warn_touches"])
    print(f"Execução em {run_dir}  (Ctrl+C para parar com segurança)")
    runner = Runner(sc, robot, adb, run_dir, wear=wear, probe=probe,
                    meta_extra={"dry_run": bool(args.dry_run), "serial": serial})
    try:
        meta = runner.run()
    finally:
        if isinstance(probe, TouchProbe):
            probe.stop()
        if link is not None:
            link.close()
    report = build_report(run_dir)
    from .report import analyze, load_run
    s = analyze(*load_run(run_dir))
    print(f"\nStatus: {meta['status']} ({meta.get('reason')})")
    print(f"Veredito: {s['verdict']}")
    for r in s["reasons"]:
        print(f"  - [{'falha' if r['level'] == 'fail' else 'atenção'}] {r['text']}")
    print(f"Relatório: {report}")
    return 0 if meta["status"] == "completed" else 3


def cmd_report(args) -> int:
    run_dir = Path(args.run_dir)
    if not (run_dir / "samples.csv").exists():
        print(f"ERRO: {run_dir} não parece uma pasta de execução (sem samples.csv)")
        return 2
    print(build_report(run_dir))
    return 0


def cmd_ui(args) -> int:
    """Itens visíveis com texto e o centro em px: ajuda a montar o cenário."""
    adb = AdbClient(args.serial or pick_serial())
    adb.shell("uiautomator dump /sdcard/soak_ui.xml")
    xml = adb.exec_out("cat /sdcard/soak_ui.xml").decode(errors="replace")
    found = 0
    for node in re.findall(r"<node [^>]*>", xml):
        attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', node))
        label = attrs.get("text") or attrs.get("content-desc")
        b = re.findall(r"\d+", attrs.get("bounds", ""))
        if not label or len(b) != 4:
            continue
        x1, y1, x2, y2 = map(int, b)
        click = " (clicável)" if attrs.get("clickable") == "true" else ""
        print(f"[{(x1 + x2) // 2:4d}, {(y1 + y2) // 2:4d}]  {label[:60]}{click}")
        found += 1
    if not found:
        print("nenhum item com texto na tela (tela apagada ou bloqueada?)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m soak", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="executa um cenário")
    r.add_argument("scenario")
    r.add_argument("--config", default=str(ROOT / "config.yaml"))
    r.add_argument("--serial", help="serial USB ou IP:porta do celular")
    r.add_argument("--out", default=str(ROOT / "runs"))
    r.add_argument("--duration-min", type=float)
    r.add_argument("--sample-s", type=float, help="intervalo da amostra completa (s)")
    r.add_argument("--dry-run", action="store_true", help="sem P1S e sem celular (adb e robô falsos)")
    r.add_argument("--simulate-crash", action="store_true", help="no dry-run, simula um crash aos 45 s")
    r.add_argument("--yes", action="store_true", help="não pede confirmação antes de mover a impressora")
    rp = sub.add_parser("report", help="(re)gera o relatório de uma execução")
    rp.add_argument("run_dir")
    u = sub.add_parser("ui", help="lista itens da tela com coordenadas")
    u.add_argument("--serial")
    args = ap.parse_args(argv)
    try:
        return {"run": cmd_run, "report": cmd_report, "ui": cmd_ui}[args.cmd](args)
    except (ScenarioError, AdbError) as exc:
        print(f"ERRO: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
