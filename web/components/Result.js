"use client";

// Pieces of the customer result that the details page reuses too.

import { img } from "../lib/api";
import { hazardWord } from "../lib/format";

export function HazardChips({ hazards }) {
  const rows = [
    ["Hail risk here", hazards.hail],
    ["Water risk here", hazards.water],
  ];
  return (
    <div className="chips">
      {rows.map(([name, h]) => {
        const { word, colour } = hazardWord(h);
        return (
          <span className="chip" key={name}>
            <i style={{ background: colour }} aria-hidden="true" />
            {name}: {word}
          </span>
        );
      })}
    </div>
  );
}

export function counted(result) {
  return (result.weak_points || []).filter((w) => w.status === "counted");
}

export function WeakCards({ points, jobId, field }) {
  return (
    <div className="cards">
      {points.map((w, i) => (
        <article className="card reveal" key={w.kind} style={{ animationDelay: `${i * 60}ms` }}>
          <div className="photo">
            <img src={img.crop(jobId, w.best)} alt={`${w.name} in your video`} loading="lazy" />
          </div>
          <div className="body">
            <span className={`tag ${w.label}`}>{w.label} risk</span>
            <h3>
              {w.name}
              {w.count > 1 ? ` (${w.count}×)` : ""}
            </h3>
            <p>{w[field]}</p>
            {field === "now" && <p className="why">{w.why}</p>}
          </div>
        </article>
      ))}
    </div>
  );
}
