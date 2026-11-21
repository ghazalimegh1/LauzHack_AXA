"""Website API tests, offline: MOCK answers, no API key, no internet. Run: python -m pytest -q
One full check is uploaded once and reused by the tests below, because it takes a few seconds."""
import io
import os
import sys
import time
from pathlib import Path

os.environ["FRUGAL_MOCK"] = "1"        # never call a paid model from a test
os.environ["FRUGAL_NO_CACHE"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)
LEVELS = '{"water": 2, "hail": 2}'      # simulated: every object type is asked, no map needed


def _video_bytes(tmp_path) -> bytes:
    """eval/test_walk.mp4 if it exists (tools/make_test_video.py), else a tiny made-up walk."""
    sample = ROOT / "eval" / "test_walk.mp4"
    if sample.exists():
        return sample.read_bytes()
    import cv2
    rng = np.random.default_rng(1)
    base = rng.integers(40, 220, (300, 1200, 3), dtype=np.uint8)
    path = str(tmp_path / "walk.mp4")
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for i in range(40):
        out.write(cv2.resize(base[:, i * 20:i * 20 + 400], (320, 240)))
    out.release()
    return open(path, "rb").read()


def _wait(job_id: str) -> dict:
    for _ in range(300):                 # up to 60 s; usually 1-3 s
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.2)
    raise AssertionError("job did not finish")


@pytest.fixture(scope="module")
def done(tmp_path_factory):
    files = {"video": ("IMG_0001.MOV", _video_bytes(tmp_path_factory.mktemp("v")), "video/quicktime")}
    data = {"address": "Test site", "simulate": "1", "levels": LEVELS, "use_detector": "0", "k": "4"}
    r = client.post("/api/analyze", data=data, files=files)
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    body = _wait(job_id)
    assert body["status"] == "ok", body
    return job_id, body["result"]


def test_result_has_what_both_pages_need(done):
    _, res = done
    for key in ("hazards", "map_ok", "asked", "frames", "objects", "result", "frugal",
                "ledger", "totals", "mock"):
        assert key in res
    assert res["mock"] is True and res["simulated_levels"] is True
    assert res["hazards"]["hail"] == {"level": 2, "level_name": "high", "answered": True,
                                      "in_zone": True, "sources": ["manual / test value"]}
    assert 1 <= len(res["frames"]) <= 4
    assert res["objects"], "mock mode should find something with all hazards high"
    o = res["objects"][0]
    assert set(o) == {"id", "frame", "kind", "name", "label", "score", "conf", "by", "box"}
    item = res["result"]["items"][0]
    assert item["now"] and item["later"] and item["why"] and item["name"]
    fr = res["frugal"]
    assert fr["naive_usd"] > fr["same_frames_strong_usd"] > fr["ours_usd_est"] > 0


def test_frame_crop_and_strip_are_images(done):
    job_id, res = done
    n = res["frames"][0]["n"]
    oid = res["result"]["items"][0]["object_id"]
    for url, fmt in ((f"/api/jobs/{job_id}/frame/{n}.jpg", "JPEG"),
                     (f"/api/jobs/{job_id}/crop/{oid}.jpg", "JPEG"),
                     (f"/api/jobs/{job_id}/strip.png", "PNG")):
        r = client.get(url)
        assert r.status_code == 200, url
        assert Image.open(io.BytesIO(r.content)).format == fmt


def test_latest_points_to_the_finished_job(done):
    job_id, _ = done
    assert client.get("/api/latest").json() == {"job_id": job_id}


def test_unknown_job_and_frame_give_404(done):
    job_id, _ = done
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/frame/99.jpg").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/crop/9999.jpg").status_code == 404


def test_bad_video_gives_a_friendly_error():
    files = {"video": ("broken.mp4", b"not a video", "video/mp4")}
    r = client.post("/api/analyze", data={"address": "x", "simulate": "1", "levels": LEVELS},
                    files=files)
    body = _wait(r.json()["job_id"])
    assert body["status"] == "error" and "video" in body["error"].lower()


def test_info_says_mock_and_shares_colours():
    info = client.get("/api/info").json()
    assert info["mock"] is True and info["colours"]["high"] == "#D70015"


# ---------------- core changes behind the website ----------------
def test_map_that_does_not_answer_is_unavailable_not_low(monkeypatch, tmp_path):
    from frugal import geo, hazards, sitecheck

    def down(*args):
        raise geo.GeoError("map service down")
    monkeypatch.setattr(geo, "geocode", lambda a: {"label": a, "lat": 46.5, "lon": 6.6,
                                                   "e": 2538000, "n": 1152000})
    monkeypatch.setattr(hazards, "_wms_text", down)
    path = tmp_path / "walk.mp4"
    path.write_bytes(_video_bytes(tmp_path))
    # The website carries on and marks the levels as unknown...
    res = sitecheck.run("x", video_path=str(path), use_detector=False, allow_map_fail=True)
    assert res["status"] == "ok"
    assert server.to_json(res)["hazards"]["water"]["answered"] is False
    assert server.to_json(res)["map_ok"] is False
    # ...while the Streamlit app keeps its old behaviour (an error, not "low").
    res = sitecheck.run("x", video_path=str(path), use_detector=False)
    assert res["status"] == "geo_error"


def test_fair_baseline_differs_only_in_model_price():
    from frugal import config, sitecheck
    from frugal.ledger import Ledger
    info = {"duration": 10, "total": 300, "frames": [1] * 20}
    picked = [{"safe": Image.new("RGB", (1280, 720))}] * 6
    fr = sitecheck._frugal(info, picked, ["vehicle"], Ledger())
    price = lambda m, ref: (config.PRICES.get(m) or config.PRICES[ref])[0]  # noqa: E731
    ratio = price(config.NAIVE_MODEL, "claude-sonnet-5-5") / price(config.CHEAP_MODEL, "claude-haiku-5-5")
    assert fr["same_frames_strong_usd"] == pytest.approx(fr["ours_usd_est"] * ratio)
