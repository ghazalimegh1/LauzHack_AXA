# Frugal Site Check

**Film one minute around a business site. Official Swiss hazard maps decide what we look for,
free code picks a few sharp frames, a free local detector finds vehicles and blurs people,
and a small AI model finds what hail or water would hit first.**
The expensive model only sees the frames that are still unclear. Built for the AXA challenge
"Frugal use of Multimodal AI" at LauzHack 2026.

- **Input:** an address (text) + a walk-around video (or one photo) = multimodal.
- **Output for the customer:** the key frames with boxes on each object, how important each one is
  at this address, a "do now before the storm" list and a "fix this year" list.
- **Output for AXA:** a site score, a recommended action (no action / send tips / on-site check)
  and a cost ledger showing what every step cost.

## The cascade (why it is frugal)

| Step | What happens | Cost |
|---|---|---|
| 1 | Address -> coordinates -> hazard maps (geo.admin.ch, BAFU, MeteoSwiss) | free, cached |
| 2 | Video -> ~6 key frames: 2 frames/s sampled, dark, blurry and repeated views dropped | free |
| 3 | Local detector (YOLO11n, 5 MB) finds vehicles and people; **people blurred before upload** | free |
| 4 | Map picks which object types to look for. Nothing elevated -> **stop, no AI** | free |
| 5 | Small model: **all key frames in one call**, 512 px, compact JSON with boxes | small |
| 6 | Strong model: **only frames the small model was unsure about**, 768 px | only when needed |
| 7 | Fixed rules: importance = object weight x hazard level; advice; site score | free |

Every AI answer is cached, so repeating a demo costs nothing. The app shows the estimated cost
next to a naive design (one full-HD frame per second to the strong model): for a 60 s video
about 1,000x cheaper. Both sides use Claude's rule of one token per 28x28 pixels.

Importance (0-6): >= 4 high, 2-3 medium, 1 low, 0 not relevant at this address.
Low-confidence objects are shown as "uncertain" and not counted: a person should check them.

## Files you will touch most

- `frugal/objects.py` – **the catalogue**: what to look for, hazard group, weight, why, "do now", "fix later". Tune texts and weights here.
- `frugal/video.py` – key-frame picking and the filmstrip image.
- `frugal/detect.py` – free local detector and people blurring.
- `frugal/sitecheck.py` – the video cascade and the box drawing.
- `frugal/vision.py` – the only code that calls a paid model (Claude API or OpenRouter).

## Setup (about 10 minutes)

1. Install Python 3.10 or newer from python.org (on macOS you may already have it: type `python3 --version` in Terminal).
2. Open a terminal in this folder and run:
   ```
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   With the **fish** shell use `source .venv/bin/activate.fish` instead.
   The first video run downloads the 5 MB detector model into `models/`.
3. Copy `.env.example` to `.env` and put ONE key in: `ANTHROPIC_API_KEY=` (Claude API, used first)
   or `OPENROUTER_API_KEY=`.
   **Never commit `.env`** (it's already in `.gitignore`). Without a key the app runs in MOCK mode with fake answers.
4. Start the app: `streamlit run app.py` → it opens in your browser.

## First things to run at the hackathon

```
python -m pytest -q                                   # 25 offline tests, should all pass
python tools/make_test_video.py                       # writes eval/test_walk.mp4 for a quick demo
python tools/check_models.py                          # are the two model IDs available? prices?
python tools/check_layers.py "Gerberngasse 10, Bern"  # do the hazard layers answer?
```

**Checked on 2026-11-21 (re-check if something breaks):**
- **Models (OpenRouter).** Cheap `google/gemini-2.5-flash-lite`, strong `google/gemini-2.5-flash`,
  naive baseline for the cost comparison `google/gemini-2.5-pro`. Claude Haiku on OpenRouter is
  `anthropic/claude-haiku-5.5` (dot, not dash). On two public site photos Gemini flash-lite drew
  tight, correct boxes; Claude Haiku's boxes were misplaced or loose. Gemini 2.5 Flash drew the same
  boxes as Pro at about 1/5 of the cost. Only 2 photos: re-check with a real site video.
- **Hidden "thinking" is switched off** (or capped at 128 tokens for Gemini Pro, which cannot turn it
  off). With it on, Haiku spent its whole output budget thinking and returned nothing.
- **Hazard maps** are read with the federal WMS (`wms.geo.admin.ch`, GetFeatureInfo), free and cached.
  The older REST "identify" endpoint answers "No GeoTable was found" for these layers.
  Route Cantonale 11, Lausanne: hail 3.5 cm (medium), no flood zone (water low).
  Gerberngasse 10, Bern: inside Aquaprotect 100 + 500 (water high), hail 4 cm (high).
  Hail values are in cm (MeteoSwiss legend). **Our assumption:** >= 3 cm = medium, >= 4 cm = high.
  The flood layers only say "inside the zone", not how deep.
- **Hail layer ID.** The 50-year hail-size layer still answers. The STAC collection
  `ch.meteoschweiz.ogd-radar-derived-grid` is a downloadable hail climatology, not needed here.
- **Box formats.** Gemini models answer boxes as [ymin, xmin, ymax, xmax] 0-1000, others are asked
  for [xmin, ymin, xmax, ymax]; the parser also accepts fractions, pixels, dict boxes, renamed keys
  and replies that were cut off. Override with `BOX_ORDER=xy` or `yx` in `.env` if a new model draws
  boxes in the wrong place.
- `check_layers.py` shows the raw map answer; the *Raw map attributes* box in the AXA view shows it live.

## Proof for the pitch

- **Video decoding.** On a Mac the app uses Apple's hardware decoder (AVFoundation) and falls back to
  FFmpeg. Measured on an M2 with a 47 s 4K 60 fps HEVC iPhone clip (302 MB): 37 s before, 10-12 s now,
  frames upright (rotation tag applied). Windows/Linux use FFmpeg only (slower, ~37 s per minute of 4K60).
  Uploads are copied to a temp file, so a 300 MB video is not held in memory twice.
- **Benchmark (accuracy vs cost).**
  ```
  python tools/benchmark_video.py --from-video walk.MOV eval/frames      # frames (people blurred) + label template
  FRUGAL_MOCK=1 python tools/benchmark_video.py eval/frames eval/frames/labels_template.csv   # free dry run
  python tools/benchmark_video.py eval/frames eval/frames/labels_template.csv                 # real, prints a cost estimate first
  ```
  Fill in `present` (y/n) in the template first. Output: a table, a CSV and `chart.png` for the slides.
  Estimated cost of a real run (all three designs, upper bound): ~$0.02 for 40 frames with Gemini,
  ~$0.11 with Claude Haiku/Sonnet. Mock charts are stamped "MOCK" and are not for the slides.
- **Report.** "Download report" on the Site check tab saves a one-page HTML report (prints to one A4 page).
- **Demo fallback.** Open the app as `http://localhost:8501/?demo=1` to get a "Run sample video" button.
  `eval/test_walk.mp4` is not in git: run `python tools/make_test_video.py` once. It is a pan over a bus,
  so use a real, pre-run site video for the actual demo.

## The pieces, in plain words

- `frugal/config.py` – all settings: which models, image sizes, thresholds. Change things here, not in the logic.
- `frugal/geo.py` – turns an address into Swiss coordinates and asks the federal map service what lies at that point. Converts coordinates itself, because the API once swapped its x/y fields.
- `frugal/hazards.py` – reads the map answers and turns them into one level per group: low, medium or high.
- `frugal/checklist.py` – the list of weak points to look for (light wells, low doors, blinds, skylights...) and the tip for each. Each question belongs to "water" or "hail" and is only asked if that hazard is elevated.
- `frugal/photo.py` – free photo checks (too dark, blurry, small) and shrinking the image before sending it, because image size drives token cost.
- `frugal/vision.py` – the only code that calls a paid model. Asks for a tiny JSON answer and handles messy replies. In MOCK mode it returns fake answers.
- `frugal/score.py` – plain rules for score, action and tips, so an underwriter can see exactly why.
- `frugal/ledger.py` – records every step with tokens, cost and time.
- `frugal/pipeline.py` – runs the steps in order and stops as early as possible.
- `app.py` – the web app: Site check (video), Single photo, AXA view, How it works.
- `tools/benchmark.py` – accuracy vs cost on your own labelled photos (see below).

## The pitch chart: do this by hour 16

1. Take 20–40 photos of real houses (your own, friends', street views you're allowed to use).
2. Fill in `eval/labels.csv` like `eval/labels_example.csv`: hazard levels plus the true y/n per question.
3. Run `python tools/benchmark.py`. It compares always-cheap, always-strong and the cascade on accuracy and total cost.

If the cascade gets close to the strong model's accuracy at a fraction of its cost, that's your headline.
The "Also run the naive baseline" checkbox in the sidebar shows the same comparison live for one photo.

## Splitting the work (2 people)

- **Person A – data & logic:** run the check scripts, fix `hazards.py` if needed, tune the questions and tips in `checklist.py`, run the benchmark.
- **Person B – app & pitch:** collect and label photos, polish `app.py` (texts, layout), write the 2-minute demo script, record a backup video.
- Both commit to the same GitHub repo, so the history shows both contributions.

## Demo tips

- Film in landscape at 1080p, walk slowly, pause 1-2 s on each roof, car park, door and basement window.
- Use a real address with elevated hail or water hazard, or the developer switch "simulate hazard levels".
- Turn on "Storm warning active (simulated)" to show the "do now" list. It is simulated: say so.
- Run it once before presenting: the second run comes from the cache, so it is instant and free.

## Honest limits (say them in the pitch)

- The app only judges what the camera sees: not roof strength, not what is behind walls.
- The local detector cannot tell whether a car stands under a roof; check the boxes.
- People are blurred; number plates are not yet. Frames are not stored. A data-protection review would be needed.
- Weights in `objects.py` are our assumption for AXA to tune.

- Aquaprotect is a coarse national flood overview and ignores existing protection; detailed cantonal hazard maps are better.
- One photo can't show every side of a house; unclear answers are reported as unclear, not guessed.
- This supports prevention and triage. It does not set premiums: Swiss natural-hazard insurance is pooled and solidarity-based.

Data: BAFU (Aquaprotect, surface runoff hazard map), MeteoSwiss (hail hazard), swisstopo / geo.admin.ch.
