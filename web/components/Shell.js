// Page frame: the AXA logo at the top right, the blue hero with its pixel blocks, the footer.

export function Logo() {
  return (
    <div className="logo">
      <img src="/axa-logo.png" alt="AXA" width="146" height="194" />
    </div>
  );
}

// The pixel blocks of the blue band (the team's pattern from the earlier app).
// "#" = white block, "o" = lighter blue block, "." = empty.
const PATTERN = ["..#..#", ".#.#..", "#..o.#", ".#..#.", "o.#...", ".#..o#"];

export function Pixels() {
  const size = 40;
  const blocks = [];
  PATTERN.forEach((row, y) => row.split("").forEach((c, x) => {
    if (c !== ".") blocks.push([x, y, c === "#" ? "#FFFFFF" : "#3B3FD8"]);
  }));
  return (
    <svg className="pixels" viewBox="0 0 240 240" aria-hidden="true" focusable="false">
      {blocks.map(([x, y, fill], i) => (
        <rect key={i} x={x * size} y={y * size} width={size} height={size} fill={fill}
          style={{ animationDelay: `${(i * 0.53) % 4}s` }} />
      ))}
    </svg>
  );
}

export function Hero({ title, children, toplink }) {
  return (
    <header className="hero band">
      {toplink}
      <Logo />
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
        <span>Frugal Site Check · LauzHack 2026 · AXA challenge “Frugal use of Multimodal AI”</span>
        {children}
      </div>
    </footer>
  );
}
