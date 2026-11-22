"use client";

// Assessment details: how the check works, for the jury. Shows the newest finished check.

import { useEffect, useRef, useState } from "react";
import CheckForm, { Running } from "../../components/CheckForm";
import { HazardChips } from "../../components/Result";
import { Footer, Hero } from "../../components/Shell";
import Story from "../../components/Story";
import { follow, getInfo, getLatest, img, startCheck } from "../../lib/api";
import { RISK, clock, ms, pct, tokens, usd } from "../../lib/format";

const SOURCE = { "local detector": "Local detector (free)", "cheap model": "Cheap model", "strong model": "Strong model" };

function Settings({ value, onChange, info }) {
  const k = info ? info.keyframes : { min: 4, max: 10 };
  const set = (patch) => onChange({ ...value, ...patch });
  return (
    <fieldset className="settings">
      <legend>Settings</legend>
      <div className="row">
        <label htmlFor="kf">Key frames: <b>{value.keyframes}</b></label>
        <input id="kf" type="range" min={k.min} max={k.max} value={value.keyframes}
          onChange={(e) => set({ keyframes: Number(e.target.value) })} />
      </div>
      <div className="row">
        <label className="check">
          <input type="checkbox" checked={value.detector} onChange={(e) => set({ detector: e.target.checked })} />
          Free vehicle detector on this computer (people are always blurred)
        </label>
      </div>
      <div className="row">
        <label className="check">
          <input type="checkbox" checked={value.nocache} onChange={(e) => set({ nocache: e.target.checked })} />
          Fresh run: don&apos;t reuse cached AI answers (costs a little)
        </label>
      </div>
      <div className="row">
        <label className="check">
          <input type="checkbox" checked={value.simulate} onChange={(e) => set({ simulate: e.target.checked })} />
          Simulate hazard levels
        </label>
        {value.simulate && (
          <>
            <label>Hail{" "}
              <select value={value.hail} onChange={(e) => set({ hail: Number(e.target.value) })}>
                <option value={0}>0 · low</option><option value={1}>1 · medium</option><option value={2}>2 · high</option>
              </select>
            </label>
            <label>Water{" "}
              <select value={value.water} onChange={(e) => set({ water: Number(e.target.value) })}>
                <option value={0}>0 · low</option><option value={1}>1 · medium</option><option value={2}>2 · high</option>
              </select>
            </label>
          </>
        )}
      </div>
    </fieldset>
  );
}

function Section({ id, title, intro, paper, children }) {
  return (
    <section className={`band${paper ? " paper" : ""}`} aria-labelledby={id}>
      <div className="inner">
        <div className="section-head">
          <h2 id={id}>{title}</h2>
          {intro && <p>{intro}</p>}
        </div>
        {children}
      </div>
    </section>
  );
}

function Camera({ job }) {
  const r = job.result;
  const [open, setOpen] = useState(null);
  const close = useRef(null);

  useEffect(() => {
    if (open === null) return undefined;
    const onKey = (e) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    if (close.current) close.current.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const people = r.people_blurred;
  return (
    <Section id="camera" title="What the camera found" paper
      intro="Boxes come from the free detector and the AI models. People are blurred before upload.">
      <div className="camstrip" tabIndex={0} aria-label="Key frames with the objects found">
        {r.keyframes.map((k) => (
          <figure key={k.index}>
            <button type="button" onClick={() => setOpen(k.index)} aria-label={`Enlarge key frame ${k.index + 1}`}>
              <img src={img.keyframe(job.id, k.index)} alt={`Key frame ${k.index + 1} at ${Math.round(k.t)} s`} loading="lazy" />
            </button>
            <figcaption>#{k.index + 1} · {Math.round(k.t)} s{k.brightened ? " · brightened" : ""}</figcaption>
          </figure>
        ))}
      </div>
      <div className="taglegend">
        <span className="tag high">high</span>
        <span className="tag medium">medium</span>
        <span className="tag low">low</span>
        <span className="tag">not relevant here</span>
        <span className="tag privacy">privacy</span>
      </div>
      <p style={{ marginTop: 14 }}>
        <b>{people} {people === 1 ? "person was" : "people were"} found and blurred before upload.</b>
      </p>
      {open !== null && (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Enlarged key frame" onClick={() => setOpen(null)}>
          <button ref={close} type="button" className="button light" onClick={() => setOpen(null)}>Close</button>
          <div>
            <img src={img.keyframe(job.id, open)} alt="Enlarged key frame" />
            <p>Press Escape or click anywhere to close</p>
          </div>
        </div>
      )}
    </Section>
  );
}

function Frames({ job }) {
  const r = job.result;
  const f = r.frames;
  const steps = [
    [f.in_video, "frames in video"],
    [f.sampled, "checked by free code"],
    [f.picked, "key frames picked"],
    [f.assessed, "images sent to AI"],
  ];
  return (
    <Section id="frames" title="Frames"
      intro="Free code drops dark, blurry and repeated views before any AI sees the video.">
      <div className="funnel">
        {steps.map(([n, text]) => (
          <div key={text}>
            <b>{n.toLocaleString("en-US")}</b>
            <span className="label">{text}</span>
          </div>
        ))}
      </div>
      <div className="sheet">
        <img src={`/api/jobs/${job.id}/filmstrip.jpg`}
          alt={`All ${f.sampled} frames checked by free code; ${f.picked} picked, framed in green`} />
      </div>
      <p className="quiet">Green = picked. Grey = skipped, with the reason. No AI in this step.</p>
    </Section>
  );
}

// One part of the "frugal" section: a short heading and one intro line.
function Part({ title, intro, children }) {
  return (
    <div className="frugal-part">
      <h3>{title}</h3>
      {intro && <p className="quiet frugal-intro">{intro}</p>}
      {children}
    </div>
  );
}

const HAZARD_NAME = { hail: "hail", water: "water" };

function MapPart({ r }) {
  const rows = [["Hail", r.hazards.hail], ["Water (heavy rain, floods)", r.hazards.water]];
  const missing = Object.keys(r.hazards).filter((k) => !r.hazards[k].available);
  // Say plainly when the listed kinds were never looked at, so "not seen" never reads as "safe".
  const notRun = { failed: "The AI did not answer, so these were not checked.",
    off: "The AI was not available, so these were not checked." }[r.ai.status];
  return (
    <Part title="1 · How the map decided"
      intro="The official map level decides what the AI looks for; a hazard at level 0 is not searched for, and a map that did not answer is not counted as low.">
      <div className="map">
        {rows.map(([name, h]) => (
          <div key={name}>
            <span className="label">{name}</span>
            <span className="level" style={{ color: h.available ? ["#027180", RISK.medium, RISK.high][h.level] : RISK.none }}>
              {h.available ? `Level ${h.level} · ${h.word}` : "Map unavailable (not the same as low)"}
            </span>
            {h.value && <p>{h.value}</p>}
            <p className="quiet">Source: {h.sources.join("; ")}</p>
          </div>
        ))}
      </div>
      <h4 className="frugal-sub">What the AI was asked to look for</h4>
      <ul className="asked">
        {r.asked.length === 0 && (
          <li className="off">
            {missing.length
              ? `Nothing: the ${missing.map((k) => HAZARD_NAME[k] || k).join(" and ")} ${missing.length > 1 ? "maps" : "map"} did not answer and no other hazard is at level 1 or higher, so nothing was searched for. This does not mean the risk is low.`
              : "Nothing: no hazard is at level 1 or higher here, so no AI was needed."}
          </li>
        )}
        {r.asked.map((a) => (
          <li key={a.kind}>
            <b>{a.name}</b>
            <span className="quiet">{a.find} · weight {a.weight} × {a.hazard} level</span>
          </li>
        ))}
        {r.not_asked.map((a) => (
          <li key={a.kind} className="off">
            <span>{a.name}: skipped, {a.reason}</span>
          </li>
        ))}
      </ul>
      {r.asked.length > 0 && notRun && <p className="error" style={{ marginTop: 12 }}>{notRun}</p>}
    </Part>
  );
}

function detectorText(r) {
  if (!r.settings.detector) return ["off", "switched off in the settings"];
  const missing = r.ledger.some((row) => (row.note || "").includes("detector file missing"));
  if (missing) return ["–", "detector file missing"];
  const n = r.findings.filter((f) => f.source === "local detector").length;
  return [n, n === 1 ? "vehicle found by the free local detector" : "vehicles found by the free local detector"];
}

function FreePart({ r }) {
  const f = r.frames;
  const [vehicles, vehicleText] = detectorText(r);
  const steps = [
    [f.in_video.toLocaleString("en-US"), "frames in the video"],
    [f.sampled, "sampled and checked by free code"],
    [f.picked, "key frames picked"],
    [r.people_blurred, r.people_blurred === 1 ? "person blurred" : "people blurred"],
    [vehicles, vehicleText],
  ];
  // Older results have no merge count; only show it when the check reported one.
  if (r.duplicates_removed != null) {
    steps.push([r.duplicates_removed, r.duplicates_removed === 1 ? "repeated find merged" : "repeated finds merged"]);
  }
  if (r.copies_dropped != null) {
    steps.push([r.copies_dropped, r.copies_dropped === 1 ? "copied AI box dropped" : "copied AI boxes dropped"]);
  }
  return (
    <Part title="2 · Free steps first"
      intro="All of this runs on this computer with no AI and no cost.">
      <div className="stats">
        {steps.map(([n, text]) => (
          <div className="stat" key={text}><b>{n}</b><small>{text}</small></div>
        ))}
      </div>
    </Part>
  );
}

// The cost line: a measured (billed) number when there is one, otherwise a clearly
// labelled estimate, and words instead of "$0" when no AI call was made.
function costLine(c, r) {
  const status = c.ai_status || r.ai.status;
  if (!c.ai_calls) {
    const mapGone = Object.values(r.hazards).some((h) => !h.available);
    if (status === "not needed" && mapGone) return { value: "No AI call was made", note: "the hazard map did not answer, so nothing was searched for and nothing was paid" };
    if (status === "not needed") return { value: "No AI call was needed", note: "nothing on the map called for it, so nothing was paid" };
    if (status === "failed") return { value: "No AI answer", note: "the AI did not answer, so nothing was billed" };
    return { value: "AI was not available", note: "no frames were sent, so nothing was paid" };
  }
  if (c.all_measured && c.measured_usd != null) {
    if (c.all_cached) return { value: usd(c.measured_usd), note: "measured on first run; this run reused the cached answer, $0 extra" };
    if (c.any_cached) return { value: usd(c.measured_usd), note: `measured, billed by OpenRouter; part reused from cache, this run billed ${usd(c.this_run_usd)}` };
    return { value: usd(c.measured_usd), note: "measured, billed by OpenRouter" };
  }
  return { value: `about ${usd(c.estimate_usd)}`, note: "estimate — no billed cost recorded" };
}

function CostPart({ r }) {
  const c = r.cost;
  const line = costLine(c, r);
  const max = Math.max(...c.comparison.map((b) => b.usd), 1e-9);
  const models = (r.ai.models || []).join(", ");
  return (
    <Part title="3 · Cost"
      intro="One call for all key frames on a small model, a second look only for unclear frames.">
      <p className="costline">
        <span className="label">Cost of this check</span>
        <b>{line.value}</b>
        <span className="quiet">({line.note})</span>
      </p>
      <p className="quiet">
        {c.ai_calls} AI {c.ai_calls === 1 ? "call" : "calls"}{models ? ` · ${models}` : ""} · whole check took {r.seconds} s
      </p>
      <h4 className="frugal-sub">Estimated cost of three designs for this video</h4>
      <div className="bars">
        {c.comparison.map((b) => (
          <div className={`bar ${b.key}`} key={b.key}>
            <div className="top">
              <span><b>{b.name}</b> <small>· {b.detail}</small></span>
              <span>
                <b>{b.key === "ours" && !b.usd ? "no AI call" : `est. ${usd(b.usd)}`}</b>
                {b.key !== "ours" && b.times ? <span className="times"> · about {Math.round(b.times)}×</span> : null}
              </span>
            </div>
            <div className="track"><div className="fill" style={{ width: `${Math.max(0.6, (b.usd / max) * 100)}%` }} /></div>
          </div>
        ))}
      </div>
      <p className="quiet" style={{ marginTop: 14 }}>
        All three bars are estimates made with the same rule, so they compare fairly; the billed cost above is measured separately. {c.rule}
      </p>
    </Part>
  );
}

function ledgerCost(row) {
  if (row.type !== "AI") return "free";
  if (!row.model) return "no answer";
  // A reused answer costs nothing now, but a bare "$0" looks fake: say why, and what it cost once.
  if (row.cached) {
    return row.first_run_usd != null
      ? `$0 extra (reused; first run ${usd(row.first_run_usd)})`
      : "$0 extra (reused answer)";
  }
  return usd(row.usd);
}

// Total of the "this run" column, with the same explanation when answers were reused.
function ledgerTotal(c, thisRun) {
  if (!c.ai_calls) return "free";
  if (c.any_cached && c.all_measured) return `${usd(thisRun)} extra (measured cost ${usd(c.measured_usd)})`;
  if (c.any_cached) return `${usd(thisRun)} extra (answers reused)`;
  return usd(thisRun);
}

function ledgerTokens(row) {
  if (row.type !== "AI" || !row.model) return "–";
  if (row.cached) {
    const first = row.first_run_tokens_in != null ? ` (first run ${tokens(row.first_run_tokens_in)} / ${tokens(row.first_run_tokens_out)})` : "";
    return `reused${first}`;
  }
  return `${tokens(row.tokens_in)} / ${tokens(row.tokens_out)}`;
}

function LedgerPart({ r }) {
  const c = r.cost;
  const thisRun = c.this_run_usd != null ? c.this_run_usd : r.ledger.reduce((a, x) => a + x.usd, 0);
  return (
    <Part title="4 · Ledger" intro="Every step with its time, tokens and what this run paid.">
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Step</th><th>Type</th><th className="num">Tokens in / out</th><th className="num">Cost this run</th><th className="num">Time</th></tr>
          </thead>
          <tbody>
            {r.ledger.map((row) => (
              <tr key={row.step}>
                <td>{row.step}{row.model ? <><br /><small className="quiet">{row.model}</small></> : null}{row.note ? <><br /><small className="quiet">{row.note}</small></> : null}</td>
                <td>{row.type}</td>
                <td className="num">{ledgerTokens(row)}</td>
                <td className="num">{ledgerCost(row)}</td>
                <td className="num">{ms(row.ms)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2}>Total</td>
              <td className="num">{tokens(r.ledger.reduce((a, x) => a + x.tokens_in, 0))} / {tokens(r.ledger.reduce((a, x) => a + x.tokens_out, 0))}</td>
              <td className="num">{ledgerTotal(c, thisRun)}</td>
              <td className="num">{ms(r.ledger.reduce((a, x) => a + x.ms, 0))}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Part>
  );
}

function ConfidencePart({ r }) {
  const n = r.findings.length;
  return (
    <details className="frugal-part frugal-details">
      <summary>
        <h3>5 · Detection confidence</h3>
        <span className="quiet">{n === 0 ? "no objects found" : `${n} ${n === 1 ? "object" : "objects"} found`}</span>
      </summary>
      <p className="quiet frugal-intro">
        {`Objects below ${pct(0.6)} confidence (${pct(0.5)} for the local detector) are left out.`}
      </p>
      {n === 0 ? (
        <p>No objects were found in the key frames. That does not prove there are none.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th className="num">#</th><th>Object</th><th>Frame</th><th>Importance</th><th className="num">Confidence</th><th>Found by</th></tr>
            </thead>
            <tbody>
              {r.findings.map((f) => (
                <tr key={f.id}>
                  <td className="num">{f.id + 1}</td>
                  <td>{f.name}{f.detail ? <small className="quiet"> · {f.detail}</small> : null}</td>
                  <td>{f.frame + 1} · {clock(f.t)}</td>
                  <td>
                    <span className={`tag ${f.label === "not relevant here" ? "" : f.label}`}>{f.label}</span>{" "}
                    <small className="quiet">score {f.score}</small>
                  </td>
                  <td className="num">{pct(f.confidence)}</td>
                  <td>{SOURCE[f.source] || f.source}{f.model ? <><br /><small className="quiet">{f.model}</small></> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

function Frugal({ job }) {
  const r = job.result;
  return (
    <Section id="frugal" title="How we kept the model frugal and cheap" paper>
      <MapPart r={r} />
      <FreePart r={r} />
      <CostPart r={r} />
      <LedgerPart r={r} />
      <ConfidencePart r={r} />
    </Section>
  );
}

export default function DetailsPage() {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [story, setStory] = useState(false);
  const [running, setRunning] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState(null);
  const [opts, setOpts] = useState({ keyframes: 6, detector: true, simulate: false, hail: 1, water: 1, nocache: false });
  const stop = useRef(() => {});

  useEffect(() => {
    getInfo().then((i) => {
      setInfo(i);
      setOpts((o) => ({ ...o, keyframes: i.keyframes.default }));
    }).catch(() => {});
    getLatest().then((j) => j && j.result && setJob(j)).catch(() => {}).finally(() => setLoading(false));
    return () => stop.current();
  }, []);

  async function submit({ address, file }) {
    setError("");
    try {
      const { job_id: id } = await startCheck({
        address, file, keyframes: opts.keyframes, detector: opts.detector, nocache: opts.nocache,
        simulate: opts.simulate ? { hail: opts.hail, water: opts.water } : null,
      });
      setRunning({ id, stage: "Starting the check" });
      stop.current = follow(id, (j) => {
        if (j.status === "done") {
          setJob(j);
          setRunning(null);
          setShowForm(false);
        } else if (j.status === "failed") {
          setRunning(null);
          setError(j.error || "The check could not finish.");
        } else setRunning(j);
      });
    } catch (err) {
      setError(err.message);
    }
  }

  const r = job && job.result;
  const formVisible = !loading && !running && (!job || showForm);

  return (
    <main>
      {story && <Story onClose={() => setStory(false)} />}
      <Hero title="How the check works" toplink={<a className="toplink" href="/">← Customer view</a>}
        onLogo={() => setStory(true)}>
        <p className="lead reveal">
          Free code does most of the work: the official hazard maps, picking sharp key frames, finding
          cars and blurring people on this computer. Paid AI only looks where the map says it matters.
        </p>
        {r && (
          <>
            <p className="place">{r.address.label} · {r.filename}</p>
            <HazardChips hazards={r.hazards} />
          </>
        )}
      </Hero>

      <section className="band tight paper">
        <div className="inner">
          {running && <Running stage={running.stage} />}
          {formVisible && (
            <CheckForm onSubmit={submit} error={error} submitLabel="Analyse video">
              <Settings value={opts} onChange={setOpts} info={info} />
            </CheckForm>
          )}
          {!running && job && !showForm && (
            <div className="actions">
              <button type="button" className="button ghost" onClick={() => setShowForm(true)}>Analyse another video</button>
              <span className="quiet">
                Showing the newest check: {r.settings.keyframes} key frames, detector {r.settings.detector ? "on" : "off"}
                {r.settings.simulated ? ", simulated hazard levels" : ""}
                {r.settings.use_cache === false ? ", fresh run (no cached AI answers)" : ""}.
              </span>
            </div>
          )}
          {!running && job && showForm && (
            <p style={{ marginTop: 16 }}>
              <button type="button" className="button ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </p>
          )}
          {error && !formVisible && <p className="error" role="alert" style={{ marginTop: 16 }}>{error}</p>}
        </div>
      </section>

      {r && (
        <>
          <Section id="video" title="The uploaded video">
            <video className="player" src={`${img.video(job.id)}#t=0.1`} controls playsInline preload="metadata" />
            <p className="quiet" style={{ marginTop: 12 }}>
              {r.filename} · {clock(r.video.duration_s)} · {r.video.width}×{r.video.height} · {r.video.fps} fps
            </p>
          </Section>
          <Camera job={job} />
          <Frames job={job} />
          <Frugal job={job} />
        </>
      )}

      <Footer>
        <a href="/">Customer view</a>
      </Footer>
    </main>
  );
}
