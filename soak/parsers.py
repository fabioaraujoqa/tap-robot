"""Leitura das saídas do dumpsys, /proc e logcat.

O formato muda entre versões do Android e fabricantes, então todo parser é tolerante:
o que não encontrar vira None em vez de erro. Os testes usam saídas reais do Moto G06
(Android 15) em tests/fixtures/.
"""
from __future__ import annotations

import re
from typing import Optional


def _int(s) -> Optional[int]:
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return None


def _float(s) -> Optional[float]:
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- memória
def parse_meminfo(text: str) -> dict:
    """`dumpsys meminfo <pacote>` -> PSS total, heap Java e nativa, em MB."""
    out = {"pss_mb": None, "java_heap_mb": None, "native_heap_mb": None}

    m = re.search(r"TOTAL PSS:\s+(\d+)", text)
    if m is None:  # versões antigas: linha "TOTAL" da tabela, 1ª coluna = PSS
        m = re.search(r"^\s*TOTAL\s+(\d+)", text, re.M)
    if m:
        out["pss_mb"] = int(m.group(1)) / 1024

    # "App Summary" (Android 6+): a 1ª coluna é PSS em KB.
    summary = text.split("App Summary", 1)[1] if "App Summary" in text else ""
    for key, label in (("java_heap_mb", "Java Heap"), ("native_heap_mb", "Native Heap")):
        m = re.search(rf"{label}:\s+(\d+)", summary)
        if m is None:  # sem App Summary: linha da tabela ("Dalvik Heap" / "Native Heap")
            row = "Dalvik Heap" if label == "Java Heap" else label
            m = re.search(rf"^\s*{row}\s+(\d+)", text, re.M)
        if m:
            out[key] = int(m.group(1)) / 1024
    return out


# ---------------------------------------------------------------- fluidez
def parse_gfxinfo(text: str) -> dict:
    """`dumpsys gfxinfo <pacote> reset` -> quadros desde o último reset."""
    frames = re.search(r"Total frames rendered:\s*(\d+)", text)
    janky = re.search(r"Janky frames:\s*(\d+)", text)
    p90 = re.search(r"^90th percentile:\s*(\d+)ms", text, re.M)
    f = int(frames.group(1)) if frames else None
    j = int(janky.group(1)) if janky else None
    return {
        "frames": f,
        "janky_frames": j,
        "janky_pct": (100.0 * j / f) if f and j is not None else None,
        "frame_p90_ms": int(p90.group(1)) if p90 else None,
    }


# ---------------------------------------------------------------- CPU
def parse_proc_pid_stat(text: str) -> Optional[int]:
    """/proc/<pid>/stat -> utime + stime em ticks. O nome do processo pode ter espaços."""
    if ")" not in text:
        return None
    fields = text.rsplit(")", 1)[1].split()
    # depois do ")": estado é o campo 3 do stat; utime e stime são os campos 14 e 15
    if len(fields) < 13:
        return None
    u, s = _int(fields[11]), _int(fields[12])
    return u + s if u is not None and s is not None else None


def parse_proc_stat_total(text: str) -> Optional[int]:
    """1ª linha de /proc/stat ("cpu  ...") -> soma de todos os ticks do aparelho."""
    for line in text.splitlines():
        if line.startswith("cpu "):
            vals = [_int(v) for v in line.split()[1:]]
            return sum(v for v in vals if v is not None)
    return None


def cpu_percent(prev: Optional[tuple], cur: Optional[tuple]) -> Optional[float]:
    """% da CPU TOTAL do aparelho usada pelo app entre duas leituras (proc, total)."""
    if not prev or not cur or None in prev or None in cur:
        return None
    dp, dt = cur[0] - prev[0], cur[1] - prev[1]
    if dt <= 0 or dp < 0:
        return None
    return 100.0 * dp / dt


# ---------------------------------------------------------------- bateria
def parse_battery(text: str) -> dict:
    """`dumpsys battery`. Temperatura vem em décimos de °C; contador de carga em µAh."""
    def field(name):
        m = re.search(rf"^\s*{name}:\s*(.+?)\s*$", text, re.M)
        return m.group(1) if m else None

    powered = [field(f"{k} powered") for k in ("AC", "USB", "Wireless", "Dock")]
    status = _int(field("status"))
    temp = _int(field("temperature"))
    counter = _int(field("Charge counter"))
    level, scale = _int(field("level")), _int(field("scale")) or 100
    return {
        "battery_pct": (100.0 * level / scale) if level is not None else None,
        "battery_temp_c": temp / 10 if temp is not None else None,
        # status 2 = carregando, 5 = cheia (ainda na tomada)
        "charging": any(p == "true" for p in powered) or status in (2, 5),
        "charge_mah": counter / 1000 if counter and counter > 0 else None,
        "voltage_mv": _int(field("voltage")),
    }


# ---------------------------------------------------------------- temperatura
_TEMP = re.compile(r"Temperature\{mValue=([-\d.]+),\s*mType=(\d+),\s*mName=([^,}]+)")


def parse_thermal(text: str) -> dict:
    """`dumpsys thermalservice` -> status (0 = normal ... 6 = desligando) e temperaturas.

    Prefere "Current temperatures from HAL" (leitura atual) ao cache. Aparelhos sem
    HAL de temperatura devolvem só Nones.
    """
    out = {"thermal_status": None, "temp_cpu_c": None, "temp_skin_c": None}
    m = re.search(r"Thermal Status:\s*(\d+)", text)
    if m:
        out["thermal_status"] = int(m.group(1))
    section = text
    if "Current temperatures from HAL" in text:
        section = text.split("Current temperatures from HAL", 1)[1]
        section = section.split("Current cooling devices", 1)[0]
    temps = {}
    for value, _type, name in _TEMP.findall(section):
        temps.setdefault(name.strip().upper(), _float(value))
    out["temp_cpu_c"] = temps.get("CPU") or temps.get("SOC")
    out["temp_skin_c"] = temps.get("SKIN")
    return out


# ---------------------------------------------------------------- estado do aparelho
def parse_pidof(text: str) -> Optional[int]:
    pids = [_int(p) for p in text.split()]
    pids = [p for p in pids if p]
    return pids[0] if pids else None


def parse_screen_on(text: str) -> Optional[bool]:
    """`dumpsys power`: Awake = tela ligada; Asleep/Dozing = apagada."""
    m = re.search(r"mWakefulness=(\w+)", text)
    if m:
        return m.group(1) == "Awake"
    m = re.search(r"Display Power: state=(\w+)", text)
    if m:
        return m.group(1) == "ON"
    return None


def parse_keyguard(text: str) -> Optional[bool]:
    """`dumpsys window`: True se a tela de bloqueio está aparecendo."""
    m = re.search(r"isKeyguardShowing=(\w+)", text) or re.search(r"mShowingLockscreen=(\w+)", text)
    return m.group(1) == "true" if m else None


def parse_resumed_package(text: str) -> Optional[str]:
    """Pacote da activity em primeiro plano (dumpsys activity activities)."""
    m = re.search(r"(?:topResumedActivity|ResumedActivity)[=:]\s*ActivityRecord\{\S+ \S+ ([\w.]+)/", text)
    return m.group(1) if m else None


# ---------------------------------------------------------------- logcat
_LOGCAT = re.compile(
    r"^(?P<date>\d\d-\d\d) (?P<time>[\d:.]+)\s+(?P<pid>\d+)\s+(?P<tid>\d+)\s+(?P<lvl>\w)\s+(?P<tag>[^:]*?)\s*: (?P<msg>.*)$"
)


class LogcatParser:
    """Transforma linhas do logcat em eventos do pacote alvo: crash, ANR, crash nativo, morte."""

    def __init__(self, package: str):
        self.package = package
        self._crash_pending: Optional[dict] = None
        self._last_native_pid: Optional[str] = None

    def feed(self, line: str) -> list:
        m = _LOGCAT.match(line.rstrip("\r\n"))
        if not m:
            return []
        tag, msg = m["tag"].strip(), m["msg"]
        stamp = f"{m['date']} {m['time']}"
        events = []

        # Crash Java: "FATAL EXCEPTION" -> "Process: pkg, PID: n" -> linha com a exceção
        if tag == "AndroidRuntime":
            if self._crash_pending is not None and not msg.startswith("Process:"):
                self._crash_pending["detail"] = msg.strip()
                events.append(self._crash_pending)
                self._crash_pending = None
            pm = re.match(r"Process: ([\w.:]+), PID: (\d+)", msg)
            if pm and pm.group(1).split(":")[0] == self.package:
                self._crash_pending = {"type": "crash", "log_time": stamp, "pid": int(pm.group(2)), "detail": ""}
        elif self._crash_pending is not None:
            events.append(self._crash_pending)
            self._crash_pending = None

        am = re.match(r"ANR in ([\w.:]+)", msg)
        if am and am.group(1).split(":")[0] == self.package:
            events.append({"type": "anr", "log_time": stamp, "detail": msg.strip()})

        # Crash nativo: o DEBUG (tombstone) identifica o pacote com ">>> pkg <<<"
        nm = re.search(r"pid: (\d+).*>>> ([\w.:]+) <<<", msg)
        if nm and nm.group(2).split(":")[0] == self.package and nm.group(1) != self._last_native_pid:
            self._last_native_pid = nm.group(1)
            events.append({"type": "native_crash", "log_time": stamp, "pid": int(nm.group(1)), "detail": msg.strip()})

        dm = re.match(r"Process ([\w.:]+) \(pid (\d+)\) has died", msg)
        if dm and dm.group(1) == self.package:
            events.append({"type": "process_died", "log_time": stamp, "pid": int(dm.group(2)), "detail": msg.strip()})
        return events
