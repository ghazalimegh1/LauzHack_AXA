"use client";

// "Next storm at your site": a live countdown from the real Open-Meteo forecast.

import { useEffect, useState } from "react";
import { getForecast } from "../lib/api";
import { timeOfDay } from "../lib/format";

function parts(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return [
    [Math.floor(s / 86400), "days"],
    [Math.floor((s % 86400) / 3600), "hours"],
    [Math.floor((s % 3600) / 60), "min"],
    [s % 60, "sec"],
  ];
}

const HAIL = { heavy: "heavy hail", slight: "slight hail", none: "no hail expected" };

export default function Storm({ jobId }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [now, setNow] = useState(() => Date.now() / 1000);

  useEffect(() => {
    let alive = true;
    getForecast(jobId)
      .then((d) => alive && setData(d))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [jobId]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, []);

  const storm = data && data.storm;
  const ongoing = storm && storm.starts <= now && now < storm.ends;
  const over = storm && now >= storm.ends;

  let body;
  if (failed) {
    body = <p className="lead-muted">The weather forecast is not available right now. Please look again later.</p>;
  } else if (!data) {
    body = <p className="lead-muted">Loading the forecast for your address…</p>;
  } else if (!storm || over) {
    body = (
      <div>
        <p className="storm-none">No storm coming.</p>
        <p className="lead-muted">The forecast shows no storm at your site in the next {data.hours || 48} hours.</p>
      </div>
    );
  } else {
    body = (
      <div className="storm">
        <div>
          <p className="label" style={{ color: "rgba(255,255,255,.75)" }}>
            {ongoing ? "Under way now · ends in" : `${storm.kind} expected in`}
          </p>
          <div className="clock" aria-live="off" role="timer">
            {parts((ongoing ? storm.ends : storm.starts) - now).map(([v, unit]) => (
              <div key={unit}>
                <b>{String(v).padStart(2, "0")}</b>
                <span>{unit}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="facts">
          <div>
            <span className="label">Expected</span>
            <b style={{ textTransform: "capitalize" }}>{storm.kind}</b>
          </div>
          <div>
            <span className="label">Severity</span>
            <b><span className={`sev ${storm.severity}`}>{storm.severity}</span></b>
          </div>
          <div>
            <span className="label">When</span>
            <b>{timeOfDay(storm.starts)} – {timeOfDay(storm.ends)}</b>
          </div>
          <div>
            <span className="label">Hail</span>
            <b>{HAIL[storm.hail]}</b>
          </div>
          <div>
            <span className="label">Gusts</span>
            <b>up to {storm.gust_kmh} km/h</b>
          </div>
          <div>
            <span className="label">Rain</span>
            <b>{storm.rain_mm} mm</b>
          </div>
        </div>
      </div>
    );
  }

  return (
    <section className="band ink" aria-labelledby="storm-title">
      <div className="inner">
        <div className="section-head">
          <h2 id="storm-title">Next storm at your site</h2>
          <p>From the Open-Meteo weather forecast for your address, next 48 hours.</p>
        </div>
        {body}
      </div>
    </section>
  );
}
