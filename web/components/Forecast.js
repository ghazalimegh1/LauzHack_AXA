"use client";
// Live countdown to the next storm at the site, with its expected severity.
// Real data: the server asks the free Open-Meteo forecast (frugal/weather.py).
// With the "Storm warning (simulated)" switch on, the page passes a made-up storm instead,
// clearly labelled, so the warning view can be shown on a calm day.
import { useEffect, useState } from "react";
import { getForecast } from "../lib/api";
import { COLOURS } from "../lib/format";

const REFRESH_MS = 10 * 60 * 1000;    // forecasts change; ask again every 10 minutes
// Severity colours reuse the importance colours, so "severe" looks as urgent as "high".
const SEVERITY_COLOUR = { severe: COLOURS.high, strong: COLOURS.medium, moderate: COLOURS.low };
const HAIL_TEXT = { heavy: "heavy hail", slight: "light hail", none: "not forecast" };

// Seconds left until `target` (unix seconds), updated every second.
function useSecondsLeft(target) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return target ? Math.round(target - now / 1000) : null;
}

// 93784 -> "1 d 02:03:04"; 3723 -> "01:02:03"
function clock(s) {
  const pad = (n) => String(n).padStart(2, "0");
  const d = Math.floor(s / 86400);
  const hms = `${pad(Math.floor((s % 86400) / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
  return d ? `${d} d ${hms}` : hms;
}

const when = (unix) => new Date(unix * 1000).toLocaleString("en-GB", {
  weekday: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Zurich" });

// Loads the real forecast for this check and keeps it fresh.
export function useForecast(jobId) {
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => getForecast(jobId).then((d) => alive && setData(d)).catch(() => alive && setData({ ok: false }));
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => { alive = false; clearInterval(t); };
  }, [jobId]);
  return data;
}

export default function Forecast({ data, simulated = false }) {
  const storm = data && data.storm;
  const left = useSecondsLeft(storm && storm.starts);
  if (!data) return <p className="muted">Loading the weather forecast...</p>;
  if (!data.ok) return <p className="muted">The weather forecast is not available right now.</p>;
  if (!storm) return <p className="forecast-calm">No storm or hail forecast for the next {data.hours} hours.</p>;

  const started = left <= 0;
  return (
    <div className="forecast">
      <div className="forecast-time">
        <span className="forecast-label">{started ? `${storm.kind} now` : `${storm.kind} expected in`}</span>
        <b className="countdown" aria-live="off">{started ? "Now" : clock(left)}</b>
        <span className="forecast-label">
          {when(storm.starts)} to {when(storm.ends)}{simulated ? " · simulated" : ""}
        </span>
      </div>
      <div className="forecast-detail">
        <span className="severity" style={{ background: SEVERITY_COLOUR[storm.severity] }}>
          {storm.severity}
        </span>
        <dl>
          <dt>Hail</dt><dd>{HAIL_TEXT[storm.hail]}</dd>
          <dt>Gusts</dt><dd>up to {storm.gust_kmh} km/h ({storm.wind})</dd>
          <dt>Rain</dt><dd>{storm.rain_mm} mm</dd>
        </dl>
      </div>
    </div>
  );
}
