"""Site video check: the cascade for a walk-around video of a business site.

  1 address -> coordinates -> hazard maps        free
  2 video -> key frames                          free  (~1,800 frames -> 6)
  3 local detector: vehicles + people            free  (people blurred before upload)
  4 map decides which object types to look for   free  -> none: stop, no AI at all
  5 cheap model, ALL key frames in ONE call      paid, small images
  6 strong model, only frames left unclear       paid, only when needed
  7 importance + advice by fixed rules           free
"""
from __future__ import annotations

import time

import requests
from PIL import ImageDraw, ImageFont

from . import config, detect, geo, hazards, objects, photo, score, video, vision
from .ledger import Ledger

# One set of importance colours for boxes (drawn here) and tags (app + website), so they match.
COLOURS = {"high": "#C62828", "medium": "#E8710A", "low": "#F2A900",
           "not relevant here": "#999999", "privacy": "#3B3FD8", "uncertain": "#5F5F5F"}
PROMPT_TOKENS = 350   # rough size of our instructions, for the estimate only


def run(address: str, video_bytes: bytes | None = None, *, suffix: str = ".mp4",
        levels: dict | None = None, k: int | None = None, use_detector: bool = True,
        video_path: str | None = None, allow_map_fail: bool = False) -> dict:
    """Give either video_bytes or video_path. A path avoids holding a 300 MB phone video
    in memory twice (the app copies the upload to a temp file first).
    allow_map_fail: if the hazard map does not answer, carry on with levels marked
    'unavailable' instead of stopping (the website shows "map unavailable", never "low")."""
    led = Ledger()
    out = {"kind": "video", "address": address, "status": "ok", "ledger": led,
           "place": None, "answers": {}, "objects": [], "frames": None}

    # 1: where is it, and what do the official maps say?
    if levels is not None:
        hz = hazards.from_levels(levels)
        led.add(name="Hazard levels", kind="free", note="simulated values, map skipped")
    else:
        t0, place = time.perf_counter(), None
        try:
            place = geo.geocode(address)
            hz = hazards.from_map(place["e"], place["n"])
            note = "geo.admin.ch"
        except geo.GeoError as exc:
            if not allow_map_fail or place is None:
                out.update(status="geo_error", error=str(exc))   # address itself not found
                return out
            hz, note = hazards.unavailable(), "hazard map did not answer: levels unknown"
        led.add(name="Geocode + hazard maps", kind="free", note=note,
                ms=int((time.perf_counter() - t0) * 1000))
        out["place"] = place
    out["hazards"] = hz

    # 2: key frames, no AI.
    t0 = time.perf_counter()
    try:
        info = (video.keyframes_from_path(video_path, k) if video_path
                else video.keyframes(video_bytes, k, suffix))
    except ValueError as exc:
        out.update(status="video_error", error=str(exc))
        return out
    out["frames"] = info
    picked = info["picked"]
    led.add(name="Pick key frames", kind="free", ms=int((time.perf_counter() - t0) * 1000),
            note=f"{info['total']} frames -> {len(info['frames'])} sampled -> {len(picked)} picked")
    if not picked:
        out.update(status="video_error", error="No usable frame: the video is too dark or blurry.")
        return out

    # 3: free local detector; people are blurred before anything is uploaded.
    found: list[dict] = []
    ran_detector = use_detector and detect.available()
    if ran_detector:
        t0 = time.perf_counter()
        for f in picked:
            local = detect.detect(f["img"])
            found += [{**o, "f": f["n"]} for o in local]
            f["safe"] = detect.blur_people(f["img"], local)
        people = sum(o["kind"] == "person" for o in found)
        led.add(name="Local detector (YOLO11n)", kind="free",
                ms=int((time.perf_counter() - t0) * 1000),
                note=f"{len(found) - people} vehicles, {people} people blurred")
    else:
        for f in picked:
            f["safe"] = f["img"]
        led.add(name="Local detector", kind="skipped",
                note="not installed: pip install ultralytics (free vehicle/person detection)")

    # 4: the map decides what the paid model looks for.
    kinds = objects.to_ask(hz, skip=detect.HANDLES if ran_detector else set())
    out["asked"] = kinds
    if not kinds:
        led.add(name="Vision model", kind="skipped", note="no elevated hazard needs the model")
    else:
        try:
            found += _cloud(led, picked, kinds)
        except requests.RequestException as exc:
            out.update(status="ai_error", error=str(exc))

    # 7: rules.
    for o in found:
        o["score"], o["label"] = objects.importance(o["kind"], hz)
        # The local detector's scores run lower than a language model's self-rating.
        floor = detect.SURE if o["by"].startswith("local") else config.CONF_MIN
        if o["label"] not in ("privacy", "not relevant here") and o["conf"] < floor:
            o["label"] = "uncertain"     # shown, but not counted: a person should check
    for i, o in enumerate(sorted(found, key=lambda o: (o["f"], -o["score"]))):
        o["id"] = i
    out["objects"] = sorted(found, key=lambda o: (o["f"], -o["score"]))
    out["result"] = _advice(hz, out["objects"])
    out["frugal"] = _frugal(info, picked, kinds, led)
    return out


def _cloud(led: Ledger, picked: list[dict], kinds: list[str]) -> list[dict]:
    # 5: every key frame in one request, small.
    small = [photo.jpeg(f["safe"], config.CHEAP_IMG_PX) for f in picked]
    first = vision.find(config.CHEAP_MODEL, small, kinds)
    _log(led, f"Cheap model, {len(small)} frames in 1 call", first)
    by_frame = {i: [] for i in range(len(picked))}
    for o in first["objects"]:
        by_frame[o["f"]].append({**o, "by": first["model"]})

    # 6: only frames where the cheap model was unsure go to the strong model.
    unsure = sorted(set(first["unclear"]) |
                    {o["f"] for o in first["objects"] if o["conf"] < config.CONF_MIN})
    if unsure:
        big = [photo.jpeg(picked[i]["safe"], config.STRONG_IMG_PX) for i in unsure]
        second = vision.find(config.STRONG_MODEL, big, kinds)
        _log(led, f"Strong model, {len(unsure)} of {len(picked)} frames", second)
        for i in unsure:
            by_frame[i] = []                       # the strong answer replaces the cheap one
        for o in second["objects"]:
            i = unsure[o["f"]]
            by_frame[i].append({**o, "f": i, "by": second["model"]})
    else:
        led.add(name="Strong model", kind="skipped", note="cheap model was confident")
    return [{**o, "f": picked[i]["n"]} for i, objs in by_frame.items() for o in objs]


def _log(led: Ledger, name: str, r: dict) -> None:
    note = "cache hit (free)" if r.get("cached") else ("MOCK - no API call" if r.get("mock") else "")
    led.add(name=name, kind="ai", model=r["model"], tok_in=r["tok_in"], tok_out=r["tok_out"],
            usd=r["usd"] or 0.0, ms=r["ms"], note=note)


def _advice(hz: dict, found: list[dict]) -> dict:
    """Per hazard group: score = area level x (1 + distinct weak points seen)."""
    seen: dict[str, dict] = {}
    for o in found:
        if o["label"] in ("high", "medium", "low"):
            s = seen.setdefault(o["kind"], {"kind": o["kind"], "score": o["score"],
                                            "label": o["label"], "frames": set()})
            s["frames"].add(o["f"])
    groups = {}
    for g, h in hz.items():
        weak = [k for k in seen if objects.CATALOGUE[k]["group"] == g]
        groups[g] = {"area": h["level"], "weak": weak, "score": h["level"] * (1 + len(weak))}
    top = max(v["score"] for v in groups.values())
    action = next(a for threshold, a in score.ACTIONS if top >= threshold)
    items = sorted(seen.values(), key=lambda s: -s["score"])
    for s in items:
        s["frames"] = sorted(s["frames"])
    return {"groups": groups, "score": top, "action": action, "items": items,
            "uncertain": sorted({o["f"] for o in found if o["label"] == "uncertain"})}


def _frugal(info: dict, picked: list[dict], kinds: list[str], led: Ledger) -> dict:
    """Our cost next to a naive design: one full-HD frame per second to the strong model.
    Both sides use the same estimate (Claude's 28x28 px token rule), so they are comparable."""
    seconds = max(1, round(info["duration"]))
    naive_tok = seconds * (vision.image_tokens(1568, 882) + PROMPT_TOKENS)
    ours_tok = 0
    if kinds:
        ours_tok = PROMPT_TOKENS + sum(
            vision.image_tokens(*photo._fit(f["safe"], config.CHEAP_IMG_PX).size) for f in picked)
    # In mock mode there is no real model: estimate with Claude Haiku / Sonnet prices.
    price = lambda m, ref: (config.PRICES.get(m) or config.PRICES[ref])[0]  # noqa: E731
    tot = led.totals()
    return {"video_frames": info["total"], "sampled": len(info["frames"]),
            "picked": len(picked), "images_sent": len(picked) if kinds else 0,
            "naive_calls": seconds, "naive_tokens": naive_tok,
            "naive_usd": naive_tok * price(config.NAIVE_MODEL, "claude-sonnet-5-5") / 1e6,
            "ours_tokens_est": ours_tok,
            "ours_usd_est": ours_tok * price(config.CHEAP_MODEL, "claude-haiku-5-5") / 1e6,
            # Fair baseline: the SAME selected frames, but sent to the big model. It isolates
            # the saving from model choice; the naive one adds the saving from frame picking.
            "baseline_model": config.NAIVE_MODEL,
            "same_frames_strong_usd": ours_tok * price(config.NAIVE_MODEL, "claude-sonnet-5-5") / 1e6,
            "ours_usd_real": tot["usd"], "ours_tokens_real": tot["tokens"]}


def annotate(frame: dict, found: list[dict]):
    """Draws the boxes on the (privacy-blurred) frame, coloured by importance."""
    img = frame["safe"].copy()
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=max(16, img.width // 36))  # readable when shown at half size
    w, h = img.size
    for o in found:
        if o["f"] != frame["n"]:
            continue
        colour = COLOURS[o["label"]]
        x0, y0, x1, y1 = o["box"][0] * w, o["box"][1] * h, o["box"][2] * w, o["box"][3] * h
        draw.rectangle([x0, y0, x1, y1], outline=colour, width=max(3, w // 200))
        text = f"{o['id']} {objects.CATALOGUE[o['kind']]['name']}"
        if o["label"] != "privacy":
            text += f" | {o['label'].upper()}"
        tb = draw.textbbox((x0, y0), text, font=font)
        ty = y0 - (tb[3] - tb[1]) - 6 if y0 > 30 else y0
        draw.rectangle([x0, ty, x0 + tb[2] - tb[0] + 8, ty + tb[3] - tb[1] + 6], fill=colour)
        draw.text((x0 + 4, ty + 1), text, fill="white", font=font)
    return img
