"""Derive usage statistics from raw samples and render console / HTML reports."""
from __future__ import annotations

import html
import time
from collections import defaultdict
from dataclasses import dataclass, field

from .config import Config
from .store import Store


def _fmt_dur(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


@dataclass
class Bucket:
    seconds: float = 0.0
    keys: int = 0
    clicks: int = 0
    scrolls: int = 0
    mouse_px: float = 0.0


@dataclass
class Report:
    span_start_ms: int
    span_end_ms: int
    active_seconds: float = 0.0
    away_seconds: float = 0.0
    total_keys: int = 0
    total_clicks: int = 0
    total_scrolls: int = 0
    by_app: dict[str, Bucket] = field(default_factory=lambda: defaultdict(Bucket))
    by_category: dict[str, Bucket] = field(default_factory=lambda: defaultdict(Bucket))
    by_domain: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    timeline: list[dict] = field(default_factory=list)  # merged sessions


def build_report(store: Store, since_ms: int, until_ms: int | None = None) -> Report:
    rows = store.query(since_ms, until_ms)
    rep = Report(span_start_ms=since_ms, span_end_ms=until_ms or int(time.time() * 1000))
    cur = None  # current merged session
    for r in rows:
        dur = r["interval_s"] or 5.0
        active = bool(r["active"])
        if active:
            rep.active_seconds += dur
            rep.total_keys += r["keys"] or 0
            rep.total_clicks += r["clicks"] or 0
            rep.total_scrolls += r["scrolls"] or 0
            app = r["app"] or "unknown"
            cat = r["category"] or "other"
            for bucket, key in ((rep.by_app, app), (rep.by_category, cat)):
                b = bucket[key]
                b.seconds += dur
                b.keys += r["keys"] or 0
                b.clicks += r["clicks"] or 0
                b.scrolls += r["scrolls"] or 0
                b.mouse_px += r["mouse_px"] or 0.0
            if r["domain"]:
                rep.by_domain[r["domain"]] += dur
        else:
            rep.away_seconds += dur

        # merge consecutive same-app rows into timeline sessions
        label = (r["app"] or "-", r["category"] or "-")
        if cur and cur["_label"] == label:
            cur["seconds"] += dur
            cur["keys"] += r["keys"] or 0
            cur["end_ms"] = r["ts_ms"]
            if r["domain"] and r["domain"] not in cur["domains"]:
                cur["domains"].append(r["domain"])
        else:
            if cur:
                rep.timeline.append(cur)
            cur = {
                "_label": label, "app": label[0], "category": label[1],
                "start_ms": r["ts_ms"], "end_ms": r["ts_ms"],
                "seconds": dur, "keys": r["keys"] or 0,
                "domains": [r["domain"]] if r["domain"] else [],
            }
    if cur:
        rep.timeline.append(cur)
    return rep


def render_console(rep: Report) -> str:
    total = rep.active_seconds + rep.away_seconds
    kpm = (rep.total_keys / (rep.active_seconds / 60)) if rep.active_seconds else 0
    cpm = (rep.total_clicks / (rep.active_seconds / 60)) if rep.active_seconds else 0
    lines = []
    lines.append("=" * 58)
    lines.append(f" Screen usage  {time.strftime('%Y-%m-%d %H:%M', time.localtime(rep.span_start_ms/1000))}"
                 f"  ->  {time.strftime('%H:%M', time.localtime(rep.span_end_ms/1000))}")
    lines.append("=" * 58)
    lines.append(f" active {_fmt_dur(rep.active_seconds)} | away {_fmt_dur(rep.away_seconds)}"
                 f" | total {_fmt_dur(total)}")
    lines.append(f" typing {kpm:.0f} keys/min | {cpm:.1f} clicks/min"
                 f" | scroll {rep.total_scrolls}")
    lines.append("")
    lines.append(" By category:")
    for cat, b in sorted(rep.by_category.items(), key=lambda kv: -kv[1].seconds):
        pct = 100 * b.seconds / rep.active_seconds if rep.active_seconds else 0
        rate = b.keys / (b.seconds / 60) if b.seconds else 0
        lines.append(f"   {cat:<14} {_fmt_dur(b.seconds):>8} {pct:4.0f}%   {rate:4.0f} keys/min")
    lines.append("")
    lines.append(" By app:")
    for app, b in sorted(rep.by_app.items(), key=lambda kv: -kv[1].seconds)[:12]:
        pct = 100 * b.seconds / rep.active_seconds if rep.active_seconds else 0
        lines.append(f"   {app:<20} {_fmt_dur(b.seconds):>8} {pct:4.0f}%")
    if rep.by_domain:
        lines.append("")
        lines.append(" Top domains:")
        for dom, secs in sorted(rep.by_domain.items(), key=lambda kv: -kv[1])[:10]:
            lines.append(f"   {dom:<28} {_fmt_dur(secs):>8}")
    lines.append("=" * 58)
    return "\n".join(lines)


def render_html(rep: Report, out_path: str) -> str:
    total = rep.active_seconds + rep.away_seconds
    kpm = (rep.total_keys / (rep.active_seconds / 60)) if rep.active_seconds else 0

    def bar_rows(items, denom):
        out = []
        for name, secs in items:
            pct = 100 * secs / denom if denom else 0
            out.append(
                f'<div class="row"><span class="lbl">{html.escape(str(name))}</span>'
                f'<span class="bar"><i style="width:{pct:.1f}%"></i></span>'
                f'<span class="val">{_fmt_dur(secs)} · {pct:.0f}%</span></div>'
            )
        return "\n".join(out)

    cats = sorted(((c, b.seconds) for c, b in rep.by_category.items()), key=lambda x: -x[1])
    apps = sorted(((a, b.seconds) for a, b in rep.by_app.items()), key=lambda x: -x[1])[:12]
    doms = sorted(rep.by_domain.items(), key=lambda x: -x[1])[:10]

    tl_rows = []
    for s in rep.timeline:
        if s["seconds"] < (s.get("interval_s") or 5):
            continue
        t0 = time.strftime("%H:%M", time.localtime(s["start_ms"] / 1000))
        dom = (" · " + ", ".join(s["domains"][:3])) if s["domains"] else ""
        tl_rows.append(
            f'<tr><td>{t0}</td><td>{html.escape(s["app"])}</td>'
            f'<td>{html.escape(s["category"])}</td><td>{_fmt_dur(s["seconds"])}</td>'
            f'<td class="mut">{html.escape(dom)}</td></tr>'
        )

    doc = f"""<!doctype html><meta charset="utf-8">
<title>Screen usage report</title>
<style>
 body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:860px;
   margin:24px auto;padding:0 16px;color:#1c1c1e;background:#fafafa}}
 h1{{font-size:20px}} h2{{font-size:15px;margin-top:28px;color:#444}}
 .kpi{{display:flex;gap:24px;flex-wrap:wrap;margin:12px 0 4px}}
 .kpi div{{background:#fff;border:1px solid #eee;border-radius:10px;padding:10px 16px}}
 .kpi b{{font-size:20px;display:block}}
 .row{{display:flex;align-items:center;gap:10px;margin:3px 0}}
 .lbl{{width:150px;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
 .bar{{flex:1;background:#eee;border-radius:6px;height:14px;overflow:hidden}}
 .bar i{{display:block;height:100%;background:#4f8cff}}
 .val{{width:120px;flex:none;text-align:right;color:#666;font-variant-numeric:tabular-nums}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 td,th{{padding:4px 8px;border-bottom:1px solid #eee;text-align:left}}
 .mut{{color:#888}}
</style>
<h1>Screen usage report</h1>
<p class="mut">{time.strftime('%Y-%m-%d %H:%M', time.localtime(rep.span_start_ms/1000))}
 &rarr; {time.strftime('%H:%M', time.localtime(rep.span_end_ms/1000))}</p>
<div class="kpi">
 <div><b>{_fmt_dur(rep.active_seconds)}</b>active</div>
 <div><b>{_fmt_dur(rep.away_seconds)}</b>away</div>
 <div><b>{kpm:.0f}</b>keys/min</div>
 <div><b>{rep.total_clicks}</b>clicks</div>
 <div><b>{rep.total_scrolls}</b>scrolls</div>
</div>
<h2>By category</h2>{bar_rows(cats, rep.active_seconds)}
<h2>By app</h2>{bar_rows(apps, rep.active_seconds)}
{('<h2>Top domains</h2>' + bar_rows(doms, rep.active_seconds)) if doms else ''}
<h2>Timeline</h2>
<table><tr><th>start</th><th>app</th><th>category</th><th>dur</th><th>detail</th></tr>
{''.join(tl_rows)}</table>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path
