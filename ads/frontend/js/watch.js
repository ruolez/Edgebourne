// Watch: the ads as someone scrolling Facebook or Instagram meets them, one after another, with their sound. A phone
// screen fills the height of the window (nothing to scroll), ← → or a swipe go to the next ad, the strip under it
// jumps to any of them, and the sound and "Play all" choices stay for every ad and the next visit (this browser).
// The ad before and the ad after are loaded while one plays, so switching doesn't wait. Opened from the Ads cards and
// toolbar and from an ad's Preview; the videos come through /api/ads/ad/<id>/video (same origin), the words and
// numbers through /api/ads/watch.
import { api } from "./api.js";
import { esc, icon } from "./ui.js";
import { CTA_LABELS, WORDS, count, money, pct, per, statusPill } from "./format.js";

const PREF = "ebads-watch";
const PICTURE_SECONDS = 5; // a picture ad (or a video Meta wouldn't share) stays this long in Play all
const SEGMENTS_MAX = 40;
const SOUND_ON = '<path d="M4.5 9.5h3.2L12 5.5v13l-4.3-4H4.5z" fill="currentColor"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>';
const SOUND_OFF = '<path d="M4.5 9.5h3.2L12 5.5v13l-4.3-4H4.5z" fill="currentColor"/><path d="M15.5 9.5l5 5M20.5 9.5l-5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>';
const PLAY_ALL = '<path d="M5 6v12l8.5-6z" fill="currentColor"/><path d="M15 6.5v11M19 6.5v11" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>';
const svg = (paths) => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;

function readPrefs() {
  try { return { sound: true, auto: true, look: "feed", ...JSON.parse(localStorage.getItem(PREF) || "{}") }; } catch (e) { return { sound: true, auto: true, look: "feed" }; }
}
function savePrefs(p) { try { localStorage.setItem(PREF, JSON.stringify(p)); } catch (e) { /* storage off */ } }

const initials = (name) => (name || "Ad").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
const picture = (a) => a.image_url || a.thumbnail_url || "";

// What the first lines of an ad's text look like in a feed: Meta cuts it after about two lines with "… more".
function postText(body) {
  const text = (body || "").trim();
  return text ? `<p class="wt-text">${esc(text)}</p>` : "";
}

function figures(a, rangeLabel) {
  const m = a.m || {};
  const video = a.object_type === "VIDEO" || Boolean(a.video);
  const cell = (label, value, title = "") => `<div${title ? ` title="${esc(title)}"` : ""}><dt>${esc(label)}</dt><dd>${value}</dd></div>`;
  return `<dl class="wt-figs">${cell(WORDS.spend, money(m.spend_cents, { exact: true }))}${cell(WORDS.leads, count(m.leads))}
    ${cell(WORDS.cpl, per(m.spend_cents, m.leads))}${video ? cell(WORDS.hook, pct(m.video_3s, m.video_impressions), "Watched 3 seconds, of everyone who saw it") : cell(WORDS.ctr, pct(m.link_clicks, m.impressions))}</dl>
    <p class="wt-range">${esc(rangeLabel || "")}${m.impressions ? ` · ${count(m.impressions)} ${WORDS.impressions.toLowerCase()}` : ""}</p>`;
}

// ids: the ads in the order they were showing; startId: the one to begin with; range: the dates of the numbers.
export async function openWatch({ ids, startId, range = "7" }) {
  const list = [...new Set((ids || []).map(String))];
  if (!list.length) return null;
  const prefs = readPrefs();
  let items = [], page = "", rangeLabel = "", at = 0, soundBlocked = false, picStart = 0, raf = 0, closed = false, stallTimer = 0;
  const pool = new Map(); // ad id -> <video>, only the current ad and its two neighbours

  const dlg = document.createElement("dialog");
  dlg.className = "wt";
  dlg.tabIndex = -1;
  dlg.setAttribute("aria-label", "Watch ads");
  dlg.innerHTML = `<header class="wt-bar">
      <div class="wt-where"><b>Watch</b><span class="wt-title"></span><span class="wt-n" aria-live="polite"></span></div>
      <div class="wt-ctrl">
        <div class="segmented wt-look" role="group" aria-label="Show it as">${[["feed", "Feed"], ["story", "Story"]].map(([k, l]) =>
          `<button type="button" data-look="${k}" aria-pressed="${prefs.look === k}">${l}</button>`).join("")}</div>
        <button type="button" class="wt-pill" data-auto aria-pressed="${prefs.auto}" title="Go on to the next ad when one ends">${svg(PLAY_ALL)}<span>Play all</span></button>
        <button type="button" class="wt-pill wt-sound" data-sound aria-pressed="${prefs.sound}" title="Sound (M)"></button>
      </div>
      <button type="button" class="wt-close" data-close aria-label="Close" title="Close (Esc)">${icon("close")}</button>
    </header>
    <div class="wt-body">
      <button type="button" class="wt-step prev" data-step="-1" aria-label="Previous ad" title="Previous ad (←)">${icon("back")}</button>
      <div class="wt-phone" data-view="${prefs.look}">
        <div class="wt-segs" aria-hidden="true"></div>
        <div class="wt-head"></div>
        <div class="wt-copy"></div>
        <div class="wt-media">
          <div class="wt-videos"></div>
          <img class="wt-pic" alt="" hidden referrerpolicy="no-referrer">
          <span class="wt-spin" aria-hidden="true"></span>
          <span class="wt-paused" aria-hidden="true">${icon("play")}<b>Tap to play</b></span>
          <div class="wt-over"></div>
          <p class="wt-note" hidden>Meta didn't share this video's file, so its picture shows instead.</p>
          <button type="button" class="wt-mute" data-sound aria-label="Sound"></button>
        </div>
        <div class="wt-cta"></div>
      </div>
      <button type="button" class="wt-step next" data-step="1" aria-label="Next ad" title="Next ad (→)">${icon("chev")}</button>
      <aside class="wt-info" aria-live="polite"></aside>
    </div>
    <nav class="wt-strip" aria-label="All ads"></nav>
    <p class="wt-loading" role="status">Loading the ads…</p>`;
  document.body.appendChild(dlg);
  const $ = (sel) => dlg.querySelector(sel);
  const phone = $(".wt-phone"), media = $(".wt-media"), videos = $(".wt-videos"), pic = $(".wt-pic");
  pic.addEventListener("load", () => { const a = current(); if (a && !videoOf(a) && pic.naturalWidth) { a.ratio = pic.naturalWidth / pic.naturalHeight; fitMedia(a); } });

  const current = () => items[at];
  const videoOf = (a) => (a && a.video && !a.failed ? pool.get(a.id) : null);

  function drawSound() {
    const on = prefs.sound && !soundBlocked;
    dlg.querySelectorAll("[data-sound]").forEach((b) => b.setAttribute("aria-pressed", String(on)));
    $(".wt-bar [data-sound]").innerHTML = `${svg(on ? SOUND_ON : SOUND_OFF)}<span>${on ? "Sound on" : "Sound off"}</span>`;
    const mute = $(".wt-mute");
    mute.innerHTML = svg(on ? SOUND_ON : SOUND_OFF) + (soundBlocked ? "<span>Tap for sound</span>" : "");
    mute.classList.toggle("ask", soundBlocked);
    mute.setAttribute("aria-label", on ? "Turn the sound off" : "Turn the sound on");
    pool.forEach((v) => { v.muted = !on; });
  }

  function makeVideo(a) {
    const v = document.createElement("video");
    v.className = "wt-video";
    v.playsInline = true;
    v.preload = "auto";
    v.muted = !(prefs.sound && !soundBlocked);
    if (picture(a)) v.poster = picture(a);
    v.src = a.video;
    v.dataset.id = a.id;
    v.addEventListener("loadedmetadata", () => { if (v.videoWidth) { a.ratio = v.videoWidth / v.videoHeight; if (a === current()) fitMedia(a); } });
    v.addEventListener("waiting", () => { if (v === videoOf(current())) media.classList.add("is-loading"); });
    v.addEventListener("playing", () => { if (v === videoOf(current())) media.classList.remove("is-loading", "is-paused", "needs-tap"); });
    v.addEventListener("ended", () => { if (v === videoOf(current())) onEnd(); });
    v.addEventListener("error", async () => {
      a.failed = true;
      v.remove();
      pool.delete(a.id);
      // The server says why (Meta's answer, a download that failed); the video element can't read it.
      try {
        const r = await fetch(a.video, { headers: { Range: "bytes=0-0", "X-Requested-With": "ebads" }, credentials: "same-origin" });
        if (!r.ok) a.why = (await r.json()).error;
      } catch (e) { /* offline: the plain note */ }
      if (a === current()) show(at, { keepPool: true });
    });
    return v;
  }

  // Keep only the current ad's video and its neighbours': the next swipe is already loaded, the rest free memory.
  function fillPool() {
    const want = new Set([at, at + 1, at - 1].map((i) => items[(i + items.length) % items.length]).filter((a) => a && a.video && !a.failed).map((a) => a.id));
    pool.forEach((v, id) => {
      if (want.has(id)) return;
      v.pause(); v.removeAttribute("src"); v.load(); v.remove(); pool.delete(id);
    });
    want.forEach((id) => {
      if (pool.has(id)) return;
      const v = makeVideo(items.find((x) => x.id === id));
      pool.set(id, v);
      videos.appendChild(v);
    });
  }

  function play(v) {
    v.loop = !prefs.auto || items.length < 2;
    v.muted = !(prefs.sound && !soundBlocked);
    // A browser that won't start a video by itself (Safari, an iPhone in Low Power Mode) gets a big Play to tap; one
    // that only refuses sound plays silent and offers the tap for sound.
    const needTap = () => { if (v === videoOf(current())) media.classList.add("is-paused", "needs-tap"); };
    const p = v.play();
    if (p) p.catch((err) => {
      if (v !== videoOf(current())) return;
      if (err.name === "NotAllowedError" && !v.muted) { soundBlocked = true; drawSound(); v.muted = true; v.play().catch(needTap); }
      else if (err.name !== "AbortError") needTap();
    });
  }

  function onEnd() {
    if (prefs.auto && items.length > 1) step(1);
  }

  function segsHtml() {
    if (items.length > SEGMENTS_MAX) return '<span class="wt-seg one"><i></i></span>';
    return items.map((_, i) => `<span class="wt-seg${i < at ? " done" : ""}"><i></i></span>`).join("");
  }

  function show(i, { keepPool = false } = {}) {
    if (!items.length) return;
    at = (i + items.length) % items.length;
    const a = current();
    pool.forEach((v) => { if (v.dataset.id !== a.id) { v.pause(); try { v.currentTime = 0; } catch (e) { /* not loaded yet */ } } });
    if (!keepPool) fillPool();
    const cta = CTA_LABELS[a.cta_type] || (a.cta_type ? a.cta_type.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : "Learn more");
    $(".wt-n").textContent = items.length > 1 ? `${at + 1} of ${items.length}` : "";
    $(".wt-title").textContent = a.name;
    $(".wt-head").innerHTML = `<span class="wt-avatar">${esc(initials(page))}</span><span class="wt-who"><b>${esc(page || "Your Page")}</b><small>Sponsored</small></span><span class="wt-dots" aria-hidden="true">${icon("dots")}</span>`;
    $(".wt-copy").innerHTML = postText(a.body);
    $(".wt-cta").innerHTML = `<span class="wt-headline">${esc(a.title || "")}</span><span class="wt-btn">${esc(cta)}</span>`;
    $(".wt-over").innerHTML = `<div class="wt-over-who"><span class="wt-avatar">${esc(initials(page))}</span><b>${esc(page || "Your Page")}</b><small>Sponsored</small></div>
      ${a.body ? `<p class="wt-over-text">${esc(a.body.trim())}</p>` : ""}<span class="wt-btn wide">${esc(cta)}</span>`;
    $(".wt-segs").innerHTML = segsHtml();
    $(".wt-info").innerHTML = `<p class="wt-kicker">${esc(a.title || "")}</p>
      <h2 class="wt-name"><a href="/ad.html?id=${encodeURIComponent(a.id)}">${esc(a.name)}</a></h2>
      <div class="wt-state">${statusPill(a.effective_status)}</div>
      ${figures(a, rangeLabel)}
      ${a.body ? `<details class="wt-body-text"><summary>Ad text</summary><p>${esc(a.body.trim())}</p></details>` : ""}
      <a class="btn wt-open" href="/ad.html?id=${encodeURIComponent(a.id)}">Open this ad</a>
      <p class="wt-keys"><kbd>←</kbd> <kbd>→</kbd> switch · <kbd>Space</kbd> pause · <kbd>M</kbd> sound</p>`;
    $(".wt-strip").querySelectorAll("[data-go]").forEach((b) => b.setAttribute("aria-current", String(Number(b.dataset.go) === at)));
    $(".wt-strip [aria-current='true']")?.scrollIntoView({ block: "nearest", inline: "center" });
    media.classList.remove("is-paused", "is-loading", "needs-tap");
    clearTimeout(stallTimer);
    const v = videoOf(a);
    pool.forEach((x) => x.classList.toggle("on", x === v));
    pic.hidden = Boolean(v);
    if (!v) { if (picture(a)) pic.src = picture(a); else pic.removeAttribute("src"); picStart = performance.now(); }
    fitMedia(a);
    media.classList.toggle("no-media", !v && !picture(a));
    media.classList.toggle("no-video", !v);
    $(".wt-note").hidden = !a.failed;
    $(".wt-note").textContent = a.why ? `The video couldn't be played here, so its picture shows. ${a.why}` : "The video couldn't be played here, so its picture shows.";
    if (v) {
      if (v.readyState < 3) media.classList.add("is-loading");
      play(v);
      // Still on its first frame after a while: something held it (a browser setting, a slow line). Offer the tap.
      stallTimer = setTimeout(() => { if (v === videoOf(current()) && v.currentTime < 0.05) { media.classList.remove("is-loading"); media.classList.add("is-paused", "needs-tap"); } }, 6000);
    }
    if (!dlg.contains(document.activeElement)) dlg.focus();
  }

  // The Feed look gives the video (or picture) its own shape, as a feed does: nothing is cropped.
  function fitMedia(a) { media.style.aspectRatio = String(a.ratio || 4 / 5); }

  function step(d) { if (items.length > 1) show(at + d); }

  function togglePause() {
    const v = videoOf(current());
    if (!v) return;
    if (v.paused) { media.classList.remove("is-paused", "needs-tap"); play(v); } else { v.pause(); media.classList.add("is-paused"); }
  }

  function toggleSound() {
    if (soundBlocked) { soundBlocked = false; prefs.sound = true; } else prefs.sound = !prefs.sound;
    savePrefs(prefs);
    drawSound();
    const v = videoOf(current());
    if (v && (!v.paused || media.classList.contains("needs-tap"))) { media.classList.remove("is-paused", "needs-tap"); play(v); }
  }

  // The bar of the ad on screen fills as it plays; the ones before it stay full.
  function tick() {
    if (closed) return;
    raf = requestAnimationFrame(tick);
    const a = current();
    if (!a) return;
    const bar = dlg.querySelector(items.length > SEGMENTS_MAX ? ".wt-seg.one i" : `.wt-seg:nth-child(${at + 1}) i`);
    const v = videoOf(a);
    let p;
    if (v) p = v.duration ? v.currentTime / v.duration : 0;
    else {
      p = Math.min(1, (performance.now() - picStart) / (PICTURE_SECONDS * 1000));
      if (p >= 1 && prefs.auto && items.length > 1) { step(1); return; }
    }
    if (bar) bar.style.transform = `scaleX(${p})`;
  }

  // ---------------------------------------------------------------- input
  dlg.addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) { dlg.close(); return; }
    const s = e.target.closest("[data-step]");
    if (s) { step(Number(s.dataset.step)); return; }
    const g = e.target.closest("[data-go]");
    if (g) { show(Number(g.dataset.go)); return; }
    if (e.target.closest("[data-sound]")) { toggleSound(); return; }
    if (e.target.closest("[data-auto]")) {
      prefs.auto = !prefs.auto; savePrefs(prefs);
      $("[data-auto]").setAttribute("aria-pressed", String(prefs.auto));
      const v = videoOf(current());
      if (v) v.loop = !prefs.auto || items.length < 2;
      picStart = performance.now();
      return;
    }
    const l = e.target.closest("[data-look]");
    if (l) {
      prefs.look = l.dataset.look; savePrefs(prefs);
      phone.dataset.view = prefs.look;
      dlg.querySelectorAll("[data-look]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.look === prefs.look)));
      return;
    }
    if (e.target.closest(".wt-media") && !swiped) togglePause();
  });

  let down = null, swiped = false;
  media.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY }; swiped = false; });
  media.addEventListener("pointerup", (e) => {
    if (!down) return;
    const dx = e.clientX - down.x, dy = e.clientY - down.y;
    down = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.3) { swiped = true; step(dx < 0 ? 1 : -1); }
  });
  media.addEventListener("pointercancel", () => { down = null; });

  dlg.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.closest("a, summary") && (e.key === " " || e.key === "Enter")) return;
    const k = e.key;
    if (k === "ArrowRight" || k === "ArrowDown") { e.preventDefault(); step(1); }
    else if (k === "ArrowLeft" || k === "ArrowUp") { e.preventDefault(); step(-1); }
    else if (k === " " || k === "k" || k === "K") { e.preventDefault(); togglePause(); }
    else if (k === "m" || k === "M") { e.preventDefault(); toggleSound(); }
  });

  dlg.addEventListener("close", () => {
    closed = true;
    cancelAnimationFrame(raf);
    clearTimeout(stallTimer);
    pool.forEach((v) => { v.pause(); v.removeAttribute("src"); v.load(); });
    pool.clear();
    dlg.remove();
  });

  dlg.showModal();
  dlg.focus();
  drawSound();

  try {
    const d = await api(`/api/ads/watch?ids=${encodeURIComponent(list.join(","))}&range=${encodeURIComponent(range)}`);
    if (closed) return dlg;
    items = d.items;
    page = d.page?.name || "";
    rangeLabel = d.range?.label || "";
  } catch (err) {
    $(".wt-loading").textContent = err.message;
    return dlg;
  }
  if (!items.length) { $(".wt-loading").textContent = "None of these ads can be shown."; return dlg; }
  $(".wt-loading").remove();
  dlg.classList.add("ready");
  dlg.classList.toggle("single", items.length < 2);
  $(".wt-strip").innerHTML = items.length > 1 ? items.map((a, i) => `<button type="button" class="wt-thumb" data-go="${i}" aria-label="${esc(a.name)}" title="${esc(a.name)}">${
    picture(a) ? `<img src="${esc(picture(a))}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<span>${esc(initials(a.name))}</span>`}</button>`).join("") : "";
  show(Math.max(0, items.findIndex((a) => a.id === String(startId))));
  tick();
  return dlg;
}
