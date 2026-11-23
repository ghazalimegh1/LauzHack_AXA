// Page frame: the AXA logo at the top right, the blue hero with its pixel blocks, the footer.

// With onOpen (jury page) the logo is a button that opens the story; otherwise just the logo.
export function Logo({ onOpen }) {
  const picture = <img src="/axa-logo.png" alt="AXA" width="146" height="194" />;
  return (
    <div className="logo">
      {onOpen ? (
        <button className="logo-button" type="button" onClick={onOpen} aria-label="AXA: open the story">
          {picture}
        </button>
      ) : picture}
    </div>
  );
}

// The pixel blocks of the blue band, laid out as one line of letters: ΣΩΤΗΡΙΑ ("soteria",
// Greek for safety and rescue), written as on the Roman mosaic, with a round sigma (C) and ω.
// "#" = block, "." = empty; every letter is 5 blocks tall.
const GLYPHS = {
  C: [".##", "#..", "#..", "#..", ".##"],
  ω: [".....", "#...#", "#.#.#", "#.#.#", ".#.#."],
  T: ["###", ".#.", ".#.", ".#.", ".#."],
  H: ["#.#", "#.#", "###", "#.#", "#.#"],
  P: ["##.", "#.#", "##.", "#..", "#.."],
  I: ["#", "#", "#", "#", "#"],
  A: [".#.", "#.#", "###", "#.#", "#.#"],
};
const WORD = ["C", "ω", "T", "H", "P", "I", "A"];
const ROWS = 5;

// Columns of the whole word, one empty column between letters.
const LINE = WORD.flatMap((ch, i) => {
  const g = GLYPHS[ch];
  const cols = g[0].split("").map((_, x) => g.map((row) => row[x]));
  return i === 0 ? cols : [Array(ROWS).fill("."), ...cols];
});

export function Pixels() {
  const size = 10;
  const gap = 1.2;            // thin seams between the blocks, like mosaic stones
  const blocks = [];
  LINE.forEach((col, x) => col.forEach((c, y) => {
    if (c === "#") blocks.push([x, y]);
  }));
  return (
    <svg className="pixels" viewBox={`0 0 ${LINE.length * size} ${ROWS * size}`}
      aria-hidden="true" focusable="false">
      {blocks.map(([x, y], i) => (
        // Colour and pulse come from globals.css; the delays make the blocks shimmer one by one.
        <rect key={i} x={x * size + gap / 2} y={y * size + gap / 2}
          width={size - gap} height={size - gap}
          style={{ animationDelay: `${(i * 0.53) % 4}s` }} />
      ))}
    </svg>
  );
}

export function Hero({ title, children, toplink, onLogo }) {
  return (
    <header className="hero band">
      {toplink}
      <Logo onOpen={onLogo} />
      <div className="inner">
        <h1 className="reveal">{title}</h1>
        {children}
      </div>
      <Pixels />
    </header>
  );
}

export function Footer({ children }) {
  return (
    <footer className="footer">
      <div className="inner">
        <span>Site Check AXA · LauzHack 2026 · AXA challenge “Frugal use of Multimodal AI”</span>
        {children}
      </div>
    </footer>
  );
}
