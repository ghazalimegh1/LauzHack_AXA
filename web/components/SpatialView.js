"use client";

// 2.5D spatial risk view: a flat site, raised walls and a slightly floating roof, with hail
// and flood overlays whose strength comes from the real map levels. Pins are placed
// approximately: the layer comes from the object type, left-to-right follows when the object
// appeared in the walk. Plain SVG, no 3D library, no measured positions.

import { useMemo, useRef, useState } from "react";
import { img } from "../lib/api";
import { RISK, clock, hazardWord, lower, pct } from "../lib/format";

const D = { x: 110, y: -70 };            // depth direction of the oblique drawing
const F = { x0: 180, x1: 520, base: 380, top: 250 };   // front wall
const ROOF_LIFT = 18;
const LAYER_Y = { roof: F.top - ROOF_LIFT + D.y / 2, wall: 292, wall_base: 356, ground: 412 };
const LAYER_X = {
  roof: [F.x0 + D.x / 2 + 18, F.x1 + D.x / 2 - 18],
  wall: [F.x0 + 26, F.x1 - 26],
  wall_base: [F.x0 + 26, F.x1 - 26],
  ground: [70, 600],
};

function pts(list) {
  return list.map(([x, y]) => `${x},${y}`).join(" ");
}

// Deterministic "random" points for the hail overlay.
function hailDots(count) {
  const out = [];
  let seed = 7;
  const rnd = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
  for (let i = 0; i < count; i += 1) out.push([24 + rnd() * 760, 126 + rnd() * 320]);
  return out;
}

function placePins(points, duration) {
  const span = Math.max(duration || 0, ...points.map((p) => p.t), 1);
  const placed = points.map((p, i) => {
    const [a, b] = LAYER_X[p.layer] || LAYER_X.ground;
    return { ...p, n: i + 1, x: a + (b - a) * Math.min(1, Math.max(0, p.t / span)), y: LAYER_Y[p.layer] || LAYER_Y.ground };
  });
  // keep pins on the same layer at least 40 px apart
  Object.keys(LAYER_Y).forEach((layer) => {
    const row = placed.filter((p) => p.layer === layer).sort((a, b) => a.x - b.x);
    for (let i = 1; i < row.length; i += 1) {
      if (row[i].x - row[i - 1].x < 40) row[i].x = row[i - 1].x + 40;
    }
    const [, max] = LAYER_X[layer];
    const over = row.length ? row[row.length - 1].x - max : 0;
    if (over > 0) row.forEach((p) => { p.x -= over; });
  });
  return placed;
}

function colourOf(p) {
  return p.status === "uncertain" ? RISK.uncertain : RISK[p.label] || RISK.none;
}

export default function SpatialView({ result, jobId }) {
  const { weak_points: points = [], hazards = {}, video = {} } = result;
  const pins = useMemo(() => placePins(points, video.duration_s), [points, video.duration_s]);
  const [sel, setSel] = useState(0);
  const refs = useRef([]);
  const anyMap = Object.values(hazards).some((h) => h && h.available);
  if (!anyMap || pins.length === 0) return null;

  const hail = hazards.hail && hazards.hail.available ? hazards.hail.level : 0;
  const water = hazards.water && hazards.water.available ? hazards.water.level : 0;
  const dots = hailDots(hail === 2 ? 110 : hail === 1 ? 48 : 0);
  const flood = water === 2 ? 26 : water === 1 ? 14 : 0;
  const current = pins[Math.min(sel, pins.length - 1)];
  const best = result.findings.find((f) => f.id === current.best);

  function select(i, focus) {
    const n = (i + pins.length) % pins.length;
    setSel(n);
    if (focus && refs.current[n]) refs.current[n].focus();
  }

  function onKey(e, i) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      select(i, false);
    } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      select(i + 1, true);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      select(i - 1, true);
    }
  }

  const g = { fl: [30, 446], fr: [650, 446], br: [780, 280], bl: [160, 280] };
  const fb = [[F.x0, F.base], [F.x1, F.base]];
  const side = [[F.x1, F.top], [F.x1 + D.x, F.top + D.y], [F.x1 + D.x, F.base + D.y], [F.x1, F.base]];
  const roofY = F.top - ROOF_LIFT;
  const roof = [[F.x0, roofY], [F.x1, roofY], [F.x1 + D.x, roofY + D.y], [F.x0 + D.x, roofY + D.y]];

  return (
    <div className="spatial">
      <div>
        <div className="scene">
          <svg viewBox="16 118 784 340" role="group" aria-label="Spatial view of the weak points found at your site">
            <defs>
              <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
                <path d="M24 0H0V24" fill="none" stroke="#E2E2E8" strokeWidth="1" />
              </pattern>
            </defs>
            {/* site surface */}
            <polygon points={pts([g.fl, g.fr, g.br, g.bl])} fill="#F3F3F6" />
            <polygon points={pts([g.fl, g.fr, g.br, g.bl])} fill="url(#grid)" />
            {flood > 0 && (
              <polygon points={pts([g.fl, g.fr, g.br, g.bl])} fill="#3B3FD8" opacity={water === 2 ? 0.2 : 0.12} />
            )}
            {/* footprint shadow */}
            <polygon points={pts([...fb, [F.x1 + D.x, F.base + D.y], [F.x0 + D.x, F.base + D.y]])} fill="#D9D9E3" />
            {/* walls */}
            <polygon points={pts(side)} fill="#E3E4EE" stroke="#B9BAC9" strokeWidth="1" />
            <rect x={F.x0} y={F.top} width={F.x1 - F.x0} height={F.base - F.top} fill="#FFFFFF" stroke="#B9BAC9" strokeWidth="1" />
            {[0, 1, 2, 3, 4].map((i) => (
              <rect key={i} x={F.x0 + 22 + i * 64} y={F.top + 22} width="40" height="26" fill="#ECECF4" aria-hidden="true" />
            ))}
            {/* water rising slightly up the walls */}
            {flood > 0 && (
              <>
                <rect x={F.x0} y={F.base - flood} width={F.x1 - F.x0} height={flood} fill="#3B3FD8" opacity="0.28" />
                <polygon
                  points={pts([[F.x1, F.base - flood], [F.x1 + D.x, F.base + D.y - flood], [F.x1 + D.x, F.base + D.y], [F.x1, F.base]])}
                  fill="#3B3FD8" opacity="0.22"
                />
              </>
            )}
            {/* floating roof, drawn as a slab so the layers read clearly */}
            <polygon points={pts(roof.map(([x, y]) => [x, y + 6]))} fill="#9EA1E0" />
            <polygon points={pts(roof)} fill="#C8CAF3" stroke="#8D90DA" strokeWidth="1" />
            {/* layer names */}
            <g className="label" aria-hidden="true" fontFamily="var(--mono)" fontSize="11" fill="#8A8A8A" letterSpacing="1">
              <text x="34" y="200">ROOF</text>
              <text x="34" y="300">WALLS</text>
              <text x="34" y="436">GROUND</text>
            </g>
            {/* hail */}
            {dots.length > 0 && (
              <g className="hail" aria-hidden="true">
                {dots.map(([x, y], i) => (
                  <circle key={i} cx={x} cy={y} r={hail === 2 ? 3 : 2.4} fill="#6E72E3" opacity="0.55" />
                ))}
              </g>
            )}
            {/* pins */}
            {pins.map((p, i) => {
              const c = colourOf(p);
              const unsure = p.status === "uncertain";
              const right = p.x < 600;
              return (
                <g
                  key={p.kind}
                  ref={(el) => { refs.current[i] = el; }}
                  className={`pin${i === sel ? " selected" : ""}`}
                  tabIndex={0}
                  role="button"
                  aria-pressed={i === sel}
                  aria-label={`${p.n}: ${lower(p.name)}, ${unsure ? "uncertain" : `${p.label} risk`}`}
                  onClick={() => select(i, false)}
                  onKeyDown={(e) => onKey(e, i)}
                >
                  <circle className="ring" cx={p.x} cy={p.y} r="25" fill="none" stroke="#00008F" strokeWidth="3" />
                  <g className="dot">
                    <circle cx={p.x} cy={p.y} r="17" fill={unsure ? "#FFFFFF" : c} stroke={unsure ? c : "#FFFFFF"}
                      strokeWidth="2.5" strokeDasharray={unsure ? "4 3" : undefined} />
                    <text x={p.x} y={p.y + 5} textAnchor="middle" fontFamily="var(--head)" fontWeight="700"
                      fontSize="15" fill={unsure ? c : p.label === "low" ? "#212529" : "#FFFFFF"}>{p.n}</text>
                  </g>
                  <text className="pin-label" x={right ? p.x + 24 : p.x - 24} y={p.y + 5} textAnchor={right ? "start" : "end"}>
                    {lower(p.name)}
                  </text>
                </g>
              );
            })}
          </svg>
          <div className="legend">
            <span><i style={{ background: RISK.high }} />high</span>
            <span><i style={{ background: RISK.medium }} />medium</span>
            <span><i style={{ background: RISK.low }} />low</span>
            {pins.some((p) => p.status === "uncertain") && (
              <span><i style={{ border: `1.5px dashed ${RISK.uncertain}` }} />uncertain</span>
            )}
            <span><i style={{ background: "#6E72E3" }} />hail: {hazardWord(hazards.hail).word}</span>
            <span><i className="sq" style={{ background: "rgba(59,63,216,.3)" }} />water: {hazardWord(hazards.water).word}</span>
          </div>
        </div>
        <div className="pinrow" role="group" aria-label="Weak points">
          {pins.map((p, i) => (
            <button key={p.kind} type="button" className="pinbtn" aria-pressed={i === sel} onClick={() => select(i, false)}>
              <b style={{ background: p.status === "uncertain" ? RISK.uncertain : colourOf(p), color: p.label === "low" && p.status !== "uncertain" ? "#212529" : "#fff" }}>{p.n}</b>
              {lower(p.name)}
            </button>
          ))}
        </div>
        <p className="disclaimer">
          This spatial view summarizes evidence from the walk-around video. It is not a structural survey.
        </p>
      </div>

      <aside className="panel" aria-live="polite">
        {best && (
          <div className="photo">
            <img src={img.crop(jobId, best.id)} alt={`${current.name}, seen in your video`} />
          </div>
        )}
        <div className="body">
          <span className={`tag ${current.status === "uncertain" ? "uncertain" : current.label}`}>
            {current.status === "uncertain" ? "uncertain" : `${current.label} risk`}
          </span>
          <h3>{current.n}. {current.name}{current.count > 1 ? ` (${current.count}×)` : ""}</h3>
          <dl>
            <dt>Hazard</dt>
            <dd>{current.hazard === "hail" ? "Hail" : "Heavy rain / flooding"}: {hazardWord(hazards[current.hazard]).word} at this address</dd>
            <dt>Confidence</dt>
            <dd>{pct(current.confidence)}</dd>
            <dt>Seen at</dt>
            <dd>{current.seen_at.map(clock).join(", ")} in your video</dd>
          </dl>
          <div className="todo">
            <span className="label">Before a storm</span>
            <p>{current.now}</p>
          </div>
          <div className="todo">
            <span className="label">This year</span>
            <p>{current.later}</p>
          </div>
        </div>
      </aside>
    </div>
  );
}
