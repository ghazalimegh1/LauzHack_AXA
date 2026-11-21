"use client";
// The assessment details page: image processing, the map's role, and efficiency.
// Every number and box here comes from the real run (via the API); nothing is hard-coded.
import { useEffect, useState } from "react";
import CheckForm from "../../components/CheckForm";
import { Chip, Eyebrow, Hero, Spinner, Tag, VideoPlayer } from "../../components/ui";
import { frameUrl, getInfo, getLatest, runCheck, stripUrl } from "../../lib/api";
import { COLOURS, GROUP_NAMES, riskText, times, usd } from "../../lib/format";

const LEVELS = ["low", "medium", "high"];

export default function DemoPage() {
  const [info, setInfo] = useState(null);
  const [check, setCheck] = useState(null);      // { jobId, result }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [settings, setSettings] = useState({ k: 6, detector: true, simulate: false, water: 1, hail: 2 });

  useEffect(() => {
    document.title = "Site Check: assessment details";
    getInfo().then((i) => { setInfo(i); setSettings((s) => ({ ...s, k: i.keyframes, detector: i.detector })); })
      .catch(() => setError("The server did not answer. Is it running?"));
    getLatest().then((c) => c && setCheck(c)).catch(() => {});
  }, []);

  async function onSubmit(address, file) {
    const form = new FormData();
    form.append("address", address);
    form.append("video", file);
    form.append("k", settings.k);
    form.append("use_detector", settings.detector ? "1" : "0");
    form.append("simulate", settings.simulate ? "1" : "0");
    form.append("levels", JSON.stringify({ water: settings.water, hail: settings.hail }));
    setBusy(true);
    setError("");
    try {
      setCheck(await runCheck(form));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const colours = (info && info.colours) || COLOURS;
  return (
    <main className="page">
      <header className="top">
        <span className="brand">Site Check <span className="muted">· assessment details</span></span>
        <span className="top-right"><a href="/">Customer view</a><b className="axa">AXA</b></span>
      </header>

      <Hero eyebrow="Assessment details" title="How the check works">
        <p>Official hazard maps and privacy-first image processing help identify what to protect.</p>
      </Hero>

      <section className="form-card">
        <CheckForm onSubmit={onSubmit} busy={busy} buttonText="→  Analyse site">
          <Settings settings={settings} setSettings={setSettings} info={info} />
        </CheckForm>
        {busy && <Spinner>Picking frames, detecting objects, checking the maps...</Spinner>}
        {error && <p className="error">{error}</p>}
      </section>

      {check && <Results check={check} colours={colours} />}
    </main>
  );
}

function Settings({ settings, setSettings, info }) {
  const set = (key) => (e) =>
    setSettings({ ...settings, [key]: e.target.type === "checkbox" ? e.target.checked : Number(e.target.value) });
  return (
    <div className="settings">
      <label className="field">
        <span>Key frames: {settings.k}</span>
        <input type="range" min="4" max="10" value={settings.k} onChange={set("k")} />
      </label>
      <label className="check">
        <input type="checkbox" checked={settings.detector} onChange={set("detector")}
               disabled={info && !info.detector} />
        Free local detector (finds vehicles, blurs people)
      </label>
      <label className="check">
        <input type="checkbox" checked={settings.simulate} onChange={set("simulate")} />
        Simulate hazard levels (skips the map)
      </label>
      {settings.simulate && (
        <div className="row">
          {["water", "hail"].map((g) => (
            <label className="field" key={g}>
              <span>{GROUP_NAMES[g]}</span>
              <select value={settings[g]} onChange={set(g)}>
                {LEVELS.map((name, i) => <option key={name} value={i}>{name}</option>)}
              </select>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function Results({ check, colours }) {
  const r = check.result;
  return (
    <div className="fade" key={check.jobId}>
      {r.mock && <p className="note">This result is illustrative and not a final assessment.</p>}
      {r.warning && <p className="error">{r.warning}</p>}
      <section className="block">
        <Eyebrow>Step 0 · the upload</Eyebrow>
        <h2>The uploaded video</h2>
        <p className="lead">Shown for reference only. The assessment uses the selected key frames below.</p>
        <VideoPlayer jobId={check.jobId} />
      </section>
      <Frames check={check} />
      <Found check={check} colours={colours} />
      <MapDecision r={r} />
      <Cost r={r} />
      <Limits />
    </div>
  );
}

// 1. Free code turns thousands of video frames into a handful.
function Frames({ check }) {
  const f = check.result.frugal;
  const numbers = [
    [f.video_frames, "frames in video"], [f.sampled, "checked by free code"],
    [f.picked, "key frames picked"], [f.images_sent, "images assessed"],
  ];
  return (
    <section className="block">
      <Eyebrow>Step 1 · free code</Eyebrow>
      <h2>Frames</h2>
      <p className="lead">Dark, blurry and repeated views are removed before the assessment.</p>
      <div className="numbers">
        {numbers.map(([n, label]) => (
          <div key={label}><b>{Number(n).toLocaleString("en")}</b><span>{label}</span></div>
        ))}
      </div>
      <img className="strip" src={stripUrl(check.jobId)} alt="All checked frames; picked ones outlined in green" />
      <p className="caption">Green = picked. Grey = skipped. This step is fully automatic.</p>
    </section>
  );
}

// 2. The key frames with the boxes the detector and the models really returned.
function Found({ check, colours }) {
  const [open, setOpen] = useState(null);
  const r = check.result;
  // People are only found to be blurred; listing each one would bury the real findings.
  const shown = r.objects.filter((o) => o.label !== "privacy");
  const people = r.objects.length - shown.length;
  useEffect(() => {
    const close = (e) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  return (
    <section className="block">
      <Eyebrow>Step 2 · image processing</Eyebrow>
      <h2>What the camera found</h2>
      <p className="lead">Objects are identified in the selected frames, and people are blurred before upload.</p>
      <div className="frames">
        {r.frames.map((f) => (
          <button key={f.n} className="frame" onClick={() => setOpen(f.n)}>
            <img src={frameUrl(check.jobId, f.n)} alt={`Key frame ${f.n}`} />
            <span>#{f.n} · {f.t} s</span>
          </button>
        ))}
      </div>
      <div className="legend">
        {Object.keys(colours).map((label) => <Tag key={label} label={label} colours={colours} />)}
      </div>
      {shown.length ? (
        <table>
          <thead><tr><th>Object</th><th>Frame</th><th>Importance</th><th>Confidence</th><th>Found by</th></tr></thead>
          <tbody>
            {shown.map((o) => (
              <tr key={o.id}>
                <td>{o.id} {o.name}</td><td>#{o.frame}</td>
                <td><Tag label={o.label} colours={colours} /></td>
                <td>{Math.round(o.conf * 100)}%</td><td>{o.by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">Nothing relevant was found in the key frames.</p>}
      {people > 0 && <p className="caption">{people} people were found and blurred on this computer before upload.</p>}
      {open !== null && (
        <div className="lightbox" onClick={() => setOpen(null)} role="dialog">
          <img src={frameUrl(check.jobId, open)} alt={`Key frame ${open}, large`} />
        </div>
      )}
    </section>
  );
}

// 3. The official map decides which risks matter at this address.
function MapDecision({ r }) {
  return (
    <section className="block">
      <Eyebrow>Step 3 · official hazard maps</Eyebrow>
      <h2>How the map decided</h2>
      <p className="lead">Only object types that matter at this address are included in the assessment.</p>
      <div className="two">
        {["hail", "water"].map((g) => {
          const h = r.hazards[g];
          return (
            <div className="card" key={g}>
              <h3>{GROUP_NAMES[g]}: {h.answered ? h.level_name : "map unavailable"}</h3>
              <p className="muted small">{h.sources.join(" · ") || "No mapped hazard zone at this point"}</p>
            </div>
          );
        })}
      </div>
      <p className="label">Risk factors checked</p>
      <div className="chips">
        {r.asked.length
          ? r.asked.map((a) => <Chip key={a.kind}>{a.name}</Chip>)
          : <span className="muted">Nothing: no elevated hazard was found at this address.</span>}
      </div>
      {r.simulated_levels && <p className="muted small">Hazard levels were simulated for this run.</p>}
    </section>
  );
}

// 4. Our cost next to two baselines, all estimated with the same rule.
function Cost({ r }) {
  const f = r.frugal;
  const fromCache = r.ledger.some((s) => s.kind === "ai" && s.note.includes("cache"));
  const measured = r.mock ? "illustrative" : fromCache ? "repeat run, from cache" : "measured";
  const bars = [
    ["Our cascade (estimate)", f.ours_usd_est, ""],
    [`Same frames, ${f.baseline_model} (fair)`, f.same_frames_strong_usd, times(f.same_frames_strong_usd, f.ours_usd_est)],
    [`1 HD frame per second, ${f.baseline_model} (naive)`, f.naive_usd, times(f.naive_usd, f.ours_usd_est)],
  ];
  const max = Math.max(...bars.map((b) => b[1]), 1e-12);
  return (
    <section className="block">
      <Eyebrow>Step 4 · efficiency</Eyebrow>
      <h2>Processing efficiency</h2>
      <p className="lead">Only the information needed for a clear assessment is processed.</p>
      <div className="numbers">
        <div><b>{usd(r.totals.usd)}</b><span>this check, {measured}</span></div>
        <div><b>{usd(f.ours_usd_est)}</b><span>our estimate</span></div>
        <div><b>{r.totals.ai_calls}</b><span>assessment calls</span></div>
      </div>
      <div className="bars">
        {bars.map(([label, value, mult]) => (
          <div className="bar-row" key={label}>
            <span className="bar-label">{label}</span>
            <span className="bar"><i style={{ width: `${Math.max(0.6, (value / max) * 100)}%` }} /></span>
            <span className="bar-value">{usd(value)} <em>{mult}</em></span>
          </div>
        ))}
      </div>
      <table className="ledger">
        <thead><tr><th>Step</th><th>Type</th><th>Usage</th><th>Cost</th><th>Time</th></tr></thead>
        <tbody>
          {r.ledger.map((s, i) => (
            <tr key={i}>
              <td>{s.name}{s.note && <small className="muted"> · {s.note}</small>}</td>
              <td>{s.kind === "ai" ? "assessment" : s.kind}</td>
              <td>{(s.tok_in + s.tok_out).toLocaleString("en")}</td><td>{usd(s.usd)}</td><td>{s.ms} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="caption">
        Usage estimates are based on image size and the service usage report.
      </p>
    </section>
  );
}

function Limits() {
  return (
    <section className="block">
      <Eyebrow>Limits</Eyebrow>
      <h2>Honest limits</h2>
      <ul className="limits">
        <li>It only judges what the camera sees: not roof strength, not what is behind walls.</li>
        <li>Not seen does not mean safe: a missing box is not a clean bill of health.</li>
        <li>Unclear frames are escalated for additional review.</li>
      </ul>
    </section>
  );
}
