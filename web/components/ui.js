// Tiny building blocks used on both pages.
import { COLOURS } from "../lib/format";

// Importance tag (HIGH / MEDIUM ...): the only place besides the boxes with risk colours.
export function Tag({ label, colours = COLOURS }) {
  return (
    <span className="tag" style={{ background: colours[label] || "#999999" }}>
      {label}
    </span>
  );
}

// Neutral blue chip, e.g. "Hail risk here: high".
export function Chip({ children }) {
  return <span className="chip">{children}</span>;
}

export function Spinner({ children }) {
  return (
    <p className="progress" role="status">
      <span className="spinner" aria-hidden="true" />
      {children}
    </p>
  );
}

// Shown only when no AI key is set, so nobody mistakes simulated answers for real ones.
export function DemoBadge({ info }) {
  if (!info || !info.mock) return null;
  return <span className="badge">demo mode (no AI key)</span>;
}

// Small "■ STEP 1 · FREE" label above a heading (the square comes from the CSS).
export function Eyebrow({ children }) {
  return <p className="eyebrow">{children}</p>;
}

// The pixel blocks in the corner of the blue band, the same pattern as the Streamlit app.
// "#" = white block, "o" = lighter blue block, "." = empty.
const PIXELS = ["..#..#", ".#.#..", "#..o.#", ".#..#.", "o.#...", ".#..o#"];

function Pixels() {
  return (
    <div className="pixels" aria-hidden="true">
      {PIXELS.join("").split("").map((c, i) => (
        <i key={i} className={c === "#" ? "on" : c === "o" ? "mid" : ""} />
      ))}
    </div>
  );
}

// The blue band at the top of each page: label, big headline, then any text or chips.
export function Hero({ eyebrow, title, children }) {
  return (
    <section className="hero">
      <Pixels />
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <h1>{title}</h1>
      {children}
    </section>
  );
}
