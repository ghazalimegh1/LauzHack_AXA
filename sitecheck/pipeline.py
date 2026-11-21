"""One site check, start to finish. Free steps first; paid AI only where it is needed.

address -> hazard map -> key frames -> free detector + blur -> cheap model (one call)
-> strong model (only unsure frames) -> rules -> ledger and cost comparison
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from . import ai, catalogue, frames, hazard_map, privacy, rules, settings, vision


class Ledger:
    """Time, tokens and USD for every step."""

    def __init__(self):
        self.rows = []

    @contextmanager
    def step(self, name: str, kind: str = "free code"):
        row = {"step": name, "type": kind, "model": None, "tokens_in": 0, "tokens_out": 0,
               "usd": 0.0, "ms": 0, "note": ""}
        start = time.perf_counter()
        try:
            yield row
        finally:
            row["ms"] = round((time.perf_counter() - start) * 1000)
            self.rows.append(row)


def _levels(hazards: dict) -> dict:
    return {k: (v["level"] if v.get("available") else 0) for k, v in hazards.items()}


def run(video_path: str, address: str, keyframes: int = settings.KEYFRAMES_DEFAULT,
        detector_on: bool = True, simulate=None, progress=lambda text: None,
        ask=ai.ask) -> tuple:
    """Returns (result dict for the website, images dict kept in server memory)."""
    started = time.perf_counter()
    ledger = Ledger()
    keyframes = max(settings.KEYFRAMES_MIN, min(settings.KEYFRAMES_MAX, int(keyframes)))

    # 1) address and hazard maps (free)
    progress("Finding your address")
    with ledger.step("Find the address (geo.admin.ch)") as row:
        place = hazard_map.geocode(address)          # AddressNotFound / MapError go up
        row["note"] = place["label"]
    progress("Reading the official hazard maps")
    with ledger.step("Read hail and water hazard maps (geo.admin.ch)") as row:
        if simulate:
            hazards = hazard_map.simulated(simulate.get("hail", 0), simulate.get("water", 0))
            row["note"] = "simulated levels"
        else:
            try:
                hazards = hazard_map.read_hazards(place["e"], place["n"])
            except hazard_map.MapError:
                hazards = hazard_map.unavailable()
                row["note"] = "map did not answer"
    for h in hazards.values():
        h["word"] = hazard_map.LEVEL_WORDS[h["level"]] if h.get("available") else "map unavailable"
    levels = _levels(hazards)

    # 2) key frames (free)
    progress("Picking the sharpest frames from your video")
    with ledger.step("Pick key frames (sharpness, brightness, blur)") as row:
        samples, video_info = frames.read_samples(video_path)
        picked = frames.pick(samples, keyframes)
        key_imgs, key_meta = [], []
        for i, s in enumerate(picked):
            img, brightened = frames.brighten(frames.decode(s.jpeg))
            key_imgs.append(img)
            key_meta.append({"index": i, "sample": s.index, "t": round(s.t, 2),
                             "brightened": brightened, "width": img.shape[1],
                             "height": img.shape[0], "people": 0})
        row["note"] = f"{len(samples)} sampled, {len(picked)} picked"
    usable = sum(1 for s in samples if s.reason in ("", "same view as a picked frame",
                                                    "a sharper frame was picked nearby"))

    # 3) free detector: vehicles + people, blur people (free)
    progress("Blurring people and finding vehicles on this computer")
    findings, people_total, detector_ok = [], 0, True
    with ledger.step("Find vehicles and people, blur people (YOLO11n, local)") as row:
        try:
            for meta, img in zip(key_meta, key_imgs):
                found = privacy.detect(img)
                people = [d for d in found if d["kind"] == "person"]
                meta["people"] = len(people)
                people_total += len(people)
                key_imgs[meta["index"]] = privacy.blur_people(img, people)
                if detector_on:
                    for d in found:
                        if d["kind"] == "vehicle":
                            findings.append({"frame": meta["index"], "t": meta["t"],
                                             "kind": "vehicle", "box": d["box"],
                                             "confidence": d["confidence"],
                                             "source": "local detector", "model": "YOLO11n",
                                             "detail": d["label"]})
            row["note"] = f"{people_total} people blurred"
        except privacy.DetectorMissing:
            detector_ok = False
            row["note"] = "detector file missing: no frames are sent to the AI"

    # 4) the map decides what the AI looks for
    kinds = catalogue.kinds_to_ask(levels, detector_on=detector_on and detector_ok)
    ai_info = {"status": "ok", "calls": 0, "frames_sent": 0, "models": []}
    sent_sizes = {"cheap": [], "strong": []}

    if not detector_ok:
        ai_info["status"] = "off"          # never send unblurred people
    elif not kinds:
        ai_info["status"] = "not needed"
    elif not settings.ai_enabled():
        ai_info["status"] = "off"

    unsure_frames = set()
    if ai_info["status"] == "ok":
        # 5) cheap model: all key frames in ONE call, small images
        progress("Looking for weak points (quick check)")
        with ledger.step("First look: all key frames in one call", "AI") as row:
            imgs = []
            for img in key_imgs:
                data, size = vision.jpeg(img, settings.CHEAP_IMG_PX)
                imgs.append(data)
                sent_sizes["cheap"].append(size)
            try:
                ans = ask(settings.CHEAP_MODEL, vision.parts_for(vision.prompt(kinds, len(imgs)), imgs),
                          settings.CHEAP_MAX_OUT)
                _book(row, ans, ai_info, len(imgs))
                objects, unsure_frames = vision.read_answer(ai.parse_json(ans["text"]), kinds, len(imgs))
                for o in objects:
                    meta = key_meta[o["frame"] - 1]
                    findings.append({"frame": meta["index"], "t": meta["t"], "kind": o["kind"],
                                     "box": o["box"], "confidence": o["confidence"],
                                     "source": "cheap model", "model": ans["model"], "detail": ""})
                    if o["confidence"] < settings.UNSURE_BELOW:
                        unsure_frames.add(o["frame"])
            except (ai.AIError, ValueError) as exc:
                ai_info["status"] = "failed"
                row["note"] = "no answer: " + type(exc).__name__

        # 6) strong model: only frames where the cheap model was unsure, larger images
        if ai_info["status"] == "ok" and unsure_frames:
            progress("Taking a closer look at unclear photos")
            order = sorted(unsure_frames)
            with ledger.step(f"Second look: {len(order)} unclear frame(s)", "AI") as row:
                imgs = []
                for n in order:
                    data, size = vision.jpeg(key_imgs[n - 1], settings.STRONG_IMG_PX, 85)
                    imgs.append(data)
                    sent_sizes["strong"].append(size)
                try:
                    ans = ask(settings.STRONG_MODEL, vision.parts_for(vision.prompt(kinds, len(imgs)), imgs),
                              settings.STRONG_MAX_OUT)
                    _book(row, ans, ai_info, len(imgs))
                    objects, _ = vision.read_answer(ai.parse_json(ans["text"]), kinds, len(imgs))
                    redo = {n - 1 for n in order}
                    findings = [f for f in findings
                                if not (f["source"] == "cheap model" and f["frame"] in redo)]
                    for o in objects:
                        meta = key_meta[order[o["frame"] - 1] - 1]
                        findings.append({"frame": meta["index"], "t": meta["t"], "kind": o["kind"],
                                         "box": o["box"], "confidence": o["confidence"],
                                         "source": "strong model", "model": ans["model"],
                                         "detail": ""})
                except (ai.AIError, ValueError) as exc:
                    row["note"] = "no answer, first look kept: " + type(exc).__name__
                    ai_info["second_look_failed"] = True

    # 7) rules (free)
    progress("Putting your results together")
    with ledger.step("Apply rules (importance = weight x hazard level)") as row:
        findings = [rules.score_finding(f, levels) for f in findings]
        findings.sort(key=lambda f: (f["frame"], -f["confidence"]))
        for i, f in enumerate(findings):
            f["id"] = i
            f["name"] = catalogue.KINDS[f["kind"]]["name"]
            f["confidence"] = round(f["confidence"], 3)
            f["box"] = [round(v, 4) for v in f["box"]]
        points = rules.weak_points(findings, levels)
        action = rules.decide(points, hazards)
        row["note"] = action["text"]

    result = {
        "address": place,
        "hazards": hazards,
        "asked": [{"kind": k, "name": catalogue.KINDS[k]["name"], "find": catalogue.KINDS[k]["find"],
                   "hazard": catalogue.KINDS[k]["hazard"], "weight": catalogue.KINDS[k]["weight"]}
                  for k in kinds],
        "not_asked": _not_asked(levels, kinds, detector_on and detector_ok),
        "video": video_info,
        "frames": {"in_video": video_info["frames_in_video"], "sampled": len(samples),
                   "usable": usable, "picked": len(picked),
                   "assessed": ai_info.get("frames_sent", 0)},
        "samples": [s.public() for s in samples],
        "keyframes": key_meta,
        "findings": findings,
        "weak_points": points,
        "action": action,
        "people_blurred": people_total,
        "ai": ai_info,
        "ledger": ledger.rows,
        "cost": _costs(ledger.rows, sent_sizes, video_info, len(key_imgs)),
        "settings": {"keyframes": keyframes, "detector": detector_on,
                     "simulated": bool(simulate)},
        "seconds": round(time.perf_counter() - started, 1),
    }
    images = {"keyframes": key_imgs, "thumbs": [s.thumb for s in samples]}
    return result, images


def _book(row: dict, ans: dict, ai_info: dict, n_images: int) -> None:
    row.update(model=ans["model"], tokens_in=ans["tokens_in"], tokens_out=ans["tokens_out"],
               usd=ans["usd"])
    if ans.get("cached"):
        row["note"] = "answer reused from cache (free)"
    retries = [a for a in ans.get("attempts", []) if a["status"] != 200]
    if retries:
        row["note"] = f"answered after {len(retries)} busy/failed attempt(s)"
    ai_info["calls"] += 1
    ai_info["frames_sent"] = ai_info.get("frames_sent", 0) + n_images
    if ans["model"] not in ai_info["models"]:
        ai_info["models"].append(ans["model"])


def _not_asked(levels: dict, kinds: list, detector_on: bool) -> list:
    out = []
    for k, item in catalogue.KINDS.items():
        if k in kinds:
            continue
        if k == "vehicle" and detector_on and levels.get("hail", 0) >= 1:
            reason = "found by the free local detector instead"
        else:
            reason = f"{item['hazard']} level is 0 here"
        out.append({"kind": k, "name": item["name"], "reason": reason})
    return out


def _costs(rows: list, sizes: dict, video: dict, n_key: int) -> dict:
    """Measured cost, plus the same estimate rule applied to three designs."""
    measured = sum(r["usd"] for r in rows)
    calls = sum(1 for r in rows if r["type"] == "AI" and r["model"])
    ours = ai.estimate(settings.CHEAP_MODEL, sizes["cheap"], 1 if sizes["cheap"] else 0)
    strong = ai.estimate(settings.STRONG_MODEL, sizes["strong"], 1 if sizes["strong"] else 0)
    ours_usd = ours["usd"] + strong["usd"]
    # (a) the same key frames, at the same size, in one call to Gemini 2.5 Pro
    same = sizes["cheap"] or [(settings.CHEAP_IMG_PX, round(settings.CHEAP_IMG_PX * 9 / 16))] * n_key
    pro = ai.estimate(settings.BASELINE_MODEL, same, 1)
    # (b) naive: one HD frame per second of video, one call per frame, Gemini 2.5 Pro
    n_naive = max(1, round(video.get("duration_s", 0)))
    naive = ai.estimate(settings.BASELINE_MODEL, [settings.NAIVE_FRAME] * n_naive, n_naive)
    base = ours_usd if ours_usd > 0 else None
    bars = [
        {"key": "ours", "name": "This check (our design)", "usd": ours_usd,
         "detail": f"{len(sizes['cheap'])} small frames on Flash-Lite"
                   + (f", {len(sizes['strong'])} on Flash" if sizes["strong"] else "")},
        {"key": "pro", "name": "Same frames on Gemini 2.5 Pro", "usd": pro["usd"],
         "detail": f"{len(same)} frames, one call"},
        {"key": "naive", "name": "Naive: 1 HD frame per second on Gemini 2.5 Pro",
         "usd": naive["usd"], "detail": f"{n_naive} frames of 1280x720, one call each"},
    ]
    for b in bars:
        b["times"] = round(b["usd"] / base, 1) if base else None
    return {"measured_usd": measured, "estimate_usd": ours_usd, "ai_calls": calls,
            "comparison": bars,
            "rule": "Same estimate for all three: 400 prompt tokens per call, Google's image "
                    "token rule (258 tokens per 768-px tile), 40 output tokens per frame, "
                    "plus 128 thinking tokens per Gemini 2.5 Pro call; prices from OpenRouter."}
