// Column charts (one measure per chart, rounded data-ends, tooltips). Colors come
// from CSS variables validated with the dataviz palette checker.
import { esc } from "./ui.js";
import { dayLabel } from "./format.js";

// Clean tick steps (1, 2, 2.5, 5 × 10^n) so the axis reads in round numbers.
export function niceMax(max, ticks = 4, integer = false) {
  if (max <= 0) return { top: ticks, step: 1 };
  const raw = max / ticks;
  const mag = 10 ** Math.floor(Math.log10(raw));
  let step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  if (integer) step = Math.max(1, Math.ceil(step));
  return { top: step * Math.ceil(max / step), step };
}

export function columnChart({ el, series, key, color, format, axisFormat, title, integer = false, height = 220 }) {
  const W = 560, H = height, L = 52, R = 8, T = 10, B = 26;
  const values = series.map((d) => d[key]);
  const { top, step } = niceMax(Math.max(...values, 0), 4, integer);
  const plotW = W - L - R, plotH = H - T - B;
  const band = plotW / series.length;
  const bw = Math.min(24, Math.max(3, band - 2));
  const y = (v) => T + plotH - (v / top) * plotH;
  let grid = "", ticks = "";
  for (let v = 0; v <= top + 1e-9; v += step) {
    grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
    ticks += `<text class="tick" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${axisFormat(v)}</text>`;
  }
  const every = Math.ceil(series.length / 6);
  const cols = series.map((d, i) => {
    const x = L + i * band + (band - bw) / 2;
    const h = (d[key] / top) * plotH;
    const r = Math.min(4, h);
    const path = h <= 0 ? "" : `M${x},${T + plotH} V${T + plotH - h + r} Q${x},${T + plotH - h} ${x + r},${T + plotH - h} H${x + bw - r} Q${x + bw},${T + plotH - h} ${x + bw},${T + plotH - h + r} V${T + plotH} Z`;
    const label = i % every === 0 || i === series.length - 1 ? `<text class="tick" x="${L + i * band + band / 2}" y="${H - 6}" text-anchor="middle">${dayLabel(d.day)}</text>` : "";
    return `<rect class="hit" data-i="${i}" x="${L + i * band}" y="${T}" width="${band}" height="${plotH}"/><path class="col" d="${path}" fill="${color}"/>${label}`;
  }).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}"><g class="grid">${grid}</g>${ticks}${cols}</svg><div class="tip" hidden></div>`;
  el.querySelector("svg").style.height = `${H}px`;
  const tip = el.querySelector(".tip");
  const svg = el.querySelector("svg");
  el.querySelectorAll(".hit").forEach((hit) => {
    hit.addEventListener("mouseenter", () => {
      const i = Number(hit.dataset.i);
      const d = series[i];
      const scale = svg.getBoundingClientRect().width / W;
      tip.innerHTML = `${format(d[key])}<small>${dayLabel(d.day)}</small>`;
      tip.style.left = `${(L + i * band + band / 2) * scale}px`;
      tip.style.top = `${y(d[key]) * scale}px`;
      tip.hidden = false;
    });
    hit.addEventListener("mouseleave", () => { tip.hidden = true; });
  });
}
