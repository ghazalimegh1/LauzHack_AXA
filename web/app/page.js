"use client";

// Customer app: for a business owner. No costs, no model names, no tables.

import { useEffect, useRef, useState } from "react";
import CheckForm, { Running } from "../components/CheckForm";
import { HazardChips, LaterList, NowList, counted } from "../components/Result";
import { Footer, Hero } from "../components/Shell";
import SpatialView from "../components/SpatialView";
import Storm from "../components/Storm";
import { follow, getLatest, img, startCheck } from "../lib/api";

function Start({ onSubmit, error }) {
  return (
    <>
      <Hero title="What would a storm hit first?">
        <p className="lead reveal">
          Film a short walk around your business site. We compare it with the official Swiss hail
          and flood maps and show you what to protect first.
        </p>
      </Hero>
      <section className="band">
        <div className="inner">
          <CheckForm onSubmit={onSubmit} error={error} />
        </div>
      </section>
    </>
  );
}

function Result({ job, onAgain }) {
  const r = job.result;
  const todo = counted(r).slice(0, 5);
  const unsure = r.uncertain_count || 0;
  const aiFailed = r.ai && r.ai.status === "failed";

  return (
    <>
      <Hero title={r.action.headline}>
        <p className="place reveal">{r.address.label}</p>
        <HazardChips hazards={r.hazards} />
      </Hero>

      <section className="band paper tight" aria-labelledby="video-title">
        <div className="inner">
          <div className="section-head">
            <h2 id="video-title">Your video</h2>
          </div>
          <video className="player" src={`${img.video(job.id)}#t=0.1`} controls playsInline preload="metadata" />
        </div>
      </section>

      <section className="band" aria-labelledby="where-title">
        <div className="inner">
          {todo.length > 0 && r.action.key !== "unknown" ? (
            <>
              <div className="section-head">
                <h2 id="where-title">Where your site is exposed</h2>
                <p>Each pin is a weak point we saw in your video. Select one to see what to do.</p>
              </div>
              <SpatialView result={r} jobId={job.id} />
            </>
          ) : (
            <div className="section-head">
              <h2 id="where-title">
                {r.action.key === "unknown" ? "We could not judge the risk this time" : "Nothing at risk in your video"}
              </h2>
              <p>
                {r.action.key === "unknown"
                  ? "The official hazard map did not answer for your address. Please try again in a few minutes."
                  : "We did not see anything in your video that the hail or water risk at this address would damage."}
              </p>
            </div>
          )}
        </div>
      </section>

      {todo.length > 0 && (
        <section className="band paper" aria-labelledby="now-title">
          <div className="inner">
            <div className="section-head">
              <h2 id="now-title">Do this before a storm</h2>
              <p>The most important first. Each step takes minutes, not days.</p>
            </div>
            <NowList points={todo} jobId={job.id} />
          </div>
        </section>
      )}

      <Storm jobId={job.id} />

      {todo.length > 0 && (
        <section className="band" aria-labelledby="year-title">
          <div className="inner">
            <div className="section-head">
              <h2 id="year-title">Fix this year</h2>
              <p>Lasting improvements that keep the next storm from causing damage.</p>
            </div>
            <LaterList points={todo} jobId={job.id} />
          </div>
        </section>
      )}

      {(unsure > 0 || aiFailed) && (
        <section className="band tight">
          <div className="inner" style={{ display: "grid", gap: 14 }}>
            {unsure > 0 && (
              <p className="quiet">Some things in your video were unclear. An expert should take a look.</p>
            )}
            {aiFailed && (
              <p className="note">
                Part of the photo check could not finish this time. What you see comes from the hazard
                map and from the check that runs on our own computer. You can run the check again later.
              </p>
            )}
          </div>
        </section>
      )}

      <section className="band tight paper">
        <div className="inner actions">
          <button className="button" type="button" onClick={onAgain}>Check another site</button>
        </div>
      </section>
    </>
  );
}

export default function CustomerPage() {
  const [view, setView] = useState("loading");
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const stop = useRef(() => {});

  useEffect(() => {
    getLatest()
      .then((latest) => {
        if (latest && latest.result) {
          setJob(latest);
          setView("result");
        } else setView("start");
      })
      .catch(() => setView("start"));
    return () => stop.current();
  }, []);

  async function submit({ address, file }) {
    setError("");
    try {
      const { job_id: id } = await startCheck({ address, file });
      setJob({ id, status: "queued", stage: "Uploading done, starting the check" });
      setView("running");
      window.scrollTo({ top: 0 });
      stop.current = follow(id, (j) => {
        if (j.status === "done") {
          setJob(j);
          setView("result");
          window.scrollTo({ top: 0 });
        } else if (j.status === "failed") {
          setError(j.error || "The check could not finish. Please try again.");
          setView("start");
        } else setJob(j);
      });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main>
      {view === "loading" && <Hero title="What would a storm hit first?" />}
      {view === "start" && <Start onSubmit={submit} error={error} />}
      {view === "running" && (
        <>
          <Hero title="Checking your site">
            <p className="lead">We are reading the hazard maps and looking at your video.</p>
          </Hero>
          <section className="band">
            <div className="inner">
              <Running stage={job && job.stage} />
            </div>
          </section>
        </>
      )}
      {view === "result" && job && (
        <Result
          job={job}
          onAgain={() => {
            setError("");
            setView("start");
            window.scrollTo({ top: 0 });
          }}
        />
      )}
      <Footer>
        <a href="/demo.html">View assessment details</a>
      </Footer>
    </main>
  );
}
