"""Acesso ao celular via adb (USB ou Wi-Fi), com tempo-limite em todo comando."""
from __future__ import annotations

import subprocess
from typing import Iterator, Optional


class AdbError(RuntimeError):
    """O adb falhou ou o aparelho não respondeu (desconectado, Wi-Fi caiu...)."""


class AdbClient:
    def __init__(self, serial: Optional[str] = None, path: str = "adb"):
        self.serial = serial
        self.base = [path] + (["-s", serial] if serial else [])
        self._logcat: Optional[subprocess.Popen] = None

    def _run(self, args, timeout, text=True):
        try:
            res = subprocess.run(self.base + args, capture_output=True, text=text, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb {' '.join(args[:3])}: sem resposta em {timeout}s") from exc
        except OSError as exc:
            raise AdbError(f"não consegui rodar o adb: {exc}") from exc
        if res.returncode != 0:
            err = res.stderr if text else res.stderr.decode(errors="replace")
            raise AdbError(f"adb {' '.join(args[:3])}: {err.strip() or 'falhou'}")
        return res.stdout

    def shell(self, cmd: str, timeout: float = 20) -> str:
        """Roda um comando no celular. Saída vazia não é erro (ex.: pidof sem processo)."""
        return self._run(["shell", cmd], timeout)

    def exec_out(self, cmd: str, timeout: float = 30) -> bytes:
        return self._run(["exec-out", cmd], timeout, text=False)

    def logcat_follow(self) -> Iterator[str]:
        """Linhas novas do logcat (main, system e crash) a partir de agora."""
        self._logcat = subprocess.Popen(
            self.base + ["logcat", "-v", "threadtime", "-b", "main,system,crash", "-T", "1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            bufsize=1,
        )
        yield from self._logcat.stdout

    def stop_logcat(self):
        if self._logcat is not None:
            self._logcat.terminate()
            self._logcat = None
