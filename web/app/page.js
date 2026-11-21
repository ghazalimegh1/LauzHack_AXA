"use client";
// The customer page: a business owner sees only what to do. No costs, models or tables.
import { useEffect, useState } from "react";
import CheckForm from "../components/CheckForm";
import { Chip, DemoBadge, Eyebrow, Hero, Spinner, Tag } from "../components/ui";
import { cropUrl, getInfo, getLatest, runCheck } from "../lib/api";
import { COLOURS, riskText } from "../lib/format";

// The rules in frugal/score.py name an action for AXA; the customer gets it in plain words.
const HEADLINES = {
  "Propose an on-site prevention check": "Have your site checked before the next storm",
  "Send targeted prevention tips": "A few simple steps will protect your site",
  "No action needed": "Nothing urgent for this site",
};
const MAX_NOW = 5;   // more than five "do now" items would not get done before a storm

export default function CustomerPage() {
  const [info, setInfo] = useState(null);
  const [check, setCheck] = useState(null);     // { jobId, result }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(true);
  const [storm, setStorm] = useState(false);

  useEffect(() => {
    getInfo().then(setInfo).catch(() => setError("The server did not answer. Is it running?"));
    getLatest().then((c) => { if (c) { setCheck(c); setShowForm(false); } }).catch(() => {});
  }, []);

  async function onSubmit(address, file) {
    const form = new FormData();
    form.append("address", address);
    form.append("video", file);
    setBusy(true);
    setError("");
    try {
      setCheck(await runCheck(form));
      setShowForm(false);
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
        <span className="brand">Site Check</span>
        <span className="top-right"><DemoBadge info={info} /><b className="axa">AXA</b></span>
      </header>

      {showForm ? (
        <>
          <Hero eyebrow="Site check · storm prevention" title="What would a storm hit first?">
            <p>Film a one-minute walk around your site. We tell you what to protect.</p>
          </Hero>
          <section className="form-card">
            <CheckForm onSubmit={onSubmit} busy={busy} buttonText="→  Check my site" />
            {busy && <Spinner>Looking at your video... this takes about half a minute.</Spinner>}
            {error && <p className="error">{error}</p>}
          </section>
        </>
      ) : (
        <Result check={check} colours={colours} storm={storm} setStorm={setStorm}
                onNew={() => { setShowForm(true); setStorm(false); }} />
      )}

      <footer className="foot">
        <a href="/demo.html">For the jury: technical view</a>
      </footer>
    </main>
  );
}

function Result({ check, colours, storm, setStorm, onNew }) {
  const r = check.result;
  const now = r.result.items.filter((i) => i.now).slice(0, MAX_NOW);
  return (
    <div className="fade" key={check.jobId}>
      <div className="result-bar">
        <label className="switch">
          <input type="checkbox" checked={storm} onChange={(e) => setStorm(e.target.checked)} />
          <span>Storm warning (simulated)</span>
        </label>
        <button className="link" onClick={onNew}>Check another site</button>
      </div>

      {storm ? (
        <section className="storm">
          <Eyebrow>Storm warning (simulated)</Eyebrow>
          <h2>Do this now</h2>
          <NowList items={now} jobId={check.jobId} colours={colours} />
        </section>
      ) : (
        <>
          <Headline r={r} />
          <section className="block">
            <Eyebrow>Before a storm</Eyebrow>
            <h2>Do this before a storm</h2>
            <NowList items={now} jobId={check.jobId} colours={colours} />
          </section>
          {r.result.items.length > 0 && (
            <section className="block">
              <Eyebrow>This year</Eyebrow>
              <h2>Fix this year</h2>
              <ul className="later">
                {r.result.items.map((i) => <li key={i.kind}>{i.later}</li>)}
              </ul>
            </section>
          )}
          {r.result.uncertain.length > 0 && (
            <p className="quiet">A few things were unclear: a person should take a look.</p>
          )}
        </>
      )}
    </div>
  );
}

function Headline({ r }) {
  const where = r.place ? r.place.label : r.address;
  if (!r.map_ok) {
    return (
      <Hero eyebrow="Your result" title="We could not reach the official hazard maps">
        <p>Please try again in a few minutes. Address: {where}</p>
      </Hero>
    );
  }
  return (
    <>
      <Hero eyebrow="Your result" title={HEADLINES[r.result.action] || r.result.action}>
        <p>{where}</p>
        <div className="chips">
          <Chip>Hail risk here: {riskText(r.hazards.hail)}</Chip>
          <Chip>Water risk here: {riskText(r.hazards.water)}</Chip>
        </div>
      </Hero>
      {r.warning && <p className="quiet">Part of the check could not run. Please try again later.</p>}
    </>
  );
}

function NowList({ items, jobId, colours }) {
  if (!items.length) return <p className="muted">Nothing in your video needs action before a storm.</p>;
  return (
    <ol className="now">
      {items.map((i) => (
        <li key={i.kind} className="now-card">
          {i.object_id !== null
            ? <img src={cropUrl(jobId, i.object_id)} alt={i.name} />
            : <span className="no-photo" />}
          <div>
            <p className="now-title">{i.name} <Tag label={i.label} colours={colours} /></p>
            <p>{i.now}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
