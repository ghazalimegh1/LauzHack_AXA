// Page frame: the AXA logo at the top right, the blue hero with its pixel blocks, the footer.

export function Logo() {
  return (
    <div className="logo">
      <img src="/axa-logo.png" alt="AXA" width="146" height="194" />
    </div>
  );
}

// A small field of square "pixel" blocks for the hero's bottom-right corner.
const BLOCKS = [
  [9, 0, "#3B3FD8", 1], [8, 1, "#3B3FD8", 0.7], [9, 1, "#027180", 1], [6, 2, "#ffffff", 0.16],
  [8, 2, "#3B3FD8", 1], [9, 2, "#3B3FD8", 0.5], [5, 3, "#3B3FD8", 0.6], [7, 3, "#027180", 0.9],
  [8, 3, "#3B3FD8", 1], [9, 3, "#ffffff", 0.22], [3, 4, "#ffffff", 0.12], [6, 4, "#3B3FD8", 1],
  [7, 4, "#3B3FD8", 0.55], [8, 4, "#027180", 1], [9, 4, "#3B3FD8", 1], [4, 5, "#3B3FD8", 0.5],
  [5, 5, "#3B3FD8", 1], [6, 5, "#027180", 0.7], [7, 5, "#3B3FD8", 1], [8, 5, "#ffffff", 0.18],
  [9, 5, "#3B3FD8", 1], [1, 5, "#3B3FD8", 0.35],
];

export function Pixels() {
  const size = 40;
  return (
    <svg className="pixels" viewBox="0 0 400 240" aria-hidden="true" focusable="false">
      {BLOCKS.map(([x, y, fill, opacity], i) => (
        <rect key={i} x={x * size} y={y * size} width={size} height={size} fill={fill}
          opacity={opacity} style={{ animationDelay: `${(i * 0.37) % 4}s` }} />
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
