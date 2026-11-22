# Frugal Site Check

LauzHack 2026 · AXA challenge "Frugal use of Multimodal AI".

A business owner films a short walk around their site and enters the address. The app
tells them what a storm would hit first, and what to do about it. Free code does most of
the work. Paid AI only looks where the official hazard map says it matters, and costs
about a tenth of a US cent per check.

## Start it

You need Python 3.9 with the `.venv` folder, Node.js, and an OpenRouter key.

1. Put the key in a file called `.env` in this folder (copy `.env.example`):
   `OPENROUTER_API_KEY=...`. `.env` is ignored by git and is never committed.
2. Build the website once (and again after every design change):

   ```bash
   cd web && npm install && npm run build && cd ..
   ```

3. Start the server:

   ```bash
   .venv/bin/python -m uvicorn server:app --port 8000
   ```

4. Open http://localhost:8000.

First time only: `.venv/bin/pip install -r requirements.txt`. The free detector needs
`models/yolo11n.pt` (5 MB, not in git); ultralytics downloads it if it is missing:
`.venv/bin/python -c "from ultralytics import YOLO; YOLO('models/yolo11n.pt')"`.

If `npm run build` sits at 0% CPU without printing anything: the project lives in an
iCloud-synced folder, and iCloud may have moved the files in `web/node_modules` to the cloud
(only placeholders stay on disk, and reading one waits for a download). Fix: `cd web && npm ci`
(reinstalls them from `package-lock.json` in a few seconds), then build again.

Tests (no internet, no AI cost):

```bash
.venv/bin/python -m pytest -q
```

## The two pages

- **`/` Customer app.** Address + video, then "Check my site". The result shows the action
  in plain words, the hail and water risk at the address, "Do this before a storm" cards, a live countdown to the next storm, "Fix
  this year" cards and the video. No costs, models or tables.
- **`/demo.html` Assessment details** (for the jury). The same check, opened up: key frames
  with boxes, the filmstrip of every sampled frame and why it was picked or skipped, cost
  per step, the comparison with bigger designs, how the map decided what to look for, and
  the confidence of every object. Its upload form has settings (key frames, detector,
  simulated hazard levels).

Both pages show the newest finished check.

## How a check works

| Step | What | Cost |
| --- | --- | --- |
| 1 | Address -> coordinates (geo.admin.ch), then the official hail and surface-water/flood maps at that point (geo.admin.ch WMS). Level 0-2 per hazard. If the map does not answer: "map unavailable", never "low". | free |
| 2 | Key frames (the team's earlier frame picker, ported): 2 frames per second; drop dark / overexposed / blurry ones, judged against the video's own median; "walking sharpness" clips street lamps and lets the weaker of the two edge directions count, because walking smears one direction; best frame of each equal part of the walk, unless a 32×18 miniature shows the same view as a frame already picked; brighten dim ones. Default 6. | free |
| 3 | YOLO11n on this computer finds vehicles and people: one look at 960 px (the size of our frames; only car / truck / bus / motorcycle / person, one box per object), plus a second people-only look at 640 px. A person either look finds is blurred before any image leaves the computer. Confidence from 35%, a vehicle counts from 50%. | free |
| 4 | The map decides what the AI looks for: only object types whose hazard is at least level 1. Vehicles are left to the free detector. | free |
| 5 | Cheap model `google/gemini-2.5-flash-lite`: all key frames in ONE call, 512 px images. The prompt asks for a tight box per object and one plain word for it ("pallets", "machine"); boxes are clamped to the picture and boxes under 3% of its width or height are dropped. Compact JSON, boxes on a 0-1000 grid, cut-off answers still give their complete objects. | paid |
| 6 | Strong model `google/gemini-2.5-flash`: only frames the cheap model was unsure about, 768 px. | paid |
| 7 | AI boxes copied from an earlier key frame (same kind, same box to the digit, on a different view) are dropped; our test set showed the AI sometimes repeats one frame's answer on a later frame. Repeats are merged: the same kind of object with heavily overlapping boxes in one frame, or in a key frame up to 1.5 s later, counts once (the most confident box is kept unchanged). Rules: importance = weight × hazard level; high ≥ 4, medium ≥ 2, low ≥ 1. Finds below 60% confidence (50% for the detector) are left out everywhere; the customer page only says that an expert should take a look. A close-up that is too small or too blurred to recognise is not shown; the label is shown alone. Action: on-site prevention check / targeted tips / no action. | free |

Busy or broken model answers are retried after 2 s and 5 s, then sent to a fallback
(flash-lite -> gemini-3.1-flash-lite -> gemini-2.5-flash). Answers are cached, so running
the same check again costs nothing extra; the page then still shows what the first run was
billed. "Fresh run" on the details page (or `POST /api/analyze?nocache=1`) asks the AI again.
The detector label shown everywhere comes from the weights file name
(`settings.DETECTOR_LABEL`). The storm countdown uses the free Open-Meteo forecast.

## Measured cost (2026-11-22, address "Route Cantonale 11, 1015 Lausanne", fresh AI answers)

The map gives hail level 1 (3.5 cm hailstones, 50-year) and water level 0 there, so the
AI only looks for skylights, solar panels, blinds and goods/machines.

| Video | AI calls | Cost (billed by OpenRouter) | Found |
| --- | --- | --- | --- |
| `IMG_2406.MOV` (daytime walk, 41 s) | 1 (Flash-Lite) | $0.00022 | parked cars (high); glass canopy, external blinds (medium); pallets and a machine at 23 s and 34 s (medium); 4 people blurred |
| `IMG_2408.MOV` (night walk, 24 s) | 2 (Flash-Lite, then Flash for 6 unclear frames) | $0.0012 | parked cars (high); equipment outside at 0 s and 6.5 s (medium) |
| `IMG_1420.MOV` (47 s, indoor room) | 2 | $0.00069 | nothing -> "No action needed" |

Before the computer-vision refinement (same day, same videos) the bills were $0.00031,
$0.0012 and $0.00080. Billed cost can include OpenRouter's discount for repeated input, so
the fair comparison is tokens: +38 prompt tokens per call (+2%), slightly shorter answers,
about 2% cheaper overall.

Same estimate rule for all three designs (night video): ours $0.0015, the same frames on
Gemini 2.5 Pro $0.0061 (about 4×), a naive 1 HD frame per second on Gemini 2.5 Pro $0.068
(about 46×).

## Files

- `server.py`: the web server (API + both pages, one port).
- `sitecheck/`: the analysis. `settings.py` (models, prices, thresholds), `catalogue.py`
  (what we look for, weights, advice), `hazard_map.py`, `frames.py`, `privacy.py`,
  `ai.py` (OpenRouter, retry, fallback, cache, estimate), `vision.py` (prompt),
  `rules.py`, `forecast.py`, `pipeline.py` (all steps + ledger), `render.py` (boxes, crops).
- `web/`: the Next.js website (plain JavaScript and CSS), built to `web/out`.
- `tests/`: offline tests.

## Limits

- Weights and the hail cut-offs (3 cm = level 1, 4 cm = level 2) are our team's assumptions.
- Jobs live in memory: restarting the server forgets them, and at most 5 are kept.
