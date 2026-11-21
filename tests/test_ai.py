"""Model calls: retry on busy/broken answers, then fall back, and cache answers."""
import pytest

from sitecheck import ai, settings, vision

OK = {"choices": [{"message": {"content": '{"objects": [], "unsure_frames": []}'}}],
      "usage": {"prompt_tokens": 1000, "completion_tokens": 20, "cost": 0.0001}}


class FakeServer:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, model, parts, max_tokens):
        self.calls.append(model)
        return self.answers.pop(0)


def run(answers, model=settings.CHEAP_MODEL):
    server, waits = FakeServer(answers), []
    out = ai.ask(model, ["hello"], 100, post=server, sleep=waits.append)
    return out, server.calls, waits


def test_retries_after_2_then_5_seconds():
    out, calls, waits = run([(429, None), (503, None), (200, OK)])
    assert waits == [2, 5]
    assert calls == [settings.CHEAP_MODEL] * 3
    assert out["model"] == settings.CHEAP_MODEL and out["usd"] == 0.0001


def test_falls_back_to_similar_model_after_retries():
    out, calls, waits = run([(429, None)] * 3 + [(200, OK)])
    assert calls == [settings.CHEAP_MODEL] * 3 + ["google/gemini-3.1-flash-lite"]
    assert out["model"] == "google/gemini-3.1-flash-lite"
    assert waits == [2, 5]


def test_full_fallback_chain_and_final_error():
    with pytest.raises(ai.AIError) as err:
        run([(429, None)] * 9)
    assert "google/gemini-2.5-flash" in str(err.value)


def test_error_inside_a_200_answer_is_treated_as_busy():
    busy = {"error": {"code": 429, "message": "rate-limited upstream"}}
    out, calls, waits = run([(200, busy), (200, OK)])
    assert waits == [2] and out["text"]


def test_client_error_skips_straight_to_fallback():
    out, calls, waits = run([(400, {"error": {"code": 400}}), (200, OK)])
    assert calls == [settings.CHEAP_MODEL, "google/gemini-3.1-flash-lite"]
    assert waits == []


def test_network_error_is_retried():
    out, calls, waits = run([(None, None), (200, OK)])
    assert waits == [2] and out["text"]


def test_repeat_question_comes_from_cache_for_free():
    first, _, _ = run([(200, OK)])
    second, calls, _ = run([])
    assert second["cached"] and second["usd"] == 0 and calls == []
    assert second["text"] == first["text"]


def test_price_fallback_when_no_cost_reported():
    no_cost = {"choices": [{"message": {"content": "{}"}}],
               "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}}
    out, _, _ = run([(200, no_cost)])
    assert out["usd"] == pytest.approx(0.10)


def test_parse_answer_with_fences_and_bad_entries():
    text = '```json\n{"objects": [{"frame": 1, "type": "glass_roof", "box": [100, 200, 300, 400], ' \
           '"confidence": 0.7}, {"frame": 9, "type": "glass_roof", "box": [1, 2, 3, 4]}, ' \
           '{"frame": 1, "type": "spaceship", "box": [0, 0, 500, 500]}], "unsure_frames": [2, 7]}\n```'
    objs, unsure = vision.read_answer(ai.parse_json(text), ["glass_roof"], 2)
    assert len(objs) == 1
    assert objs[0]["box"] == [0.2, 0.1, 0.4, 0.3]       # [ymin,xmin,ymax,xmax] -> [x0,y0,x1,y1]
    assert unsure == {2}


def test_estimate_rule_is_shared():
    assert ai.image_tokens(384, 216) == 258
    assert ai.image_tokens(512, 288) == 258
    assert ai.image_tokens(1280, 720) == 516
    cheap = ai.estimate(settings.CHEAP_MODEL, [(512, 288)] * 6, 1)
    pro = ai.estimate(settings.BASELINE_MODEL, [(512, 288)] * 6, 1)
    assert pro["tokens_in"] == cheap["tokens_in"]          # same frames, same tokens in
    assert pro["usd"] > cheap["usd"] * 5
