# Frugal Site Check

## What it does

Frugal Site Check helps a business owner prepare a property for hail and flooding.

The user enters an address and films about one minute while walking around the site.
The app returns:

- the main hail and water risks at that address;
- the parts of the property that need attention;
- a short list of things to do before the next storm;
- improvements to plan for this year;
- photos and boxes showing the evidence behind each recommendation.

The result is designed to be useful to a customer, an insurer, or someone preparing a site visit.

## Why it is frugal

The app does not send an entire video for processing.

1. The address is checked against official Swiss hazard maps.
2. Local video processing removes dark, blurry, and repeated frames.
3. People are blurred before images leave the computer.
4. Only a few useful frames are selected.
5. The map determines which weaknesses matter at that location.
6. A second review is requested only when an important finding is unclear.
7. Clear rules turn the findings into recommendations and a site score.

This keeps the result explainable, reduces upload size, and records the real processing cost.
Repeated checks are served from the cache.

## Run the website

Requirements:

- Python 3.10 or newer
- Node.js 18.18 or newer
- FFmpeg for video decoding

Install the dependencies:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd web
npm install
npm run build
cd ..
```

Create a local `.env` file with your OpenRouter key:

```text
OPENROUTER_API_KEY=your_key_here
```

Never commit `.env`. It is already ignored by Git.

Start the website:

```powershell
uvicorn server:app --port 8000
```

Open [http://localhost:8000/](http://localhost:8000/).

The main page is for a property owner. The **Assessment details** page shows the selected frames,
the map reasoning, the evidence, the usage, and the limitations.

For frontend development, run this from `web/`:

```powershell
npm run dev
```

Then open [http://localhost:3000/](http://localhost:3000/). The API still runs on port 8000.

## Project structure

- `server.py` — web server and upload API.
- `web/` — the customer website.
- `frugal/geo.py` — address lookup and Swiss hazard maps.
- `frugal/video.py` — frame selection and filmstrip creation.
- `frugal/detect.py` — local object detection and people blurring.
- `frugal/objects.py` — the catalogue of property weaknesses and advice.
- `frugal/sitecheck.py` — the full inspection workflow.
- `frugal/score.py` — deterministic scoring and recommendations.
- `frugal/ledger.py` — processing usage and cost tracking.
- `tests/` — offline tests.

## Demo checklist

1. Use a real address with a known hail or flood risk.
2. Film in landscape at 1080p.
3. Walk slowly and pause briefly at roofs, doors, windows, car parks, and basement openings.
4. Run the check once before presenting so the repeat run is instant.
5. Show one result, one evidence frame, and one recommendation rather than every screen.

The storm-warning switch is a presentation aid and is labelled as simulated.

## Current limitations

- The inspection can only judge what the camera can see.
- One walk-around video cannot prove the condition of a roof or anything behind a wall.
- The local detector may not understand whether a vehicle is protected by a roof.
- People are blurred, but number plates still need a separate privacy review.
- The national flood maps are useful for triage but are not a replacement for detailed local maps.
- The recommendations and weights are assumptions that AXA should tune with real inspection data.

## The technical idea

This is a multimodal web application: text from the address is combined with images extracted from
the user's video. The system uses a small first pass and escalates only important uncertain findings.

The current OpenRouter setup is:

- `qwen/qwen3-vl-8b-instruct` — primary vision model;
- `openai/gpt-4o` — selective escalation for important uncertain findings;
- `google/gemini-2.5-flash-lite` — optional comparison model.

The website records which steps ran, what evidence was found, and how much processing was used.

The goal is not to replace an expert. It is to make the first prevention check faster, clearer, and
more consistent.
