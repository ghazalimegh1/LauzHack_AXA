"""Frugal Site Check: one server on port 8000 for the API and both web pages.

Start:  .venv/bin/python -m uvicorn server:app --port 8000
"""
from __future__ import annotations

import logging
import queue
import shutil
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from sitecheck import forecast as weather
from sitecheck import hazard_map, pipeline, render, settings

log = logging.getLogger("sitecheck")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Frugal Site Check", docs_url=None, redoc_url=None)

VIDEO_TYPES = {".mov": "video/mp4", ".mp4": "video/mp4", ".m4v": "video/mp4",
               ".webm": "video/webm"}   # QuickTime files play in Chrome when sent as MP4
MAX_UPLOAD_BYTES = 1_500_000_000


# ---------------- jobs: at most 5 in memory, one runs at a time ----------------
class Job:
    def __init__(self, address: str, options: dict, video: Path, filename: str):
        self.id = uuid.uuid4().hex[:12]
        self.address, self.options = address, options
        self.video, self.filename = video, filename
        self.status, self.stage, self.error = "queued", "Waiting for the previous check to finish", None
        self.created, self.finished = time.time(), None
        self.result, self.images = None, None

    def public(self, with_result: bool = True) -> dict:
        out = {"id": self.id, "status": self.status, "stage": self.stage, "error": self.error,
               "created": self.created, "finished": self.finished, "filename": self.filename}
        if with_result and self.result is not None:
            out["result"] = self.result
        return out

    def drop_files(self) -> None:
        shutil.rmtree(self.video.parent, ignore_errors=True)


JOBS: "OrderedDict[str, Job]" = OrderedDict()
LOCK = threading.Lock()
WORK: "queue.Queue[Job]" = queue.Queue()


def _add(job: Job) -> None:
    with LOCK:
        JOBS[job.id] = job
        while len(JOBS) > settings.MAX_JOBS:
            old = next((j for j in JOBS.values() if j.status in ("done", "failed")), None)
            if old is None:
                break
            JOBS.pop(old.id)
            old.drop_files()          # the uploaded video goes with the job


def _plain_error(exc: Exception) -> str:
    if isinstance(exc, hazard_map.AddressNotFound):
        return "We could not find this address. Please check the spelling and add the town."
    if isinstance(exc, hazard_map.MapError):
        return "The Swiss address service is not answering right now. Please try again in a minute."
    if isinstance(exc, ValueError):
        return "We could not read this video. Please try another file (MP4 or MOV)."
    return "Something went wrong on our side. Please try again."


def _worker() -> None:
    while True:
        job = WORK.get()
        if job.id not in JOBS:
            continue
        job.status = "running"

        def progress(text: str, job=job) -> None:
            job.stage = text

        try:
            job.result, job.images = pipeline.run(str(job.video), job.address, progress=progress,
                                                  **job.options)
            job.result["filename"] = job.filename
            job.status, job.stage = "done", "Done"
        except Exception as exc:  # noqa: BLE001 - every failure becomes a plain message
            log.exception("check %s failed", job.id)
            job.status, job.error, job.stage = "failed", _plain_error(exc), "Stopped"
        job.finished = time.time()


threading.Thread(target=_worker, daemon=True, name="sitecheck-worker").start()


def _job(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "This check is no longer available. Please run it again.")
    return job


def _done(job_id: str) -> Job:
    job = _job(job_id)
    if job.status != "done" or not job.images:
        raise HTTPException(409, "This check has not finished yet.")
    return job


def _jpeg(data: bytes) -> Response:
    return Response(data, media_type="image/jpeg")


# ---------------- API ----------------
@app.get("/api/info")
def info():
    return {
        "risk_colours": settings.RISK_COLOURS,
        "keyframes": {"default": settings.KEYFRAMES_DEFAULT, "min": settings.KEYFRAMES_MIN,
                      "max": settings.KEYFRAMES_MAX},
        "models": {"cheap": settings.CHEAP_MODEL, "strong": settings.STRONG_MODEL,
                   "baseline": settings.BASELINE_MODEL, "fallbacks": settings.FALLBACKS},
        "ai_enabled": settings.ai_enabled(),
        "unsure_below": settings.UNSURE_BELOW,
        "max_jobs": settings.MAX_JOBS,
    }


@app.get("/api/suggest")
def suggest(q: str = ""):
    try:
        return {"suggestions": hazard_map.suggest(q)}
    except hazard_map.MapError:
        return {"suggestions": []}


@app.post("/api/analyze")
async def analyze(
    address: str = Form(...),
    video: UploadFile = File(...),
    keyframes: int = Form(settings.KEYFRAMES_DEFAULT),
    detector: bool = Form(True),
    sim_hail: Optional[int] = Form(None),
    sim_water: Optional[int] = Form(None),
):
    address = address.strip()
    if len(address) < 3:
        raise HTTPException(422, "Please enter the address of your site.")
    name = Path(video.filename or "video.mp4").name
    ext = Path(name).suffix.lower() or ".mp4"
    if ext not in VIDEO_TYPES:
        raise HTTPException(422, "Please choose a video file (MP4 or MOV).")
    folder = Path(tempfile.mkdtemp(prefix="sitecheck-"))
    target = folder / f"upload{ext}"
    size = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await video.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "This video is too large. Please keep it under 1.5 GB.")
                out.write(chunk)
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    if size == 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(422, "The video file is empty.")
    simulate = None
    if sim_hail is not None or sim_water is not None:
        simulate = {"hail": max(0, min(2, sim_hail or 0)), "water": max(0, min(2, sim_water or 0))}
    options = {"keyframes": keyframes, "detector_on": bool(detector), "simulate": simulate}
    job = Job(address, options, target, name)
    _add(job)
    WORK.put(job)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return _job(job_id).public()


@app.get("/api/latest")
def latest():
    with LOCK:
        done = [j for j in JOBS.values() if j.status == "done"]
    if not done:
        raise HTTPException(404, "No finished check yet.")
    return max(done, key=lambda j: j.finished or 0).public()


@app.get("/api/jobs/{job_id}/keyframes/{n}.jpg")
def keyframe(job_id: str, n: int, boxes: int = 1):
    job = _done(job_id)
    imgs = job.images["keyframes"]
    if not 0 <= n < len(imgs):
        raise HTTPException(404, "No such frame.")
    img = imgs[n]
    if boxes:
        img = render.with_boxes(img, [f for f in job.result["findings"] if f["frame"] == n],
                                [p for p in job.result.get("people", []) if p["frame"] == n])
    return _jpeg(render.encode(img))


@app.get("/api/jobs/{job_id}/crops/{finding_id}.jpg")
def crop(job_id: str, finding_id: int):
    job = _done(job_id)
    found = next((f for f in job.result["findings"] if f["id"] == finding_id), None)
    if found is None:
        raise HTTPException(404, "No such object.")
    return _jpeg(render.encode(render.crop(job.images["keyframes"][found["frame"]], found["box"]), 88))


@app.get("/api/jobs/{job_id}/thumbs/{i}.jpg")
def thumb(job_id: str, i: int):
    job = _done(job_id)
    thumbs = job.images["thumbs"]
    if not 0 <= i < len(thumbs):
        raise HTTPException(404, "No such frame.")
    return _jpeg(thumbs[i])


@app.get("/api/jobs/{job_id}/filmstrip.jpg")
def filmstrip(job_id: str):
    job = _done(job_id)
    if "filmstrip" not in job.images:     # drawn once, then kept with the job
        job.images["filmstrip"] = render.filmstrip(job.result["samples"], job.images["thumbs"])
    return _jpeg(job.images["filmstrip"])


@app.get("/api/jobs/{job_id}/video")
def play(job_id: str):
    job = _job(job_id)
    if not job.video.exists():
        raise HTTPException(404, "The video is no longer stored.")
    return FileResponse(job.video, media_type=VIDEO_TYPES.get(job.video.suffix.lower(), "video/mp4"))


@app.get("/api/jobs/{job_id}/forecast")
def job_forecast(job_id: str):
    job = _done(job_id)
    place = job.result["address"]
    try:
        return weather.forecast(place["lat"], place["lon"])
    except Exception:  # noqa: BLE001
        log.warning("forecast unavailable for job %s", job_id)
        return JSONResponse({"detail": "The weather forecast is not available right now."}, 503)


# ---------------- pages ----------------
@app.middleware("http")
async def no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/_next/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        # Pages are always re-checked, so a rebuild never leaves the browser holding an old
        # page that points to scripts that no longer exist ("Application error").
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=settings.WEB_OUT, html=True, check_dir=False), name="web")
