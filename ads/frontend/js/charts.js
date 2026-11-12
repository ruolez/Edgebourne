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

// About six day labels: every k-th day and always the last, minus a regular one too close to the last to fit
// (closer than half a step; 14 days → 0,3,6,9,13, 30 days → 0,5,…,25,29).
function dayTick(i, n) {
  const every = Math.ceil(n / 6);
  return i === n - 1 || (i % every === 0 && n - 1 - i >= Math.ceil(every / 2));
}

// The chart in words, for screen readers (and anyone who'd rather read): the period, the total and the best day.
let sumSeq = 0;
export function columnSummary(series, key, format, title) {
  if (!series.length) return `${title}: no days to show.`;
  const values = series.map((d) => d[key] || 0);
  const total = values.reduce((a, b) => a + b, 0);
  const span = `${dayLabel(series[0].day)} to ${dayLabel(series[series.length - 1].day)}`;
  if (!total) return `${title}, ${span}: nothing on any day.`;
  const top = values.indexOf(Math.max(...values));
  return `${title}, ${span}: ${format(total)} in total, the most on ${dayLabel(series[top].day)} (${format(values[top])}).`;
}

export function lineSummary(series, format, title) {
  const parts = series.map((s) => {
    const pts = s.points.filter((p) => p.value != null);
    if (!pts.length) return `${s.label}: no data`;
    const top = pts.reduce((a, b) => (b.value > a.value ? b : a));
    return `${s.label}: highest ${format(top.value)} on ${dayLabel(top.day)}, last ${format(pts[pts.length - 1].value)}`;
  });
  return `${title}. ${parts.join("; ")}.`;
}

const described = (svgLabel, text) => {
  const id = `chart-sum-${++sumSeq}`;
  return { attrs: `role="img" aria-label="${esc(svgLabel)}" aria-describedby="${id}"`, note: `<p class="sr-only" id="${id}">${esc(text)}</p>` };
};

// Charts are drawn 560 wide and scaled to fit; in a narrower box (phones) they are drawn at the box's own width,
// so 12px labels stay 12px and the height isn't left half empty.
function drawWidth(el) {
  const cs = getComputedStyle(el);
  const w = Math.floor(el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight));
  return w >= 240 && w < 560 ? w : 560;
}

export function columnChart({ el, series, key, color, format, axisFormat, title, integer = false, height = 220 }) {
  const W = drawWidth(el), H = height, L = 52, R = 8, T = 10, B = 26;
  const values = series.map((d) => d[key]);
  const { top, step } = niceMax(Math.max(...values, 0), 4, integer);
  const plotW = W - L - R, plotH = H - T - B;
  const band = plotW / series.length;
  const bw = Math.min(24, Math.max(3, band - 2));
  const y = (v) => T + plotH - (v / top) * plotH;
  const empty = !values.some((v) => v > 0);
  let grid = "", ticks = "";
  for (let v = 0; v <= top + 1e-9; v += step) {
    grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
    if (empty && v > 0) continue;
    ticks += `<text class="tick" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${axisFormat(v)}</text>`;
  }
  const cols = series.map((d, i) => {
    const x = L + i * band + (band - bw) / 2;
    const h = (d[key] / top) * plotH;
    const r = Math.min(4, h);
    const path = h <= 0 ? "" : `M${x},${T + plotH} V${T + plotH - h + r} Q${x},${T + plotH - h} ${x + r},${T + plotH - h} H${x + bw - r} Q${x + bw},${T + plotH - h} ${x + bw},${T + plotH - h + r} V${T + plotH} Z`;
    const label = dayTick(i, series.length) ? `<text class="tick" x="${L + i * band + band / 2}" y="${H - 6}" text-anchor="middle">${dayLabel(d.day)}</text>` : "";
    return `<rect class="hit" data-i="${i}" x="${L + i * band}" y="${T}" width="${band}" height="${plotH}"/><path class="col" d="${path}" fill="${color}"/>${label}`;
  }).join("");
  const sum = described(title, columnSummary(series, key, format, title));
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" ${sum.attrs}><g class="grid">${grid}</g>${ticks}${cols}</svg>${sum.note}<div class="tip" hidden></div>`;
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

// Horizontal bars for a breakdown: one measure, sorted, labels left, values right.
export function barList(el, items, { key, format, max = null, extra = null }) {
  const top = max ?? Math.max(...items.map((i) => i[key]), 0);
  el.innerHTML = items.length ? `<ul class="bars">${items.map((i) => `
    <li><span class="bar-label">${esc(i.label)}</span>
      <span class="bar-track"><i data-w="${top ? (i[key] / top) * 100 : 0}"></i></span>
      <span class="bar-value">${esc(format(i[key]))}</span>${extra ? `<span class="bar-extra">${extra(i)}</span>` : ""}</li>`).join("")}</ul>`
    : '<p class="muted flush">No data for this period.</p>';
  el.querySelectorAll(".bar-track i[data-w]").forEach((b) => { b.style.width = `${b.dataset.w}%`; });
}

// Several lines on one axis (compare: one line per ad). series = [{ label, cls, points: [{day, value}] }].
// Thin lines, round joins, one shared y axis, a tooltip listing every line on the hovered day.
export function lineChart({ el, series, format, axisFormat, title, integer = false, height = 220 }) {
  const W = drawWidth(el), H = height, L = 52, R = 10, T = 12, B = 26;
  const days = series[0]?.points.map((p) => p.day) || [];
  const values = series.flatMap((s) => s.points.map((p) => p.value ?? 0));
  const { top, step } = niceMax(Math.max(...values, 0), 4, integer);
  const plotW = W - L - R, plotH = H - T - B;
  const x = (i) => L + (days.length > 1 ? (i / (days.length - 1)) * plotW : plotW / 2);
  const y = (v) => T + plotH - (v / top) * plotH;
  let grid = "", ticks = "";
  for (let v = 0; v <= top + 1e-9; v += step) {
    grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
    ticks += `<text class="tick" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${esc(axisFormat(v))}</text>`;
  }
  const labels = days.map((d, i) => (dayTick(i, days.length) ? `<text class="tick" x="${x(i)}" y="${H - 6}" text-anchor="middle">${dayLabel(d)}</text>` : "")).join("");
  const lines = series.map((s) => {
    const pts = s.points.map((p, i) => (p.value == null ? null : `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`)).filter(Boolean).join(" ");
    return `<polyline class="ln ${s.cls}" points="${pts}"/>`;
  }).join("");
  const hits = days.map((d, i) => `<rect class="hit" data-i="${i}" x="${x(i) - plotW / Math.max(days.length - 1, 1) / 2}" y="${T}" width="${plotW / Math.max(days.length - 1, 1)}" height="${plotH}"/>`).join("");
  const sum = described(title, lineSummary(series, format, title));
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" ${sum.attrs}><g class="grid">${grid}</g>${ticks}${labels}${lines}<line class="cursor" x1="0" x2="0" y1="${T}" y2="${T + plotH}" hidden/>${hits}</svg>${sum.note}<div class="tip" hidden></div>`;
  el.querySelector("svg").style.height = `${H}px`;
  const svg = el.querySelector("svg"), tip = el.querySelector(".tip"), cursor = el.querySelector(".cursor");
  el.querySelectorAll(".hit").forEach((hit) => {
    hit.addEventListener("mouseenter", () => {
      const i = Number(hit.dataset.i);
      const scale = svg.getBoundingClientRect().width / W;
      cursor.setAttribute("x1", x(i)); cursor.setAttribute("x2", x(i)); cursor.hidden = false;
      tip.innerHTML = `<small>${dayLabel(days[i])}</small>${series.map((s) => `<span class="tip-row"><i class="sw ${s.cls}"></i>${esc(s.label)} <b>${s.points[i].value == null ? "—" : esc(format(s.points[i].value))}</b></span>`).join("")}`;
      tip.style.left = `${x(i) * scale}px`;
      tip.style.top = `${T * scale}px`;
      tip.hidden = false;
    });
    hit.addEventListener("mouseleave", () => { tip.hidden = true; cursor.hidden = true; });
  });
}
