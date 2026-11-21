"""The one-page site report (HTML) and the summary numbers the app also shows.

HTML instead of PDF: it needs no extra library, opens on any laptop or phone,
and the browser's "Print -> Save as PDF" turns it into a one-page A4 PDF.
Everything here is plain formatting of results we already have: no AI, no cost.
"""
from __future__ import annotations

import base64
import html
import io
from datetime import datetime

from . import config, objects, score, sitecheck
from .hazards import LEVEL_NAMES

# One colour set for the whole product (app + report), so "red" always means the same.
# Brand colours were read from axaxl.com (2026-11-21); we use colours only, never the AXA logo.
PALETTE = {
    "blue": "#00008F",       # AXA blue: headings, primary buttons, the header band
    "blue_hover": "#3B3FD8",
    "teal": "#027180",       # secondary accent, also "low" hazard
    "teal_bg": "#EBF8FA",
    "ink": "#212529",        # body text
    "muted": "#5F5F5F",      # small print
    "line": "#CCCCCC",       # thin dividers (dream-machines.eu style: lines, not shadows)
    "paper": "#F5F5F5",      # panels
}
LEVEL_COLOURS = {0: PALETTE["teal"], 1: "#e8710a", 2: "#c62828"}   # hazard low / medium / high
IMPORTANCE_COLOURS = sitecheck.COLOURS                        # high / medium / low / uncertain ...
GROUP_TITLES = {"water": "Water (river flood + surface runoff)", "hail": "Hail"}
REPORT_IMG_PX = 640   # big enough to read the boxes, small enough to keep the file light
LIMITS = ("The check only judges what the camera sees: not roof strength, not what is behind "
          "walls. Low-confidence findings are shown but not counted. People are blurred "
          "before upload; number plates are not.")
DISCLAIMER = "Prototype built for the AXA challenge at LauzHack 2026. Not an underwriting decision."


# ---------------- numbers shared by the app and the report ----------------
def is_mock(res: dict) -> bool:
    """True if any answer in this result is a fake MOCK answer (no key / test mode)."""
    return config.MOCK or any("MOCK" in s.note for s in res["ledger"].steps)


def came_from_cache(res: dict) -> bool:
    return any("cache" in s.note for s in res["ledger"].steps if s.kind == "ai")


def fmt_usd(x: float) -> str:
    # Our costs are fractions of a cent: show enough digits to see them at all.
    if x == 0:
        return "$0"
    return f"${x:.5f}" if x < 0.01 else f"${x:.4f}"


def cost_parts(res: dict) -> tuple[str, str]:
    """What this run cost, as (amount, honest label), e.g. ("~$0.00016", "estimate")."""
    fr = res.get("frugal") or {}
    if not fr.get("images_sent"):
        return "$0", "no AI needed"
    if is_mock(res):
        return f"~{fmt_usd(fr['ours_usd_est'])}", "MOCK estimate"
    if came_from_cache(res) and fr["ours_usd_real"] == 0:
        return "$0", "repeat run, from cache"
    return fmt_usd(fr["ours_usd_real"]), "measured"


def cost_text(res: dict) -> str:
    amount, label = cost_parts(res)
    return f"{amount} ({label})"


def action_level(site_score: int) -> int:
    """0 / 1 / 2 for colouring the AXA action, from the same thresholds as score.ACTIONS."""
    for i, (threshold, _) in enumerate(score.ACTIONS):
        if site_score >= threshold:
            return len(score.ACTIONS) - 1 - i
    return 0


def summary(res: dict) -> dict:
    """The four headline numbers of a site check, used by the app card and the report."""
    r = res["result"]
    return {"score": r["score"], "action": r["action"], "action_level": action_level(r["score"]),
            "keyframes": len(res["frames"]["picked"]), "cost": cost_text(res),
            "hazards": {g: h["level"] for g, h in res["hazards"].items()}}


def naive_ratio(res: dict) -> float | None:
    fr = res.get("frugal") or {}
    return fr["naive_usd"] / fr["ours_usd_est"] if fr.get("ours_usd_est") else None


def frames_text(frames: list[int]) -> str:
    return ", ".join(f"#{n}" for n in frames)


# ---------------- HTML pieces ----------------
def _e(text) -> str:
    return html.escape(str(text))


def _pill(text: str, colour: str) -> str:
    return f'<span class="pill" style="background:{colour}">{_e(text)}</span>'


def _jpeg_data_uri(img) -> str:
    img = img.copy()
    img.thumbnail((REPORT_IMG_PX, REPORT_IMG_PX))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _header(res: dict, when: datetime) -> str:
    where = res["place"]["label"] if res.get("place") else res["address"]
    note = ""
    if is_mock(res):
        note = '<p class="mock">MOCK mode: AI answers are simulated, not real findings.</p>'
    if any("simulated" in s.note for s in res["ledger"].steps):
        note += '<p class="mock">Hazard levels are simulated (developer setting), not from the map.</p>'
    return (f'<header><h1>Frugal Site Check</h1><div class="where">{_e(where)}</div>'
            f'<div class="small">Report created {when:%d.%m.%Y %H:%M}</div>{note}</header>')


def _summary_card(res: dict) -> str:
    s = summary(res)
    hz = " ".join(f"{_e(GROUP_TITLES[g].split(' (')[0])} "
                  f"{_pill(LEVEL_NAMES[lvl], LEVEL_COLOURS[lvl])}" for g, lvl in s["hazards"].items())
    cells = [("Site score", s["score"]), ("Key frames checked", s["keyframes"]),
             ("AI cost of this check", s["cost"])]
    return ('<section class="card">'
            f'<div class="action" style="border-color:{LEVEL_COLOURS[s["action_level"]]}">'
            f'<div class="small">Recommended AXA action</div><b>{_e(s["action"])}</b></div>'
            + "".join(f'<div class="cell"><div class="small">{_e(k)}</div><b>{_e(v)}</b></div>'
                      for k, v in cells)
            + f'<div class="hz">Area hazard: {hz}</div></section>')


def _hazard_table(res: dict) -> str:
    rows = "".join(
        f"<tr><td>{_e(GROUP_TITLES[g])}</td>"
        f"<td>{_pill(LEVEL_NAMES[h['level']], LEVEL_COLOURS[h['level']])}</td>"
        f"<td>{_e(', '.join(h['sources']) or 'no mapped hazard zone at this point')}</td></tr>"
        for g, h in res["hazards"].items())
    return ("<section><h2>Official hazard maps at this address</h2>"
            f"<table><tr><th>Hazard</th><th>Level</th><th>Source</th></tr>{rows}</table></section>")


def frame_caption(frame: dict, found: list[dict]) -> str:
    here = [o for o in found if o["f"] == frame["n"] and o["label"] != "privacy"]
    # One mention per object type and label, so three cars read as "vehicle (high)" once.
    seen = dict.fromkeys(f"{objects.CATALOGUE[o['kind']]['name']} ({o['label']})" for o in here)
    what = "; ".join(seen)
    return f"#{frame['n']} at {frame['t']:.1f} s" + (f": {what}" if what else ": nothing relevant")


def _frames(res: dict) -> str:
    tiles = "".join(
        f'<figure><img src="{_jpeg_data_uri(sitecheck.annotate(f, res["objects"]))}" alt="">'
        f"<figcaption>{_e(frame_caption(f, res['objects']))}</figcaption></figure>"
        for f in res["frames"]["picked"])
    return f'<section><h2>Key frames with what was found</h2><div class="grid">{tiles}</div></section>'


def _advice(res: dict, storm: bool) -> str:
    items = res["result"]["items"]
    if not items:
        return ("<section><h2>Advice</h2><p>No weak points found for the hazards at this "
                "address.</p></section>")
    now = "".join(f"<li>{_pill(i['label'], IMPORTANCE_COLOURS[i['label']])} "
                  f"{_e(objects.CATALOGUE[i['kind']]['now'])}</li>"
                  for i in items if objects.CATALOGUE[i["kind"]]["now"])
    later = "".join(f"<li>{_pill(i['label'], IMPORTANCE_COLOURS[i['label']])} "
                    f"{_e(objects.CATALOGUE[i['kind']]['later'])} "
                    f"<span class='small'>Why: {_e(objects.CATALOGUE[i['kind']]['why'])} "
                    f"Seen in {frames_text(i['frames'])}.</span></li>" for i in items)
    title = "Storm warning (simulated): do these now" if storm else "Before a storm (minutes)"
    return ('<section class="cols"><div><h2>' + _e(title) + f"</h2><ol>{now}</ol></div>"
            f"<div><h2>Prevention (this year)</h2><ol>{later}</ol></div></section>")


def _uncertain(res: dict) -> str:
    frames = res["result"]["uncertain"]
    if not frames:
        return ""
    return (f'<p class="note">Low-confidence objects in frames {frames_text(frames)} are '
            "shown but not counted: a person should check them.</p>")


def _cost(res: dict) -> str:
    fr = res["frugal"]
    ratio = naive_ratio(res)
    vs = f" That is about {ratio:,.0f}x cheaper." if ratio else ""
    return ("<section><h2>What it cost</h2>"
            f"<p>This check: <b>{_e(cost_text(res))}</b>. {fr['video_frames']:,} video frames, "
            f"{fr['sampled']} checked by free code, {fr['picked']} key frames, "
            f"{fr['images_sent']} images sent to AI in one call. A naive design (one full-HD "
            f"frame per second to the strong model) would cost about "
            f"{_e(fmt_usd(fr['naive_usd']))} ({fr['naive_calls']} calls).{vs}</p>"
            '<p class="small">Both sides estimated with the same rule '
            "(1 image token per 28x28 pixels) and the model price list in the app.</p></section>")


CSS = """
/* Self-contained on purpose: no web fonts or links, so it also works offline and by e-mail.
   Style: dream-machines.eu (square corners, thin lines, mono labels) in axaxl.com colours. */
body{font-family:"Source Sans 3","Source Sans Pro",-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;
     color:%(ink)s;max-width:1000px;margin:24px auto;padding:0 16px;font-size:14px;line-height:1.45}
header{background:%(blue)s;color:#fff;padding:16px 18px;margin-bottom:4px}
header .small{color:#c9c9f0}
h1{margin:0;font-size:26px;font-weight:500;letter-spacing:-0.02em}
h2{font-family:ui-monospace,"Spline Sans Mono",Menlo,monospace;font-size:11px;font-weight:500;
   text-transform:uppercase;letter-spacing:.08em;color:%(blue)s;margin:16px 0 6px;
   padding-top:8px;border-top:1px solid %(line)s}
h2:before{content:"\\25A0  "}
.where{font-size:16px;font-weight:600}.small{color:%(muted)s;font-size:12px}
.mock{background:#fff4e5;border-left:4px solid #e8710a;padding:4px 8px;margin:6px 0;
      font-size:12px;color:%(ink)s}
.card{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:8px;margin:12px 0;
      border:1px solid %(line)s;padding:10px}
.card b{font-size:18px}.action{border-left:6px solid;padding-left:10px}
.hz{grid-column:1/-1;font-size:13px;border-top:1px solid %(line)s;padding-top:6px}
.pill{display:inline-block;padding:1px 7px;color:#fff;font-size:10px;font-weight:500;
      font-family:ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.05em}
table{border-collapse:collapse;width:100%%;font-size:12px}
td,th{border-bottom:1px solid %(line)s;padding:4px 6px;text-align:left}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
figure{margin:0}figure img{width:100%%;border:1px solid %(line)s}
figcaption{font-size:11px;color:%(muted)s}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px} ol{margin:0;padding-left:18px}
li{margin-bottom:4px}.note{background:%(teal_bg)s;border-left:4px solid %(teal)s;padding:6px 8px;
      font-size:12px}
footer{margin-top:12px;border-top:1px solid %(line)s;padding-top:6px;font-size:11px;color:%(muted)s}
@page{size:A4;margin:10mm}
@media print{body{margin:0;max-width:none;font-size:10px;line-height:1.3}h1{font-size:18px}
  header{padding:8px 10px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .pill,.card .action{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  h2{margin:8px 0 4px;padding-top:4px}.card{padding:6px;margin:8px 0}.card b{font-size:13px}
  .grid{gap:5px}figcaption{font-size:9px}li{margin-bottom:2px}.small,.note,table{font-size:9px}
  section,figure{break-inside:avoid}}
""" % PALETTE


def build_html(res: dict, storm: bool = False, when: datetime | None = None) -> str:
    """The full report as one self-contained HTML file (images embedded)."""
    when = when or datetime.now()
    body = (_header(res, when) + _summary_card(res) + _hazard_table(res) + _frames(res)
            + _advice(res, storm) + _uncertain(res) + _cost(res)
            + f"<footer>{_e(LIMITS)}<br>{_e(DISCLAIMER)}<br>Data: BAFU, MeteoSwiss, "
              "swisstopo / geo.admin.ch.</footer>")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Site report</title><style>{CSS}</style></head><body>{body}</body></html>")


def filename(res: dict, when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"site-report-{when:%Y%m%d-%H%M}.html"
