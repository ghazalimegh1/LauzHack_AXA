// The steps of a check, ticked off as the server really reaches them (see sitecheck.run).
const STEPS = [
  ["upload", "Sending your video"],
  ["address", "Finding your address on the official hazard maps"],
  ["frames", "Choosing the clearest moments of your video"],
  ["privacy", "Blurring people and spotting vehicles"],
  ["ai", "Looking for weak points"],
  ["plan", "Writing your storm plan"],
];

export default function Progress({ stage }) {
  const now = Math.max(0, STEPS.findIndex(([key]) => key === (stage || "upload")));
  return (
    <ol className="progress-steps" aria-live="polite">
      {STEPS.map(([key, text], i) => (
        <li key={key} className={i < now ? "done" : i === now ? "now" : "next"}>
          <span className="tick" aria-hidden="true">{i < now ? "✓" : ""}</span>
          {text}
        </li>
      ))}
    </ol>
  );
}
