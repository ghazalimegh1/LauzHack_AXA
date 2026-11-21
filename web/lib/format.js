// Small text helpers shared by both pages.

// Same colours as COLOURS in frugal/sitecheck.py (the boxes on the frames). Used until
// /api/info has answered, so tags never flash without colour.
export const COLOURS = {
  high: "#C62828", medium: "#E8710A", low: "#F2A900",
  "not relevant here": "#999999", privacy: "#3B3FD8", uncertain: "#5F5F5F",
};

export const GROUP_NAMES = { hail: "Hail", water: "Water" };

// "Hail risk here: high", or "unavailable" when the map did not answer (never "low").
export function riskText(group) {
  return group.answered ? group.level_name : "unavailable";
}

// Two significant digits for tiny amounts: $0.00077, $0.032, $1.25.
export function usd(x) {
  if (!x) return "$0";
  if (x >= 1) return `$${x.toFixed(2)}`;
  const decimals = Math.max(2, 1 - Math.floor(Math.log10(x)));
  return `$${x.toFixed(decimals)}`;
}

// "about 12x", "about 200x"
export function times(big, small) {
  if (!small) return "";
  const r = big / small;
  return `about ${r < 10 ? r.toFixed(1) : Math.round(r).toLocaleString("en")}x`;
}
