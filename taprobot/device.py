"""Acha o celular pelo serial, no cabo USB ou na Depuração por Wi-Fi.

Devolve o UDID que o Appium deve usar: o serial no USB, ou IP:porta no Wi-Fi. Pelo
Wi-Fi a porta muda a cada vez que a depuração é religada; ela é descoberta via mDNS
(`adb mdns services`) e conectada com `adb connect`. O celular precisa ter sido pareado
uma vez com este computador (`adb pair`).

  python -m taprobot.device              # conecta o Moto G06 e mostra o UDID
  python -m taprobot.device <serial>
"""
from __future__ import annotations

import subprocess
import sys
import time

DEFAULT_SERIAL = "ZF525PMHVF"  # Moto G06


class DeviceNotFound(RuntimeError):
    pass


def _adb(*args, adb="adb", timeout=15) -> str:
    res = subprocess.run([adb, *args], capture_output=True, text=True, timeout=timeout)
    return res.stdout


def list_devices(adb="adb") -> list[tuple[str, str]]:
    """Pares (udid, estado) do `adb devices`."""
    out = []
    for line in _adb("devices", adb=adb).splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
    return out


def parse_mdns(text: str, serial: str):
    """IP:porta anunciado pelo celular, ex.:
    "adb-ZF525PMHVF-iQtco6  _adb-tls-connect._tcp  192.168.15.20:41983"."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "_adb-tls-connect._tcp" and parts[0].startswith(f"adb-{serial}-"):
            return parts[2]
    return None


def resolve_udid(serial: str = DEFAULT_SERIAL, adb: str = "adb", attempts: int = 5) -> str:
    devices = list_devices(adb)
    if (serial, "device") in devices:
        return serial  # cabo USB

    # Já conectado pelo Wi-Fi (o mDNS nem sempre responde, mas a conexão segue viva).
    for udid, state in devices:
        if ":" in udid and state == "device":
            if _adb("-s", udid, "shell", "getprop", "ro.serialno", adb=adb).strip() == serial:
                return udid

    address = None
    for i in range(attempts):  # o mDNS às vezes demora alguns segundos para enxergar o celular
        if i:
            time.sleep(2)
        address = parse_mdns(_adb("mdns", "services", adb=adb), serial)
        if address:
            break
    if not address:
        raise DeviceNotFound(
            f"celular {serial} não encontrado no USB nem no Wi-Fi. "
            "Ligue a Depuração por Wi-Fi e confira se o computador está na mesma rede."
        )

    # Conexões antigas (porta ou rede anterior) ficam "offline": limpa para não confundir.
    for udid, state in devices:
        if udid != address and state == "offline" and ":" in udid:
            _adb("disconnect", udid, adb=adb)
    out = _adb("connect", address, adb=adb)
    if "connected to" not in out:
        raise DeviceNotFound(f"adb connect {address} falhou: {out.strip()}")
    return address


if __name__ == "__main__":
    try:
        print(resolve_udid(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERIAL))
    except DeviceNotFound as exc:
        sys.exit(str(exc))
