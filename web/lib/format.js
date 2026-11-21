export const RISK = {
  high: "#C62828",
  medium: "#E8710A",
  low: "#F2A900",
  uncertain: "#5F5F5F",
  none: "#8A8A8A",
};

export function usd(x) {
  if (!x) return "$0";
  if (x < 0.001) return `$${x.toFixed(5)}`;
  if (x < 0.1) return `$${x.toFixed(4)}`;
  return `$${x.toFixed(2)}`;
}

export function clock(seconds) {
  const s = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function ms(x) {
  if (x < 1000) return `${x} ms`;
  return `${(x / 1000).toFixed(1)} s`;
}

export function pct(x) {
  return `${Math.round((x || 0) * 100)}%`;
}

export function tokens(n) {
  return n ? n.toLocaleString("en-US") : "–";
}

export function lower(name) {
  return name ? name.charAt(0).toLowerCase() + name.slice(1) : "";
}

// Hazard level -> the word and colour shown on chips.
export function hazardWord(h) {
  if (!h || !h.available) return { word: "map unavailable", colour: RISK.none };
  return { word: h.word, colour: ["#027180", RISK.medium, RISK.high][h.level] || RISK.none };
}

export function timeOfDay(unix) {
  return new Date(unix * 1000).toLocaleString("en-GB", {
    weekday: "short", hour: "2-digit", minute: "2-digit",
  });
}
