"""Offline tests (no internet, no API key). Run:  python -m pytest -q
Each test traces one small example by hand, so a broken piece shows up fast."""
import io
import os
import sys
from pathlib import Path

os.environ["FRUGAL_MOCK"] = "1"
os.environ["FRUGAL_NO_CACHE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from frugal import checklist, geo, hazards, photo, pipeline, score, vision  # noqa: E402


def _jpeg(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _house():
    rng = np.random.default_rng(0)  # random texture = sharp, mid-brightness photo
    return _jpeg(Image.fromarray(rng.integers(40, 220, (800, 1000, 3), dtype=np.uint8)))


def test_lv95_bern_reference_point():
    # swisstopo's worked example: 46°02'38.87" N, 8°43'49.79" E -> E 2'700'000 / N 1'100'000.
    e, n = geo.wgs84_to_lv95(46 + 2 / 60 + 38.87 / 3600, 8 + 43 / 60 + 49.79 / 3600)
    assert abs(e - 2700000) < 2 and abs(n - 1100000) < 2


def test_map_picks_questions():
    hz = hazards.from_levels({"water": 0, "hail": 2})
    assert {q["group"] for q in checklist.select(hz)} == {"hail"}
    assert checklist.select(hazards.from_levels({"water": 0, "hail": 0})) == []


def test_parse_messy_reply():
    answers, conf = vision.parse('Sure! ```json\n{"blinds":"Yes","car_outside":"x","conf":0.9}```',
                                 ["blinds", "car_outside", "glass_roof"])
    assert answers == {"blinds": "y", "car_outside": "u", "glass_roof": "u"} and conf == 0.9


def test_score_and_action():
    hz = hazards.from_levels({"water": 2, "hail": 0})
    r = score.evaluate(hz, {"light_well": "y", "door_low": "y", "ramp_down": "n"})
    assert r["groups"]["water"]["score"] == 2 * (1 + 2)
    assert r["action"] == "Propose an on-site prevention check"
    assert len(r["tips"]) == 2


def test_dark_photo_is_rejected_for_free():
    dark = _jpeg(Image.new("RGB", (800, 600), (10, 10, 10)))
    res = pipeline.run("x", dark, levels={"water": 2, "hail": 2})
    assert res["status"] == "retake"
    assert res["ledger"].totals()["ai_calls"] == 0


def test_low_hazard_means_no_ai_at_all():
    res = pipeline.run("x", _house(), levels={"water": 0, "hail": 0})
    assert res["ledger"].totals()["ai_calls"] == 0
    assert res["result"]["action"] == "No action needed"


def test_full_cascade_runs_in_mock_mode():
    res = pipeline.run("x", _house(), levels={"water": 2, "hail": 1}, baseline=True)
    assert res["status"] == "ok"
    assert set(res["answers"]) == {q["id"] for q in checklist.QUESTIONS}
    assert "baseline" in res
    assert photo.problems(photo.load(_house())) == []


# ---------------- site video ----------------
def _walk_video(tmp_path):
    # 4 s of a moving random texture, with one blurred and one dark second.
    import cv2
    rng = np.random.default_rng(1)
    base = rng.integers(40, 220, (300, 1200, 3), dtype=np.uint8)
    path = str(tmp_path / "walk.mp4")
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for i in range(40):
        frame = cv2.resize(base[:, i * 20:i * 20 + 400], (320, 240))
        if 10 <= i < 20:
            frame = cv2.GaussianBlur(frame, (21, 21), 0)
        if 30 <= i < 35:
            frame = (frame * 0.05).astype(np.uint8)
        out.write(frame)
    out.release()
    return open(path, "rb").read()


def test_keyframes_skip_blur_and_dark(tmp_path):
    from frugal import video
    info = video.keyframes(_walk_video(tmp_path), k=4)
    assert 1 <= len(info["picked"]) <= 4
    assert all(1.0 > f["t"] or f["t"] >= 2.0 for f in info["picked"])      # not in blur
    assert any(f["reason"] == "dark" for f in info["frames"])
    assert [f["n"] for f in info["picked"]] == list(range(1, len(info["picked"]) + 1))


def test_parse_find_drops_bad_entries():
    text = ('```json {"o":[{"f":0,"t":"glass_roof","b":[100,200,300,400],"c":0.9},'
            '{"f":7,"t":"glass_roof","b":[1,2,3,4]},{"f":1,"t":"unicorn","b":[1,2,3,4]},'
            '{"f":1,"t":"ramp_down","b":"oops"}],"u":[1]} ```')
    objs, unclear = vision.parse_find(text, 2, ["glass_roof", "ramp_down"])
    assert len(objs) == 1 and objs[0]["box"] == (0.2, 0.1, 0.4, 0.3) and unclear == [1]


def test_importance_follows_the_map():
    from frugal import objects
    hz = hazards.from_levels({"water": 0, "hail": 2})
    assert objects.importance("vehicle", hz) == (8, "high")
    # Vehicles count as high risk already at a medium hail level, and not at all without hail.
    assert objects.importance("vehicle", hazards.from_levels({"water": 0, "hail": 1})) == (4, "high")
    assert objects.importance("vehicle", hazards.from_levels({"water": 2, "hail": 0}))[1] == "not relevant here"
    assert objects.importance("basement_opening", hz) == (0, "not relevant here")
    assert "basement_opening" not in objects.to_ask(hz)
    assert objects.to_ask(hazards.from_levels({"water": 0, "hail": 0})) == []


def test_no_hazard_means_no_ai_for_video(tmp_path):
    from frugal import sitecheck
    res = sitecheck.run("x", _walk_video(tmp_path), levels={"water": 0, "hail": 0},
                        use_detector=False)
    assert res["status"] == "ok" and res["ledger"].totals()["ai_calls"] == 0
    assert res["result"]["action"] == "No action needed"


# ---------------- real reply formats (Agent 1) ----------------
def test_parse_find_real_reply_formats():
    k = ["glass_roof", "vehicle"]
    want = (0.2, 0.1, 0.4, 0.3)
    # Gemini: ymin-first 0-1000 in a code fence
    objs, _ = vision.parse_find('```json\n{"o":[{"f":0,"t":"vehicle","b":[100,200,300,400],"c":0.9}]}\n```', 1, k, "yx")
    assert objs[0]["box"] == want
    # Claude asked for xmin-first, with prose before the JSON
    objs, _ = vision.parse_find('The bus qualifies.\n{"o":[{"f":0,"t":"vehicle","b":[200,100,400,300]}],"u":[]}', 1, k, "xy")
    assert objs[0]["box"] == want and objs[0]["conf"] == 0.5
    # fractions, swapped corners, dict boxes and renamed keys
    assert vision.parse_find('{"o":[{"f":0,"t":"vehicle","b":[0.1,0.2,0.3,0.4]}]}', 1, k)[0][0]["box"] == want
    assert vision.parse_find('{"o":[{"f":0,"t":"vehicle","b":[300,400,100,200]}]}', 1, k)[0][0]["box"] == want
    objs, unclear = vision.parse_find('{"objects":[{"frame":0,"type":"vehicle","box":{"xmin":200,'
                                      '"ymin":100,"xmax":400,"ymax":300}}],"unclear":["0"]}', 1, k)
    assert objs[0]["box"] == want and unclear == [0]
    # pixels (only detectable above 1000) use the image size
    objs, _ = vision.parse_find('{"o":[{"f":0,"t":"vehicle","b":[540,960,1080,1920]}]}', 1, k, "yx",
                                sizes=[(1920, 1080)])
    assert objs[0]["box"] == (0.5, 0.5, 1.0, 1.0)


def test_parse_find_salvages_cut_off_reply():
    text = ('{"o":[{"f":0,"t":"vehicle","b":[100,200,300,400],"c":0.9},'
            '{"f":0,"t":"glass_roof","b":[1,2,3,4],"c":0.8},{"f":0,"t":"glass_ro')
    objs, _ = vision.parse_find(text, 1, ["vehicle", "glass_roof"])
    assert [o["kind"] for o in objs] == ["vehicle", "glass_roof"]
    assert vision.parse_find('[{"box_2d":[100,200,300,400],"label":"vehicle","f":0}]', 1,
                             ["vehicle"])[0][0]["kind"] == "vehicle"
    assert vision.parse_find("sorry, I cannot help", 1, ["vehicle"]) == ([], [])


def test_box_order_and_reasoning_per_model():
    from frugal import config
    # Defaults are checked directly, so the test does not depend on which key is in .env.
    assert config._DEFAULTS["openrouter"] == ("google/gemini-2.5-flash-lite", "google/gemini-2.5-flash")
    # The comparison model must cost more than our cheap model, or the cost bars mean nothing.
    assert config.PRICES["google/gemini-2.5-pro"][0] > config.PRICES["google/gemini-2.5-flash-lite"][0]
    assert config.box_order("qwen/qwen3-vl-8b-instruct") == "xy"
    assert config.box_order("google/gemini-2.5-flash-lite") == "yx"
    assert config.box_order("anthropic/claude-haiku-5.5") == "xy"
    assert config.reasoning("google/gemini-2.5-pro") == {"max_tokens": 128}
    assert config.reasoning("anthropic/claude-haiku-5.5") == {"enabled": False}
    assert "[xmin, ymin, xmax, ymax]" in vision._find_prompt(1, ["vehicle"], "xy")


def test_wms_text_answer_becomes_levels(monkeypatch):
    text = ("GetFeatureInfo results:\n\n"
            "Layer 'ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre'\n  Feature 0: \n"
            "    ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre.value_0.name = '4'\n\n"
            "Layer 'ch.bafu.aquaprotect_500'\n  Feature 1537: \n")
    rows = hazards.parse_wms(text)
    assert rows[0]["attributes"] == {"feature": "0", "value_0": "4"}
    monkeypatch.setattr(hazards, "_wms_text", lambda e, n, ids: text)
    hz = hazards.from_map(0, 0)
    assert hz["hail"]["level"] == 2 and hz["water"]["level"] == 1
    assert hazards.parse_wms("GetFeatureInfo results:\n\n  Search returned no results.\n") == []

# ---------------- HTML report (Agent 2) ----------------
def test_report_is_self_contained_and_honest(tmp_path):
    from frugal import report, sitecheck
    res = sitecheck.run("x", _walk_video(tmp_path), levels={"water": 1, "hail": 2},
                        use_detector=False)
    page = report.build_html(res, storm=True)
    assert page.startswith("<!doctype html>") and "</html>" in page
    assert page.count("data:image/jpeg;base64,") == len(res["frames"]["picked"])
    assert "http://" not in page and "https://" not in page    # no external files needed
    assert "MOCK mode" in page and "simulated" in page          # fake answers are labelled
    assert "not an underwriting decision" in page.lower()
    assert len(page) < 1_000_000                                 # small enough to e-mail
    s = report.summary(res)
    assert s["keyframes"] == len(res["frames"]["picked"])
    assert s["cost"].startswith("~$") and "estimate" in s["cost"]
    assert report.fmt_usd(0) == "$0" and report.fmt_usd(0.000123) == "$0.00012"
    assert [report.action_level(x) for x in (0, 1, 4)] == [0, 1, 2]


# ---------------- video from a file path (main agent) ----------------
def test_site_check_reads_from_a_path(tmp_path):
    # The app copies uploads to a temp file and passes its path, so a 300 MB
    # phone video is never held in memory twice. An uppercase .MOV name must work.
    from frugal import sitecheck
    path = tmp_path / "IMG_0001.MOV"
    path.write_bytes(_walk_video(tmp_path))
    res = sitecheck.run("x", video_path=str(path), levels={"water": 0, "hail": 0},
                        use_detector=False)
    assert res["status"] == "ok" and res["frames"]["picked"]
    assert res["ledger"].totals()["ai_calls"] == 0


def test_night_frames_are_brightened_and_smear_is_caught():
    from frugal import photo
    rng = np.random.default_rng(2)
    tex = rng.integers(0, 255, (240, 320)).astype(np.uint8)
    dark = Image.fromarray((tex * 0.15).astype(np.uint8)).convert("RGB")
    mean = photo.measure(dark)[0]
    assert photo.measure(photo.brighten(dark, mean))[0] > 2 * mean        # lifted
    bright = Image.fromarray(tex).convert("RGB")
    assert photo.brighten(bright, photo.measure(bright)[0]) is bright      # left alone
    # Walking smear: averaging along one direction kills that direction's edges.
    import cv2
    smeared = Image.fromarray(cv2.blur(tex, (25, 1))).convert("RGB")
    assert photo.walk_sharpness(smeared) < 0.3 * photo.walk_sharpness(bright)


def test_keyframes_prefer_frames_with_vehicles():
    # Four equally good views in one part; the detector saw a vehicle only in the third.
    from frugal import video
    rng = np.random.default_rng(3)
    tex = rng.integers(40, 220, (270, 2000, 3), dtype=np.uint8)
    frames = [{"t": i * 0.5, "thumb": Image.fromarray(tex[:, i * 400:i * 400 + 480])}
              for i in range(4)]
    car = frames[2]["thumb"]
    video._choose(frames, 1, spot=lambda thumb: 0.9 if thumb is car else 0.0)
    assert [f["t"] for f in frames if f["picked"]] == [1.0]
    video._choose(frames, 1)                       # without the detector: sharpness decides
    assert sum(f["picked"] for f in frames) == 1
