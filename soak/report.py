"""Relatório da execução: análise (tendências, veredito) + HTML autocontido + summary.csv.

O HTML não depende de nada externo: dados, estilos, gráficos (SVG desenhado por JS
embutido) e algumas capturas de tela (base64) ficam no próprio arquivo.
"""
from __future__ import annotations

import base64
import csv
import html
import json
from pathlib import Path
from typing import Optional

import numpy as np

from .scenario import DEFAULTS

FAIL_EVENTS = ("crash", "native_crash", "anr")
APP_ABORTS = ("app", "temperature")  # abortos causados pelo app/aparelho, não pelo ambiente


# ---------------------------------------------------------------- leitura
def _num(v):
    if v in ("", None):
        return None
    if v in ("True", "False"):
        return v == "True"
    try:
        return float(v)
    except ValueError:
        return v


def load_run(run_dir: Path):
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8")) if (run_dir / "meta.json").exists() else {}
    rows = []
    if (run_dir / "samples.csv").exists():
        with (run_dir / "samples.csv").open(encoding="utf-8") as f:
            rows = [{k: _num(v) for k, v in r.items()} for r in csv.DictReader(f)]
    events = []
    if (run_dir / "events.jsonl").exists():
        events = [json.loads(ln) for ln in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    return meta, rows, events


# ---------------------------------------------------------------- análise
def slope_per_hour(ts, ys, min_span_s: float = 300, min_points: int = 3) -> Optional[float]:
    """Inclinação por hora (regressão linear). None se houver pouco dado."""
    pts = [(t, y) for t, y in zip(ts, ys) if t is not None and isinstance(y, (int, float))]
    if len(pts) < min_points or pts[-1][0] - pts[0][0] < min_span_s:
        return None
    t = np.array([p[0] for p in pts]) / 3600
    y = np.array([p[1] for p in pts])
    return float(np.polyfit(t, y, 1)[0])


def _longest_pid_segment(rows):
    """Memória só é comparável dentro do mesmo processo: um reinício zera tudo."""
    segs, cur = [], []
    for r in rows:
        if r.get("pss_mb") is None:
            continue
        if cur and r.get("pid") != cur[-1].get("pid"):
            segs.append(cur)
            cur = []
        cur.append(r)
    if cur:
        segs.append(cur)
    return max(segs, key=lambda s: s[-1]["t_s"] - s[0]["t_s"]) if segs else []


def _vals(rows, key):
    return [r[key] for r in rows if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)]


def analyze(meta: dict, rows: list, events: list) -> dict:
    v = {**DEFAULTS["verdict"], **(meta.get("scenario", {}).get("verdict") or {})}
    counts = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1

    seg = _longest_pid_segment(rows)
    mem_slope = slope_per_hour([r["t_s"] for r in seg], [r["pss_mb"] for r in seg])
    java_slope = slope_per_hour([r["t_s"] for r in seg], [r.get("java_heap_mb") for r in seg])
    native_slope = slope_per_hour([r["t_s"] for r in seg], [r.get("native_heap_mb") for r in seg])

    frames = sum(_vals(rows, "frames"))
    janky = sum(_vals(rows, "janky_frames"))
    third = max(len(rows) // 3, 1)

    def jank_of(part):
        f = sum(_vals(part, "frames"))
        return 100 * sum(_vals(part, "janky_frames")) / f if f else None

    dis = [r for r in rows if r.get("charging") is False]
    drain = slope_per_hour([r["t_s"] for r in dis], [r.get("battery_pct") for r in dis], min_span_s=600)
    drain_mah = slope_per_hour([r["t_s"] for r in dis], [r.get("charge_mah") for r in dis], min_span_s=600)
    cpu = _vals(rows, "cpu_pct")
    bt, ct, st = _vals(rows, "battery_temp_c"), _vals(rows, "temp_cpu_c"), _vals(rows, "temp_skin_c")

    s = {
        "samples": len(rows),
        "duration_s": meta.get("duration_s") or (rows[-1]["t_s"] if rows else 0),
        "touches": meta.get("touches"),
        "mem_start_mb": seg[0]["pss_mb"] if seg else None,
        "mem_end_mb": seg[-1]["pss_mb"] if seg else None,
        "mem_slope_mb_h": mem_slope,
        "java_slope_mb_h": java_slope,
        "native_slope_mb_h": native_slope,
        "janky_pct": 100 * janky / frames if frames else None,
        "janky_first_third_pct": jank_of(rows[:third]),
        "janky_last_third_pct": jank_of(rows[-third:]),
        "cpu_avg_pct": float(np.mean(cpu)) if cpu else None,
        "cpu_max_pct": max(cpu) if cpu else None,
        "battery_temp_max_c": max(bt) if bt else None,
        "cpu_temp_max_c": max(ct) if ct else None,
        "skin_temp_max_c": max(st) if st else None,
        "thermal_status_max": max(_vals(rows, "thermal_status"), default=None),
        "power_mode": "bateria" if dis and len(dis) >= len(rows) / 2 else "carregador",
        "drain_pct_h": -drain if drain is not None else None,
        "drain_mah_h": -drain_mah if drain_mah is not None else None,
        "crashes": counts.get("crash", 0) + counts.get("native_crash", 0),
        "anrs": counts.get("anr", 0),
        "app_restarts": counts.get("app_restart", 0),
        "events": counts,
    }

    reasons = []  # (nível, texto)

    def add(level, text):
        reasons.append({"level": level, "text": text})

    if s["crashes"]:
        add("fail", f"{s['crashes']} crash(es) do app")
    if s["anrs"]:
        add("fail", f"{s['anrs']} ANR(s): o app parou de responder")
    status, kind = meta.get("status"), meta.get("abort_kind")
    if status == "aborted":
        if kind in APP_ABORTS:
            add("fail", f"teste abortado: {meta.get('reason')}")
        else:
            add("warn", f"teste interrompido por problema do ambiente, não do app: {meta.get('reason')}")
    elif status == "interrupted":
        add("warn", f"teste interrompido antes do fim ({meta.get('reason')})")
    if mem_slope is None:
        add("warn", "pouco dado para medir tendência de memória (precisa de 5+ min e 3+ amostras)")
    elif mem_slope > v["mem_slope_fail_mb_h"]:
        add("fail", f"memória crescendo {mem_slope:.1f} MB/h (limite {v['mem_slope_fail_mb_h']})")
    elif mem_slope > v["mem_slope_warn_mb_h"]:
        add("warn", f"memória crescendo {mem_slope:.1f} MB/h (atenção acima de {v['mem_slope_warn_mb_h']})")
    if s["janky_pct"] is not None:
        if s["janky_pct"] > v["janky_fail_pct"]:
            add("fail", f"{s['janky_pct']:.1f}% de quadros travados (limite {v['janky_fail_pct']}%)")
        elif s["janky_pct"] > v["janky_warn_pct"]:
            add("warn", f"{s['janky_pct']:.1f}% de quadros travados (atenção acima de {v['janky_warn_pct']}%)")
    temp_max = max([t for t in (s["battery_temp_max_c"], s["skin_temp_max_c"]) if t is not None], default=None)
    if temp_max is not None and temp_max > v["temp_warn_c"]:
        add("warn", f"temperatura chegou a {temp_max:.1f} °C (atenção acima de {v['temp_warn_c']} °C)")
    if s["cpu_avg_pct"] is not None and s["cpu_avg_pct"] > v["cpu_warn_pct"]:
        add("warn", f"CPU média do app {s['cpu_avg_pct']:.1f}% (atenção acima de {v['cpu_warn_pct']}%)")
    if meta.get("mode") == "consumo":
        if s["drain_pct_h"] is None:
            add("warn", "pouco tempo na bateria para medir o consumo (precisa de 10+ min descarregando)")
        elif s["drain_pct_h"] > v["drain_warn_pct_h"]:
            add("warn", f"consumo de {s['drain_pct_h']:.1f}%/h (atenção acima de {v['drain_warn_pct_h']}%/h)")
    if s["app_restarts"] and not s["crashes"] and not s["anrs"]:
        add("warn", f"o app precisou ser reaberto {s['app_restarts']} vez(es)")
    if counts.get("wear_warning"):
        add("warn", "a ponteira passou do limite de toques acumulados: confira a borracha")

    s["verdict"] = "FALHA" if any(r["level"] == "fail" for r in reasons) else "ATENÇÃO" if reasons else "OK"
    s["reasons"] = reasons
    return s


# ---------------------------------------------------------------- saída
def write_summary_csv(path: Path, s: dict, meta: dict):
    keys = ["verdict", "duration_s", "touches", "samples", "mem_start_mb", "mem_end_mb", "mem_slope_mb_h",
            "java_slope_mb_h", "native_slope_mb_h", "janky_pct", "janky_first_third_pct", "janky_last_third_pct",
            "cpu_avg_pct", "cpu_max_pct", "battery_temp_max_c", "cpu_temp_max_c", "skin_temp_max_c",
            "thermal_status_max", "power_mode", "drain_pct_h", "drain_mah_h", "crashes", "anrs", "app_restarts"]
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metrica", "valor"])
        w.writerow(["cenario", meta.get("name", "")])
        w.writerow(["modo", meta.get("mode", "")])
        w.writerow(["status", meta.get("status", "")])
        for k in keys:
            val = s.get(k)
            w.writerow([k, round(val, 3) if isinstance(val, float) else ("" if val is None else val)])


def _screenshots(run_dir: Path, limit: int = 8):
    shots = sorted((run_dir / "screenshots").glob("*.png")) if (run_dir / "screenshots").exists() else []
    if len(shots) > limit:  # espalhadas no tempo, sempre com a primeira e a última
        idx = sorted({round(i * (len(shots) - 1) / (limit - 1)) for i in range(limit)})
        shots = [shots[i] for i in idx]
    out = []
    for p in shots:
        data = p.read_bytes()
        if len(data) > 3_000_000:
            continue
        out.append({"name": p.name, "t_s": int(p.name[:6]) if p.name[:6].isdigit() else None,
                    "src": "data:image/png;base64," + base64.b64encode(data).decode()})
    return out, len(list((run_dir / "screenshots").glob("*.png"))) if (run_dir / "screenshots").exists() else 0


def build_report(run_dir) -> Path:
    run_dir = Path(run_dir)
    meta, rows, events = load_run(run_dir)
    s = analyze(meta, rows, events)
    write_summary_csv(run_dir / "summary.csv", s, meta)
    shots, total_shots = _screenshots(run_dir)
    payload = {"meta": meta, "summary": s, "rows": rows, "events": events, "shots": shots, "totalShots": total_shots}
    # "<" vira \u003c: nenhum texto do cenário/logcat consegue fechar ou abrir tags aqui
    data = json.dumps(payload, ensure_ascii=False, default=str).replace("<", "\\u003c")
    title = html.escape(f"Soak · {meta.get('name', run_dir.name)}")
    out = run_dir / "report.html"
    out.write_text(TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data), encoding="utf-8")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --ring: rgba(11,11,11,0.10);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
  --good: #0ca30c; --warning: #fab219; --serious: #ec835a; --critical: #d03b3b; --good-text: #006300;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --good-text: #0ca30c;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10);
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --good-text: #0ca30c;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 32px 0 12px; }
.sub { color: var(--ink-2); margin: 0; }
.card { background: var(--surface); border: 1px solid var(--ring); border-radius: 12px; padding: 16px; margin-top: 16px; }
.verdict { display: flex; gap: 16px; align-items: flex-start; }
.badge { display: inline-flex; align-items: center; gap: 8px; font-weight: 700; font-size: 20px; padding: 6px 14px; border-radius: 999px; border: 2px solid currentColor; white-space: nowrap; }
.badge svg { width: 20px; height: 20px; }
.lvl-ok { color: var(--good-text); } .lvl-warn { color: #a86b00; } .lvl-fail { color: var(--critical); }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .lvl-warn { color: var(--warning); } }
:root[data-theme="dark"] .lvl-warn { color: var(--warning); }
.reasons { margin: 0; padding: 0; list-style: none; }
.reasons li { display: flex; gap: 8px; align-items: baseline; padding: 2px 0; }
.reasons .tag { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .02em; min-width: 64px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.tile .label { color: var(--ink-2); font-size: 13px; }
.tile .value { font-size: 22px; font-weight: 600; }
.tile .note { color: var(--muted); font-size: 12px; }
.chart-title { font-weight: 600; margin: 0; }
.chart-sub { color: var(--ink-2); font-size: 13px; margin: 0 0 8px; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--ink-2); margin-bottom: 4px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.key { width: 16px; height: 2px; border-radius: 1px; display: inline-block; }
.chart { position: relative; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart svg text { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.chart svg .endlabel { fill: var(--ink-2); font-size: 12px; }
.tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--ring); border-radius: 8px; padding: 8px 10px; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,.12); min-width: 150px; display: none; z-index: 2; }
.tip .t { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.tip .row { display: flex; align-items: center; gap: 8px; }
.tip .row b { font-variant-numeric: tabular-nums; }
.tip .row span:last-child { color: var(--ink-2); }
.tip .ev { color: var(--ink-2); font-size: 12px; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--grid); vertical-align: top; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.scroll { overflow-x: auto; }
details summary { cursor: pointer; color: var(--ink-2); margin-top: 8px; }
.ev-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.shots { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 12px; }
.shots figure { margin: 0; }
.shots img { width: 100%; border-radius: 8px; border: 1px solid var(--ring); }
.shots figcaption { color: var(--ink-2); font-size: 12px; }
.meta-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 4px 16px; font-size: 13px; }
.meta-grid div span { color: var(--ink-2); }
</style>
</head>
<body>
<main id="app"></main>
<script type="application/json" id="data">__DATA__</script>
<script>
(() => {
  const D = JSON.parse(document.getElementById('data').textContent);
  const S = D.summary, M = D.meta, rows = D.rows, events = D.events;
  const app = document.getElementById('app');
  const NS = 'http://www.w3.org/2000/svg';

  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v);
    }
    for (const k of kids) if (k) n.append(k);
    return n;
  };
  const sv = (tag, attrs = {}) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };
  const fmt = (v, d = 1) => v === null || v === undefined || Number.isNaN(v) ? '—'
    : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  const dur = s => { s = Math.round(s || 0); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
    return h ? `${h} h ${String(m).padStart(2, '0')} min` : m ? `${m} min ${String(s % 60).padStart(2, '0')} s` : `${s} s`; };
  const tmin = s => `${fmt(s / 60, 1)} min`;

  // ---------------------------------------------------------- cabeçalho e veredito
  const modeTxt = M.mode === 'consumo' ? 'consumo (bateria)' : 'soak (carregador)';
  app.append(el('h1', { text: M.name || 'Teste de resistência' }),
    el('p', { class: 'sub', text: `${M.package || ''} · modo ${modeTxt} · ${M.started || ''} · ${dur(S.duration_s)}` }));

  const icons = {
    OK: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10.5l4 4 8-9"/></svg>',
    'ATENÇÃO': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2.5l8 14.5H2z"/><path d="M10 8v4M10 14.6v.1"/></svg>',
    FALHA: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M5 5l10 10M15 5L5 15"/></svg>',
  };
  const lvlClass = { OK: 'lvl-ok', 'ATENÇÃO': 'lvl-warn', FALHA: 'lvl-fail' };
  const badge = el('span', { class: `badge ${lvlClass[S.verdict]}` });
  badge.innerHTML = icons[S.verdict];
  badge.append(document.createTextNode(S.verdict));
  const list = el('ul', { class: 'reasons' });
  if (!S.reasons.length) list.append(el('li', { text: 'Nenhum problema encontrado dentro dos limites configurados.' }));
  for (const r of S.reasons) {
    list.append(el('li', {}, el('span', { class: `tag ${r.level === 'fail' ? 'lvl-fail' : 'lvl-warn'}`, text: r.level === 'fail' ? 'falha' : 'atenção' }),
      el('span', { text: r.text })));
  }
  const statusTxt = { completed: 'concluída', aborted: 'abortada', interrupted: 'interrompida' }[M.status] || M.status || '—';
  app.append(el('div', { class: 'card verdict' }, badge,
    el('div', {}, el('p', { class: 'sub', text: `Execução ${statusTxt}${M.reason ? ': ' + M.reason : ''}` }), list)));

  // ---------------------------------------------------------- números principais
  const tiles = el('div', { class: 'tiles' });
  const tile = (label, value, note) => tiles.append(el('div', { class: 'card tile' },
    el('div', { class: 'label', text: label }), el('div', { class: 'value', text: value }), note ? el('div', { class: 'note', text: note }) : null));
  tile('Memória (PSS)', S.mem_slope_mb_h === null ? '—' : `${S.mem_slope_mb_h > 0 ? '+' : ''}${fmt(S.mem_slope_mb_h)} MB/h`,
    S.mem_start_mb !== null ? `${fmt(S.mem_start_mb, 0)} → ${fmt(S.mem_end_mb, 0)} MB` : 'sem dados');
  tile('Quadros travados', S.janky_pct === null ? '—' : `${fmt(S.janky_pct)}%`,
    S.janky_first_third_pct !== null ? `início ${fmt(S.janky_first_third_pct)}% · fim ${fmt(S.janky_last_third_pct)}%` : '');
  tile('CPU do app', S.cpu_avg_pct === null ? '—' : `${fmt(S.cpu_avg_pct)}%`, S.cpu_max_pct !== null ? `média · pico ${fmt(S.cpu_max_pct)}%` : '');
  tile('Temperatura máx.', S.battery_temp_max_c === null ? '—' : `${fmt(S.battery_temp_max_c)} °C`,
    `bateria${S.skin_temp_max_c !== null ? ` · pele ${fmt(S.skin_temp_max_c)} °C` : ''}`);
  if (S.power_mode === 'bateria' || M.mode === 'consumo')
    tile('Consumo', S.drain_pct_h === null ? '—' : `${fmt(S.drain_pct_h)} %/h`, S.drain_mah_h !== null ? `${fmt(S.drain_mah_h, 0)} mAh/h` : 'na bateria');
  else tile('Energia', 'Carregador', 'consumo não medido');
  tile('Crashes / ANRs', `${S.crashes} / ${S.anrs}`, `${S.app_restarts} reinício(s) do app`);
  tile('Toques', fmt(M.touches ?? 0, 0), `${fmt(M.iterations ?? 0, 0)} iterações`);
  app.append(el('h2', { text: 'Resumo' }), tiles);

  // ---------------------------------------------------------- gráficos
  const MARKED = { crash: 'var(--critical)', native_crash: 'var(--critical)', anr: 'var(--critical)',
    app_restart: 'var(--serious)', abort: 'var(--critical)', stopped: 'var(--serious)', adb_offline: 'var(--serious)' };
  const evLabel = { crash: 'crash', native_crash: 'crash nativo', anr: 'ANR', app_restart: 'app reaberto', abort: 'abortado',
    stopped: 'interrompido', adb_offline: 'adb fora', adb_online: 'adb voltou', calibration_ok: 'calibração ok',
    app_start: 'app aberto', run_start: 'início', run_end: 'fim', warning: 'aviso', collector_warning: 'aviso do coletor',
    robot_error: 'erro do robô', robot_parked: 'ponteira estacionada', wear_warning: 'desgaste da ponteira', process_died: 'processo morreu' };
  const marks = events.filter(e => MARKED[e.type]);

  function niceTicks(lo, hi, n = 4) {
    if (lo === hi) { lo -= 1; hi += 1; }
    const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    const t0 = Math.floor(lo / step) * step, out = [];
    for (let v = t0; v <= hi + step * 0.5; v += step) out.push(+v.toFixed(10));
    return out;
  }

  function lineChart({ title, sub, series, unit, digits = 1, zero = false, trend = null }) {
    const pts = series.map(s => rows.map(r => [r.t_s, r[s.key]]).filter(p => typeof p[1] === 'number'));
    if (!pts.some(p => p.length)) return null;
    const W = 960, H = 260, L = 48, R = 96, T = 12, B = 30;
    const xs = rows.map(r => r.t_s), xmax = Math.max(60, ...xs);
    const allY = pts.flat().map(p => p[1]);
    let ylo = Math.min(...allY), yhi = Math.max(...allY);
    if (zero) ylo = Math.min(0, ylo);
    const pad = (yhi - ylo) * 0.08 || 1; if (!zero) ylo -= pad; yhi += pad;
    const yt = niceTicks(ylo, yhi); ylo = Math.min(ylo, yt[0]); yhi = Math.max(yhi, yt[yt.length - 1]);
    const X = t => L + (t / xmax) * (W - L - R), Y = v => T + (1 - (v - ylo) / (yhi - ylo)) * (H - T - B);

    const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': title });
    for (const v of yt) {
      svg.append(sv('line', { x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: 'var(--grid)', 'stroke-width': 1 }));
      const tx = sv('text', { x: L - 8, y: Y(v) + 4, 'text-anchor': 'end' }); tx.textContent = fmt(v, Math.abs(v) < 10 && v % 1 ? 1 : 0); svg.append(tx);
    }
    svg.append(sv('line', { x1: L, x2: W - R, y1: H - B, y2: H - B, stroke: 'var(--axis)', 'stroke-width': 1 }));
    for (const t of niceTicks(0, xmax / 60, 6).filter(m => m * 60 <= xmax)) {
      const tx = sv('text', { x: X(t * 60), y: H - B + 18, 'text-anchor': 'middle' }); tx.textContent = `${fmt(t, t % 1 ? 1 : 0)} min`; svg.append(tx);
    }
    for (const e of marks) {
      svg.append(sv('line', { x1: X(e.t_s), x2: X(e.t_s), y1: T, y2: H - B, stroke: MARKED[e.type], 'stroke-width': 1, opacity: 0.7 }));
    }
    if (trend) {
      const [a, b] = trend; // y = a + b*t_h, desenhada só no trecho medido
      svg.append(sv('line', { x1: X(a[0]), y1: Y(a[1]), x2: X(b[0]), y2: Y(b[1]), stroke: 'var(--muted)', 'stroke-width': 1.5, 'stroke-linecap': 'round', opacity: 0.9 }));
    }
    const endLabels = [];
    series.forEach((s, i) => {
      const p = pts[i]; if (!p.length) return;
      const d = p.map((q, j) => `${j ? 'L' : 'M'}${X(q[0]).toFixed(1)},${Y(q[1]).toFixed(1)}`).join('');
      svg.append(sv('path', { d, fill: 'none', stroke: `var(--s${s.slot})`, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
      const last = p[p.length - 1];
      svg.append(sv('circle', { cx: X(last[0]), cy: Y(last[1]), r: 4, fill: `var(--s${s.slot})`, stroke: 'var(--surface)', 'stroke-width': 2 }));
      endLabels.push({ y: Y(last[1]), text: `${series.length > 1 ? s.label + ' ' : ''}${fmt(last[1], digits)}${unit}` });
    });
    endLabels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < endLabels.length; i++) endLabels[i].y = Math.max(endLabels[i].y, endLabels[i - 1].y + 14);
    for (const l of endLabels) { const tx = sv('text', { x: W - R + 8, y: l.y + 4, class: 'endlabel' }); tx.textContent = l.text; svg.append(tx); }

    // camada de hover: linha vertical + tooltip com todas as séries
    const cross = sv('line', { y1: T, y2: H - B, stroke: 'var(--axis)', 'stroke-width': 1, visibility: 'hidden' });
    const dots = series.map(s => sv('circle', { r: 4, fill: `var(--s${s.slot})`, stroke: 'var(--surface)', 'stroke-width': 2, visibility: 'hidden' }));
    svg.append(cross, ...dots);
    const hit = sv('rect', { x: L, y: T, width: W - L - R, height: H - T - B, fill: 'transparent', tabindex: 0 });
    svg.append(hit);
    const wrap = el('div', { class: 'chart' }, svg);
    const tip = el('div', { class: 'tip' }); wrap.append(tip);
    let idx = rows.length - 1;
    const show = i => {
      idx = Math.max(0, Math.min(rows.length - 1, i));
      const r = rows[idx], x = X(r.t_s);
      cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.setAttribute('visibility', 'visible');
      tip.replaceChildren(el('div', { class: 't', text: tmin(r.t_s) }));
      series.forEach((s, i) => {
        const v = r[s.key];
        if (typeof v === 'number') { dots[i].setAttribute('cx', x); dots[i].setAttribute('cy', Y(v)); dots[i].setAttribute('visibility', 'visible'); }
        else dots[i].setAttribute('visibility', 'hidden');
        tip.append(el('div', { class: 'row' }, el('span', { class: 'key', style: `background: var(--s${s.slot})` }),
          el('b', { text: typeof v === 'number' ? `${fmt(v, digits)}${unit}` : '—' }), el('span', { text: s.label })));
      });
      const near = events.filter(e => Math.abs(e.t_s - r.t_s) <= 30 && MARKED[e.type]);
      for (const e of near) tip.append(el('div', { class: 'ev', text: `${evLabel[e.type] || e.type}: ${e.detail || ''}`.slice(0, 120) }));
      tip.style.display = 'block';
      const box = wrap.getBoundingClientRect(), px = x / W * box.width;
      tip.style.left = `${Math.min(Math.max(px + 12, 0), box.width - tip.offsetWidth)}px`;
      tip.style.top = '8px';
    };
    const hide = () => { tip.style.display = 'none'; cross.setAttribute('visibility', 'hidden'); dots.forEach(d => d.setAttribute('visibility', 'hidden')); };
    hit.addEventListener('pointermove', ev => {
      const b = svg.getBoundingClientRect(), t = ((ev.clientX - b.left) / b.width * W - L) / (W - L - R) * xmax;
      let best = 0; rows.forEach((r, i) => { if (Math.abs(r.t_s - t) < Math.abs(rows[best].t_s - t)) best = i; });
      show(best);
    });
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('focus', () => show(idx));
    hit.addEventListener('blur', hide);
    hit.addEventListener('keydown', ev => { if (ev.key === 'ArrowLeft') show(idx - 1); if (ev.key === 'ArrowRight') show(idx + 1); });

    const card = el('div', { class: 'card' }, el('p', { class: 'chart-title', text: title }), el('p', { class: 'chart-sub', text: sub }));
    if (series.length > 1) {
      const lg = el('div', { class: 'legend' });
      for (const s of series) lg.append(el('span', {}, el('span', { class: 'key', style: `background: var(--s${s.slot})` }), document.createTextNode(s.label)));
      card.append(lg);
    }
    card.append(wrap);
    return card;
  }

  // reta da regressão de memória sobre o trecho medido (mesmo processo)
  let memTrend = null;
  const memRows = rows.filter(r => typeof r.pss_mb === 'number');
  if (S.mem_slope_mb_h !== null && memRows.length > 2) {
    const pidRows = (() => { const segs = []; let cur = [];
      for (const r of memRows) { if (cur.length && r.pid !== cur[cur.length - 1].pid) { segs.push(cur); cur = []; } cur.push(r); }
      if (cur.length) segs.push(cur);
      return segs.sort((a, b) => (b[b.length - 1].t_s - b[0].t_s) - (a[a.length - 1].t_s - a[0].t_s))[0]; })();
    const n = pidRows.length, mt = pidRows.reduce((a, r) => a + r.t_s, 0) / n, my = pidRows.reduce((a, r) => a + r.pss_mb, 0) / n;
    const b = S.mem_slope_mb_h / 3600, at = t => my + b * (t - mt);
    memTrend = [[pidRows[0].t_s, at(pidRows[0].t_s)], [pidRows[n - 1].t_s, at(pidRows[n - 1].t_s)]];
  }

  app.append(el('h2', { text: 'Ao longo do tempo' }),
    el('p', { class: 'sub', text: 'Linhas verticais: vermelho = crash, ANR ou aborto; laranja = app reaberto ou adb fora. Passe o mouse (ou use as setas) para ver os valores.' }));
  const charts = [
    lineChart({ title: 'Memória do app', unit: ' MB', digits: 0, zero: true,
      sub: S.mem_slope_mb_h === null ? 'PSS total e heaps. Pouco dado para tendência.'
        : `PSS total e heaps. Tendência do PSS (reta cinza): ${S.mem_slope_mb_h > 0 ? '+' : ''}${fmt(S.mem_slope_mb_h)} MB/h`,
      series: [{ key: 'pss_mb', label: 'PSS total', slot: 1 }, { key: 'java_heap_mb', label: 'Heap Java', slot: 2 }, { key: 'native_heap_mb', label: 'Heap nativa', slot: 3 }],
      trend: memTrend }),
    lineChart({ title: 'Quadros travados', sub: '% dos quadros acima do tempo de vsync em cada intervalo de amostra', unit: '%', zero: true,
      series: [{ key: 'janky_pct', label: 'Quadros travados', slot: 1 }] }),
    lineChart({ title: 'CPU do app', sub: '% da CPU total do aparelho usada pelo processo', unit: '%', zero: true,
      series: [{ key: 'cpu_pct', label: 'CPU', slot: 1 }] }),
    lineChart({ title: 'Temperatura', sub: 'Bateria, CPU e pele (superfície) do aparelho', unit: ' °C',
      series: [{ key: 'battery_temp_c', label: 'Bateria', slot: 1 }, { key: 'temp_cpu_c', label: 'CPU', slot: 2 }, { key: 'temp_skin_c', label: 'Pele', slot: 3 }] }),
    lineChart({ title: 'Nível da bateria', unit: '%', digits: 0,
      sub: S.drain_pct_h !== null ? `Consumo na bateria: ${fmt(S.drain_pct_h)} %/h${S.drain_mah_h !== null ? ` (${fmt(S.drain_mah_h, 0)} mAh/h)` : ''}` : 'No carregador durante o teste',
      series: [{ key: 'battery_pct', label: 'Bateria', slot: 1 }] }),
  ].filter(Boolean);
  app.append(...charts);

  // ---------------------------------------------------------- eventos
  app.append(el('h2', { text: 'Linha do tempo de eventos' }));
  const evTable = el('table', {}, el('thead', {}, el('tr', {}, el('th', { class: 'n', text: 'Tempo' }), el('th', { text: 'Evento' }), el('th', { text: 'Detalhe' }))));
  const tb = el('tbody');
  for (const e of events.filter(e => e.type !== 'calibration_ok')) {
    const dot = el('span', { class: 'ev-dot', style: `background: ${MARKED[e.type] || 'var(--axis)'}` });
    tb.append(el('tr', {}, el('td', { class: 'n', text: tmin(e.t_s) }), el('td', {}, dot, document.createTextNode(evLabel[e.type] || e.type)),
      el('td', { text: (e.detail || '').slice(0, 300) })));
  }
  const cal = events.filter(e => e.type === 'calibration_ok');
  evTable.append(tb);
  app.append(el('div', { class: 'card scroll' }, evTable,
    cal.length ? el('p', { class: 'chart-sub', text: `Verificações de calibração: ${cal.length}, erro máximo ${fmt(Math.max(...cal.map(e => e.error_px || 0)))} px.` }) : null));

  // ---------------------------------------------------------- capturas
  if (D.shots.length) {
    const g = el('div', { class: 'shots' });
    for (const s of D.shots) g.append(el('figure', {}, el('img', { src: s.src, alt: `Captura em ${s.t_s !== null ? tmin(s.t_s) : s.name}` }),
      el('figcaption', { text: s.t_s !== null ? tmin(s.t_s) : s.name })));
    app.append(el('h2', { text: 'Capturas de tela' }), el('p', { class: 'sub', text: `${D.shots.length} de ${D.totalShots} capturas (todas na pasta screenshots/).` }), el('div', { class: 'card' }, g));
  }

  // ---------------------------------------------------------- tabela de amostras e configuração
  const cols = [['t_s', 'Tempo', v => tmin(v)], ['pss_mb', 'PSS (MB)', v => fmt(v, 1)], ['java_heap_mb', 'Java (MB)', v => fmt(v, 1)],
    ['native_heap_mb', 'Nativa (MB)', v => fmt(v, 1)], ['janky_pct', 'Travados (%)', v => fmt(v, 1)], ['cpu_pct', 'CPU (%)', v => fmt(v, 1)],
    ['battery_pct', 'Bateria (%)', v => fmt(v, 0)], ['battery_temp_c', 'Bat. (°C)', v => fmt(v, 1)], ['temp_cpu_c', 'CPU (°C)', v => fmt(v, 1)],
    ['charging', 'Carregando', v => v === true ? 'sim' : v === false ? 'não' : '—'], ['app_alive', 'App vivo', v => v === true ? 'sim' : v === false ? 'não' : '—'],
    ['touches', 'Toques', v => fmt(v, 0)]];
  const t = el('table', {}, el('thead', {}, el('tr', {}, ...cols.map(c => el('th', { class: 'n', text: c[1] })))));
  const body = el('tbody');
  for (const r of rows) body.append(el('tr', {}, ...cols.map(c => el('td', { class: 'n', text: c[2](r[c[0]]) }))));
  t.append(body);
  app.append(el('h2', { text: 'Dados' }), el('div', { class: 'card' },
    el('details', {}, el('summary', { text: `Tabela com as ${rows.length} amostras (o mesmo conteúdo de samples.csv)` }), el('div', { class: 'scroll' }, t))));

  const dev = M.device || {};
  const mg = el('div', { class: 'meta-grid' });
  const kv = (k, v) => mg.append(el('div', {}, el('span', { text: `${k}: ` }), document.createTextNode(v ?? '—')));
  kv('Aparelho', dev.model ? `${dev.model} (Android ${dev.android})` : '—');
  kv('Modo', modeTxt); kv('Energia medida', S.power_mode);
  kv('Brilho', dev.brightness ? `${dev.brightness}${dev.brightness_auto === '1' ? ' (automático)' : ' (fixo)'}` : '—');
  kv('Semente', String(M.seed ?? '—')); kv('Toques acumulados da ponteira', fmt(M.wear_total_touches ?? 0, 0));
  kv('Simulação', M.dry_run ? 'sim (dry-run, dados falsos)' : 'não'); kv('Serial adb', M.serial || '—');
  app.append(el('h2', { text: 'Configuração' }), el('div', { class: 'card' }, mg));
})();
</script>
</body>
</html>
"""
