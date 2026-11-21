"use client";

// Assessment details: how the check works, for the jury. Shows the newest finished check.

import { useEffect, useRef, useState } from "react";
import CheckForm, { Running } from "../../components/CheckForm";
import { HazardChips } from "../../components/Result";
import { Footer, Hero } from "../../components/Shell";
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

function Efficiency({ job }) {
  const r = job.result;
  const c = r.cost;
  const max = Math.max(...c.comparison.map((b) => b.usd), 1e-9);
  return (
    <Section id="cost" title="Processing efficiency" paper
      intro="Free steps first, and paid AI only where needed: one call for all key frames, a second look only for unclear frames.">
      <div className="stats">
        <div className="stat"><span className="label">Cost of this check</span><b>{usd(c.measured_usd)}</b><small>as billed by OpenRouter{c.measured_usd === 0 && c.ai_calls > 0 ? " (answers reused from cache)" : ""}</small></div>
        <div className="stat"><span className="label">Our estimate</span><b>{usd(c.estimate_usd)}</b><small>same rule as the comparison</small></div>
        <div className="stat"><span className="label">AI calls</span><b>{c.ai_calls}</b><small>{(r.ai.models || []).join(", ") || "none"}</small></div>
        <div className="stat"><span className="label">Total time</span><b>{r.seconds} s</b><small>for the whole check</small></div>
      </div>

      <h3 style={{ margin: "40px 0 18px" }}>Compared with sending more to a bigger model</h3>
      <div className="bars">
        {c.comparison.map((b) => (
          <div className={`bar ${b.key}`} key={b.key}>
            <div className="top">
              <span><b>{b.name}</b> <small>· {b.detail}</small></span>
              <span>
                <b>{usd(b.usd)}</b>
                {b.key !== "ours" && b.times ? <span className="times"> · about {Math.round(b.times)}×</span> : null}
              </span>
            </div>
            <div className="track"><div className="fill" style={{ width: `${Math.max(0.6, (b.usd / max) * 100)}%` }} /></div>
          </div>
        ))}
      </div>
      <p className="quiet" style={{ marginTop: 14 }}>{c.rule}</p>

      <h3 style={{ margin: "40px 0 18px" }}>Ledger</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Step</th><th>Type</th><th className="num">Tokens in / out</th><th className="num">Cost</th><th className="num">Time</th></tr>
          </thead>
          <tbody>
            {r.ledger.map((row) => (
              <tr key={row.step}>
                <td>{row.step}{row.model ? <><br /><small className="quiet">{row.model}</small></> : null}{row.note ? <><br /><small className="quiet">{row.note}</small></> : null}</td>
                <td>{row.type}</td>
                <td className="num">{row.type === "AI" ? `${tokens(row.tokens_in)} / ${tokens(row.tokens_out)}` : "–"}</td>
                <td className="num">{usd(row.usd)}</td>
                <td className="num">{ms(row.ms)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2}>Total</td>
              <td className="num">{tokens(r.ledger.reduce((a, x) => a + x.tokens_in, 0))} / {tokens(r.ledger.reduce((a, x) => a + x.tokens_out, 0))}</td>
              <td className="num">{usd(c.measured_usd)}</td>
              <td className="num">{ms(r.ledger.reduce((a, x) => a + x.ms, 0))}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Section>
  );
}

function MapDecided({ job }) {
  const r = job.result;
  const rows = [["Hail", r.hazards.hail], ["Water (heavy rain, floods)", r.hazards.water]];
  return (
    <Section id="map" title="How the map decided"
      intro="The official map level at the address decides what the AI is asked to look for. A hazard at level 0 is not searched for at all.">
      <div className="map">
        {rows.map(([name, h]) => (
          <div key={name}>
            <span className="label">{name}</span>
            <span className="level" style={{ color: h.available ? ["#027180", RISK.medium, RISK.high][h.level] : RISK.none }}>
              {h.available ? `Level ${h.level} · ${h.word}` : "Map unavailable"}
            </span>
            {h.value && <p>{h.value}</p>}
            <p className="quiet">Source: {h.sources.join("; ")}</p>
          </div>
        ))}
      </div>
      <h3 style={{ margin: "36px 0 16px" }}>The AI was asked to look for</h3>
      <ul className="asked">
        {r.asked.length === 0 && <li className="off">Nothing: no hazard at level 1 or higher here, so no AI was needed.</li>}
        {r.asked.map((a) => (
          <li key={a.kind}>
            <b>{a.name}</b>
            <span className="quiet">{a.find} · weight {a.weight} × {a.hazard} level</span>
          </li>
        ))}
        {r.not_asked.map((a) => (
          <li key={a.kind} className="off">
            <span>{a.name}: not asked, {a.reason}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Confidence({ job }) {
  const r = job.result;
  return (
    <Section id="confidence" title="Detection confidence" paper
      intro={`Every object found and counted. Objects below ${pct(0.6)} confidence (${pct(0.5)} for the local detector) are left out.`}>
      {r.findings.length === 0 ? (
        <p>No objects were found in the key frames.</p>
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
                  <td>{SOURCE[f.source] || f.source}{f.model && f.source !== "local detector" ? <><br /><small className="quiet">{f.model}</small></> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

export default function DetailsPage() {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState(null);
  const [opts, setOpts] = useState({ keyframes: 6, detector: true, simulate: false, hail: 1, water: 1 });
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
        address, file, keyframes: opts.keyframes, detector: opts.detector,
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
      <Hero title="How the check works" toplink={<a className="toplink" href="/">← Customer view</a>}>
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
                {r.settings.simulated ? ", simulated hazard levels" : ""}.
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
          <Efficiency job={job} />
          <MapDecided job={job} />
          <Confidence job={job} />
        </>
      )}

      <Footer>
        <a href="/">Customer view</a>
      </Footer>
    </main>
  );
}
