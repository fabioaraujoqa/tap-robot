#!/usr/bin/env python3
"""Testa a conexão MQTT com a P1S e mede a latência de comando.

Não move nada, a menos que você passe --home (e confirme que a mesa está vazia).
"""
import argparse
import statistics
import sys
import time

from taprobot import BambuLink, load_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--latency", action="store_true", help="mede o tempo de ack de 10 comandos inofensivos")
    ap.add_argument("--home", action="store_true", help="executa G28 (mesa e cabeçote se movem)")
    ap.add_argument("--bed-empty", action="store_true", help="confirma que NÃO há gabarito/celular na mesa")
    args = ap.parse_args()

    cfg = load_config(args.config)
    p = cfg["printer"]
    link = BambuLink(p["ip"], p["serial"], p["access_code"])
    link.connect()
    print("Conectado ao broker MQTT da P1S.")

    res = link.send_gcode("G90")
    print("Resposta ao G90:", res if res else "(sem ack: veja o aviso acima; o formato pode ter mudado no firmware)")

    if args.latency:
        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            link.send_gcode("G4 P0")
            times.append((time.perf_counter() - t0) * 1000)
        print(f"Latência do ack: mediana {statistics.median(times):.0f} ms, máx {max(times):.0f} ms")

    if args.home:
        if not args.bed_empty:
            sys.exit("Recuso o G28: confirme com --bed-empty que a mesa está vazia.")
        print("Executando G28... (aguarde)")
        link.send_gcode("G28")
        time.sleep(cfg["motion"]["home_wait_s"])
        print("Homing enviado. Agora monte o gabarito e o celular e rode `python calibrate.py run`.")

    link.close()


if __name__ == "__main__":
    main()
