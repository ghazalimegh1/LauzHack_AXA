"""Accuracy vs cost on your own labelled video frames: the chart for the pitch.

Compares three designs on the same frames:
  always cheap   every frame to the cheap model   (CHEAP_IMG_PX)
  always strong  every frame to the strong model  (STRONG_IMG_PX)
  cascade        what the app does: cheap first, strong only for frames the cheap
                 model was unsure about (it calls sitecheck._cloud, the app's own code)
Frames go in batches of config.KEYFRAMES per call, like the app sends one walk's key frames.

1. Get frames, either your own JPG/PNG files in a folder, or key frames from a video:
       python tools/benchmark_video.py --from-video my_walk.MOV eval/frames
   This writes eval/frames/frame_01.jpg ... and eval/frames/labels_template.csv.
2. Fill in the labels CSV (see eval/video_labels_example.csv), one row per frame and type:
       frame,object_type,present
       frame_01.jpg,vehicle,y
       frame_01.jpg,glass_roof,n
   object_type is a key of frugal/objects.py CATALOGUE. Only labelled types are asked for.
3. Try it for free first (fake answers, estimated cost):
       FRUGAL_MOCK=1 python tools/benchmark_video.py eval/frames eval/frames/labels_template.csv
   Then the real run (costs money: see the estimate it prints first):
       python tools/benchmark_video.py eval/frames eval/frames/labels_template.csv
Output: a table on screen, results.csv and chart.png in --out (default eval/benchmark_video/).

"Present" means the design reported that type in that frame with confidence >= CONF_MIN,
the same rule the app uses before it counts an object.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("FRUGAL_NO_CACHE", "1")  # every design pays for its own calls

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from frugal import config, detect, objects, photo, sitecheck, video, vision  # noqa: E402
from frugal.ledger import Ledger  # noqa: E402

DESIGNS = ("always cheap", "always strong", "cascade")
OUT_TOKENS_EST = 150   # assumption for the estimate: a compact JSON reply for one batch
REF_PRICE = {"cheap": "claude-haiku-5-5", "strong": "claude-sonnet-5-5"}  # mock-mode stand-ins


# ---------------- input ----------------
def read_labels(path: Path) -> dict[tuple[str, str], bool]:
    """(frame file, object type) -> truly present. Blank or unknown rows are skipped."""
    labels, skipped = {}, 0
    for row in csv.DictReader(path.open(encoding="utf-8")):
        kind, value = row["object_type"].strip(), row["present"].strip().lower()[:1]
        if kind not in objects.CATALOGUE or kind == "person" or value not in ("y", "n"):
            skipped += 1
            continue
        labels[(row["frame"].strip(), kind)] = value == "y"
    if skipped:
        print(f"Note: {skipped} label rows skipped (blank, not y/n, or unknown object type).")
    return labels


def load_frames(folder: Path, names: list[str]) -> dict[str, Image.Image]:
    missing = [n for n in names if not (folder / n).exists()]
    if missing:
        sys.exit(f"Frames listed in the labels but not in {folder}: {', '.join(missing[:5])}")
    return {n: photo.load((folder / n).read_bytes()) for n in names}


def batches(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


# ---------------- running the designs ----------------
class CallLog:
    """Wraps vision.find so every design's calls are recorded the same way,
    including the calls the cascade makes inside sitecheck._cloud."""

    def __init__(self):
        self.calls: list[dict] = []
        self._real = vision.find

    def __enter__(self):
        def recorded(model, jpegs, *args, **kwargs):
            r = self._real(model, jpegs, *args, **kwargs)
            sizes = [Image.open(io.BytesIO(j)).size for j in jpegs]
            self.calls.append({"model": model, "sizes": sizes, "usd": r["usd"] or 0.0,
                               "tokens": r["tok_in"] + r["tok_out"]})
            return r
        vision.find = recorded
        return self

    def __exit__(self, *exc):
        vision.find = self._real


def present(objs: list[dict], frame_of) -> set[tuple[str, str]]:
    """Objects -> set of (frame, type) the design says are there (confident ones only)."""
    return {(frame_of(o["f"]), o["kind"]) for o in objs if o["conf"] >= config.CONF_MIN}


def run_single(model: str, px: int, imgs: dict, kinds: list[str]) -> set:
    found = set()
    for batch in batches(sorted(imgs), config.KEYFRAMES):
        r = vision.find(model, [photo.jpeg(imgs[n], px) for n in batch], kinds)
        found |= present(r["objects"], lambda f: batch[f])
    return found


def run_cascade(imgs: dict, kinds: list[str]) -> set:
    found = set()
    for batch in batches(sorted(imgs), config.KEYFRAMES):
        picked = [{"n": i, "safe": imgs[name]} for i, name in enumerate(batch)]
        objs = sitecheck._cloud(Ledger(), picked, kinds)   # the app's exact cascade
        found |= present(objs, lambda f: batch[f])
    return found


def run_design(design: str, imgs: dict, kinds: list[str]) -> tuple[set, list[dict]]:
    with CallLog() as log:
        if design == "always cheap":
            found = run_single(config.CHEAP_MODEL, config.CHEAP_IMG_PX, imgs, kinds)
        elif design == "always strong":
            found = run_single(config.STRONG_MODEL, config.STRONG_IMG_PX, imgs, kinds)
        else:
            found = run_cascade(imgs, kinds)
    return found, log.calls


# ---------------- scoring and cost ----------------
def score(found: set, labels: dict) -> dict:
    tp = sum(1 for k, v in labels.items() if v and k in found)
    fp = sum(1 for k, v in labels.items() if not v and k in found)
    fn = sum(1 for k, v in labels.items() if v and k not in found)
    tn = len(labels) - tp - fp - fn
    return {"accuracy": (tp + tn) / len(labels) if labels else 0.0,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _price(model: str) -> tuple[float, float]:
    ref = REF_PRICE["strong" if model == config.STRONG_MODEL else "cheap"]
    return (config.PRICES.get(model) or config.PRICES.get(model.split("/")[-1])
            or config.PRICES[ref])


def estimate_usd(call: dict) -> float:
    """Same token rule the app uses (1 token per 28x28 px + prompt), so mock runs
    still show a meaningful cost. An estimate, not a bill."""
    tok_in = sitecheck.PROMPT_TOKENS + sum(vision.image_tokens(w, h) for w, h in call["sizes"])
    cin, cout = _price(call["model"])
    return (tok_in * cin + OUT_TOKENS_EST * cout) / 1e6


def cost(calls: list[dict]) -> dict:
    strong_imgs = sum(len(c["sizes"]) for c in calls if c["model"] == config.STRONG_MODEL)
    return {"calls": len(calls), "strong_frames": strong_imgs,
            "usd": sum(c["usd"] for c in calls), "tokens": sum(c["tokens"] for c in calls),
            "usd_est": sum(estimate_usd(c) for c in calls)}


def benchmark(imgs: dict, labels: dict) -> list[dict]:
    kinds = sorted({k for _, k in labels})
    rows = []
    for d in DESIGNS:
        found, calls = run_design(d, imgs, kinds)
        rows.append({"design": d, **score(found, labels), **cost(calls)})
    return rows


# ---------------- output ----------------
def print_table(rows: list[dict], n_frames: int) -> None:
    print(f"\n{n_frames} frames, {config.KEYFRAMES} per call. "
          f"cheap = {config.CHEAP_MODEL}, strong = {config.STRONG_MODEL}")
    print(f"{'design':<14} {'accuracy':>8} {'precision':>9} {'recall':>7} {'calls':>5} "
          f"{'strong fr.':>10} {'tokens':>8} {'USD':>9} {'USD est.':>9}")
    for r in rows:
        print(f"{r['design']:<14} {r['accuracy']:8.1%} {r['precision']:9.1%} {r['recall']:7.1%} "
              f"{r['calls']:5d} {r['strong_frames']:10d} {r['tokens']:8d} "
              f"{r['usd']:9.5f} {r['usd_est']:9.5f}")


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# Colours from the reference data-viz palette: one blue highlight for our design,
# neutral grey for the alternatives, text in ink colours (never the bar colour).
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
HIGHLIGHT, OTHER = "#2a78d6", "#a9a8a2"


def _bar_panel(draw, box, rows, value, fmt, title, font, small):
    """One horizontal bar per design, value written at the bar end."""
    x0, y0, x1, y1 = box
    draw.text((x0, y0), title, fill=INK, font=font)
    top, label_w = y0 + 70, 230
    bar_h, gap = 110, 60
    vmax = max(value(r) for r in rows) or 1.0
    span = x1 - x0 - label_w - 170
    draw.line([x0 + label_w, top - 10, x0 + label_w, top + 3 * (bar_h + gap) - gap + 10],
              fill=GRID, width=2)
    for i, r in enumerate(rows):
        y = top + i * (bar_h + gap)
        draw.text((x0, y + bar_h / 2), r["design"], fill=INK_2, font=small, anchor="lm")
        w = max(4, span * value(r) / vmax)
        colour = HIGHLIGHT if r["design"] == "cascade" else OTHER
        draw.rounded_rectangle([x0 + label_w, y, x0 + label_w + w, y + bar_h], radius=4,
                               fill=colour)
        draw.text((x0 + label_w + w + 14, y + bar_h / 2), fmt(value(r)), fill=INK, font=small,
                  anchor="lm")


def headline(rows: list[dict], cost_key: str) -> str:
    by = {r["design"]: r for r in rows}
    c, s = by["cascade"], by["always strong"]
    pts = (c["accuracy"] - s["accuracy"]) * 100
    if not c[cost_key]:
        return f"Cascade accuracy {c['accuracy']:.0%} ({pts:+.0f} pts vs always strong)"
    return (f"Cascade: {s[cost_key] / c[cost_key]:.1f}x cheaper than always strong, "
            f"accuracy {pts:+.0f} pts")


def draw_chart(rows: list[dict], n_frames: int, mock: bool, path: Path) -> None:
    """16:9 slide image. Two panels, not a dual axis: accuracy and cost have different units."""
    cost_key = "usd_est" if mock else "usd"
    img = Image.new("RGB", (1920, 1080), SURFACE)
    draw = ImageDraw.Draw(img)
    big, font, small = (ImageFont.load_default(size=s) for s in (54, 38, 32))
    draw.text((80, 60), headline(rows, cost_key), fill=INK, font=big)
    sub = (f"{n_frames} labelled frames, cheap = {config.CHEAP_MODEL}, "
           f"strong = {config.STRONG_MODEL}")
    draw.text((80, 140), sub, fill=INK_2, font=small)
    if mock:
        draw.text((80, 190), "MOCK RUN: accuracy is fake, cost is an estimate (1 token per "
                  "28x28 px). Not for the slides.", fill="#b3261e", font=small)
    _bar_panel(draw, (80, 300, 940, 1000), rows, lambda r: r["accuracy"] * 100,
               lambda v: f"{v:.0f} %", "Accuracy (% of labelled checks right)", font, small)
    unit = "USD, estimated" if mock else "USD"
    _bar_panel(draw, (1000, 300, 1860, 1000), rows, lambda r: r[cost_key],
               lambda v: f"${v:.4f}", f"Cost for {n_frames} frames ({unit})", font, small)
    draw.text((80, 960), "Accuracy = share of labelled (frame, object type) checks answered right. "
              "Precision and recall are in results.csv.", fill=INK_2, font=small)
    img.save(path)


# ---------------- frames from a video ----------------
def _blur_people(img: Image.Image) -> Image.Image:
    # These frames are uploaded in a real run, so people are blurred exactly as in the app.
    if not detect.available():
        print("Warning: ultralytics not installed, people in the frames are NOT blurred.")
        return img
    return detect.blur_people(img, detect.detect(img))


def extract(video_path: Path, folder: Path, k: int) -> None:
    """Key frames -> JPGs plus a label template with every catalogue type, blank."""
    folder.mkdir(parents=True, exist_ok=True)
    info = video.keyframes_from_path(str(video_path), k)
    names = []
    for f in info["picked"]:
        name = f"frame_{f['n']:02d}.jpg"
        _blur_people(f["img"]).save(folder / name, quality=92)
        names.append(name)
    kinds = [k for k in objects.CATALOGUE if k != "person"]
    with (folder / "labels_template.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "object_type", "present"])
        w.writerows([n, kind, ""] for n in names for kind in kinds)
    print(f"Wrote {len(names)} frames and labels_template.csv to {folder}. "
          "Fill in present = y or n, delete rows you do not want to judge.")


def estimate_before_run(n_frames: int) -> float:
    """Rough upper bound of a real run: all three designs, every frame at full size."""
    per = lambda m, px: estimate_usd({"model": m, "sizes": [(px, px * 9 // 16)] * config.KEYFRAMES})  # noqa: E731
    n_calls = -(-n_frames // config.KEYFRAMES)
    cheap = n_calls * per(config.CHEAP_MODEL, config.CHEAP_IMG_PX)
    strong = n_calls * per(config.STRONG_MODEL, config.STRONG_IMG_PX)
    # always cheap + always strong, plus the cascade at its worst (every frame escalated).
    return 2 * (cheap + strong)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("frames", type=Path, help="folder with the frame images")
    ap.add_argument("labels", type=Path, nargs="?", help="labels CSV: frame,object_type,present")
    ap.add_argument("--from-video", type=Path, help="extract key frames from this video first")
    ap.add_argument("--k", type=int, default=12, help="key frames to extract (--from-video)")
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "benchmark_video")
    a = ap.parse_args(argv)

    if a.from_video:
        extract(a.from_video, a.frames, a.k)
        return
    if not a.labels:
        ap.error("give a labels CSV (or use --from-video to make frames and a template)")
    labels = read_labels(a.labels)
    if not labels:
        sys.exit("No usable label rows (present must be y or n).")
    imgs = load_frames(a.frames, sorted({f for f, _ in labels}))
    if config.MOCK:
        print("MOCK MODE: answers are fake, accuracy means nothing. Cost is an estimate.")
    else:
        print(f"Real run: at most ~${estimate_before_run(len(imgs)):.4f} (estimate).")

    rows = benchmark(imgs, labels)
    a.out.mkdir(parents=True, exist_ok=True)
    print_table(rows, len(imgs))
    write_csv(rows, a.out / "results.csv")
    draw_chart(rows, len(imgs), config.MOCK, a.out / "chart.png")
    print(f"\nWrote {a.out / 'results.csv'} and {a.out / 'chart.png'}")


if __name__ == "__main__":
    main()
