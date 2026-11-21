"use client";

// The AXA logo on the jury page opens this two-part story (problem, then solution).
// Charts and drawings are hand-made SVG/CSS: no chart library, we are the frugal project.
// Every number comes from the DATA the team supplied (sources printed under each chart).

import { useEffect, useRef, useState } from "react";

// AXA storm damage per year, CHF million (vehicles, buildings, contents, fixtures).
const DAMAGE = [
  { year: "2021", chf: 291 },
  { year: "2023", chf: 240 },
  { year: "2024", chf: 132 },
  { year: "2025", chf: 72 },
];
const AVERAGE_30Y = 115;

// Measured, billed by OpenRouter on our two test videos (see README "Measured cost").
// The page only knows the latest run, so the two reference numbers are kept here.
const MEASURED = { day: "$0.0003", night: "$0.0012" };

const PARTS = 2;

export default function Story({ onClose }) {
  const [part, setPart] = useState(0);
  const box = useRef(null);

  // Next part; after the last one the story closes.
  function next() {
    if (part + 1 < PARTS) setPart(part + 1);
    else onClose();
  }

  function back() {
    setPart(Math.max(0, part - 1));
  }

  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
      else if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) {
        e.preventDefault();
        next();
      } else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key)) {
        e.preventDefault();
        back();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // While open, the page behind must not scroll and focus starts inside the story.
  useEffect(() => {
    const before = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (box.current) box.current.focus();
    return () => { document.body.style.overflow = before; };
  }, []);

  return (
    <div className="story" onClick={onClose}>
      <div
        className="story-box"
        role="dialog"
        aria-modal="true"
        aria-label={`Story, part ${part + 1} of ${PARTS}`}
        tabIndex={-1}
        ref={box}
        onClick={(e) => { e.stopPropagation(); next(); }}
      >
        <button className="story-close" type="button" aria-label="Close story"
          onClick={(e) => { e.stopPropagation(); onClose(); }}>×</button>
        {part === 0 ? <Problem /> : <Solution />}
        <div className="story-dots" aria-hidden="true">
          {Array.from({ length: PARTS }, (_, i) => <i key={i} className={i === part ? "on" : ""} />)}
        </div>
      </div>
    </div>
  );
}

// ---------------- part 1: the problem ----------------

function Problem() {
  return (
    <div className="story-part story-two" key="problem">
      <div className="story-block">
        <h2>Storms cost AXA a lot.</h2>
        <DamageChart />
        <p className="story-source">Source: AXA Schweiz, press release 4 Aug 2026; Keystone-SDA (2021, 2023)</p>
      </div>
      <div className="story-block">
        <h2>Cars are the biggest part.</h2>
        <CarShare />
        <p className="story-source">Source: Swiss Insurance Association (SVV) estimate, Sept 2026</p>
      </div>
    </div>
  );
}

// Bars per year with the 30-year average as a dashed line. Scale: 0..300 CHF million.
function DamageChart() {
  const W = 520, H = 300, top = 34, base = 250, left = 20, slot = 120, bar = 74;
  const y = (v) => base - (v / 300) * (base - top);
  return (
    <svg className="story-chart" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label="AXA storm damage in CHF million: 2021 291, 2023 240, 2024 132, 2025 72. 30-year average about 115.">
      {DAMAGE.map((d, i) => {
        const x = left + i * slot + (slot - bar) / 2;
        return (
          <g key={d.year}>
            <rect x={x} y={y(d.chf)} width={bar} height={base - y(d.chf)} className="sc-bar" />
            <text x={x + bar / 2} y={y(d.chf) - 10} textAnchor="middle" className="sc-value">{d.chf}</text>
            <text x={x + bar / 2} y={base + 30} textAnchor="middle" className="sc-year">{d.year}</text>
          </g>
        );
      })}
      <line x1={left} x2={W - 8} y1={y(AVERAGE_30Y)} y2={y(AVERAGE_30Y)} className="sc-avg" />
      <text x={W - 8} y={y(AVERAGE_30Y) - 8} textAnchor="end" className="sc-avg-label">30-year average ≈115</text>
      <line x1={left} x2={W - 8} y1={base} y2={base} className="sc-axis" />
      <text x={left} y={16} className="sc-unit">CHF million · selected years</text>
    </svg>
  );
}

// One bar split ">80% cars" vs "rest" for the late-August 2026 hailstorm.
function CarShare() {
  return (
    <div className="share" role="img"
      aria-label="Hailstorm end of August 2026: more than 80 percent of the private insured damage was cars. More than 100,000 cars hit.">
      <p className="share-title">Hailstorm, end of Aug 2026</p>
      <div className="share-bar">
        <div className="share-cars">
          <CarIcon />
          <b>&gt;80% cars</b>
        </div>
        <div className="share-rest">rest</div>
      </div>
      <p className="share-note">share of private insured damage</p>
      <p className="share-big">&gt;100,000 cars hit</p>
    </div>
  );
}

function CarIcon() {
  return (
    <svg className="share-car" viewBox="0 0 64 32" aria-hidden="true">
      <path d="M6 22 L10 13 Q12 9 17 9 L40 9 Q45 9 48 13 L54 19 L60 20 Q62 21 62 24 L62 26 L2 26 L2 23 Q2 22 6 22 Z" />
      <circle cx="16" cy="27" r="5" />
      <circle cx="48" cy="27" r="5" />
    </svg>
  );
}

// ---------------- part 2: the solution ----------------

function Solution() {
  return (
    <div className="story-part" key="solution">
      <h2>Fewer car damages. Cheaply.</h2>
      <div className="story-three">
        <figure><StormCar /><figcaption>Storm is coming.</figcaption></figure>
        <figure><AppLooks /><figcaption>The app looks.</figcaption></figure>
        <figure><SafeCar /><figcaption>Car safe. Cost tiny.</figcaption></figure>
      </div>
      <p className="story-last">Must be really cheap.</p>
      <p className="story-cost">
        {MEASURED.day} day video · {MEASURED.night} night video (measured, billed by OpenRouter)
      </p>
    </div>
  );
}

// Crayon look: a little noise pushes every line off its straight path.
function Crayon({ id }) {
  return (
    <defs>
      <filter id={id} x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="7" />
        <feDisplacementMap in="SourceGraphic" scale="4.5" />
      </filter>
    </defs>
  );
}

// Shared car, drawn by hand (slightly crooked on purpose).
function Car({ x = 0, y = 0, mood = "plain" }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <path className="cr cr-car" d="M8 62 C9 50 18 47 30 46 L44 30 C48 26 54 25 70 25 L96 26 C104 27 108 31 114 42 L130 45 C138 47 141 52 140 63 Z" />
      <path className="cr cr-window" d="M50 43 L58 33 C60 31 64 31 72 31 L72 44 Z M78 31 L94 32 C99 33 102 37 105 43 L78 44 Z" />
      <circle className="cr cr-wheel" cx="38" cy="64" r="11" />
      <circle className="cr cr-wheel" cx="112" cy="64" r="11" />
      {mood === "sad" && <path className="cr cr-face" d="M118 56 Q124 52 130 57" />}
      {mood === "happy" && <path className="cr cr-face" d="M118 53 Q124 59 131 53" />}
    </g>
  );
}

function StormCar() {
  const hail = [[52, 92], [80, 118], [110, 96], [140, 124], [168, 98], [196, 120], [96, 146], [154, 150], [62, 136]];
  return (
    <svg className="drawing" viewBox="0 0 240 240" aria-hidden="true">
      <Crayon id="crayon-a" />
      <g filter="url(#crayon-a)">
        <path className="cr cr-cloud" d="M40 70 C26 70 22 50 38 44 C40 26 64 20 76 34 C86 14 120 14 128 34 C142 22 170 28 168 46 C188 44 196 66 180 72 C150 78 72 78 40 70 Z" />
        <circle className="cr cr-eye" cx="88" cy="50" r="3.5" />
        <circle className="cr cr-eye" cx="128" cy="50" r="3.5" />
        <path className="cr cr-face" d="M94 64 Q108 54 122 64" />
        {hail.map(([cx, cy], i) => <circle key={i} className="cr cr-hail" cx={cx} cy={cy} r={i % 2 ? 6 : 7.5} />)}
        <Car x={44} y={150} mood="sad" />
        <path className="cr cr-ground" d="M10 226 C70 222 150 230 230 224" />
      </g>
    </svg>
  );
}

function AppLooks() {
  return (
    <svg className="drawing" viewBox="0 0 240 240" aria-hidden="true">
      <Crayon id="crayon-b" />
      <g filter="url(#crayon-b)">
        {/* the yard with a car */}
        <path className="cr cr-ground" d="M8 214 C80 208 160 218 232 210" />
        <Car x={84} y={136} />
        {/* the phone filming it */}
        <rect className="cr cr-phone" x="18" y="40" width="70" height="124" rx="12" transform="rotate(-8 53 102)" />
        <path className="cr cr-screen" d="M30 58 L80 52 L88 140 L38 146 Z" />
        <circle className="cr cr-rec" cx="44" cy="68" r="5" />
        <path className="cr cr-beam" d="M88 76 L168 118 M90 128 L150 196" />
        {/* the small happy computer-eye */}
        <rect className="cr cr-screenbox" x="150" y="22" width="74" height="56" rx="8" />
        <ellipse className="cr cr-bigeye" cx="187" cy="48" rx="20" ry="13" />
        <circle className="cr cr-pupil" cx="181" cy="51" r="6" />
        <path className="cr cr-face" d="M174 70 Q187 78 200 70" />
        <path className="cr cr-stand" d="M187 78 L185 96 M170 98 L202 96" />
      </g>
    </svg>
  );
}

function SafeCar() {
  return (
    <svg className="drawing" viewBox="0 0 240 240" aria-hidden="true">
      <Crayon id="crayon-c" />
      <g filter="url(#crayon-c)">
        {/* smiling sun */}
        <circle className="cr cr-sun" cx="200" cy="38" r="20" />
        <path className="cr cr-ray" d="M200 6 L201 13 M232 38 L226 39 M224 14 L219 19 M176 14 L181 20 M224 62 L219 57" />
        <path className="cr cr-face" d="M192 42 Q200 49 208 42" />
        {/* the roof over the car */}
        <path className="cr cr-roof" d="M6 84 L84 52 L166 82 Z" />
        <path className="cr cr-post" d="M20 84 L22 196 M152 82 L150 196" />
        <Car x={8} y={128} mood="happy" />
        <path className="cr cr-ground" d="M4 212 C60 206 120 214 168 208" />
        {/* the coin stays in the piggy bank */}
        <ellipse className="cr cr-pig" cx="204" cy="178" rx="28" ry="21" />
        <path className="cr cr-pigleg" d="M190 196 L189 208 M216 196 L218 208 M178 170 L170 168 M226 166 Q236 160 232 172" />
        <circle className="cr cr-eye" cx="214" cy="170" r="2.6" />
        <path className="cr cr-slot" d="M196 158 L212 157" />
        <ellipse className="cr cr-coin" cx="204" cy="146" rx="9" ry="9" />
      </g>
    </svg>
  );
}
