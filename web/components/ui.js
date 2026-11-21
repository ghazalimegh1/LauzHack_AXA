// Tiny building blocks used on both pages.
import { COLOURS } from "../lib/format";

// Importance tag (HIGH / MEDIUM ...): the only place besides the boxes with risk colours.
export function Tag({ label, colours = COLOURS }) {
  return (
    <span className="tag" style={{ background: colours[label] || "#8E8E93" }}>
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
