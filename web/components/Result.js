"use client";

// Pieces of the customer result that the details page reuses too.

import { img } from "../lib/api";
import { clock, hazardWord } from "../lib/format";

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

// "Do this before a storm": one row per thing found, with its close-up from the video,
// its name, the risk tag and the quick action (the team's earlier row design).
export function NowList({ points, jobId }) {
  return (
    <ol className="now">
      {points.map((w, i) => (
        <li className="now-card reveal" key={w.kind} style={{ animationDelay: `${i * 60}ms` }}>
          {/* No clear close-up: show the label alone rather than a misleading picture. */}
          {w.photo != null ? (
            <img src={img.crop(jobId, w.photo)} alt={`${w.name} in your video`} loading="lazy" />
          ) : (
            <div className="nophoto"><span>No clear close-up</span></div>
          )}
          <div>
            <p className="now-title">
              {w.name}{w.count > 1 ? ` (${w.count}×)` : ""} <span className={`tag ${w.label}`}>{w.label} risk</span>
            </p>
            {w.details && w.details.length > 0 && <p className="quiet">Seen: {w.details.join(", ")}</p>}
            <p>{w.now}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

// "Fix this year": the same row design, but it shows something else: the lasting fix as the
// title, the wider view of where on the site it was seen, and why it matters.
export function LaterList({ points, jobId }) {
  return (
    <ol className="now later-list">
      {points.map((w, i) => (
        <li className="now-card reveal" key={w.kind} style={{ animationDelay: `${i * 60}ms` }}>
          <img src={img.keyframe(jobId, w.frame)} alt={`Where the ${w.name.toLowerCase()} was seen on your site`} loading="lazy" />
          <div>
            <p className="now-title">{w.later}</p>
            <p className="quiet">For: {w.name.toLowerCase()} · seen at {w.seen_at.map(clock).join(", ")} in your video</p>
            <p className="why">{w.why}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
