"""API endpoints, job handling and cache headers. The pipeline is replaced by a fake."""
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import server
from sitecheck import settings


def fake_run(video_path, address, progress=lambda t: None, **options):
    progress("Looking")
    img = np.full((180, 320, 3), 120, np.uint8)
    finding = {"id": 0, "frame": 0, "t": 1.0, "kind": "vehicle", "name": "Vehicle parked outside",
               "box": [0.1, 0.2, 0.5, 0.6], "confidence": 0.9, "source": "local detector",
               "label": "high", "uncertain": False, "counted": True, "score": 4}
    result = {"address": {"label": address, "lat": 46.5, "lon": 6.6}, "findings": [finding],
              "options": {k: v for k, v in options.items() if k != "simulate"},
              "simulate": options.get("simulate")}
    result["people"] = [{"frame": 0, "t": 1.0, "box": [0.6, 0.1, 0.8, 0.9], "confidence": 0.8}]
    result["samples"] = [{"index": 0, "t": 0.0, "status": "picked", "reason": ""},
                         {"index": 1, "t": 0.5, "status": "skipped", "reason": "blurry"}]
    thumb = cv2.imencode(".jpg", np.full((90, 160, 3), 90, np.uint8))[1].tobytes()
    return result, {"keyframes": [img], "thumbs": [thumb, thumb]}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(server.pipeline, "run", fake_run)
    with server.LOCK:
        for job in server.JOBS.values():
            job.drop_files()
        server.JOBS.clear()
    out = tmp_path / "out"
    (out / "_next" / "static").mkdir(parents=True)
    (out / "index.html").write_text("<html>customer</html>")
    (out / "demo.html").write_text("<html>details</html>")
    (out / "_next" / "static" / "app.js").write_text("console.log(1)")
    web = next(r for r in server.app.routes if getattr(r, "name", "") == "web")
    monkeypatch.setattr(web.app, "directory", out)
    monkeypatch.setattr(web.app, "all_directories", [out])
    monkeypatch.setattr(web.app, "config_checked", False)
    return TestClient(server.app)


def upload(client, **extra):
    data = {"address": "Route Cantonale 11, 1015 Lausanne", **extra}
    files = {"video": ("walk.mov", b"not really a video", "video/quicktime")}
    r = client.post("/api/analyze", data=data, files=files)
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def wait(client, job_id):
    for _ in range(100):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_info(client):
    body = client.get("/api/info").json()
    assert body["risk_colours"]["high"] == "#C62828"
    assert body["keyframes"] == {"default": 6, "min": 4, "max": 10}
    assert body["models"]["cheap"] == "google/gemini-2.5-flash-lite"


def test_analyze_poll_latest_and_images(client):
    assert client.get("/api/latest").status_code == 404
    job_id = upload(client, keyframes="8", detector="false", sim_hail="2", sim_water="0")
    body = wait(client, job_id)
    assert body["status"] == "done"
    assert body["result"]["options"] == {"keyframes": 8, "detector_on": False}
    assert body["result"]["simulate"] == {"hail": 2, "water": 0}
    assert client.get("/api/latest").json()["id"] == job_id
    for path in ("keyframes/0.jpg", "keyframes/0.jpg?boxes=0", "crops/0.jpg", "thumbs/0.jpg",
                 "filmstrip.jpg"):
        r = client.get(f"/api/jobs/{job_id}/{path}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg", path
    assert client.get(f"/api/jobs/{job_id}/keyframes/5.jpg").status_code == 404
    video = client.get(f"/api/jobs/{job_id}/video")
    assert video.status_code == 200 and video.content == b"not really a video"


def test_forecast_endpoint(client, monkeypatch):
    monkeypatch.setattr(server.weather, "forecast", lambda lat, lon: {"storm": None, "hours": 48})
    job_id = upload(client)
    wait(client, job_id)
    assert client.get(f"/api/jobs/{job_id}/forecast").json() == {"storm": None, "hours": 48}

    def broken(lat, lon):
        raise RuntimeError("down")
    monkeypatch.setattr(server.weather, "forecast", broken)
    assert client.get(f"/api/jobs/{job_id}/forecast").status_code == 503


def test_bad_input_gets_plain_errors(client):
    r = client.post("/api/analyze", data={"address": "x"},
                    files={"video": ("a.mov", b"1", "video/quicktime")})
    assert r.status_code == 422
    r = client.post("/api/analyze", data={"address": "Bern"},
                    files={"video": ("a.txt", b"1", "text/plain")})
    assert r.status_code == 422 and "video" in r.json()["detail"]
    assert client.get("/api/jobs/nope").status_code == 404


def test_failed_job_shows_plain_words(client, monkeypatch):
    from sitecheck import hazard_map

    def no_address(*a, **k):
        raise hazard_map.AddressNotFound("x")
    monkeypatch.setattr(server.pipeline, "run", no_address)
    body = wait(client, upload(client))
    assert body["status"] == "failed" and "could not find this address" in body["error"]


def test_at_most_five_jobs_and_dropped_videos_are_deleted(client):
    first = upload(client)
    wait(client, first)
    folder = server.JOBS[first].video.parent
    assert folder.exists()
    for _ in range(settings.MAX_JOBS):
        wait(client, upload(client))
    assert len(server.JOBS) == settings.MAX_JOBS
    assert first not in server.JOBS and not folder.exists()


def test_pages_are_served_with_no_cache(client):
    for path in ("/", "/demo.html"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert "customer" in client.get("/").text and "details" in client.get("/demo.html").text
    static = client.get("/_next/static/app.js")
    assert "immutable" in static.headers["cache-control"]
    assert client.get("/api/info").headers["cache-control"] == "no-cache"
