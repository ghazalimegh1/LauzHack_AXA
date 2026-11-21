"""Frugal Site Check - Streamlit UI.
Run:  streamlit run app.py
Main flow: a walk-around video of a business site -> key frames -> objects -> advice.
Second flow: one photo of a home. The AXA tab shows cost and portfolio for both.
Demo fallback: open the app with ?demo=1 to get a "Run sample video" button that uses
eval/test_walk.mp4 (made by tools/make_test_video.py), in case an upload fails on stage."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from frugal import checklist, config, detect, objects, pipeline, report, sitecheck, video
from frugal.hazards import LEVEL_NAMES

SAMPLE_VIDEO = Path(__file__).parent / "eval" / "test_walk.mp4"
PREVIEW_MAX_MB = 50   # above this, no inline video preview (slow to send back to the browser)
GROUP_TITLES = report.GROUP_TITLES
LEVEL_COLOURS = report.LEVEL_COLOURS          # one colour set, shared with the report
IMPORTANCE_COLOURS = report.IMPORTANCE_COLOURS

st.set_page_config(page_title="Frugal Site Check", layout="wide")
P = report.PALETTE
MONO = '"Spline Sans Mono", ui-monospace, Menlo, monospace'
HEAD = '"Inter Tight", "Source Sans", "Source Sans Pro", sans-serif'
# Style: the layout of dream-machines.eu (square corners, thin lines, small mono labels,
# pixel blocks) in the colours of axaxl.com. Fonts come from .streamlit/config.toml.
st.markdown(f"""<style>
.hero{{position:relative;overflow:hidden;background:{P['blue']};color:#fff;
      padding:34px 36px 30px;margin:0 0 18px}}
.hero h1{{font-family:{HEAD};font-weight:500;font-size:3.1rem;line-height:1.02;
      letter-spacing:-0.03em;margin:8px 0 12px;color:#fff;max-width:70%;padding:0}}
.hero p{{font-family:{MONO};font-size:0.86rem;line-height:1.55;letter-spacing:.02em;
      max-width:62%;color:#e6e6f6;margin:0}}
.hero .eyebrow{{color:#c9c9f0}}
.pixels{{position:absolute;right:28px;top:22px;display:grid;
      grid-template-columns:repeat(6,26px);grid-auto-rows:26px}}
.pixels i{{display:block}} .pixels i.on{{background:#fff}} .pixels i.mid{{background:{P['blue_hover']}}}
.eyebrow{{font-family:{MONO};font-size:0.72rem;font-weight:500;text-transform:uppercase;
      letter-spacing:.09em;color:{P['blue']};margin:22px 0 2px;display:block}}
.eyebrow:before{{content:"\\25A0";margin-right:8px}}
.pill{{display:inline-block;padding:2px 8px;font-family:{MONO};font-weight:500;color:#fff;
      font-size:0.68rem;text-transform:uppercase;letter-spacing:.06em}}
.small{{color:{P['muted']};font-size:0.85rem}}
.card{{display:grid;grid-template-columns:2.2fr 1fr 1fr 1.3fr;gap:0;border:1px solid {P['line']};
      background:#fff;margin-bottom:8px}}
.card > div{{padding:16px 20px;border-right:1px solid {P['line']}}}
.card > div:nth-child(4){{border-right:none}}
.card .label{{font-family:{MONO};color:{P['muted']};font-size:0.7rem;text-transform:uppercase;
      letter-spacing:.08em;margin-bottom:6px}}
.card .value{{font-family:{HEAD};font-size:1.9rem;font-weight:500;letter-spacing:-0.02em;
      line-height:1.1;color:{P['ink']}}}
.card .action{{border-left:8px solid}}
.card .action .value{{font-size:1.45rem}}
.card .hz{{grid-column:1/-1;border-top:1px solid {P['line']};border-right:none;padding:10px 20px;
      background:{P['paper']}}}
.funnel{{display:flex;gap:0;flex-wrap:wrap;align-items:stretch;margin:6px 0 10px;
      font-family:{MONO};font-size:0.8rem}}
.funnel span.step{{border:1px solid {P['line']};padding:8px 14px;margin-right:-1px}}
.funnel span.arrow{{padding:8px 10px;color:{P['muted']}}}
.funnel span.ai{{background:{P['blue']};border-color:{P['blue']};color:#fff}}
.warn{{background:#fdecea;border-left:6px solid {LEVEL_COLOURS[2]};padding:12px 16px;margin:8px 0}}
.empty{{border:1px solid {P['line']};padding:18px 22px;color:{P['ink']};background:{P['paper']}}}
.empty ol{{margin:6px 0 0 0}}
[data-testid="stMetricValue"]{{font-family:{HEAD};font-weight:500;letter-spacing:-0.02em}}
[data-testid="stMetricLabel"] p{{font-family:{MONO};font-size:0.72rem;text-transform:uppercase;
      letter-spacing:.06em}}
button[data-baseweb="tab"] p{{font-family:{MONO};font-size:0.8rem;text-transform:uppercase;
      letter-spacing:.06em}}
hr{{border-color:{P['line']}}}
</style>""", unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("cases", [])     # every successful check this session (AXA portfolio)
ss.setdefault("last", None)    # the last check of any kind (AXA view)
ss.setdefault("site", None)    # last video check
ss.setdefault("photo", None)   # last photo check


# ---------------- small display helpers ----------------
def pill(text: str, colour: str) -> str:
    return f'<span class="pill" style="background:{colour}">{text}</span>'


def level_pill(level: int) -> str:
    return pill(LEVEL_NAMES[level], LEVEL_COLOURS[level])


def importance_pill(label: str) -> str:
    return pill(label, IMPORTANCE_COLOURS[label])


def html(text: str) -> None:
    st.markdown(text, unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    """Small mono "■ LABEL" above a heading, as on dream-machines.eu."""
    html(f'<span class="eyebrow">{text}</span>')


def safe_run(fn, *args, **kwargs) -> dict:
    """A live demo must never show a Python traceback: unexpected errors become a message."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        return {"status": "crash", "error": f"{type(exc).__name__}: {exc}"}


# ---------------- sidebar: mode, models, developer tools ----------------
with st.sidebar:
    st.header("Settings")
    if config.MOCK:
        st.warning("MOCK mode: no API key found, AI answers are simulated. Add "
                   "ANTHROPIC_API_KEY or OPENROUTER_API_KEY to .env for real answers.")
    else:
        st.success(f"Live AI via {'Claude API' if config.PROVIDER == 'anthropic' else 'OpenRouter'}")
    storm = st.toggle("Storm warning active (simulated)",
                      help="Demo switch. Shows the 'do now' list first, as if MeteoSwiss "
                           "had issued a hail or heavy-rain warning for this address.")
    keyframes = st.slider("Key frames per video", 3, 10, config.KEYFRAMES,
                          help="Frames that may reach a paid model. Fewer = cheaper.")
    use_det = st.checkbox("Use free local detector", detect.available(),
                          disabled=not detect.available(),
                          help="YOLO11n on this computer: finds vehicles and people for free "
                               "and blurs people before upload. pip install ultralytics")
    st.caption(f"Cheap model: `{config.CHEAP_MODEL}`  \nStrong model: `{config.STRONG_MODEL}`")
    baseline = st.checkbox("Photo check: also run the naive baseline",
                           help="Strong model, big image, all questions. Costs extra; "
                                "use it to show how much the cascade saves.")
    with st.expander("Developer: simulate hazard levels"):
        st.caption("Skips the map lookup. For testing and offline demos only; "
                   "results are labelled as simulated.")
        simulate = st.checkbox("Use simulated levels")
        sim = {g: st.select_slider(GROUP_TITLES[g], [0, 1, 2], 1,
                                   format_func=LEVEL_NAMES.get) for g in GROUP_TITLES}

PIXELS = ("..#..#", ".#.#..", "#..o.#", ".#..#.", "o.#...", ".#..o#")  # # white, o light blue


def pixel_blocks() -> str:
    cells = "".join(f'<i class="{ {"#": "on", "o": "mid"}.get(c, "")}"></i>'
                    for row in PIXELS for c in row)
    return f'<div class="pixels" aria-hidden="true">{cells}</div>'


html(f'''<div class="hero">{pixel_blocks()}
<span class="eyebrow">Built for the AXA challenge &middot; LauzHack 2026</span>
<h1>Frugal Site Check</h1>
<p>Film a one-minute walk around a business site. Official Swiss hazard maps decide what we
look for, free code picks a few sharp frames, and a small AI model finds what hail or water
would hit first. The expensive model only sees what is still unclear.</p></div>''')
if config.MOCK:
    st.caption(":orange[MOCK mode: AI answers on this page are simulated, not real findings.]")

tab_v, tab_c, tab_a, tab_h = st.tabs(["Site check (video)", "Single photo", "AXA view",
                                      "How it works"])


# ---------------- site video: input ----------------
def empty_state() -> None:
    html('<div class="empty"><b>How it works in three steps</b><ol>'
         "<li>Type the site address: official hazard maps say whether hail or water matter here.</li>"
         "<li>Upload a walk-around video (about 60 s, MP4 or MOV from a phone).</li>"
         "<li>Press <b>Analyse site</b>: free code picks the sharp frames, AI marks what a storm "
         "would hit first, and you get advice and a report to download.</li></ol>"
         '<p class="small">Tip: walk slowly and pause 1-2 s on each roof, car park, door and '
         "basement window.</p></div>")


def video_preview(upload) -> None:
    """Small MP4s play inline. iPhone .MOV files are usually HEVC, which Chrome often
    cannot play, and sending 300 MB back to the browser is slow: show a file card instead."""
    mb = upload.size / 1e6
    if upload.name.lower().endswith(".mov") or mb > PREVIEW_MAX_MB:
        html(f'<div class="empty"><b>{upload.name}</b> &nbsp; <span class="small">{mb:,.0f} MB'
             "</span><br>Ready to analyse. No preview for large or iPhone .MOV files: "
             "the browser often cannot play them, but the analysis reads them fine.</div>")
    else:
        st.video(upload)


def run_site(address: str, path: str, size: int) -> None:
    """Runs the video check on a file on disk (never the whole video in memory)."""
    big = size > PREVIEW_MAX_MB * 1e6
    text = ("Reading a large video (4K files take about 10-20 s), then picking frames, "
            "detecting objects and checking maps..." if big else
            "Picking frames, detecting objects, checking maps...")
    with st.spinner(text):
        res = safe_run(sitecheck.run, address, video_path=path,
                       levels=sim if simulate else None, k=keyframes, use_detector=use_det)
    ss.site = res
    if res["status"] in ("ok", "ai_error"):
        ss.last = res
    if res["status"] == "ok":
        ss.cases.append(res)


def run_upload(address: str, up) -> None:
    """Copies the upload to a temp file in chunks: a 300 MB iPhone video then exists
    once on disk instead of twice in memory. iPhones name files IMG_1234.MOV, so the
    suffix is lower-cased for the video reader."""
    suffix = "." + up.name.rsplit(".", 1)[-1].lower()
    up.seek(0)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(up, tmp)
    try:
        run_site(address, tmp.name, up.size)
    finally:
        os.unlink(tmp.name)


# ---------------- site video: results ----------------
def show_problem(res: dict) -> None:
    """Errors that stop the check before any result exists, in plain words."""
    if res["status"] == "geo_error":
        st.error("We could not look up this address. Check the spelling (street and town, "
                 "e.g. 'Route Cantonale, Lausanne') or the internet connection. For an "
                 "offline demo, use 'simulate hazard levels' in the sidebar.")
    elif res["status"] == "video_error":
        st.error(f"We could not use this video: {res['error']} Try an MP4 or MOV filmed "
                 "in daylight, walking slowly.")
    else:
        st.error("Something unexpected went wrong. Please try again or use another video.")
    with st.expander("Technical details"):
        st.code(res.get("error", ""))


def summary_card(res: dict) -> None:
    s = report.summary(res)
    amount, note = report.cost_parts(res)
    hz = " &nbsp; ".join(f"{GROUP_TITLES[g]} {level_pill(lvl)}" for g, lvl in s["hazards"].items())
    where = res["place"]["label"] if res.get("place") else res["address"]
    html('<div class="card">'
         f'<div class="action" style="border-color:{LEVEL_COLOURS[s["action_level"]]}">'
         f'<div class="label">Recommended AXA action</div><div class="value">{s["action"]}</div></div>'
         f'<div><div class="label">Site score</div><div class="value">{s["score"]}</div></div>'
         f'<div><div class="label">Key frames</div><div class="value">{s["keyframes"]}</div></div>'
         f'<div><div class="label">AI cost</div><div class="value">{amount}</div>'
         f'<div class="small">{note}</div></div>'
         f'<div class="hz"><span class="small">{where} &nbsp;|&nbsp; Area hazard:</span> {hz}</div>'
         "</div>")


def storm_box(res: dict) -> None:
    now = [i for i in res["result"]["items"] if objects.CATALOGUE[i["kind"]]["now"]]
    if not now:
        return
    html('<div class="warn"><b>Storm warning (simulated): do these now</b><ol>'
         + "".join(f"<li>{objects.CATALOGUE[i['kind']]['now']} <span class='small'>"
                   f"(frames {report.frames_text(i['frames'])})</span></li>" for i in now)
         + "</ol></div>")


def report_html(res: dict) -> str:
    # Building the report encodes 6 images; keep it until the result or storm switch changes.
    key = (id(res), storm)
    if ss.get("report_key") != key:
        ss.report_key, ss.report_html = key, report.build_html(res, storm=storm)
    return ss.report_html


def section_frames(res: dict) -> None:
    fr = res["frugal"]
    eyebrow("Step 1 · free")
    st.subheader("Frames picked from your video")
    html('<div class="funnel">'
         f'<span class="step">{fr["video_frames"]:,} frames in video</span><span class="arrow">&rarr;</span>'
         f'<span class="step">{fr["sampled"]} checked by free code</span><span class="arrow">&rarr;</span>'
         f'<span class="step">{fr["picked"]} key frames</span><span class="arrow">&rarr;</span>'
         f'<span class="step ai">{fr["images_sent"]} sent to AI</span></div>')
    with st.expander("Show all checked frames and why they were skipped"):
        st.image(video.filmstrip(res["frames"]["frames"]), width="stretch")
        st.caption("Green = picked (sharpest new view in its part of the walk). "
                   "Grey = skipped, with the reason. No AI is used for this step.")


def annotated(res: dict, frame: dict):
    # Drawing boxes is cheap, but Streamlit reruns on every click: draw each frame once.
    cache = res.setdefault("_annotated", {})
    if frame["n"] not in cache:
        cache[frame["n"]] = sitecheck.annotate(frame, res["objects"])
    return cache[frame["n"]]


def section_findings(res: dict) -> None:
    eyebrow("Step 2 · AI, one call")
    st.subheader("What was found in each key frame")
    html(" ".join(importance_pill(l) for l in ("high", "medium", "low", "uncertain",
                                                "not relevant here", "privacy"))
         + '<br><span class="small">Importance = object weight x hazard level at this '
           "address. People are blurred on this computer before upload.</span>")
    picked = res["frames"]["picked"]
    for a in range(0, len(picked), 3):
        for col, f in zip(st.columns(3), picked[a:a + 3]):
            col.image(annotated(res, f), width="stretch",
                      caption=report.frame_caption(f, res["objects"]))
    if res["objects"]:
        with st.expander("All findings as a table"):
            st.dataframe(pd.DataFrame([{
                "#": o["id"], "frame": f"#{o['f']}", "object": objects.CATALOGUE[o["kind"]]["name"],
                "importance": o["label"], "conf": o["conf"], "found by": o["by"]}
                for o in res["objects"]]), hide_index=True, width="stretch")


def section_advice(res: dict) -> None:
    r = res["result"]
    eyebrow("Step 3 · fixed rules")
    st.subheader("Advice")
    if not r["items"]:
        st.success("No weak points found for the hazards at this address.")
        return
    now_col, later_col = st.columns(2)
    with now_col:
        st.markdown("**Before a storm (minutes)**")
        for i in r["items"]:
            c = objects.CATALOGUE[i["kind"]]
            if c["now"]:
                html(f"{importance_pill(i['label'])} {c['now']}")
    with later_col:
        st.markdown("**Prevention (this year)**")
        for i in r["items"]:
            c = objects.CATALOGUE[i["kind"]]
            html(f"{importance_pill(i['label'])} {c['later']}  \n<span class='small'>Why: "
                 f"{c['why']} Seen in {report.frames_text(i['frames'])}.</span>")
    if r["uncertain"]:
        st.info(f"Some objects were found with low confidence (frames "
                f"{report.frames_text(r['uncertain'])}). They are not counted; a person "
                "should check them.")


def section_cost(res: dict) -> None:
    fr = res["frugal"]
    eyebrow("Step 4 · measured")
    st.subheader("What it cost")
    c = st.columns(3)
    amount, note = report.cost_parts(res)
    c[0].metric(f"This check ({note})", amount)
    c[1].metric("Naive: 1 HD frame/s to strong model", f"~{report.fmt_usd(fr['naive_usd'])}")
    ratio = report.naive_ratio(res)
    c[2].metric("Naive / ours", f"{ratio:,.0f}x" if ratio else "no AI needed")
    st.caption(f"Same estimate on both sides (1 token per 28x28 px): naive {fr['naive_calls']} "
               f"calls / {fr['naive_tokens']:,} tokens, ours 1 call / {fr['ours_tokens_est']:,} tokens.")
    with st.expander("Step-by-step cost ledger"):
        st.dataframe(pd.DataFrame(res["ledger"].rows()), hide_index=True, width="stretch")


def show_site(res: dict) -> None:
    if res["status"] in ("geo_error", "video_error", "crash"):
        show_problem(res)
        return
    if res["status"] == "ai_error":
        st.warning("The AI step did not answer (check the API key and model IDs in the sidebar). "
                   "Below is what the free steps found: hazard maps, key frames and the local detector.")
        with st.expander("Technical details"):
            st.code(res["error"])
    card_col, btn_col = st.columns([5, 1], vertical_alignment="center")
    with card_col:
        summary_card(res)
    with btn_col:
        st.download_button("↓  Download report", report_html(res), report.filename(res),
                           mime="text/html", type="primary", on_click="ignore",
                           help="One-page HTML report. Open it and use Print -> Save as PDF.")
    if storm:
        storm_box(res)
    section_frames(res)
    section_findings(res)
    section_advice(res)
    section_cost(res)


with tab_v:
    left, right = st.columns([1, 1])
    with left:
        v_address = st.text_input("Site address in Switzerland", "Route Cantonale, Lausanne",
                                  key="v_addr")
        v_up = st.file_uploader("Walk-around video (about 60 s; iPhone .MOV or MP4 are fine)",
                                type=["mp4", "mov", "m4v", "avi"],
                                help="Straight from the phone: iPhone HEVC .MOV, portrait or "
                                     "landscape, up to 1 GB. 1080p is enough; 4K works but "
                                     "takes longer to read.")
        v_go = st.button("→  Analyse site", type="primary", width="stretch", disabled=not v_up)
        demo = st.query_params.get("demo") == "1" and SAMPLE_VIDEO.exists()
        demo_go = demo and st.button("Run sample video (demo fallback)", width="stretch")
    with right:
        if v_up:
            video_preview(v_up)
        else:
            empty_state()

    if v_go and v_up:
        run_upload(v_address, v_up)
    elif demo_go:
        run_site(v_address, str(SAMPLE_VIDEO), SAMPLE_VIDEO.stat().st_size)

    if ss.site:
        st.divider()
        show_site(ss.site)

# ---------------- single photo ----------------
with tab_c:
    left, right = st.columns([1, 1])
    with left:
        address = st.text_input("Address in Switzerland", "Gerberngasse 10, Bern", key="p_addr")
        up = st.file_uploader("Photo of the outside of your home (optional)",
                              type=["jpg", "jpeg", "png"])
        force = False
        if ss.photo and ss.photo["status"] == "retake":
            force = st.checkbox("My photo is fine, analyse it anyway")
        go = st.button("→  Check my home", type="primary", width="stretch")
    with right:
        if up:
            st.image(up, width="stretch")
        else:
            st.caption("Without a photo we check the address only (free). Add a photo to "
                       "find the building's weak points.")

    if go:
        with st.spinner("Checking maps and photo..."):
            res = safe_run(pipeline.run, address, up.getvalue() if up else None,
                           levels=sim if simulate else None, force=force, baseline=baseline)
        ss.photo = res
        if res["status"] in ("ok", "area_only", "ai_error"):
            ss.last = res
        if res["status"] in ("ok", "area_only"):
            ss.cases.append(res)

    res = ss.photo
    if res:
        st.divider()
        if res["status"] == "geo_error":
            st.error("We could not look up this address. Check the spelling or the internet "
                     "connection, or use 'simulate hazard levels' in the sidebar.")
        elif res["status"] == "crash":
            st.error("Something unexpected went wrong with this photo. Try a JPG or PNG.")
            with st.expander("Technical details"):
                st.code(res["error"])
        else:
            if res["status"] == "ai_error":
                st.warning("The AI step did not answer (check key and model IDs). "
                           "Showing the hazard levels from the free map lookup.")
            if res.get("place"):
                st.caption(f"Found: {res['place']['label']}")
            if res["status"] == "retake":
                st.warning("Before we analyse: " + " ".join(res["photo_problems"])
                           + " Please take another photo. (No AI cost so far.)")
            cols = st.columns(len(res["hazards"]))
            for col, (g, h) in zip(cols, res["hazards"].items()):
                with col:
                    html(f"**{GROUP_TITLES[g]}** {level_pill(h['level'])}")
                    weak = res["result"]["groups"][g]["weak"]
                    if weak:
                        st.markdown("Weak points seen: " + ", ".join(
                            checklist.BY_ID[i]["q"].rstrip("?").lower() for i in weak))
                    if not h["answered"]:
                        html('<span class="small">No mapped hazard zone at this point.</span>')
            if res["result"]["tips"]:
                st.subheader("What you can do")
                for t in res["result"]["tips"]:
                    st.markdown(f"- {t}")
            elif res["status"] == "area_only":
                st.info("Address checked. Add a photo to check your building's weak points.")
            elif res["status"] == "ok" and not up:
                st.success("No elevated hazard at this address, so no photo check is needed.")
            elif res["status"] == "ok":
                st.success("No specific weak points found for the hazards at this address.")

# ---------------- AXA screen ----------------
with tab_a:
    res = ss.last
    if not res:
        st.info("Run a site check or a photo check first; the underwriter view appears here.")
    else:
        tot = res["ledger"].totals()
        level = report.action_level(res["result"]["score"])
        # The action is a sentence, too long for st.metric: show it as a coloured banner.
        html(f'<div class="card" style="grid-template-columns:1fr"><div class="action" '
             f'style="border-color:{LEVEL_COLOURS[level]}"><div class="label">Recommended action'
             f'</div><div class="value">{res["result"]["action"]}</div></div></div>')
        if res.get("kind") == "video":
            amount, note = report.cost_parts(res)
        else:
            amount, note = report.fmt_usd(tot["usd"]), "MOCK" if config.MOCK else "measured"
        m = st.columns(4)
        m[0].metric("Risk score", res["result"]["score"])
        m[1].metric("AI calls", tot["ai_calls"])
        m[2].metric(f"Cost ({note})", amount)
        m[3].metric("Steps skipped", tot["skipped"])

        st.subheader("Area hazards (official maps)")
        st.dataframe(pd.DataFrame([{
            "group": GROUP_TITLES[g], "level": LEVEL_NAMES[h["level"]],
            "sources": ", ".join(h["sources"]) or "-",
            "score": res["result"]["groups"][g]["score"]} for g, h in res["hazards"].items()]),
            hide_index=True, width="stretch")
        with st.expander("Raw map attributes (for tuning hazards.py)"):
            st.json({g: h["raw"] for g, h in res["hazards"].items()})

        if res.get("kind") == "video":
            st.subheader("Site findings (from video)")
            if res["objects"]:
                st.dataframe(pd.DataFrame([{
                    "frame": f"#{o['f']}", "object": objects.CATALOGUE[o["kind"]]["name"],
                    "hazard": objects.CATALOGUE[o["kind"]]["group"], "importance": o["label"],
                    "conf": o["conf"], "found by": o["by"]} for o in res["objects"]]),
                    hide_index=True, width="stretch")
            else:
                st.caption("Nothing relevant found in the key frames.")
        if res.get("answers"):
            st.subheader("Photo findings")
            st.dataframe(pd.DataFrame([{
                "question": checklist.BY_ID[i]["q"],
                "answer": {"y": "yes", "n": "no", "u": "unclear"}[a],
                "answered by": res["answered_by"].get(i, "")} for i, a in res["answers"].items()]),
                hide_index=True, width="stretch")
            st.caption(f"{len(res['questions'])} of {len(checklist.QUESTIONS)} questions asked - "
                       "the others are irrelevant for this address.")

        with st.expander("Cost ledger"):
            st.dataframe(pd.DataFrame(res["ledger"].rows()), hide_index=True, width="stretch")

        if res.get("baseline"):
            b = res["baseline"]
            same = sum(res["answers"].get(i) == a for i, a in b["answers"].items()
                       if i in res["answers"])
            st.subheader("Cascade vs naive baseline")
            c = st.columns(3)
            c[0].metric("Cascade cost", report.fmt_usd(tot["usd"]))
            c[1].metric("Naive cost", report.fmt_usd(b["usd"]))
            ratio = (b["usd"] / tot["usd"]) if tot["usd"] else None
            c[2].metric("Naive / cascade", f"{ratio:.1f}x" if ratio else "n/a")
            st.caption(f"Answers agree on {same} of {len(res['answers'])} shared questions."
                       + (" (MOCK answers, not meaningful)" if b["mock"] else ""))

    if ss.cases:
        st.subheader("Portfolio (this session)")
        df = pd.DataFrame([{
            "address": c["place"]["label"] if c.get("place") else c["address"],
            "water": LEVEL_NAMES[c["hazards"]["water"]["level"]],
            "hail": LEVEL_NAMES[c["hazards"]["hail"]["level"]],
            "score": c["result"]["score"], "action": c["result"]["action"],
            "usd": round(c["ledger"].totals()["usd"], 6),
            "lat": c["place"]["lat"] if c.get("place") else None,
            "lon": c["place"]["lon"] if c.get("place") else None} for c in ss.cases])
        st.dataframe(df.drop(columns=["lat", "lon"]), hide_index=True, width="stretch")
        pts = df.dropna(subset=["lat", "lon"])
        if not pts.empty:
            st.map(pts, latitude="lat", longitude="lon")
        st.download_button("Download portfolio CSV", df.to_csv(index=False), "portfolio.csv",
                           on_click="ignore")

# ---------------- explanation ----------------
with tab_h:
    st.markdown("""
**The idea:** a hazard map knows the *area*, a short video shows the *site*.
Together they tell the customer what to do before a storm, and tell AXA which sites need a risk engineer.

**Why it is cheap (the cascade):**
1. Address and hazard maps come from free federal APIs (cached).
2. Free code turns ~1,800 video frames into about 6 key frames: it drops dark, blurry and repeated views.
3. A free local detector (YOLO11n, 5 MB) finds vehicles and people. People are blurred before upload.
4. The map picks what the AI looks for: no flood zone means no flood objects; no elevated hazard means **no AI call at all**.
5. One call to a small model with all key frames at 512 px, answering in compact JSON.
6. Only frames the small model was unsure about go to the strong model, at 768 px.
7. Importance and advice are fixed rules: the same input always gives the same, explainable result.
8. Every answer is cached, so a repeated demo costs nothing.
""")
    st.latex(r"\text{importance} = \text{weight}_{\text{object}} \times \text{level}_{\text{hazard at address}}"
             r"\qquad \text{score}_g = \text{level}_g \times (1 + \text{weak points}_g)")
    st.latex(r"C = c_0 + \sum_i p_i\, c_i \quad (p_i = \text{share of cases that reach step } i)")
    st.markdown("""
Importance >= 4 high, 2-3 medium, 1 low. Site score >= 4: propose an on-site prevention check;
>= 1: send prevention tips. Weights (3 = typical large claim, 2 = moderate) are our assumption for AXA to tune.

**Limits:** the app only judges what the camera sees; it cannot judge roof strength or what is behind walls.
Low-confidence findings are shown but not counted. This is prevention and triage, not pricing.
""")
    st.caption("Data: BAFU (Aquaprotect, surface runoff map), MeteoSwiss (hail hazard), "
               "swisstopo / geo.admin.ch. Prototype built for the AXA challenge at LauzHack 2026, "
               "not an underwriting decision.")
