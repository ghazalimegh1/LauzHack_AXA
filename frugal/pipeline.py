"""The cascade. Every step is cheaper than the next, and each one can stop the run:

  1 address -> coordinates          free (federal geo API, cached)
  2 hazard maps at that point       free (cached)
  3 pick only relevant questions    free  -> if none: stop, no AI at all
  4 photo quality gate              free  -> if bad: ask for a retake, no AI spent
  5 cheap vision model, small image paid, small
  6 strong model, only unclear ids  paid, only when needed
  7 rules score + advice            free
"""
from __future__ import annotations

import time

import requests

from . import checklist, config, geo, hazards, photo, score, vision
from .ledger import Ledger


def _timed(fn, *args):
    t0 = time.perf_counter()
    result = fn(*args)
    return result, int((time.perf_counter() - t0) * 1000)


def run(address: str, photo_bytes: bytes | None = None, *, levels: dict | None = None,
        force: bool = False, baseline: bool = False) -> dict:
    led = Ledger()
    out = {"address": address, "status": "ok", "ledger": led, "answers": {},
           "answered_by": {}, "place": None, "photo_problems": []}

    # 1 + 2: where is it, and what do the official maps say?
    if levels is not None:
        hz = hazards.from_levels(levels)
        led.add(name="Hazard levels", kind="free", note="manual/test values, map skipped")
    else:
        try:
            place, ms = _timed(geo.geocode, address)
            led.add(name="Geocode address", kind="free", ms=ms, note="geo.admin.ch")
            hz, ms = _timed(hazards.from_map, place["e"], place["n"])
            led.add(name="Hazard map lookup", kind="free", ms=ms, note="BAFU + MeteoSwiss layers")
            out["place"] = place
        except geo.GeoError as exc:
            out.update(status="geo_error", error=str(exc))
            return out
    out["hazards"] = hz

    # 3: the map decides which questions are worth paying for.
    questions = checklist.select(hz)
    out["questions"] = [q["id"] for q in questions]
    if not questions:
        led.add(name="Vision model", kind="skipped", note="no elevated hazard here")
        out["result"] = score.evaluate(hz, {})
        return out
    if photo_bytes is None:
        led.add(name="Vision model", kind="skipped", note="no photo uploaded")
        out["result"] = score.evaluate(hz, {})
        out["status"] = "area_only"
        return out

    # 4: never pay to look at a bad photo.
    img = photo.load(photo_bytes)
    out["photo_problems"] = photo.problems(img)
    led.add(name="Photo quality gate", kind="free",
            note="; ".join(out["photo_problems"]) or "ok")
    if out["photo_problems"] and not force:
        out["status"] = "retake"
        out["result"] = score.evaluate(hz, {})
        return out

    try:
        _vision_steps(out, led, hz, img, questions, baseline)
    except requests.RequestException as exc:
        # A wrong model ID or network issue should show a message, not crash the demo.
        out.update(status="ai_error", error=str(exc), result=score.evaluate(hz, {}))
    return out


def _vision_steps(out, led, hz, img, questions, baseline) -> None:
    # 5: cheap model first, on a small image.
    small = photo.jpeg(img, config.CHEAP_IMG_PX)
    first = vision.ask(config.CHEAP_MODEL, small, questions)
    _log(led, "Cheap vision model", first)
    answers = dict(first["answers"])
    out["answered_by"] = {i: first["model"] for i in answers}

    # 6: escalate only what the cheap model could not decide, and only if it matters.
    unsure = [q for q in questions
              if (answers[q["id"]] == "u" or first["conf"] < config.CONF_MIN)
              and hz[q["group"]]["level"] >= 1]
    if unsure:
        second = vision.ask(config.STRONG_MODEL, photo.jpeg(img, config.STRONG_IMG_PX), unsure)
        _log(led, f"Strong model ({len(unsure)} of {len(questions)} questions)", second)
        answers.update(second["answers"])
        out["answered_by"].update({q["id"]: second["model"] for q in unsure})
    else:
        led.add(name="Strong model", kind="skipped", note="cheap model was confident")
    out["answers"] = answers

    # 7: deterministic scoring and advice.
    out["result"] = score.evaluate(hz, answers)

    if baseline:
        out["baseline"] = _naive(img)


def _log(led: Ledger, name: str, r: dict) -> None:
    note = "cache hit (free)" if r.get("cached") else ("MOCK - no API call" if r.get("mock") else "")
    led.add(name=name, kind="ai", model=r["model"], tok_in=r["tok_in"], tok_out=r["tok_out"],
            usd=r["usd"] or 0.0, ms=r["ms"], note=note)


def _naive(img) -> dict:
    """What a 'send everything to the big model' design costs: strong model,
    big image, all questions, every time."""
    r = vision.ask(config.NAIVE_MODEL, photo.jpeg(img, config.NAIVE_IMG_PX, 85),
                   checklist.QUESTIONS)
    return {"answers": r["answers"], "usd": r["usd"] or 0.0,
            "tokens": r["tok_in"] + r["tok_out"], "ms": r["ms"], "cached": r["cached"],
            "mock": r.get("mock", False)}
