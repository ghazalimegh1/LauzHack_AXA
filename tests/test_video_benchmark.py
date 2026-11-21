"""Offline tests for phone-video handling and the video benchmark (no internet, no key).
Run:  python -m pytest -q"""
import csv
import importlib.util
import os
import struct
import sys
from pathlib import Path

os.environ["FRUGAL_MOCK"] = "1"
os.environ["FRUGAL_NO_CACHE"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from frugal import config, video  # noqa: E402


def _clip(path: Path, frames: int = 40, fps: int = 10, size=(320, 240)) -> Path:
    """A sharp, moving random texture (so frames are neither dark nor blurry),
    with a red block in the top-left corner to check orientation."""
    rng = np.random.default_rng(2)
    w, h = size
    base = rng.integers(40, 220, (h, w * 3, 3), dtype=np.uint8)
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(frames):
        frame = np.ascontiguousarray(base[:, i * 8:i * 8 + w])
        frame[:40, :60] = (0, 0, 255)
        out.write(frame)
    out.release()
    return path


def _tag_rotation_90(path: Path, height: int) -> None:
    """Writes the same 90-degree display matrix an iPhone writes for a portrait video
    into the MP4 track header, so the file is stored landscape but meant upright."""
    data = bytearray(path.read_bytes())
    i = data.find(b"tkhd")
    offset = i + 4 + (52 if data[i + 4] == 1 else 40)   # version 1 headers have 64-bit times
    data[offset:offset + 36] = struct.pack(">9i", 0, 0x10000, 0, -0x10000, 0, 0,
                                           height << 16, 0, 0x40000000)
    path.write_bytes(data)


# ---------------- phone videos ----------------
def test_uppercase_mov_from_iphone(tmp_path):
    # iPhones name files IMG_1234.MOV; both the bytes path (app) and the file path must work.
    src = _clip(tmp_path / "clip.mov")
    phone = tmp_path / "IMG_0001.MOV"
    src.rename(phone)
    from_bytes = video.keyframes(phone.read_bytes(), k=3, suffix=".MOV")
    from_path = video.keyframes_from_path(str(phone), k=3)
    assert from_bytes["picked"] and from_path["picked"]
    assert video.keyframes(phone.read_bytes(), k=3, suffix="MOV")["picked"]


@pytest.mark.parametrize("backend", ["default", "ffmpeg"])
def test_portrait_rotation_tag_is_applied(tmp_path, monkeypatch, backend):
    # "default" is AVFoundation on a Mac; "ffmpeg" is the fallback used elsewhere.
    if backend == "ffmpeg":
        monkeypatch.setattr(video, "_backends", lambda: [cv2.CAP_FFMPEG])
    path = _clip(tmp_path / "portrait.mp4")
    _tag_rotation_90(path, 240)
    info = video.keyframes_from_path(str(path), k=3)
    img = info["picked"][0]["img"]
    assert img.height > img.width                       # upright: portrait, not landscape
    red = np.asarray(img)[:, :, 0] > 200
    ys, xs = np.nonzero(red & (np.asarray(img)[:, :, 2] < 60))
    assert xs.mean() > img.width / 2 and ys.mean() < img.height / 2   # top-left -> top-right
    strip = video.filmstrip(info["frames"])
    assert strip.width > 0 and strip.height > 0


def test_missing_frame_count_still_bounded(tmp_path, monkeypatch):
    # Some files report 0 frames in the header; sampling must still stop at MAX_SAMPLES
    # and the true length must come from counting.
    real = cv2.VideoCapture

    class NoCount:
        def __init__(self, *args):
            self._cap = real(*args)

        def get(self, prop):
            return 0.0 if prop == cv2.CAP_PROP_FRAME_COUNT else self._cap.get(prop)

        def __getattr__(self, name):
            return getattr(self._cap, name)

    monkeypatch.setattr(video.cv2, "VideoCapture", NoCount)
    monkeypatch.setattr(config, "MAX_SAMPLES", 5)
    info = video.keyframes_from_path(str(_clip(tmp_path / "long.mp4")), k=3)
    assert len(info["frames"]) <= 5
    assert info["total"] == 40 and abs(info["duration"] - 4.0) < 0.2
    assert info["frames"][-1]["t"] >= 2.5                # the end of the walk is still covered


def test_nonsense_fps_falls_back():
    class Cap:
        def get(self, prop):
            return 90000.0                                # a time base, not a frame rate
    assert video._fps(Cap()) == video.FALLBACK_FPS


def test_samples_follow_real_timestamps(tmp_path):
    info = video.keyframes_from_path(str(_clip(tmp_path / "t.mp4", frames=40, fps=10)), k=3)
    times = [round(f["t"], 2) for f in info["frames"]]
    assert times[:3] == [0.0, 0.5, 1.0]                   # 2 per second by timestamp


# ---------------- benchmark ----------------
def _bench():
    spec = importlib.util.spec_from_file_location("benchmark_video",
                                                  ROOT / "tools" / "benchmark_video.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_benchmark_score_math():
    b = _bench()
    labels = {("a", "vehicle"): True, ("a", "glass_roof"): False,
              ("b", "vehicle"): True, ("b", "glass_roof"): False}
    s = b.score({("a", "vehicle"), ("b", "glass_roof")}, labels)
    assert (s["tp"], s["fp"], s["fn"], s["tn"]) == (1, 1, 1, 1)
    assert s["accuracy"] == 0.5 and s["precision"] == 0.5 and s["recall"] == 0.5


def test_benchmark_runs_in_mock_mode(tmp_path):
    b = _bench()
    rng = np.random.default_rng(3)
    frames = tmp_path / "frames"
    frames.mkdir()
    for n in range(8):
        Image.fromarray(rng.integers(40, 220, (270, 480, 3), dtype=np.uint8)).save(
            frames / f"f{n}.jpg")
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "object_type", "present"])
        for n in range(8):
            w.writerow([f"f{n}.jpg", "vehicle", "y" if n % 2 else "n"])
            w.writerow([f"f{n}.jpg", "glass_roof", "n"])
        w.writerow(["f0.jpg", "unicorn", "y"])            # unknown type: skipped
    out = tmp_path / "out"
    b.main([str(frames), str(labels), "--out", str(out)])
    rows = list(csv.DictReader((out / "results.csv").open()))
    by = {r["design"]: r for r in rows}
    assert set(by) == set(b.DESIGNS) and (out / "chart.png").exists()
    assert int(by["always cheap"]["calls"]) == 2          # 8 frames, 6 per call
    assert int(by["always strong"]["strong_frames"]) == 8
    assert int(by["cascade"]["strong_frames"]) <= 8
    assert float(by["always cheap"]["usd_est"]) < float(by["always strong"]["usd_est"])
    assert all(0 <= float(r["accuracy"]) <= 1 for r in rows)
