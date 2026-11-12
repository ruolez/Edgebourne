// Column charts (one measure per chart, rounded data-ends, tooltips). Colors come
// from CSS variables validated with the dataviz palette checker.
import { entityLink, esc, historyHref, switchHtml } from "./ui.js";
import { CHANGE_CATS, dayLabel } from "./format.js";

// ---- change marks (D2): small ticks under the days something changed, listed in the tooltip ----
const LEVEL_NAMES = { campaign: "Campaign", adset: "Ad set", ad: "Ad" };
const markOf = (marks) => new Map((marks || []).map((m) => [m.day, m]));
// The tooltip's list of changes on one day: the change, then what it was on (when that isn't this page) and who.
function tipChanges(m) {
  if (!m) return "";
  const here = new URLSearchParams(location.search).get("id");
  return `<ul class="tip-chg">${m.items.map((i) => `<li><i class="chg-dot chg-${esc(i.cat)}" aria-hidden="true"></i><span>${esc(i.title)}<small>${[
    i.entity_id && i.entity_id !== here && i.entity_name ? esc(i.entity_name) : "", i.by ? esc(i.by) : ""].filter(Boolean).join(" · ")}</small></span></li>`).join("")}${
    m.more ? `<li class="tip-more">and ${m.more} more</li>` : ""}</ul>`;
}
// Ticks under the plot, coloured by the day's first (most important) kind; a budget day also gets a faint guide.
function markShapes(marks, xCenter, T, plotH) {
  return (marks || []).map(({ m, i }) => {
    const x = xCenter(i);
    const cat = m.cats[0] || "meta";
    return `${m.cats.includes("money") ? `<line class="chg-guide" x1="${x}" x2="${x}" y1="${T}" y2="${T + plotH}"/>` : ""}<rect class="chg-mark chg-${esc(cat)}" x="${x - 2}" y="${T + plotH + 3}" width="4" height="6" rx="1"/>`;
  }).join("");
}
// One tooltip open at a time; a tap outside a chart closes it (touch only: a mouse closes it on leave).
let openTip = null;
document.addEventListener("pointerdown", (e) => {
  if (openTip && !openTip.box.contains(e.target)) { openTip.hide(); openTip = null; }
});
// Hover with a mouse, tap with a finger: the same tooltip, its left edge kept inside the chart box.
function wireTips(el, show, hide) {
  const tip = el.querySelector(".tip");
  const place = () => {
    const box = el.getBoundingClientRect();
    const w = tip.offsetWidth;
    const left = parseFloat(tip.style.left) || 0;
    const min = w / 2, max = box.width - w / 2;
    if (max > min) tip.style.left = `${Math.min(Math.max(left, min), max)}px`;
  };
  el.querySelectorAll(".hit").forEach((hit) => {
    hit.addEventListener("mouseenter", () => { show(Number(hit.dataset.i)); place(); });
    hit.addEventListener("mouseleave", hide);
    hit.addEventListener("pointerup", (e) => {
      if (e.pointerType === "mouse") return;
      const i = Number(hit.dataset.i);
      if (openTip && openTip.box === el && openTip.i === i) { hide(); openTip = null; return; }
      if (openTip) openTip.hide();
      show(i); place();
      openTip = { box: el, i, hide };
    });
  });
}

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

export function columnChart({ el, series, key, color, format, axisFormat, title, integer = false, height = 220, marks = [], marksSummary = "" }) {
  const byDay = markOf(marks);
  const marked = series.map((d, i) => ({ m: byDay.get(d.day), i })).filter((x) => x.m);
  const W = drawWidth(el), H = height + (marked.length ? 10 : 0), L = 52, R = 8, T = 10, B = 26 + (marked.length ? 10 : 0);
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
  const sum = described(marksSummary ? `${title}. ${marksSummary}` : title, columnSummary(series, key, format, title));
  const shapes = markShapes(marked, (i) => L + i * band + band / 2, T, plotH);
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" ${sum.attrs}><g class="grid">${grid}</g>${ticks}${shapes}${cols}</svg>${sum.note}<div class="tip" hidden></div>`;
  el.querySelector("svg").style.height = `${H}px`;
  const tip = el.querySelector(".tip");
  const svg = el.querySelector("svg");
  wireTips(el, (i) => {
    const d = series[i];
    const scale = svg.getBoundingClientRect().width / W;
    tip.innerHTML = `${format(d[key])}<small>${dayLabel(d.day)}</small>${tipChanges(byDay.get(d.day))}`;
    tip.style.left = `${(L + i * band + band / 2) * scale}px`;
    tip.style.top = `${y(d[key]) * scale}px`;
    tip.hidden = false;
  }, () => { tip.hidden = true; });
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
// `dashes[i]` gives line i its own dash pattern and a series `key` (1, 2…) is drawn where its line ends, so the
// lines can be told apart without their colour.
export function lineChart({ el, series, format, axisFormat, title, integer = false, height = 220, dashes = [], marks = [], marksSummary = "" }) {
  const keyed = series.some((s) => s.key);
  const days = series[0]?.points.map((p) => p.day) || [];
  const byDay = markOf(marks);
  const marked = days.map((d, i) => ({ m: byDay.get(d), i })).filter((x) => x.m);
  const W = drawWidth(el), H = height + (marked.length ? 10 : 0), L = 52, R = keyed ? 26 : 10, T = 12, B = 26 + (marked.length ? 10 : 0);
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
  const lines = series.map((s, n) => {
    const pts = s.points.map((p, i) => (p.value == null ? null : `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`)).filter(Boolean).join(" ");
    return `<polyline class="ln ${s.cls}" points="${pts}"${dashes[n] ? ` stroke-dasharray="${dashes[n]}"` : ""}/>`;
  }).join("");
  // Keys at the line ends, nudged apart when two lines end at the same height.
  const ends = series.map((s) => {
    const i = s.points.map((p) => p.value != null).lastIndexOf(true);
    return s.key && i >= 0 ? { s, cx: x(i), cy: y(s.points[i].value) } : null;
  }).filter(Boolean).sort((a, b) => a.cy - b.cy);
  ends.forEach((e, i) => { if (i && e.cy - ends[i - 1].cy < 15) e.cy = ends[i - 1].cy + 15; });
  const keys = ends.map((e) => `<g class="ln-key ${e.s.cls}" aria-hidden="true"><circle cx="${(e.cx + 12).toFixed(1)}" cy="${e.cy.toFixed(1)}" r="7.5"/><text x="${(e.cx + 12).toFixed(1)}" y="${(e.cy + 3.5).toFixed(1)}" text-anchor="middle">${esc(e.s.key)}</text></g>`).join("");
  const hits = days.map((d, i) => `<rect class="hit" data-i="${i}" x="${x(i) - plotW / Math.max(days.length - 1, 1) / 2}" y="${T}" width="${plotW / Math.max(days.length - 1, 1)}" height="${plotH}"/>`).join("");
  const sum = described(marksSummary ? `${title}. ${marksSummary}` : title, lineSummary(series, format, title));
  const shapes = markShapes(marked, x, T, plotH);
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" ${sum.attrs}><g class="grid">${grid}</g>${ticks}${labels}${shapes}${lines}${keys}<line class="cursor" x1="0" x2="0" y1="${T}" y2="${T + plotH}" hidden/>${hits}</svg>${sum.note}<div class="tip" hidden></div>`;
  el.querySelector("svg").style.height = `${H}px`;
  const svg = el.querySelector("svg"), tip = el.querySelector(".tip"), cursor = el.querySelector(".cursor");
  wireTips(el, (i) => {
    const scale = svg.getBoundingClientRect().width / W;
    cursor.setAttribute("x1", x(i)); cursor.setAttribute("x2", x(i)); cursor.hidden = false;
    tip.innerHTML = `<small>${dayLabel(days[i])}</small>${series.map((s) => `<span class="tip-row"><i class="sw ${s.cls}"></i>${s.key ? `${esc(s.key)} · ` : ""}${esc(s.label)} <b>${s.points[i].value == null ? "—" : esc(format(s.points[i].value))}</b></span>`).join("")}${tipChanges(byDay.get(days[i]))}`;
    tip.style.left = `${x(i) * scale}px`;
    tip.style.top = `${T * scale}px`;
    tip.hidden = false;
  }, () => { tip.hidden = true; cursor.hidden = true; });
}

// ---- the changes panel under the charts (D2) ----
// Whether marks show on the charts: one switch per viewer, remembered in this browser (on by default).
const MARKS_KEY = "eb-chg-marks";
export function marksShown() {
  try { return localStorage.getItem(MARKS_KEY) !== "0"; } catch (e) { return true; }
}
export function applyMarksShown(on = marksShown()) {
  document.body.classList.toggle("chg-off", !on);
}
function rememberMarks(on) {
  try { localStorage.setItem(MARKS_KEY, on ? "1" : "0"); } catch (e) { /* storage off: it just isn't remembered */ }
}
// "3 changes in this period" with a Show on charts switch and the list, each linking to the History of what changed.
// `list` = the server's newest changes of the period ({items, total}, newest first, not cut per day like the marks).
export function marksPanel(el, marks, summary, list = null) {
  if (!el) return;
  applyMarksShown();
  const rows = list ? list.items || []
    : (marks || []).flatMap((m) => m.items.map((i) => ({ ...i, day: m.day }))).reverse();
  if (!rows.length) { el.innerHTML = '<p class="muted small flush">No changes in this period.</p>'; return; }
  const total = list ? list.total : rows.length + (marks || []).reduce((n, m) => n + (m.more || 0), 0);
  const here = new URLSearchParams(location.search).get("id");
  const legend = Object.entries(CHANGE_CATS).map(([k, l]) => `<span><i class="chg-dot chg-${k}" aria-hidden="true"></i>${esc(l)}</span>`).join("");
  const row = (i) => {
    const where = i.entity_id && i.entity_id !== here && LEVEL_NAMES[i.level]
      ? ` · ${entityLink(i.level, i.entity_id, i.entity_name ? `${LEVEL_NAMES[i.level]} “${i.entity_name}”` : `the ${LEVEL_NAMES[i.level].toLowerCase()}`)}` : "";
    const open = i.entity_id && LEVEL_NAMES[i.level] ? `<a class="chg-open" href="${esc(historyHref(i.level, i.entity_id))}">History</a>` : "";
    return `<li><span class="r-date">${esc(dayLabel(i.day))}</span><i class="chg-dot chg-${esc(i.cat)}" aria-hidden="true"></i><span class="chg-what">${esc(i.title)}${where}${i.by ? ` · by ${esc(i.by)}` : ""}</span>${open}</li>`;
  };
  el.innerHTML = `<details class="chg-fold"><summary>${total} change${total === 1 ? "" : "s"} in this period</summary>
    <div class="chg-tools"><div class="chg-legend">${legend}</div>
      <span class="chg-show">${switchHtml(marksShown(), "data-chg-toggle", "Show on charts")}<span data-chg-label>Show on charts</span></span></div>
    <ul class="chg-rows">${rows.map(row).join("")}</ul>${total > rows.length ? `<p class="muted small flush">The latest ${rows.length} of ${total}, newest first. Each History has the rest.</p>` : ""}</details>
    <p class="sr-only">${esc(summary || "")}</p>`;
  const sw = el.querySelector("[data-chg-toggle]");
  const flip = () => {
    const on = sw.getAttribute("aria-checked") !== "true";
    sw.setAttribute("aria-checked", on ? "true" : "false");
    rememberMarks(on);
    applyMarksShown(on);
  };
  sw.addEventListener("click", flip);
  el.querySelector("[data-chg-label]").addEventListener("click", flip);
}
