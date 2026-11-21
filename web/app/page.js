"use client";
// The customer app: a business owner films their site and gets a storm plan they can tick off.
// Three screens: start (address + video), progress (real steps), result (the plan).
// No costs, models or tables here: those are on the details page (/demo.html).
import { useEffect, useState } from "react";
import AddressField from "../components/AddressField";
import Forecast, { useForecast } from "../components/Forecast";
import Progress from "../components/Progress";
import VideoPicker from "../components/VideoPicker";
import { Chip, Eyebrow, Hero, Tag, TopBar, VideoPlayer } from "../components/ui";
import { cropUrl, getInfo, getLatest, retryCheck, runCheck } from "../lib/api";
import { COLOURS, riskText } from "../lib/format";

// The rules in frugal/score.py name an action for AXA; the customer gets it in plain words.
const HEADLINES = {
  "Propose an on-site prevention check": "Have your site checked before the next storm",
  "Send targeted prevention tips": "A few simple steps will protect your site",
  "No action needed": "Nothing urgent for this site",
};
const MAX_NOW = 5;   // more than five "do now" items would not get done before a storm
const WARNING_LEAD_S = 90 * 60;   // the demo storm arrives 90 minutes after it is switched on

// Example storm for the "Show a storm warning (demo)" button, so the warning screen can be
// shown on a calm day. Made-up values, always labelled "simulated" on screen.
function simulatedStorm(switchedOn) {
  const starts = switchedOn + WARNING_LEAD_S;
  return { ok: true, hours: 48, storm: {
    kind: "hail storm", starts, ends: starts + 3600, severity: "severe", hail: "heavy",
    gust_kmh: 80, wind: "gale-force gusts", rain_mm: 20 } };
}

export default function CustomerApp() {
  const [colours, setColours] = useState(COLOURS);
  const [check, setCheck] = useState(null);       // { jobId, result }
  const [screen, setScreen] = useState("start");  // start | busy | result
  const [stage, setStage] = useState(null);       // step the server is on, while busy
  const [error, setError] = useState("");
  const [address, setAddress] = useState("Route Cantonale 11, 1015 Lausanne");
  const [file, setFile] = useState(null);

  useEffect(() => {
    getInfo().then((i) => i.colours && setColours(i.colours))
      .catch(() => setError("The service is not reachable right now. Please try again later."));
    getLatest().then((c) => { if (c) { setCheck(c); setScreen("result"); } }).catch(() => {});
  }, []);

  // One place for "run a check and show the result": used by the form and by "Try again".
  async function run(start) {
    setScreen("busy");
    setStage(null);
    setError("");
    window.scrollTo(0, 0);
    try {
      setCheck(await start(setStage));
      setScreen("result");
    } catch (e) {
      setError(e.message);
      setScreen("start");
    }
  }

  function submit(e) {
    e.preventDefault();
    const form = new FormData();
    form.append("address", address.trim());
    form.append("video", file);
    run((onStage) => runCheck(form, onStage));
  }

  return (
    <main className="page app">
      <TopBar />
      {screen === "start" && (
        <Start address={address} setAddress={setAddress} file={file} setFile={setFile}
               error={error} onSubmit={submit} />
      )}
      {screen === "busy" && <Busy stage={stage} />}
      {screen === "result" && check && (
        <Result check={check} colours={colours}
                onRetry={() => run((onStage) => retryCheck(check.jobId, onStage))}
                onNew={() => { setFile(null); setScreen("start"); window.scrollTo(0, 0); }} />
      )}
      <footer className="foot no-print">
        <a href="/demo.html">View assessment details</a>
      </footer>
    </main>
  );
}

// ---------------- screen 1: start ----------------
function Start({ address, setAddress, file, setFile, error, onSubmit }) {
  return (
    <>
      <Hero eyebrow="AXA storm check" title="Is your business ready for the next storm?">
        <p>Film a one-minute walk around your site. You get a plan of what to protect first.</p>
      </Hero>
      <section className="how">
        <ol className="how-steps">
          <li><b>1</b><span>Enter your address</span></li>
          <li><b>2</b><span>Film a slow walk around the site</span></li>
          <li><b>3</b><span>Get your storm plan in about a minute</span></li>
        </ol>
      </section>
      <form className="app-card start-form" onSubmit={onSubmit}>
        <AddressField value={address} onChange={setAddress} />
        <div className="field">
          <span>Video of your site</span>
          <VideoPicker file={file} onFile={setFile} />
        </div>
        <details className="tips">
          <summary>Tips for a good video</summary>
          <ul>
            <li>Walk slowly, about one minute is enough.</li>
            <li>Show every side: roof edges, windows, entrances and the car park.</li>
            <li>Daylight works best, but evening videos work too.</li>
            <li>People in the video are blurred before any picture is analysed.</li>
          </ul>
        </details>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="button button--wide" type="submit" disabled={!file || !address.trim()}>
          Check my site
        </button>
      </form>
    </>
  );
}

// ---------------- screen 2: progress ----------------
function Busy({ stage }) {
  return (
    <>
      <Hero eyebrow="Please wait" title="Checking your site">
        <p>This usually takes less than a minute. You can keep this page open.</p>
      </Hero>
      <section className="app-card">
        <Progress stage={stage} />
      </section>
    </>
  );
}

// ---------------- screen 3: the plan ----------------
// Ticked items are remembered in this browser only (per check), so the plan survives a reload.
function useTicks(jobId) {
  const key = `site-check-done-${jobId}`;
  const [done, setDone] = useState([]);
  useEffect(() => {
    try { setDone(JSON.parse(localStorage.getItem(key)) || []); } catch { setDone([]); }
  }, [key]);
  function toggle(kind) {
    const next = done.includes(kind) ? done.filter((k) => k !== kind) : [...done, kind];
    setDone(next);
    try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* private mode: fine */ }
  }
  return [done, toggle];
}

function Result({ check, colours, onRetry, onNew }) {
  const r = check.result;
  const now = r.result.items.filter((i) => i.now).slice(0, MAX_NOW);
  const later = r.result.items.filter((i) => i.later);
  const forecast = useForecast(check.jobId);
  const [done, toggle] = useTicks(check.jobId);
  const [storm, setStorm] = useState(null);       // when the demo warning was switched on
  const ticked = now.filter((i) => done.includes(i.kind)).length;
  const list = (items, text) => (
    <ActionList items={items} text={text} jobId={check.jobId} colours={colours}
                done={text === "now" ? done : null} toggle={toggle} />
  );

  if (storm) {
    return (
      <div className="fade" key={`${check.jobId}-storm`}>
        <section className="storm">
          <Eyebrow>Storm warning (demo)</Eyebrow>
          <h2>Do this now</h2>
          <Forecast data={simulatedStorm(storm)} simulated />
          {list(now, "now")}
          <button className="link no-print" onClick={() => setStorm(null)}>Back to my plan</button>
        </section>
      </div>
    );
  }

  return (
    <div className="fade" key={check.jobId}>
      <Headline r={r} />

      {r.warning && (
        <section className="app-card notice no-print" role="status">
          <p><b>Part of the check could not run.</b> The analysis service was busy, so only
            vehicles were checked. Your video is still here.</p>
          <button className="button" onClick={onRetry}>Try again</button>
        </section>
      )}

      <section className="block">
        <h2>Before a storm</h2>
        {now.length > 0 && (
          <div className="score" aria-label={`${ticked} of ${now.length} done`}>
            <span>{ticked === now.length ? "All done. Well prepared!" : `${ticked} of ${now.length} done`}</span>
            <span className="score-bar"><i style={{ width: `${(ticked / now.length) * 100}%` }} /></span>
          </div>
        )}
        {list(now, "now")}
      </section>

      <section className="block">
        <h2>Next storm at your site</h2>
        <Forecast data={forecast} />
        <p className="caption">Live weather forecast for the next 48 hours (Open-Meteo), updated every 10 minutes.</p>
        <button className="link no-print" onClick={() => setStorm(Math.floor(Date.now() / 1000))}>
          Show a storm warning (demo)
        </button>
      </section>

      {later.length > 0 && (
        <section className="block">
          <h2>Fix this year</h2>
          {list(later, "later")}
        </section>
      )}

      <section className="block no-print">
        <h2>Your video</h2>
        <VideoPlayer jobId={check.jobId} />
      </section>

      {r.result.uncertain.length > 0 && (
        <p className="quiet">A few things in the video were unclear: an expert should take a look.</p>
      )}

      <section className="actions no-print">
        <button className="button" onClick={() => window.print()}>Save as PDF</button>
        <button className="button button--ghost" onClick={onNew}>Check another site</button>
      </section>
    </div>
  );
}

function Headline({ r }) {
  const where = r.place ? r.place.label : r.address;
  if (!r.map_ok) {
    return (
      <Hero eyebrow="Your storm plan" title="We could not reach the official hazard maps">
        <p>Please try again in a few minutes. Address: {where}</p>
      </Hero>
    );
  }
  return (
    <Hero eyebrow="Your storm plan" title={HEADLINES[r.result.action] || r.result.action}>
      <p>{where}</p>
      <div className="chips">
        <Chip>Hail risk here: {riskText(r.hazards.hail)}</Chip>
        <Chip>Water risk here: {riskText(r.hazards.water)}</Chip>
      </div>
    </Hero>
  );
}

// One card per thing found: its photo from the video, what to do, and why it matters.
// text = "now" (before a storm, with a tick box) or "later" (fix this year).
function ActionList({ items, text, jobId, colours, done, toggle }) {
  if (!items.length) return <p className="muted">Nothing in your video needs action before a storm.</p>;
  return (
    <ul className="now">
      {items.map((i) => {
        const isDone = done && done.includes(i.kind);
        return (
          <li key={i.kind} className={`now-card ${isDone ? "now-card--done" : ""}`}>
            {i.object_id !== null
              ? <img src={cropUrl(jobId, i.object_id)} alt={i.name} />
              : <span className="no-photo" />}
            <div className="now-text">
              <p className="now-title">{i.name} <Tag label={i.label} colours={colours} /></p>
              <p>{i[text]}</p>
              <details className="why">
                <summary>Why?</summary>
                <p>{i.why}</p>
              </details>
            </div>
            {done && (
              <label className="tickbox no-print">
                <input type="checkbox" checked={isDone} onChange={() => toggle(i.kind)} />
                <span>{isDone ? "Done" : "Mark done"}</span>
              </label>
            )}
          </li>
        );
      })}
    </ul>
  );
}
