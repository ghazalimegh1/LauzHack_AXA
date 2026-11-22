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

// The thumbnail shows only part of the frame: aim it at the middle of the cars' box.
function focus(box) {
  if (!box) return "center";
  const pc = (v) => `${Math.round(Math.min(1, Math.max(0, v)) * 100)}%`;
  return `${pc((box[0] + box[2]) / 2)} ${pc((box[1] + box[3]) / 2)}`;
}

// "Do this before a storm": one row per thing found, with its close-up from the video,
// its name, the risk tag and the quick action (the team's earlier row design).
export function NowList({ points, jobId }) {
  // Parked vehicles: one row per picture they were seen in, so different cars are each
  // named; cars standing side by side in one picture share their row.
  const rows = points.flatMap((w) =>
    w.kind === "vehicle" && w.sightings && w.sightings.length > 0
      ? w.sightings.map((s) => ({ ...w, sighting: s }))
      : [w]);
  return (
    <ol className="now">
      {rows.map((w, i) => w.sighting ? (
        <li className="now-card reveal" key={`${w.kind}-${w.sighting.frame}`} style={{ animationDelay: `${i * 60}ms` }}>
          <img src={img.keyframe(jobId, w.sighting.frame)} style={{ objectPosition: focus(w.sighting.box) }}
            alt={`${w.name} seen at ${clock(w.sighting.t)} in your video`} loading="lazy" />
          <div>
            <p className="now-title">
              {w.name}{w.sighting.count > 1 ? ` (${w.sighting.count} side by side)` : ""}{" "}
              <span className={`tag ${w.label}`}>{w.label} risk</span>
            </p>
            <p className="quiet">
              Seen at {clock(w.sighting.t)} in your video
              {w.sighting.details.length > 0 ? ` · ${w.sighting.details.join(", ")}` : ""}
            </p>
            <p>{w.now}</p>
          </div>
        </li>
      ) : (
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
