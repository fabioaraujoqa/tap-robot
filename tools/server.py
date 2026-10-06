#!/usr/bin/env python3
"""Servidor HTTP local que expõe o robô para testes em qualquer linguagem (ex.: WebdriverIO).

  python -m tools.server                 # sobe em http://127.0.0.1:8765
  python -m tools.server --dry-run       # não envia nada à impressora (só imprime o G-code)

No --dry-run, sem config.yaml ou sem calibration.json, usa valores simulados (o /health
responde "simulated": true). Serve para testar a integração dos testes sem hardware.

Rotas (JSON):
  GET  /health
  POST /tap         {"x": 360, "y": 800, "dwell_ms": 60}
  POST /long_press  {"x": 360, "y": 800, "seconds": 1.0}
  POST /swipe       {"x1": 360, "y1": 1200, "x2": 360, "y2": 500, "duration_s": 0.35}
  POST /park

As coordenadas são em PIXELS da tela do celular (as mesmas do element.rect do Appium).
Cada chamada só responde quando o movimento estimado terminou, então o `await` do teste
já espera o toque acontecer. Há um único robô, então as chamadas são serializadas.

Sem autenticação: por isso o padrão é escutar só em 127.0.0.1. Não exponha na rede.
"""
from __future__ import annotations

import argparse
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from taprobot import (
    BambuLink, Calibration, ConfigError, RobotTap, load_config, simulated_config, simulated_robot,
)

log = logging.getLogger("taprobot.server")


def _num(body: dict, key: str, default=None) -> float:
    if key not in body:
        if default is None:
            raise KeyError(f"campo obrigatório ausente: {key}")
        return default
    value = body[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"campo {key} deve ser número")
    return float(value)


def make_server(
    robot: RobotTap, host: str = "127.0.0.1", port: int = 8765, simulated: bool = False
) -> ThreadingHTTPServer:
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # silencia o log padrão
            log.info("%s %s", self.address_string(), fmt % args)

        def _send(self, status: int, payload: dict):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 10_000:
                raise ValueError("corpo grande demais")
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict):
                raise TypeError("o corpo deve ser um objeto JSON")
            return body

        def do_GET(self):
            if self.path != "/health":
                return self._send(404, {"ok": False, "error": "rota inexistente"})
            cal = robot.cal
            self._send(
                200,
                {
                    "ok": True,
                    "calibrated": cal is not None,
                    "simulated": simulated,
                    "screen": {"width": cal.screen_w, "height": cal.screen_h} if cal else None,
                    "fit_error_mm": cal.fit_error_mm if cal else None,
                    "z_contact": cal.z_contact if cal else None,
                },
            )

        def do_POST(self):
            routes = {
                "/tap": lambda b: robot.tap_px(
                    _num(b, "x"), _num(b, "y"), dwell_ms=b.get("dwell_ms")
                ),
                "/long_press": lambda b: robot.long_press_px(
                    _num(b, "x"), _num(b, "y"), seconds=_num(b, "seconds", 1.0)
                ),
                "/swipe": lambda b: robot.swipe_px(
                    _num(b, "x1"), _num(b, "y1"), _num(b, "x2"), _num(b, "y2"),
                    duration_s=_num(b, "duration_s", 0.35),
                ),
                "/park": lambda b: robot.park(),
            }
            action = routes.get(self.path)
            if action is None:
                return self._send(404, {"ok": False, "error": "rota inexistente"})
            try:
                body = self._body()
                with lock:
                    action(body)
                self._send(200, {"ok": True})
            except (ValueError, KeyError, TypeError, ConfigError) as exc:
                self._send(400, {"ok": False, "error": str(exc).strip("'\"")})
            except Exception as exc:  # noqa: BLE001  (ex.: falha de rede com a P1S)
                log.exception("erro no robô")
                self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--dry-run", action="store_true", help="não conecta na P1S; imprime o G-code")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    simulated = False
    try:
        cfg = load_config(args.config, require_printer=not args.dry_run)
    except ConfigError as exc:
        if not args.dry_run:
            raise
        # dry-run antes de terminar a montagem (sem config.yaml ou com z_floor vazio)
        print(f"[dry-run] usando configuração simulada. Motivo: {exc}", flush=True)
        cfg = simulated_config()
        cfg["_dir"] = str(Path.cwd())
        simulated = True

    cal_path = Path(cfg["_dir"]) / cfg["calibration_file"]
    if args.dry_run and not cal_path.exists():
        print(f"[dry-run] {cal_path.name} não encontrado: usando calibração simulada")
        cal = Calibration.simulated(cfg)
        simulated = True
    else:
        cal = Calibration.load(cal_path)

    if args.dry_run:
        robot = simulated_robot(cfg=cfg, calibration=cal)
    else:
        p = cfg["printer"]
        link = BambuLink(p["ip"], p["serial"], p["access_code"])
        link.connect()
        robot = RobotTap(cfg, link, cal)

    server = make_server(robot, args.host, args.port, simulated=simulated)
    print(f"Robô disponível em http://{args.host}:{args.port}  (Ctrl+C para parar)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            robot.park()
        except Exception as exc:  # noqa: BLE001
            print("Aviso: não consegui estacionar a ponteira:", exc)
        robot.link.close()


if __name__ == "__main__":
    main()
