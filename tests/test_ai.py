"""Model calls: retry on busy/broken answers, then fall back, and cache answers."""
import pytest

from sitecheck import ai, cache, settings, vision

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


def test_cache_hit_keeps_the_first_runs_bill():
    run([(200, OK)])
    second, _, _ = run([])
    assert second["usd"] == 0.0 and second["tokens_in"] == 0
    assert second["first_run_usd"] == 0.0001
    assert second["first_run_tokens_in"] == 1000 and second["first_run_tokens_out"] == 20


def test_old_cache_entry_without_cost_is_unknown_not_free():
    key = cache.make_key("v1", settings.CHEAP_MODEL, 100, "hello")
    cache.put("ai", key, {"text": "{}", "model": settings.CHEAP_MODEL})
    out, calls, _ = run([])
    assert calls == [] and out["cached"] and out["first_run_usd"] is None


def test_fresh_run_asks_again_and_rewrites_the_cache():
    run([(200, OK)])
    newer = {**OK, "usage": {"prompt_tokens": 900, "completion_tokens": 10, "cost": 0.0002}}
    server, waits = FakeServer([(200, newer)]), []
    fresh = ai.ask(settings.CHEAP_MODEL, ["hello"], 100, post=server, sleep=waits.append,
                   use_cache=False)
    assert server.calls == [settings.CHEAP_MODEL]
    assert not fresh["cached"] and fresh["usd"] == 0.0002
    again, calls, _ = run([])
    assert calls == [] and again["first_run_usd"] == 0.0002


def test_price_fallback_when_no_cost_reported():
    no_cost = {"choices": [{"message": {"content": "{}"}}],
               "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}}
    out, _, _ = run([(200, no_cost)])
    assert out["usd"] == pytest.approx(0.10) and out["billed"] is False


def test_parse_answer_with_fences_and_bad_entries():
    text = '```json\n{"o": [{"f": 0, "t": "glass_roof", "b": [100, 200, 300, 400], "c": 0.7}, ' \
           '{"f": 9, "t": "glass_roof", "b": [1, 2, 3, 4]}, ' \
           '{"f": 0, "t": "spaceship", "b": [0, 0, 500, 500]}], "u": [1, 7]}\n```'
    objs, unclear = vision.read_answer(text, ["glass_roof"], 2)
    assert len(objs) == 1 and objs[0]["frame"] == 0
    assert objs[0]["box"] == [0.2, 0.1, 0.4, 0.3]       # [ymin,xmin,ymax,xmax] -> [x0,y0,x1,y1]
    assert unclear == {1}


def test_cut_off_answer_keeps_complete_objects():
    text = '{"o":[{"f":1,"t":"solar_panel","b":[10,20,110,220],"c":0.9},{"f":0,"t":"solar_pa'
    objs, _ = vision.read_answer(text, ["solar_panel"], 2)
    assert [o["frame"] for o in objs] == [1]


def test_long_key_names_are_accepted():
    text = '{"objects":[{"frame":0,"type":"ramp_down","box":{"xmin":100,"ymin":100,"xmax":300,"ymax":400},"confidence":0.8}]}'
    objs, _ = vision.read_answer(text, ["ramp_down"], 1)
    assert objs[0]["box"] == [0.1, 0.1, 0.3, 0.4]


def test_prompt_puts_frames_first_and_explains_unclear():
    parts = vision.parts_for(vision.prompt(["glass_roof"], 2), [b"a", b"b"])
    assert parts[:4] == ["Frame 0:", b"a", "Frame 1:", b"b"]
    assert "a clear frame without these objects is not unclear" in parts[-1]


def test_estimate_rule_is_shared():
    assert ai.image_tokens(384, 216) == 258
    assert ai.image_tokens(512, 288) == 258
    assert ai.image_tokens(1280, 720) == 516
    cheap = ai.estimate(settings.CHEAP_MODEL, [(512, 288)] * 6, 1)
    pro = ai.estimate(settings.BASELINE_MODEL, [(512, 288)] * 6, 1)
    assert pro["tokens_in"] == cheap["tokens_in"]          # same frames, same tokens in
    assert pro["usd"] > cheap["usd"] * 5


def test_check_cost_counts_first_run_bill_for_reused_answers():
    from sitecheck import pipeline
    row = {"type": "AI", "model": settings.CHEAP_MODEL, "usd": 0.0, "cached": True,
           "measured_usd": 0.0003}
    fresh = {"type": "AI", "model": settings.STRONG_MODEL, "usd": 0.0002, "cached": False,
             "measured_usd": 0.0002}
    c = pipeline._measured_costs([row, fresh], "ok")
    assert c["measured_usd"] == pytest.approx(0.0005) and c["this_run_usd"] == 0.0002
    assert c["all_measured"] and c["any_cached"] and not c["all_cached"]
    unknown = pipeline._measured_costs([{**row, "measured_usd": None}], "ok")
    assert unknown["measured_usd"] is None and not unknown["all_measured"]
    assert pipeline._measured_costs([], "not needed")["ai_calls"] == 0


def test_detector_label_comes_from_the_weights_file():
    assert settings.DETECTOR_LABEL == "YOLO" + settings.DETECTOR_WEIGHTS.stem[4:]


def test_plain_name_is_kept_and_tiny_boxes_are_dropped():
    text = ('{"o":[{"f":0,"t":"outdoor_goods","d":"Pallets!!","b":[100,100,400,500],"c":0.8},'
            '{"f":0,"t":"outdoor_goods","d":"crate","b":[100,100,110,500],"c":0.8}]}')
    objs, _ = vision.read_answer(text, ["outdoor_goods"], 1)
    assert len(objs) == 1                                   # 1% high box: shows nothing, dropped
    assert objs[0]["detail"] == "pallets"


def test_boxes_outside_the_picture_are_clamped():
    objs, _ = vision.read_answer('{"o":[{"f":0,"t":"glass_roof","b":[-50,900,600,1200],"c":0.9}]}',
                                 ["glass_roof"], 1)
    assert objs[0]["box"] == [0.9, 0.0, 1.0, 0.6]
