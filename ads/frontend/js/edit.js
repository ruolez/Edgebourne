// AM-C: change a campaign or ad set after it's made. Edit opens its settings (one folded section each, its summary saying
// what it is now), Save checks with the server, shows old → new with the money questions as knowing-yes boxes, then sends
// one change through POST /api/edit/<level>/<id> with what the form showed (the server refuses if Ads Manager changed it
// since). Also: Make a paused copy (level by level, resumable), Archive… and Delete… (Turn it off instead first).
import { api } from "./api.js";
import { confirmDialog, esc, icon, toast } from "./ui.js";
import { money, currencySymbol } from "./format.js";
import { placesHtml, placesWidget } from "./places.js";
import { changeStatus, spendWords, spendBody } from "./controls.js";
import * as UrlState from "./urlstate.js";
import { audPicker, audPickHtml, savedSelectHtml } from "./audpick.js";

const WHAT = { campaign: "campaign", adset: "ad set" };
const SECTIONS = {
  adset: [["name", "Name", ["name"]], ["when", "When it runs", ["start_time", "end_time"]], ["bidding", "Bidding", ["bid_strategy", "bid_amount"]],
    ["who", "Who it reaches", ["targeting"]], ["where", "Where it shows", ["placements"]],
    ["goal", "What it optimizes for", ["optimization_goal", "destination_type", "attribution_spec", "billing_event"]],
    ["often", "How often people see it", ["frequency_control_specs"]]],
  campaign: [["name", "Name", ["name"]], ["when", "When it ends", ["stop_time"]], ["bidding", "Bidding", ["bid_strategy", "adset_bids"]],
    ["cap", "Spending cap", ["spend_cap"]], ["special", "Special ad category", ["special_ad_categories"]]],
};
const CAPPED = ["COST_CAP", "LOWEST_COST_WITH_BID_CAP"];
const AGES = Array.from({ length: 48 }, (_, i) => i + 18);
const HOURS = Array.from({ length: 24 }, (_, i) => i);
const hourWords = (h) => `${h % 12 || 12}:00 ${h < 12 ? "AM" : "PM"}`;
const dollars = (v) => { const n = Number(String(v ?? "").replace(/[$,\s]/g, "")); return Number.isFinite(n) && String(v ?? "").trim() !== "" ? Math.round(n * 100) : null; };

// ---------------------------------------------------------------- times on the account's clock

function clockParts(ms, tz) {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const p = Object.fromEntries(f.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return { day: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour) % 24, minute: Number(p.minute) };
}
const minuteMs = (m) => Date.parse(String(m).replace(/Z$/, ":00Z"));
function toMinute(day, hour, tz) {
  if (!day) return null;
  const [y, mo, d] = day.split("-").map(Number);
  const want = Date.UTC(y, mo - 1, d, Number(hour), 0);
  let guess = want;
  for (let i = 0; i < 3; i++) {
    const p = clockParts(guess, tz);
    const [py, pm, pd] = p.day.split("-").map(Number);
    guess += want - Date.UTC(py, pm - 1, pd, p.hour, p.minute);
  }
  return new Date(guess).toISOString().slice(0, 16) + "Z";
}
function minuteWords(m, tz) {
  if (!m) return null;
  return new Intl.DateTimeFormat(undefined, { timeZone: tz, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(minuteMs(m)));
}
// A draft's time can arrive as seconds since 1970 or an ISO string: the form's minute either way.
function asMinute(v) {
  if (v == null || v === "") return null;
  if (typeof v === "number") return new Date(v * 1000).toISOString().slice(0, 16) + "Z";
  const t = Date.parse(v);
  return Number.isFinite(t) ? new Date(t).toISOString().slice(0, 16) + "Z" : null;
}

// ---------------------------------------------------------------- words for the folded summaries

const label = (opts, v) => (opts.find((o) => o.value === v) || {}).label || (v ? String(v) : "none");
function summaryWords(d, key, v) {
  const tz = d.tz;
  if (key === "name") return v.name;
  if (key === "when") {
    if (d.level === "campaign") return v.stop_time ? `Ends ${minuteWords(v.stop_time, tz)}` : "Runs until turned off";
    const start = v.start_time ? `Started ${minuteWords(v.start_time, tz)}` : "Starts now";
    return `${start} · ${v.end_time ? `ends ${minuteWords(v.end_time, tz)}` : "no end date"}`;
  }
  if (key === "bidding") {
    const words = label(d.options.bid_strategies, v.bid_strategy);
    if (d.level === "adset" && CAPPED.includes(v.bid_strategy) && v.bid_amount) return `${words}: ${money(v.bid_amount, { exact: true })}`;
    if (d.level === "adset" && d.campaign && (d.campaign.daily_budget || d.campaign.lifetime_budget)) return `Set on the campaign${v.bid_amount && CAPPED.includes(d.campaign.bid_strategy) ? `: ${money(v.bid_amount, { exact: true })}` : ""}`;
    return words;
  }
  if (key === "cap") return v.spend_cap ? money(v.spend_cap, { exact: true }) : "No cap";
  if (key === "special") return v.special_ad_categories.length ? v.special_ad_categories.map((c) => label(d.options.categories, c)).join(", ") : "None";
  if (key === "who") return d.words.targeting;
  if (key === "where") return d.words.placements;
  if (key === "goal") return `${label(d.options.goals, v.optimization_goal)} · ${label(d.options.destinations, v.destination_type)}`;
  if (key === "often") return v.frequency_control_specs ? `At most ${v.frequency_control_specs.max} times in ${v.frequency_control_specs.days} days` : "No limit";
  return "";
}

// ---------------------------------------------------------------- the form

function why(d, field, extra = "") {
  const r = d.editable[field];
  return r ? `<p class="ed-why" data-why="${esc(field)}">${esc(r)}${extra}</p>` : "";
}
const opt = (list, v) => list.map((o) => `<option value="${esc(o.value)}" ${String(o.value) === String(v ?? "") ? "selected" : ""}>${esc(o.label)}</option>`).join("");
const ageOpts = (v) => AGES.map((a) => `<option value="${a}" ${a === Number(v) ? "selected" : ""}>${a === 65 ? "65+" : a}</option>`).join("");
const hourOpts = (v) => HOURS.map((h) => `<option value="${h}" ${h === Number(v) ? "selected" : ""}>${hourWords(h)}</option>`).join("");

function whenHtml(d, v) {
  const tz = d.tz;
  const pick = (key, m, { none = false } = {}) => {
    const p = m ? clockParts(minuteMs(m), tz) : { day: "", hour: key === "start" ? 9 : 23 };
    const off = d.editable[{ start: "start_time", end: "end_time", stop: "stop_time" }[key]];
    return `<div class="ed-time">
      ${none ? `<label class="check"><input type="checkbox" id="ed-${key}-none" ${m ? "" : "checked"} ${off ? "disabled" : ""}> No end date: it runs until it's turned off</label>` : ""}
      <div class="ed-pair" id="ed-${key}-when" ${none && !m ? "hidden" : ""}><div class="field"><label for="ed-${key}-day">Day</label><input class="input" type="date" id="ed-${key}-day" value="${esc(p.day)}" ${off ? "disabled" : ""}></div>
      <div class="field"><label for="ed-${key}-hour">Time</label><select class="input" id="ed-${key}-hour" ${off ? "disabled" : ""}>${hourOpts(p.hour)}</select></div></div></div>`;
  };
  if (d.level === "campaign") return `${why(d, "stop_time")}${d.editable.stop_time ? "" : pick("stop", v.stop_time)}`;
  return `<h4 class="ed-h">Starts</h4>${why(d, "start_time")}${d.editable.start_time ? `<p class="flush">${esc(minuteWords(v.start_time, d.tz) || "Now")}</p>` : pick("start", v.start_time)}
    <h4 class="ed-h">Ends</h4>${why(d, "end_time")}${pick("end", v.end_time, { none: !v.lifetime_budget })}
    <p class="muted small flush">Times are the ad account's (${esc(d.tz)}).</p>`;
}

function biddingHtml(d, v) {
  const seg = `<div class="segmented ed-bids" role="group" aria-label="Bidding">${d.options.bid_strategies.map((o) => `<button type="button" data-bid="${esc(o.value)}" aria-pressed="${o.value === v.bid_strategy}">${esc(o.label)}</button>`).join("")}</div>
    <p class="muted small flush">Highest volume: Meta gets as many results as it can for the budget. Cost per result goal: Meta aims to keep the average cost per lead at or under the goal. Bid cap: Meta never bids more than the cap in an auction.</p>`;
  if (d.level === "campaign") {
    if (d.editable.bid_strategy) return why(d, "bid_strategy");
    return `${seg}<div class="ed-capbox" id="ed-adset-bids" ${CAPPED.includes(v.bid_strategy) ? "" : "hidden"}>
      <p class="small flush">The goal goes on each ad set:</p>
      ${d.adsets.map((a) => `<div class="field ed-money"><label for="ed-ab-${esc(a.id)}">${esc(a.name)}</label><div class="affix"><span>${esc(currencySymbol())}</span><input class="input" inputmode="decimal" id="ed-ab-${esc(a.id)}" data-adset-bid="${esc(a.id)}" value="${a.bid_amount ? (a.bid_amount / 100).toFixed(2) : ""}"></div></div>`).join("")}</div>`;
  }
  const own = !d.editable.bid_strategy;
  const amount = `<div class="field ed-money" id="ed-bid-box" ${(own ? CAPPED.includes(v.bid_strategy) : !d.editable.bid_amount) ? "" : "hidden"}>
      <label for="ed-bid">${v.bid_strategy === "LOWEST_COST_WITH_BID_CAP" ? "Bid cap" : "Cost per result goal"}</label>
      <div class="affix"><span>${esc(currencySymbol())}</span><input class="input" inputmode="decimal" id="ed-bid" value="${v.bid_amount ? (v.bid_amount / 100).toFixed(2) : ""}" ${d.editable.bid_amount && !own ? "disabled" : ""}><span>a lead</span></div></div>`;
  return `${own ? seg : why(d, "bid_strategy")}${amount}`;
}

function capHtml(d, v) {
  return `<div class="field ed-money"><label for="ed-cap">Most this campaign can spend in total</label>
    <div class="affix"><span>${esc(currencySymbol())}</span><input class="input" inputmode="decimal" id="ed-cap" value="${v.spend_cap ? (v.spend_cap / 100).toFixed(2) : ""}" ${v.spend_cap ? "" : "disabled"}></div></div>
    <label class="check"><input type="checkbox" id="ed-cap-none" ${v.spend_cap ? "" : "checked"}> No cap</label>
    <p class="muted small flush">Meta stops the campaign once it has spent this much. It can't be lower than what it has already spent.</p>`;
}

function specialHtml(d, v) {
  return `<p class="small flush">For ads about housing, jobs, credit or social issues, Meta requires a category: it then limits who you can reach (ages 18–65, every gender, at least 15 miles). Once added, a category is removed only in Ads Manager.</p>
    <div class="ed-checks">${d.options.categories.map((o) => `<label class="check"><input type="checkbox" data-cat="${esc(o.value)}" ${v.special_ad_categories.includes(o.value) ? "checked disabled" : ""}> ${esc(o.label)}</label>`).join("")}</div>`;
}

function chips(list, kind) {
  return list.length ? list.map((x, i) => `<li class="ed-chip"><span>${esc(x.name || x.id || x.key)}</span><button type="button" class="btn btn-quiet btn-small" data-ed-drop="${kind}:${i}" aria-label="Remove ${esc(x.name || x.id || x.key)}">${icon("close")}</button></li>`).join("")
    : '<li class="muted small">None</li>';
}

function searchBox(id, placeholder) {
  return `<div class="place-add ed-search"><label class="sr-only" for="ed-${id}-q">${esc(placeholder)}</label>
    <input class="input" id="ed-${id}-q" data-ed-search="${id}" placeholder="${esc(placeholder)}" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="ed-${id}-res">
    <ul class="place-results" id="ed-${id}-res" role="listbox" hidden></ul></div>`;
}

function whoHtml(d, v) {
  const t = v.targeting;
  const g = t.genders.length === 1 ? String(t.genders[0]) : "";
  return `${savedSelectHtml("ed-saved", d.saved_audiences)}<h4 class="ed-h">Places</h4>${placesHtml("ed-pl")}
    <h4 class="ed-h">Ages</h4>
    <div class="ed-pair"><div class="field"><label for="ed-age-min">From</label><select class="input" id="ed-age-min">${ageOpts(t.age_min)}</select></div>
      <div class="field"><label for="ed-age-max">To</label><select class="input" id="ed-age-max">${ageOpts(t.age_max)}</select></div></div>
    <label class="check"><input type="checkbox" id="ed-adv" ${t.advantage ? "checked" : ""}> Advantage+ audience <span class="explain">Meta may show the ads to people outside the hints and suggested ages when it expects leads from them. The minimum age can then be at most ${d.advantage_max_age_min}.</span></label>
    <div class="ed-pair" id="ed-sug" ${t.advantage ? "" : "hidden"}><div class="field"><label for="ed-sug-min">Suggested from</label><select class="input" id="ed-sug-min"><option value="">None</option>${ageOpts(t.suggest_min)}</select></div>
      <div class="field"><label for="ed-sug-max">Suggested to</label><select class="input" id="ed-sug-max"><option value="">None</option>${ageOpts(t.suggest_max)}</select></div></div>
    <h4 class="ed-h">Gender</h4>
    <div class="segmented" role="group" aria-label="Gender">${[["", "Everyone"], ["2", "Women"], ["1", "Men"]].map(([k, l]) => `<button type="button" data-gender="${k}" aria-pressed="${k === g}">${l}</button>`).join("")}</div>
    <h4 class="ed-h">Languages</h4><ul class="ed-chips" id="ed-locales"></ul>${searchBox("lang", "Add a language")}
    <h4 class="ed-h">Detailed targeting</h4><p class="muted small flush">Interests and behaviours Meta starts from.</p><ul class="ed-chips" id="ed-include"></ul>${searchBox("inc", "Add an interest or behaviour")}
    <h4 class="ed-h">Exclude people who match</h4><ul class="ed-chips" id="ed-exclude"></ul>${searchBox("exc", "Exclude an interest or behaviour")}
    <h4 class="ed-h">Your audiences</h4>${audPickHtml("ed-aud")}`;
}

function whereHtml(d, v) {
  const p = v.placements;
  const pos = (plat) => `<div class="ed-checks ed-pos" data-pos-for="${plat}">${d.options.positions[plat].map((o) => `<label class="check"><input type="checkbox" data-pos="${plat}:${esc(o.value)}" ${(p[`${plat}_positions`] || []).includes(o.value) ? "checked" : ""}> ${esc(o.label)}</label>`).join("")}</div>`;
  return `<div class="ed-checks" role="radiogroup" aria-label="Where it shows">
      <label class="check"><input type="radio" name="ed-pl-mode" value="auto" ${p.auto ? "checked" : ""}> Advantage+ placements <span class="explain">Meta picks where each ad shows (recommended).</span></label>
      <label class="check"><input type="radio" name="ed-pl-mode" value="manual" ${p.auto ? "" : "checked"}> Choose them myself</label></div>
    <div id="ed-manual" ${p.auto ? "hidden" : ""}>
      <div class="ed-checks">${d.options.platforms.map((o) => `<label class="check"><input type="checkbox" data-plat="${esc(o.value)}" ${(p.platforms || []).includes(o.value) ? "checked" : ""}> ${esc(o.label)}</label>`).join("")}</div>
      <h4 class="ed-h">Facebook positions</h4><p class="muted small flush">None ticked: every Facebook position.</p>${pos("facebook")}
      <h4 class="ed-h">Instagram positions</h4><p class="muted small flush">None ticked: every Instagram position.</p>${pos("instagram")}
      <p class="muted small flush">Meta may refuse hand-picked placements for some lead ads; it says so when you save.</p></div>`;
}

function goalHtml(d, v) {
  const copy = d.delivered && d.level === "adset" ? `<button type="button" class="btn btn-small" data-ed-copy-change="goal">${icon("copy")}Make a paused copy with this change</button>` : "";
  const sel = (id, field, list, lbl) => `<div class="field"><label for="${id}">${lbl}</label><select class="input" id="${id}" ${d.editable[field] ? "disabled" : ""}>${opt(list, v[field])}</select></div>`;
  return `${why(d, "optimization_goal", copy ? " " : "")}${copy ? `<p class="flush">${copy}</p>` : ""}
    ${sel("ed-goal", "optimization_goal", d.options.goals, "Optimized for")}
    ${sel("ed-dest", "destination_type", d.options.destinations, "Where people answer")}
    ${sel("ed-attr", "attribution_spec", d.options.attributions, "How results are counted")}
    ${sel("ed-bill", "billing_event", d.options.billing, "What you pay for")}`;
}

function oftenHtml(d, v) {
  const f = v.frequency_control_specs || {};
  return `${why(d, "frequency_control_specs")}<div class="ed-pair">
    <div class="field"><label for="ed-freq-max">At most this many times</label><input class="input" inputmode="numeric" id="ed-freq-max" value="${f.max || ""}" ${d.editable.frequency_control_specs ? "disabled" : ""}></div>
    <div class="field"><label for="ed-freq-days">In this many days</label><input class="input" inputmode="numeric" id="ed-freq-days" value="${f.days || ""}" ${d.editable.frequency_control_specs ? "disabled" : ""}></div></div>`;
}

function nameHtml(d, v) {
  return `<div class="field"><label for="ed-name">Name</label><input class="input" id="ed-name" value="${esc(v.name)}" maxlength="400" autocomplete="off"></div>`;
}

const BODY = { name: nameHtml, when: whenHtml, bidding: biddingHtml, cap: capHtml, special: specialHtml, who: whoHtml, where: whereHtml, goal: goalHtml, often: oftenHtml };

// ---------------------------------------------------------------- reading the form back

function readValues(root, d, st) {
  const $ = (s) => root.querySelector(s);
  const v = d.values;
  const out = {};
  if ($("#ed-name")) out.name = $("#ed-name").value;
  const time = (key, fallback) => {
    const day = $(`#ed-${key}-day`);
    if (!day || day.disabled) return fallback;
    if ($(`#ed-${key}-none`) && $(`#ed-${key}-none`).checked) return null;
    return toMinute(day.value, $(`#ed-${key}-hour`).value, d.tz);
  };
  if (d.level === "campaign") {
    out.stop_time = time("stop", v.stop_time);
    out.bid_strategy = st.bid || v.bid_strategy;
    const bids = {};
    root.querySelectorAll("[data-adset-bid]").forEach((i) => { const c = dollars(i.value); if (c) bids[i.dataset.adsetBid] = c; });
    out.adset_bids = bids;
    out.spend_cap = $("#ed-cap-none").checked ? null : dollars($("#ed-cap").value);
    out.special_ad_categories = [...root.querySelectorAll("[data-cat]")].filter((i) => i.checked).map((i) => i.dataset.cat);
    return out;
  }
  out.start_time = time("start", v.start_time);
  out.end_time = time("end", v.end_time);
  out.bid_strategy = st.bid || v.bid_strategy;
  out.bid_amount = $("#ed-bid") && !$("#ed-bid-box").hidden ? dollars($("#ed-bid").value) : v.bid_amount;
  const gender = root.querySelector('[data-gender][aria-pressed="true"]');
  out.targeting = {
    locations: st.places.get(), age_min: Number($("#ed-age-min").value), age_max: Number($("#ed-age-max").value), advantage: $("#ed-adv").checked,
    suggest_min: $("#ed-sug-min").value ? Number($("#ed-sug-min").value) : null, suggest_max: $("#ed-sug-max").value ? Number($("#ed-sug-max").value) : null,
    genders: gender && gender.dataset.gender ? [Number(gender.dataset.gender)] : [], locales: st.locales.map((l) => l.key),
    include: st.include, exclude: st.exclude,
    custom_audiences: st.aud.get().include.map((id) => ({ id })), excluded_custom_audiences: st.aud.get().exclude.map((id) => ({ id })),
  };
  const manual = root.querySelector('input[name="ed-pl-mode"][value="manual"]').checked;
  out.placements = manual ? { auto: false, platforms: [...root.querySelectorAll("[data-plat]")].filter((i) => i.checked).map((i) => i.dataset.plat),
    facebook_positions: [...root.querySelectorAll('[data-pos^="facebook:"]')].filter((i) => i.checked).map((i) => i.dataset.pos.split(":")[1]),
    instagram_positions: [...root.querySelectorAll('[data-pos^="instagram:"]')].filter((i) => i.checked).map((i) => i.dataset.pos.split(":")[1]) } : { auto: true };
  out.optimization_goal = $("#ed-goal").value;
  out.destination_type = $("#ed-dest").value;
  out.attribution_spec = $("#ed-attr").value;
  out.billing_event = $("#ed-bill").value;
  const fm = Number($("#ed-freq-max").value), fd = Number($("#ed-freq-days").value);
  out.frequency_control_specs = fm && fd ? { max: fm, days: fd } : null;
  return out;
}

// ---------------------------------------------------------------- the panel

let open = null;  // the panel on screen: {dlg, close}

export async function openEdit({ level, id, focus = null, prefill = {}, undoOf = null, note = "", draft = null }, after = () => {}) {
  if (open) open.close();
  let d;
  try { d = await api(`/api/edit/${level}/${encodeURIComponent(id)}`); }
  catch (err) { toast(err.message, "bad"); return; }
  const dlg = document.createElement("dialog");
  dlg.className = "ed-panel";
  dlg.setAttribute("aria-labelledby", "ed-title");
  const v = d.values;
  const secs = SECTIONS[level];
  const fieldSec = Object.fromEntries(secs.flatMap(([key, , fields]) => fields.map((f) => [f, key])));
  const filled = Object.keys(prefill || {}).filter((f) => fieldSec[f]);
  dlg.innerHTML = `<form method="dialog" novalidate class="ed-form">
    <header class="ed-head"><div><p class="pk-kicker">Edit ${WHAT[level]}</p><h2 id="ed-title">${esc(d.name)}</h2>
      <p class="muted small flush">Read from Meta just now. Nothing changes until you press Save and confirm.</p></div>
      <button type="button" class="btn btn-quiet ed-x" id="ed-close" aria-label="Close">${icon("close")}</button></header>
    ${note ? `<p class="note ed-note" id="ed-note">${note}</p>` : ""}
    ${draft ? `<p class="note ed-note" id="ed-draft-note">From your Ads Manager draft: the outlined setting is filled in with the draft's value.</p>` : ""}
    <div class="ed-secs">${secs.map(([key, lbl]) => `<details class="ed-sec" id="ed-sec-${key}" data-sec="${key}" ${key === (focus && fieldSec[focus]) || filled.some((f) => fieldSec[f] === key) ? "open" : ""}>
      <summary><span class="ed-k">${esc(lbl)}</span><span class="ed-now">${esc(summaryWords(d, key, v))}</span></summary>
      <div class="ed-body">${BODY[key](d, v)}<p class="err ed-err" id="ed-err-${key}" role="alert" hidden></p></div></details>`).join("")}</div>
    <footer class="ed-foot"><button type="button" class="btn" id="ed-cancel">Cancel</button><button type="submit" class="btn btn-primary" id="ed-save">Save</button></footer>
  </form>`;
  document.body.appendChild(dlg);
  const st = { bid: null, places: null, locales: [], include: [...(v.targeting ? v.targeting.include : [])], exclude: [...(v.targeting ? v.targeting.exclude : [])], dirty: new Set() };
  const $ = (s) => dlg.querySelector(s);
  if (level === "adset") {
    st.places = placesWidget("ed-pl", { cityRadius: d.city_radius, pinRadius: d.pin_radius, onChange: () => markDirty("who") });
    st.places.set(v.targeting.locations);
    st.locales = v.targeting.locales.map((k) => ({ key: k, name: d.locale_names[String(k)] || `Language ${k}` }));
    // AM-D: include / leave out the account's audiences (the server checks each is this account's before anything reaches Meta).
    st.aud = audPicker("ed-aud", { audiences: d.audiences || [], words: d.audience_words || {}, special: () => (d.special || []).length > 0,
      advantage: () => $("#ed-adv").checked, onChange: () => markDirty("who") });
    st.aud.set(v.targeting.custom_audiences, v.targeting.excluded_custom_audiences);
  }
  const drawChips = () => {
    if (level !== "adset") return;
    $("#ed-locales").innerHTML = chips(st.locales, "locales");
    $("#ed-include").innerHTML = chips(st.include, "include");
    $("#ed-exclude").innerHTML = chips(st.exclude, "exclude");
  };
  drawChips();
  function markDirty(key) { st.dirty.add(key); $(`#ed-sec-${key}`).classList.add("is-dirty"); const e = $(`#ed-err-${key}`); if (e) e.hidden = true; }

  // Prefilled from a draft or Put it back: written into the form and marked as changed (outlined).
  const prefillField = (f, val) => {
    const key = fieldSec[f];
    if (f === "name") $("#ed-name").value = val;
    if (["start_time", "end_time", "stop_time"].includes(f)) {
      const k = { start_time: "start", end_time: "end", stop_time: "stop" }[f];
      const m = asMinute(val);
      if ($(`#ed-${k}-none`)) { $(`#ed-${k}-none`).checked = !m; $(`#ed-${k}-when`).hidden = !m; }
      if (m && $(`#ed-${k}-day`)) { const p = clockParts(minuteMs(m), d.tz); $(`#ed-${k}-day`).value = p.day; $(`#ed-${k}-hour`).value = String(p.hour); }
    }
    if (f === "bid_strategy" && dlg.querySelector(`[data-bid="${val}"]`)) pickBid(val);
    if (f === "bid_amount" && $("#ed-bid") && val != null) { $("#ed-bid").value = (Number(val) / 100).toFixed(2); $("#ed-bid-box").hidden = false; }
    if (f === "spend_cap") { $("#ed-cap-none").checked = val == null; $("#ed-cap").disabled = val == null; if (val != null) $("#ed-cap").value = (Number(val) / 100).toFixed(2); }
    if (f === "optimization_goal" && $("#ed-goal") && !$("#ed-goal").disabled) $("#ed-goal").value = val;
    $(`#ed-sec-${key}`).classList.add("ed-from-draft");
    markDirty(key);
  };
  const pickBid = (val) => {
    st.bid = val;
    dlg.querySelectorAll("[data-bid]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.bid === val)));
    if (level === "campaign" && $("#ed-adset-bids")) $("#ed-adset-bids").hidden = !CAPPED.includes(val);
    if (level === "adset" && $("#ed-bid-box")) {
      $("#ed-bid-box").hidden = !CAPPED.includes(val);
      $("#ed-bid-box label").textContent = val === "LOWEST_COST_WITH_BID_CAP" ? "Bid cap" : "Cost per result goal";
    }
  };
  filled.forEach((f) => prefillField(f, prefill[f]));

  // ---- interactions
  dlg.addEventListener("input", (e) => { const s = e.target.closest(".ed-sec"); if (s && !e.target.closest("[data-ed-search]") && !e.target.closest(".place-add")) markDirty(s.dataset.sec); });
  // AM-D: Start from a saved audience fills places, ages, gender, languages and detailed targeting (and its audiences); Save sends it.
  const applySaved = (sid) => {
    const sv = (d.saved_audiences || []).find((x) => x.id === sid);
    if (!sv) return;
    const f = sv.form;
    st.places.set(f.locations);
    $("#ed-age-min").value = String(f.age_min); $("#ed-age-max").value = String(f.age_max);
    $("#ed-adv").checked = f.advantage; $("#ed-sug").hidden = !f.advantage;
    $("#ed-sug-min").value = f.suggest_min ? String(f.suggest_min) : ""; $("#ed-sug-max").value = f.suggest_max ? String(f.suggest_max) : "";
    const g = f.genders.length === 1 ? String(f.genders[0]) : "";
    dlg.querySelectorAll("[data-gender]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.gender === g)));
    st.locales = f.locales.map((k) => ({ key: k, name: d.locale_names[String(k)] || `Language ${k}` }));
    st.include = [...f.include]; st.exclude = [...f.exclude];
    st.aud.set(f.custom_audiences, f.excluded_custom_audiences);
    drawChips(); markDirty("who");
  };
  dlg.addEventListener("change", (e) => {
    const s = e.target.closest(".ed-sec");
    if (!s || e.target.closest("[data-ed-search]")) return;
    if (e.target.id === "ed-adv") { $("#ed-sug").hidden = !e.target.checked; if (st.aud) st.aud.redraw(); }
    if (e.target.id === "ed-saved") { applySaved(e.target.value); return; }
    if (e.target.id === "ed-cap-none") $("#ed-cap").disabled = e.target.checked;
    if (e.target.id === "ed-end-none") $("#ed-end-when").hidden = e.target.checked;
    if (e.target.name === "ed-pl-mode") $("#ed-manual").hidden = e.target.value !== "manual";
    markDirty(s.dataset.sec);
  });
  const timers = {};
  const searchKinds = { lang: ["language", "locales"], inc: ["detail", "include"], exc: ["detail", "exclude"] };
  dlg.addEventListener("input", (e) => {
    const box = e.target.closest("[data-ed-search]");
    if (!box) return;
    const id = box.dataset.edSearch;
    const res = $(`#ed-${id}-res`);
    clearTimeout(timers[id]);
    const q = box.value.trim();
    if (q.length < 2) { res.hidden = true; box.setAttribute("aria-expanded", "false"); return; }
    timers[id] = setTimeout(async () => {
      try {
        const r = await api(`/api/edit/search?kind=${searchKinds[id][0]}&q=${encodeURIComponent(q)}`);
        res.innerHTML = r.items.length ? r.items.map((it, i) => `<li role="option" tabindex="-1" data-ed-pick="${id}:${i}">${it.type ? `<span class="place-kind">${it.type === "behaviors" ? "Behaviour" : "Interest"}</span>` : ""}${esc(it.name)}</li>`).join("")
          : '<li class="muted" role="option" aria-disabled="true">Nothing found</li>';
        res._items = r.items;
        res.hidden = false;
        box.setAttribute("aria-expanded", "true");
      } catch (err) { toast(err.message, "bad"); }
    }, 250);
  });
  dlg.addEventListener("click", async (e) => {
    if (e.target.closest("#ed-close") || e.target.closest("#ed-cancel")) { close(); return; }
    const pickItem = e.target.closest("[data-ed-pick]");
    if (pickItem) {
      const [id, i] = pickItem.dataset.edPick.split(":");
      const res = $(`#ed-${id}-res`);
      const it = res._items[Number(i)];
      const list = st[searchKinds[id][1]];
      const key = id === "lang" ? "key" : "id";
      if (!list.some((x) => String(x[key]) === String(it[key]))) list.push(id === "lang" ? { key: it.key, name: it.name } : { id: it.id, name: it.name, type: it.type, group: 0 });
      res.hidden = true; $(`#ed-${id}-q`).value = "";
      drawChips(); markDirty("who");
      return;
    }
    const drop = e.target.closest("[data-ed-drop]");
    if (drop) { const [k, i] = drop.dataset.edDrop.split(":"); st[k].splice(Number(i), 1); drawChips(); markDirty("who"); return; }
    const bid = e.target.closest("[data-bid]");
    if (bid) { pickBid(bid.dataset.bid); markDirty("bidding"); return; }
    const gender = e.target.closest("[data-gender]");
    if (gender) { dlg.querySelectorAll("[data-gender]").forEach((b) => b.setAttribute("aria-pressed", String(b === gender))); markDirty("who"); return; }
    const cc = e.target.closest("[data-ed-copy-change]");
    if (cc) { close(); openCopy({ level: "adset", id, name: d.name, thenEdit: "optimization_goal" }); }
  });

  // ---- save: check, review with the money questions, then write
  dlg.querySelector("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const all = readValues(dlg, d, st);
    const changes = {};
    st.dirty.forEach((key) => secs.find(([k]) => k === key)[2].forEach((f) => { if (f in all && !d.editable[f]) changes[f] = all[f]; }));
    if (!Object.keys(changes).length) { toast("Nothing changed yet."); return; }
    const save = $("#ed-save");
    save.disabled = true;
    let chk;
    try { chk = await api(`/api/edit/${level}/${encodeURIComponent(id)}/check`, { method: "POST", body: { changes } }); }
    catch (err) { toast(err.message, "bad"); save.disabled = false; return; }
    save.disabled = false;
    dlg.querySelectorAll(".ed-err").forEach((x) => { x.hidden = true; });
    if (chk.problems.length) {
      chk.problems.forEach((p) => {
        const key = fieldSec[p.field] || "name";
        const box = $(`#ed-err-${key}`);
        box.textContent = box.hidden ? p.message : `${box.textContent} ${p.message}`;
        box.hidden = false;
        $(`#ed-sec-${key}`).open = true;
      });
      const first = $(`#ed-err-${fieldSec[chk.problems[0].field] || "name"}`);
      first.scrollIntoView({ block: "nearest" });
      return;
    }
    if (!chk.changes.length) { toast("Nothing changed: that's what it is now."); return; }
    let spend = null;
    if (chk.money.some((q) => q.code === "spend")) {
      try { spend = await api(`/api/ads/${level}/${encodeURIComponent(id)}/spend`); } catch (err) { toast(err.message, "bad"); return; }
    }
    const asks = chk.money.filter((q) => ["big", "recent", "high", "danger"].includes(q.code));
    const notes = [...new Set(chk.review.map((r) => r.note).filter(Boolean))];
    const danger = asks.some((q) => q.code === "danger");
    const ok = await confirmDialog({
      title: `Save these changes to “${d.name}”?`, wide: true, extra: "ed-review",
      body: `<ul class="ed-rev">${chk.review.map((r) => `<li><b>${esc(r.label)}</b> <span class="ed-old">${esc(r.old_words)}</span> <span aria-hidden="true">→</span><span class="sr-only">changes to</span> <span class="ed-new">${esc(r.new_words)}</span></li>`).join("")}</ul>
        ${notes.map((n) => `<p class="muted small">${esc(n)}</p>`).join("")}
        ${spend ? `<p class="ed-spend">${esc((chk.money.find((q) => q.code === "spend") || {}).lead || "It's on, so it starts spending")}${spendWords(spend)}.</p>` : ""}
        ${asks.length ? `<div class="ed-asks">${asks.map((q, i) => `<label class="check ed-ask${q.code === "danger" ? " is-danger" : ""}"><input type="checkbox" data-ed-q="${esc(q.code)}" id="ed-q-${i}"> ${esc(q.message)} I mean it.</label>`).join("")}</div>` : ""}`,
      confirm: danger ? "Save anyway" : "Save", danger,
      act: () => {
        const left = [...document.querySelectorAll("dialog.ed-review [data-ed-q]")].filter((b) => !b.checked);
        return left.length ? "Tick each box to confirm it knowingly." : null;
      },
    });
    if (!ok) return;
    const codes = new Set(asks.map((q) => q.code));
    const seen = {};
    Object.keys(changes).forEach((f) => { seen[f] = d.values[f]; });
    const body = { changes, seen, accept_big: codes.has("big"), accept_recent: codes.has("recent"), accept_high: codes.has("high"),
      confirm_remove: codes.has("danger"), ...(spend ? spendBody(spend) : {}), ...(undoOf ? { undo_of: undoOf } : {}) };
    save.disabled = true;
    try {
      const r = await api(`/api/edit/${level}/${encodeURIComponent(id)}`, { method: "POST", body });
      if (r.differs.length) toast(`Saved, but Meta kept ${Object.values(r.kept).join(", ") || "another value"}. History says what it has now.`, "bad");
      else toast("Saved. Meta shows it within a minute.");
      if (draft && draft.done) await draft.done();
      close();
      after();
    } catch (err) {
      save.disabled = false;
      toast(err.message, "bad");
      if (err.status === 409 && err.body && err.body.live !== undefined) { close(); openEdit({ level, id, focus: err.body.field }, after); }
    }
  });

  // ---- open as a layer: Back (a phone's too) closes it
  let closed = false;
  const onPop = () => { if (!closed) close({ fromHistory: true }); };
  function close({ fromHistory = false } = {}) {
    if (closed) return;
    closed = true;
    removeEventListener("popstate", onPop);
    if (dlg.open) dlg.close();
    dlg.remove();
    open = null;
    if (!fromHistory) UrlState.closeLayer(location.pathname + location.search);
  }
  dlg.addEventListener("cancel", (e) => { e.preventDefault(); close(); });
  UrlState.openLayer(`${location.pathname}${location.search}#edit`);
  addEventListener("popstate", onPop);
  dlg.showModal();
  open = { dlg, close };
  const firstOpen = dlg.querySelector(".ed-sec[open] input:not([disabled]), .ed-sec[open] select:not([disabled])");
  (firstOpen || $("#ed-close")).focus({ preventScroll: true });
  if (firstOpen) firstOpen.closest(".ed-sec").scrollIntoView({ block: "nearest" });
  return { close };
}

// ---------------------------------------------------------------- Make a paused copy

export async function openCopy({ level, id, name, thenEdit = null }, after = () => {}) {
  let p;
  try { p = await api(`/api/copy/${level}/${encodeURIComponent(id)}/plan`, { method: "POST", body: {} }); }
  catch (err) { toast(err.message, "bad"); return; }
  const dlg = document.createElement("dialog");
  dlg.className = "cp-dialog";
  dlg.setAttribute("aria-labelledby", "cp-title");
  const statusWord = (s) => (s === "ACTIVE" ? "on" : s === "PAUSED" ? "off" : (s || "").toLowerCase());
  const setsHtml = p.adsets.map((s) => `<li class="cp-set">
      ${level === "campaign" ? `<label class="check"><input type="checkbox" data-cp-set="${esc(s.id)}" ${s.ticked ? "checked" : ""}> <span><b>${esc(s.name)}</b> <small class="muted">ad set · ${esc(statusWord(s.status))}</small></span></label>` : `<p class="flush"><b>Its ads</b></p>`}
      <ul class="cp-ads">${s.ads.map((a) => `<li><label class="check"><input type="checkbox" data-cp-ad="${esc(s.id)}:${esc(a.id)}" ${a.ticked ? "checked" : ""}> <span>${esc(a.name)} <small class="muted">${esc(statusWord(a.status))}</small></span></label></li>`).join("") || '<li class="muted small">No ads</li>'}</ul></li>`).join("");
  dlg.innerHTML = `<form method="dialog" novalidate>
    <h2 id="cp-title">Make a paused copy of “${esc(name || p.source.name)}”</h2>
    <div id="cp-body">
      <p class="small">The copy is made <b>switched off</b>, with the same settings${level === "campaign" ? ", ad sets and ads you tick" : " and the ads you tick"}. Nothing spends until you turn it on.${thenEdit ? " Then Edit opens on the copy so you can make the change Meta doesn't allow on the original." : ""}</p>
      <div class="field"><label for="cp-name">Name of the copy</label><input class="input" id="cp-name" value="${esc(p.name)}" maxlength="200" autocomplete="off"><span class="err" id="cp-err" role="alert" hidden></span></div>
      ${level === "adset" ? `<div class="field"><label for="cp-campaign">Goes in the campaign</label><select class="input" id="cp-campaign">${p.campaigns.map((c) => `<option value="${esc(c.id)}" ${c.id === p.target_campaign_id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>` : ""}
      <ul class="cp-list">${setsHtml}</ul>
    </div>
    <div class="row end" id="cp-acts"><button class="btn" type="button" id="cp-cancel">Cancel</button><button class="btn btn-primary" type="submit" id="cp-go">${icon("copy")}Make the copy</button></div>
  </form>`;
  document.body.appendChild(dlg);
  const $ = (s) => dlg.querySelector(s);
  const key = `cp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  let job = null;
  const done = () => { dlg.close(); };
  dlg.addEventListener("close", () => { dlg.remove(); if (job) after(job); });
  const showJob = (j) => {
    job = j;
    const mark = { done: "Made", failed: "Not made", todo: "Not yet" };
    $("#cp-body").innerHTML = `<ol class="cp-steps">${j.steps.map((s) => `<li data-state="${s.state}"><span class="cp-dot" aria-hidden="true"></span><span>${esc({ campaign: "Campaign", adset: "Ad set", ad: "Ad" }[s.kind])}: ${esc(s.label)}</span><small>${mark[s.state]}</small></li>`).join("")}</ol>
      ${j.status === "done" ? `<p class="note cp-done" id="cp-done" role="status">Made, switched off.${j.switched_off.length ? " Meta made part of it on, so the console switched it off at once (History says so)." : ""}</p>`
        : `<p class="note warn" id="cp-partial" role="alert">${esc(j.error || "Not finished.")}</p>`}`;
    const openHref = j.open ? `/${j.open.level === "campaign" ? "campaign" : "adset"}.html?id=${encodeURIComponent(j.open.id)}${thenEdit && j.status === "done" ? `&edit=${encodeURIComponent(thenEdit)}` : ""}` : null;
    $("#cp-acts").innerHTML = `<button class="btn" type="button" id="cp-cancel">Close</button>
      ${j.status !== "done" ? `<button class="btn btn-primary" type="button" id="cp-resume">Finish the copy</button>` : ""}
      ${openHref && j.status === "done" ? `<a class="btn btn-primary" id="cp-openit" href="${esc(openHref)}">${thenEdit ? "Open it and edit" : "Open it"}</a>` : ""}`;
  };
  dlg.addEventListener("click", async (e) => {
    if (e.target.closest("#cp-cancel")) { done(); return; }
    if (e.target.closest("#cp-resume")) {
      const b = e.target.closest("#cp-resume");
      b.disabled = true; b.textContent = "Finishing…";
      try { showJob(await api(`/api/copy/${job.id}/resume`, { method: "POST" })); }
      catch (err) { toast(err.message, "bad"); b.disabled = false; b.textContent = "Finish the copy"; }
    }
    const setBox = e.target.closest("[data-cp-set]");
    if (setBox) dlg.querySelectorAll(`[data-cp-ad^="${setBox.dataset.cpSet}:"]`).forEach((a) => { a.checked = setBox.checked; });
  });
  dlg.querySelector("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (job) return;
    const nm = $("#cp-name").value.trim();
    if (!nm) { $("#cp-err").textContent = "Give the copy a name"; $("#cp-err").hidden = false; $("#cp-name").focus(); return; }
    const adsets = p.adsets.filter((s) => level === "adset" || (dlg.querySelector(`[data-cp-set="${s.id}"]`) || {}).checked)
      .map((s) => ({ id: s.id, ads: s.ads.filter((a) => dlg.querySelector(`[data-cp-ad="${s.id}:${a.id}"]`).checked).map((a) => a.id) }));
    const plan = { name: nm, adsets, ...(level === "adset" ? { target_campaign_id: $("#cp-campaign").value } : {}) };
    const go = $("#cp-go");
    go.disabled = true; go.textContent = "Copying…";
    $("#cp-body").setAttribute("aria-busy", "true");
    try { showJob(await api(`/api/copy/${level}/${encodeURIComponent(id)}`, { method: "POST", body: { plan, client_key: key } })); }
    catch (err) { go.disabled = false; go.innerHTML = `${icon("copy")}Make the copy`; toast(err.message, "bad"); }
    $("#cp-body").removeAttribute("aria-busy");
  });
  dlg.showModal();
  $("#cp-name").focus();
}

// ---------------------------------------------------------------- Archive… and Delete…

async function readInside(level, id) {
  try { return await api(`/api/edit/${level}/${encodeURIComponent(id)}/inside`); }
  catch (err) { toast(err.message, "bad"); return null; }
}

function insideWords(level, x) {
  const parts = [];
  if (level === "campaign" && x.adsets) parts.push(`${x.adsets} ad set${x.adsets === 1 ? "" : "s"}`);
  if (x.ads) parts.push(`${x.ads} ad${x.ads === 1 ? "" : "s"}`);
  return parts.join(" and ");
}

async function offFirst(level, id, name, after) {
  const yes = await confirmDialog({ title: "Switch it off first", body: `<p>“${esc(name)}” is on. Meta archives and deletes only what is off: switch it off, then come back here.</p>`, confirm: "Turn it off" });
  if (yes) await changeStatus({ level, id, name, turnOn: false }, after);
}

export async function archiveEntity({ level, id, name }, after) {
  const x = await readInside(level, id);
  if (!x) return;
  if (x.status === "ACTIVE") { await offFirst(level, id, name, after); return; }
  const inside = insideWords(level, x);
  const yes = await confirmDialog({
    title: `Archive “${name}”?`,
    body: `<p>It leaves the Ads page's main views ("Show archived" brings it back into view) and Meta's main list.${inside ? ` ${esc(inside)} inside it are archived with it.` : ""} Its numbers and leads stay.</p><p>Meta can't switch an archived ${WHAT[level]} back on. To run it again, make a paused copy.</p>`,
    confirm: "Archive",
  });
  if (!yes) return;
  try { await api(`/api/ads/${level}/${encodeURIComponent(id)}/archive`, { method: "POST" }); toast("Archived"); after(); }
  catch (err) { toast(err.message, "bad"); }
}

export async function deleteEntity({ level, id, name }, after, gone) {
  const x = await readInside(level, id);
  if (!x) return;
  const on = x.status === "ACTIVE";
  const first = await confirmDialog({
    title: `Delete “${name}”?`,
    body: `<p>Deleting can't be undone. ${on ? "Turning it off stops all spending and keeps everything, so you can turn it back on later." : "It's already off, so it spends nothing; you can keep it as it is."}</p>`,
    confirm: null, extra: "ed-del-first",
    choices: { submitOnPick: true, options: [{ value: "keep", label: on ? "Turn it off instead" : "Keep it off instead" }, { value: "delete", label: "Delete anyway", hint: "Gone for good" }] },
  });
  if (first === "keep") { if (on) await changeStatus({ level, id, name, turnOn: false }, after); return; }
  if (first !== "delete") return;
  if (on) {
    let turnedOff = false;
    await changeStatus({ level, id, name, turnOn: false }, () => { turnedOff = true; });
    if (!turnedOff) return;
  }
  const inside = insideWords(level, x);
  const typed = await confirmDialog({
    title: `Delete “${name}” for good?`,
    body: `<p>Deletes it in Meta. <b>This can't be undone.</b>${inside ? ` ${esc(inside)} are deleted with it;` : ""} their past spend and leads stay in the console.</p>`,
    confirm: "Delete for good", danger: true,
    field: { label: `Type the ${WHAT[level]}'s name to confirm`, value: "", validate: (val) => (val.trim() === name.trim() ? null : "The name doesn't match") },
  });
  if (typed === false) return;
  try {
    await api(`/api/ads/${level}/${encodeURIComponent(id)}/delete`, { method: "POST", body: { name: typed } });
    toast(`Deleted “${name}”`);
    gone();
  } catch (err) { toast(err.message, "bad"); after(); }
}

// The More menu opens under its button and stays whole on screen (a phone's button can sit anywhere in the row).
export function fitMenu(details) {
  const pop = details.querySelector(".menu-pop");
  if (!pop || !details.open) return;
  pop.style.left = ""; pop.style.right = "";
  const box = details.getBoundingClientRect(), r = pop.getBoundingClientRect();
  if (r.left < 16) { pop.style.right = "auto"; pop.style.left = `${16 - box.left}px`; }
  else if (r.right > innerWidth - 16) { pop.style.left = "auto"; pop.style.right = `${box.right - (innerWidth - 16)}px`; }
}

// The More menu on a campaign or ad set page (owner and account admins): Make a paused copy, Archive…, Delete….
export function moreMenuHtml() {
  return `<details class="menu ed-more" id="ed-more"><summary class="btn" aria-label="More actions">${icon("dots")}More</summary>
    <div class="menu-pop" role="menu"><button type="button" role="menuitem" id="cp-open">${icon("copy")}Make a paused copy</button>
      <button type="button" role="menuitem" id="ed-archive">Archive…</button>
      <button type="button" role="menuitem" class="btn-danger-text" id="ed-delete">Delete…</button></div></details>`;
}
