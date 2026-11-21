"""Backend for the Site Check website (FastAPI).

Start:  uvicorn server:app --port 8000      then open http://localhost:8000
The website itself is a Next.js app in web/; `npm run build` there writes plain files to
web/out/, which this server hands out. So the demo needs ONE running program, not two.

All the real work is done by the existing frugal package (sitecheck.run); this file only
turns its result into JSON and images for the browser. No database: the last few results
live in memory, and paid AI answers are cached on disk by frugal/cache.py as before.
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from frugal import config, detect, geo, objects, report, sitecheck, video, weather
from frugal.hazards import LEVEL_NAMES

ROOT = Path(__file__).resolve().parent
WEB_OUT = ROOT / "web" / "out"
MAX_JOBS = 5          # results kept in memory; older ones are dropped
CROP_PAD = 0.15       # crops show a little context around each object
# Phones save MP4 and MOV; both use the same container, and Chrome only plays a .mov file
# when it is announced as video/mp4, so both are sent with that type.
VIDEO_TYPE = "video/mp4"
log = logging.getLogger("site-check")

app = FastAPI(title="Frugal Site Check")

# ONE worker on purpose: the local detector and the JSON caches are not made for parallel
# runs, and a live demo only ever needs one check at a time. Others simply wait their turn.
_worker = ThreadPoolExecutor(max_workers=1)
_jobs: "OrderedDict[str, dict]" = OrderedDict()
_lock = threading.Lock()


# ---------------- turning a sitecheck result into plain JSON ----------------
def _plain(x):
    """JSON cannot hold numpy numbers, tuples or sets: convert them, recursively."""
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, set):
        return sorted(_plain(v) for v in x)
    if isinstance(x, np.generic):
        return x.item()
    return x


def _found_by(by: str) -> str:
    # Plain words for the jury instead of model ids.
    if by.startswith("local"):
        return "local detector"
    if by == config.CHEAP_MODEL:
        return "cheap model"
    if by == config.STRONG_MODEL:
        return "strong model"
    return by


def _hazards_json(hz: dict) -> dict:
    return {g: {"level": h["level"], "level_name": LEVEL_NAMES[h["level"]],
                # answered = the map service replied; if not, the UI says "map unavailable".
                "answered": h.get("available", True),
                "in_zone": h["answered"], "sources": h["sources"]}
            for g, h in hz.items()}


def _object_json(o: dict) -> dict:
    return {"id": o["id"], "frame": o["f"], "kind": o["kind"],
            "name": objects.CATALOGUE[o["kind"]]["name"], "label": o["label"],
            "score": o["score"], "conf": o["conf"], "by": _found_by(o["by"]),
            "box": [round(float(v), 4) for v in o["box"]]}


def _best_object(found: list[dict], kind: str) -> int | None:
    """The clearest counted example of a kind: the customer page shows its photo."""
    counted = [o for o in found if o["kind"] == kind and o["label"] in ("high", "medium", "low")]
    return max(counted, key=lambda o: o["conf"])["id"] if counted else None


def _item_json(item: dict, found: list[dict]) -> dict:
    c = objects.CATALOGUE[item["kind"]]
    return {"kind": item["kind"], "name": c["name"], "label": item["label"],
            "score": item["score"], "frames": item["frames"], "now": c["now"],
            "later": c["later"], "why": c["why"], "object_id": _best_object(found, item["kind"])}


def to_json(res: dict) -> dict:
    """Everything both pages need, as plain JSON. Images are separate URLs."""
    r = res["result"]
    return _plain({
        "address": res["address"],
        "place": res.get("place"),
        "hazards": _hazards_json(res["hazards"]),
        "map_ok": all(h.get("available", True) for h in res["hazards"].values()),
        "asked": [{"kind": k, "name": objects.CATALOGUE[k]["name"]} for k in res.get("asked", [])],
        "frames": [{"n": f["n"], "t": round(f["t"], 1)} for f in res["frames"]["picked"]],
        "objects": [_object_json(o) for o in res["objects"]],
        "result": {"action": r["action"], "score": r["score"], "uncertain": r["uncertain"],
                   "items": [_item_json(i, res["objects"]) for i in r["items"]]},
        "frugal": res["frugal"],
        "ledger": res["ledger"].rows(),
        "totals": res["ledger"].totals(),
        "mock": report.is_mock(res),
        "simulated_levels": any("simulated" in s.note for s in res["ledger"].steps),
        "warning": _ai_warning(res),
    })


def _ai_warning(res: dict) -> str | None:
    if res["status"] != "ai_error":
        return None
    if "429" in res.get("error", ""):   # rate limit, after retries and fallback models
        return ("The AI service is very busy right now, so only the free steps are shown "
                "(vehicles). Please try again in a minute.")
    return "The AI step could not be reached, so only the free steps are shown (vehicles)."


def _friendly_error(res: dict) -> str:
    """Short, calm messages for the screen; the technical text goes to the log."""
    if res["status"] == "geo_error":
        return "Could not find that address."
    if "dark" in res.get("error", "") or "blurry" in res.get("error", ""):
        return "The video is too dark or too blurry. Film in daylight and walk slowly."
    return "Could not read this video. Try an MP4 or MOV file straight from a phone."


# ---------------- jobs ----------------
def _images_for(res: dict) -> dict:
    """Keeps only the pictures the pages ask for. The filmstrip is drawn once now, so the
    hundreds of small sampled frames can be dropped from memory."""
    return {"safe": {f["n"]: f["safe"] for f in res["frames"]["picked"]},
            "objects": res["objects"],
            "strip": _png(video.filmstrip(res["frames"]["frames"])),
            "jpg": {}}


def _run_job(job_id: str, address: str, path: str, k: int, use_detector: bool,
             levels: dict | None) -> None:
    job = _jobs[job_id]
    job["args"] = {"address": address, "k": k, "use_detector": use_detector, "levels": levels}
    try:
        res = sitecheck.run(address, video_path=path, levels=levels, k=k,
                            use_detector=use_detector, allow_map_fail=True,
                            progress=lambda step: job.update(stage=step))
        if res["status"] in ("geo_error", "video_error"):
            log.warning("job %s: %s", job_id, res.get("error"))
            job.update(status="error", error=_friendly_error(res))
        else:
            # The video file is kept (on this computer only) so both pages can play it back.
            job.update(status="ok", result=to_json(res), images=_images_for(res), video=path)
    except Exception:  # noqa: BLE001 - a demo must show a message, never a crash
        log.exception("job %s failed", job_id)
        job.update(status="error", error="Something went wrong. Please try again.")
    finally:
        if job.get("video") != path:
            os.unlink(path)


def _remember(job_id: str) -> None:
    with _lock:
        _jobs[job_id] = {"status": "running"}
        # Drop the oldest finished results; a check that is still running is never dropped.
        finished = [j for j, job in _jobs.items() if job["status"] != "running"]
        for old in finished[:max(0, len(_jobs) - MAX_JOBS)]:
            _forget(_jobs.pop(old))


def _forget(job: dict) -> None:
    # A dropped result takes its kept video with it, so old uploads do not fill the disk.
    if job.get("video") and os.path.exists(job["video"]):
        os.unlink(job["video"])


def _job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "This result is no longer available. Please run the check again.")
    return job


def _finished(job_id: str) -> dict:
    job = _job(job_id)
    if job["status"] != "ok":
        raise HTTPException(404, "No pictures for this check.")
    return job["images"]


def _parse_levels(simulate: int, levels: str) -> dict | None:
    if not simulate:
        return None
    try:
        data = json.loads(levels or "{}")
        return {g: min(2, max(0, int(data.get(g, 1)))) for g in ("water", "hail")}
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "Simulated levels must look like {\"water\": 1, \"hail\": 2}.")


def _save_upload(up: UploadFile) -> str:
    # Copy in chunks to a temp file: a 300 MB phone video never sits in memory twice.
    # iPhones name files IMG_1234.MOV, so the suffix is lower-cased for the video reader.
    suffix = "." + (up.filename or "video.mp4").rsplit(".", 1)[-1].lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(up.file, tmp)
    return tmp.name


# ---------------- API ----------------
@app.post("/api/analyze")
def analyze(address: str = Form(...), video_file: UploadFile = File(..., alias="video"),
            k: int = Form(config.KEYFRAMES), use_detector: bool = Form(True),
            simulate: int = Form(0), levels: str = Form("")) -> dict:
    parsed = _parse_levels(simulate, levels)
    path = _save_upload(video_file)
    job_id = uuid.uuid4().hex[:12]
    _remember(job_id)
    _worker.submit(_run_job, job_id, address.strip(), path, min(10, max(3, k)),
                   use_detector and detect.available(), parsed)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = _job(job_id)
    return {k: job[k] for k in ("status", "stage", "error", "result") if k in job}


@app.post("/api/jobs/{job_id}/retry")
def retry(job_id: str) -> dict:
    """Runs the same check again with the video already on this computer (no new upload),
    e.g. after the AI service was busy. The new result takes over the video file."""
    old = _job(job_id)
    if not old.get("video") or not old.get("args"):
        raise HTTPException(404, "This video is no longer here. Please upload it again.")
    path = old.pop("video")             # the old result no longer owns (or deletes) the file
    new_id = uuid.uuid4().hex[:12]
    _remember(new_id)
    a = old["args"]
    _worker.submit(_run_job, new_id, a["address"], path, a["k"], a["use_detector"], a["levels"])
    return {"job_id": new_id}


@app.get("/api/address")
def address_suggestions(q: str = "") -> dict:
    """Up to 6 Swiss addresses matching what the customer typed so far."""
    try:
        return {"suggestions": geo.suggest(q[:120])}
    except geo.GeoError:
        return {"suggestions": []}     # the field still works as plain text


@app.get("/api/latest")
def latest() -> dict:
    """Newest finished check, so a run started on one page also shows on the other."""
    done = [j for j, job in _jobs.items() if job["status"] == "ok"]
    return {"job_id": done[-1] if done else None}


@app.get("/api/info")
def info() -> dict:
    return {"mock": config.MOCK, "provider": config.PROVIDER,
            "cheap_model": config.CHEAP_MODEL, "strong_model": config.STRONG_MODEL,
            "baseline_model": config.NAIVE_MODEL, "colours": sitecheck.COLOURS,
            "keyframes": config.KEYFRAMES, "detector": detect.available()}


@app.get("/api/jobs/{job_id}/frame/{n}.jpg")
def frame_jpg(job_id: str, n: int) -> Response:
    imgs = _finished(job_id)
    if n not in imgs["safe"]:
        raise HTTPException(404, "No such key frame.")
    if n not in imgs["jpg"]:   # draw each frame once; pages ask for it repeatedly
        frame = {"n": n, "safe": imgs["safe"][n]}
        imgs["jpg"][n] = _jpeg(sitecheck.annotate(frame, imgs["objects"]))
    return Response(imgs["jpg"][n], media_type="image/jpeg")


@app.get("/api/jobs/{job_id}/crop/{object_id}.jpg")
def crop_jpg(job_id: str, object_id: int) -> Response:
    imgs = _finished(job_id)
    o = next((o for o in imgs["objects"] if o["id"] == object_id), None)
    if o is None:
        raise HTTPException(404, "No such object.")
    return Response(_jpeg(_crop(imgs["safe"][o["f"]], o["box"])), media_type="image/jpeg")


@app.get("/api/jobs/{job_id}/strip.png")
def strip_png(job_id: str) -> Response:
    return Response(_finished(job_id)["strip"], media_type="image/png")


@app.get("/api/jobs/{job_id}/video")
def video_file(job_id: str) -> FileResponse:
    """The uploaded video, for playback on both pages (just for show; no AI involved).
    FileResponse answers range requests, so the player can jump to any second."""
    job = _job(job_id)
    if not job.get("video"):
        raise HTTPException(404, "No video for this check.")
    return FileResponse(job["video"], media_type=VIDEO_TYPE)


@app.get("/api/jobs/{job_id}/forecast")
def forecast(job_id: str) -> dict:
    """Next storm at this site (live weather forecast, refreshed every 10 minutes).
    Never an error page: if the weather service is down, the site says so calmly."""
    job = _job(job_id)
    if job["status"] != "ok":
        raise HTTPException(404, "No result for this check yet.")
    place = job["result"].get("place")
    try:
        if not place:   # simulated hazard levels skip the map, so look the address up now
            place = geo.geocode(job["result"]["address"])
        return {"ok": True, **weather.forecast(place["lat"], place["lon"])}
    except (geo.GeoError, requests.RequestException, KeyError, ValueError) as exc:
        log.warning("forecast for job %s failed: %s", job_id, exc)
        return {"ok": False}


# ---------------- image helpers ----------------
def _crop(img, box):
    """Cuts one object out of the privacy-blurred frame, with some padding around it."""
    w, h = img.size
    x0, y0, x1, y1 = box
    px, py = (x1 - x0) * CROP_PAD, (y1 - y0) * CROP_PAD
    return img.crop((int(max(0, x0 - px) * w), int(max(0, y0 - py) * h),
                     int(min(1, x1 + px) * w), int(min(1, y1 + py) * h)))


def _jpeg(img) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------- the website (built Next.js files) ----------------
@app.middleware("http")
async def fresh_pages(request, call_next):
    """Pages are re-checked on every visit; only the code files under /_next/static (whose names
    change with every build) may be cached. Without this, a browser kept an old copy of
    demo.html after a rebuild, asked for code files that no longer existed, and showed
    "Application error: a client-side exception has occurred"."""
    response = await call_next(request)
    if not request.url.path.startswith("/_next/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


if WEB_OUT.exists():
    @app.get("/demo")
    def demo_page() -> FileResponse:
        return FileResponse(WEB_OUT / "demo.html")   # same page with or without ".html"

    @app.get("/favicon.ico")
    def favicon() -> FileResponse:
        # Browsers still ask for this old name; answer with the tab icon (the AXA logo).
        return FileResponse(WEB_OUT / "icon.png", media_type="image/png")

    # Mounted last, so the /api routes above always win.
    app.mount("/", StaticFiles(directory=WEB_OUT, html=True), name="web")
else:
    @app.get("/")
    def not_built() -> HTMLResponse:
        return HTMLResponse("<h1>Website not built yet</h1><p>Run once: <code>cd web && "
                            "npm install && npm run build</code>, then restart the server. "
                            "The API already works at <code>/api/info</code>.</p>")
