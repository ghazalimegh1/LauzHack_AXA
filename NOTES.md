# NOTES.md: requests between agents

Each agent may only edit its own files. If you need a change in a file you do not own,
write the request here under your own heading: file, what to change, and why.
The main agent reads this at the end and makes the changes.

## Agent 1: Real-world check

(Re Agent 3 item 5: done, `google/gemini-2.5-flash` = 0.30 / 2.50 USD per 1M is now in
config.PRICES, read from OpenRouter's /models on 2026-11-21.)

1. **sitecheck.py `_frugal` and pipeline.py `_naive`: use `config.NAIVE_MODEL` for the naive design.**
   The OpenRouter strong default is now `google/gemini-2.5-flash` (same boxes as Pro in our test,
   5.6x cheaper). Both naive-baseline places still use `config.STRONG_MODEL`, so the "naive"
   design would suddenly look ~4x cheaper (Flash 0.30 vs Pro 1.25 USD/1M in) and the
   "Naive / ours" ratio in the app would drop for no real reason.
   - sitecheck.py line ~177: `price(config.STRONG_MODEL, "claude-sonnet-5-5")` ->
     `price(config.NAIVE_MODEL, "claude-sonnet-5-5")`
   - pipeline.py `_naive`: `vision.ask(config.STRONG_MODEL, ...)` -> `vision.ask(config.NAIVE_MODEL, ...)`
   - tools/benchmark.py line 32 ("strong" design) can stay on STRONG_MODEL (it measures our escalation model).
2. **geo.py: `identify()` is now unused.** The REST identify endpoint answers
   400 "No GeoTable was found" for all four hazard layers (they are raster/WMS layers, not
   queryable there). hazards.py now asks the federal WMS (GetFeatureInfo), which answers.
   Either delete `geo.identify` or leave it with a comment saying it is unused.
3. **README.md: replace the "could not be verified" bullets with what is now verified (2026-11-21):**
   - Models (OpenRouter): cheap `google/gemini-2.5-flash-lite`, strong `google/gemini-2.5-flash`,
     naive baseline `google/gemini-2.5-pro`. Claude Haiku on OpenRouter is `anthropic/claude-haiku-5.5`
     (dot, not dash). Box test on two site photos: Gemini flash-lite boxes tight and correct;
     Haiku boxes misplaced with [ymin,xmin,...], loose with [xmin,ymin,...] (now the default for non-Gemini).
   - Hazard maps: answered via `wms.geo.admin.ch` GetFeatureInfo. Route Cantonale 11, Lausanne:
     hail 3.5 cm (medium), no flood layer -> water low. Gerberngasse 10, Bern: Aquaprotect 100 + 500
     (water high), hail 4 cm (high). Hail value is in cm (MeteoSwiss legend classes <1.5 ... >=4.5 cm);
     the 3/4 cm cut-offs remain our assumption. The flood layers give presence only, no depth.
   - The `ch.meteoschweiz.ogd-radar-derived-grid` STAC collection is a hail *climatology* download
     (grid files), not needed: the 50-year hail-size layer still answers via WMS.
   - Also the "Two things that could not be verified" heading says two but lists four.
4. **.env.example:** OpenRouter defaults line -> `CHEAP_MODEL=google/gemini-2.5-flash-lite   STRONG_MODEL=google/gemini-2.5-flash`.
5. **Demo risk, for app.py / the pitch (no code change):** `eval/test_walk.mp4` is a close-up pan
   over a bus with large blurred people. On it Gemini flash-lite marks all 6 frames "unclear",
   so all 6 go to the strong model, and Gemini 2.5 Flash then reports a "ground door" (the bus
   side) in every frame with conf 0.9 -> a false "high" item. Haiku finds nothing. Use a real
   site video for the live demo (building, car park, roof), and pre-run it so it comes from cache.
6. **tests/test_offline.py: add these offline tests** (ready to paste at the end of the file):

```python
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
```

## Agent 2: Polished app

(Re Agent 3 item 2: VERIFIED. A file named `IMG_HEVC.MOV` (uppercase, real HEVC, made with
macOS `avconvert` from eval/test_walk.mp4) uploads in headless Chrome through the real
uploader and runs to a full result. Streamlit lower-cases extensions on both sides.)

(Re Agent 3 item 1, file path instead of bytes: NOT done in app.py, because it needs the new
`video_path=` argument in sitecheck.py first. When the main agent adds it, change `run_site`
in app.py to: copy `v_up` to a NamedTemporaryFile in chunks (`v_up.seek(0)`,
`shutil.copyfileobj(v_up, tmp)`, suffix = lower-cased extension), call
`sitecheck.run(..., video_path=tmp.name)`, `os.unlink` it in `finally`. `run_site` already
gets the suffix lower-cased; the "big file" spinner text uses `len(data)`, switch it to
`v_up.size`.)

1. **tests/test_offline.py: add this offline test for the new report** (ready to paste):

```python
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
```

2. **DONE (main agent, with the user's OK, 2026-11-21): both claims softened, no AXA facts left.** ~~frugal/objects.py texts (no change made, flag only):~~ two "why" lines state facts about
   AXA that we have not verified and that now appear in the app AND the downloadable report:
   `vehicle`: "Hail damage to cars is AXA's largest share of storm claims." and
   `critical_equipment_low`: "(see AXA XL resilience report)". Either confirm with a source
   or soften, e.g. "Hail damage to parked cars is a frequent, costly storm claim." (needs the
   user's OK, since objects.py is protected).
3. **.gitignore (FYI):** `eval/*.mp4` is ignored, so `eval/test_walk.mp4` (used by the
   `?demo=1` fallback button) is not in the repo for the teammate; they must run
   `python tools/make_test_video.py` once. The app hides the button if the file is missing.

## Agent 3: Proof for the pitch

1. **app.py + sitecheck.py: pass a file path, not bytes (memory for 300 MB phone videos).**
   New public function: `video.keyframes_from_path(path, k)` (same return shape as `keyframes`).
   Today the app does `v_up.getvalue()` (300 MB bytes) and `video.keyframes` writes them to a
   temp file again; peak memory measured 536 MB for the 302 MB iPhone file.
   Suggested: in app.py copy the upload to a temp file in chunks
   (`shutil.copyfileobj(v_up, tmp)`, suffix = lower-cased extension), give `sitecheck.run`
   an optional `video_path=` argument that calls `video.keyframes_from_path(video_path, k)`
   instead of `video.keyframes(video_bytes, k, suffix)`, and delete the temp file in `finally`.
   Optional: the bytes path still works; this is only about memory.
2. **app.py: check that the uploader accepts `IMG_1420.MOV` (uppercase extension).**
   `video.keyframes` now lower-cases any suffix (".MOV", "MOV", "" all work, tested), but I could
   not verify whether Streamlit's `file_uploader(type=["mp4","mov",...])` accepts an uppercase
   file name in the browser. Please try the real file once in the app (UNVERIFIED).
3. **.gitignore: add `eval/frames*/` and `eval/benchmark_video*/`.**
   `eval/*.jpg` does not match sub-folders, and real site frames (even with people blurred)
   should never be committed by accident. The test-walk frames in `eval/frames_test_walk/`
   come from the public Ultralytics sample photo and are fine to keep locally.
4. **README.md: short "Proof for the pitch" section** (text you can paste):
   > Video decoding: on a Mac the app uses Apple's hardware decoder (AVFoundation) and falls back
   > to FFmpeg. Measured on an M2 with a 47 s 4K 60 fps HEVC iPhone clip (302 MB): 37 s before,
   > 10-12 s now, frames upright (rotation tag applied).
   > Benchmark: `python tools/benchmark_video.py --from-video walk.MOV eval/frames` makes frames
   > (people blurred) and a label template; fill in y/n; try it free with
   > `FRUGAL_MOCK=1 python tools/benchmark_video.py eval/frames eval/frames/labels_template.csv`,
   > then run without FRUGAL_MOCK for real numbers (it prints a cost estimate first).
5. **config.py (Agent 1's file), FYI only:** `config.PRICES` has no entry for
   `google/gemini-2.5-flash` (currently the strong model). The benchmark's cost *estimate*
   then falls back to Claude Sonnet prices, so it over-estimates. Real runs use OpenRouter's
   reported cost, so this only affects estimates. Add the verified price if you have it.
