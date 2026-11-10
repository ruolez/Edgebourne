import { api } from "./api.js";
import { boot, esc, toast } from "./ui.js";
import { count, dayLabel, money, setCurrency } from "./format.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const token = params.get("t");
let kind = params.get("kind") === "month" ? "month" : "week";
let start = params.get("start") || "";

const LEVEL = { campaign: "Campaign", adset: "Ad set", ad: "Ad", form: "Lead form", study: "A/B test", account: "Account" };
const ACTION = { status: "turned", budget: "budget", create: "created", duplicate: "copied", enhancement: "automatic change", recommendation: "Meta's suggestion applied",
  comment_reply: "replied to a comment", comment_hide: "hid a comment", comment_show: "showed a comment", end: "ended early" };

function changeLine(c) {
  const what = c.action === "status" ? `${c.new_value === "ACTIVE" ? "turned on" : "turned off"}`
    : c.action === "budget" ? `daily budget ${money(Number(c.old_value), { exact: true })} → ${money(Number(c.new_value), { exact: true })}`
    : c.action === "create" ? "created" : (ACTION[c.action] || c.action);
  return `<li><span class="r-date">${esc(dayLabel(c.created_at.slice(0, 10)))}</span> ${esc(LEVEL[c.level] || c.level)} “${esc(c.entity_name || "")}”: ${esc(what)}${c.action === "create" && c.new_value ? "" : ""}</li>`;
}

function reportHtml(r) {
  setCurrency(r.currency);
  const range = `${dayLabel(r.start)} – ${dayLabel(r.end)}, ${r.end.slice(0, 4)}`;
  const n = r.now;
  const cpl = n.leads ? n.spend_cents / n.leads : null;
  const cpq = n.qualified ? n.spend_cents / n.qualified : null;
  const shownChanges = r.changes.slice(-15);
  return `<header class="r-head">
      <img src="/img/favicon.svg" alt="" width="40" height="40">
      <div><p class="r-kicker">Meta ads report · ${esc(r.kind === "week" ? "Week" : "Month")}</p><h2>${esc(r.account)}</h2><p class="muted flush">${esc(range)}${r.complete ? "" : " (not finished yet: figures will still change)"}</p></div>
    </header>
    <section class="r-sec"><h3>1. What happened</h3>
      <p class="r-headline">${esc(r.headline)}</p>
      <div class="r-figs">
        <div><span>Spent</span><b>${money(n.spend_cents)}</b></div>
        <div><span>Leads</span><b>${count(n.leads)}</b></div>
        <div><span>Cost per lead</span><b>${cpl ? money(cpl, { exact: true }) : "—"}</b></div>
        <div><span>Qualified</span><b>${count(n.qualified)}</b></div>
        <div><span>Cost per qualified lead</span><b>${cpq ? money(cpq, { exact: true }) : "—"}</b>${r.target_cents ? `<small>target ${money(r.target_cents)}</small>` : ""}</div>
      </div>
      <table class="table r-funnel"><thead><tr><th>Step</th><th class="num">People</th><th class="num">Of the step before</th></tr></thead>
        <tbody>${r.funnel.map((f) => `<tr><th scope="row">${esc(f.step)}</th><td class="num">${count(f.n)}</td><td class="num">${f.rate == null ? "" : `${f.rate}%`}</td></tr>`).join("")}</tbody></table>
      ${n.median_minutes != null ? `<p class="muted flush small">Half of the leads heard back within ${n.median_minutes < 90 ? `${n.median_minutes} minutes` : `${Math.round(n.median_minutes / 60)} hours`}.</p>` : ""}
    </section>
    <section class="r-sec"><h3>2. Why</h3>
      ${r.ads.length ? `<table class="table r-ads"><thead><tr><th>Ad</th><th class="num">Spent</th><th class="num">Leads</th><th class="num">Cost per lead</th><th class="num">Click rate</th><th class="num">Stopped scrolling</th></tr></thead>
        <tbody>${r.ads.map((a) => `<tr><th scope="row">${esc(a.name || "")}</th><td class="num">${money(a.spend_cents)}</td><td class="num">${count(a.leads)}</td><td class="num">${a.cpl_cents ? money(a.cpl_cents, { exact: true }) : "—"}</td><td class="num">${a.ctr != null ? `${a.ctr}%` : "—"}</td><td class="num">${a.hook != null ? `${a.hook}%` : "—"}</td></tr>`).join("")}</tbody></table>` : '<p class="muted flush">No ad spent money in this period.</p>'}
      ${r.ideas && r.ideas.best ? `<p class="flush">Of the ideas behind the ads, <b>${esc(r.ideas.best)}</b> brought the cheapest leads${r.ideas.clear ? ` (${r.ideas.sure}% sure)` : `, but only ${r.ideas.sure}% sure, so it could still be chance`}.</p>` : ""}
    </section>
    <section class="r-sec"><h3>3. What we did</h3>
      ${shownChanges.length ? `<ul class="r-list">${shownChanges.map(changeLine).join("")}</ul>${r.changes.length > shownChanges.length ? `<p class="muted small flush">and ${r.changes.length - shownChanges.length} earlier changes.</p>` : ""}` : '<p class="muted flush">No changes to the ads in this period.</p>'}
    </section>
    <section class="r-sec"><h3>4. What's next</h3>
      ${r.tests.length ? `<ul class="r-list">${r.tests.map((t) => `<li><b>${esc(t.name)}</b> (${t.status === "running" ? "running" : "finished"}): ${esc(t.note)}</li>`).join("")}</ul>` : '<p class="muted flush">No tests running; we keep watching cost per lead and lead quality.</p>'}
    </section>
    <section class="r-sec"><h3>5. What we need from you</h3>
      ${r.needs.length ? `<ul class="r-list">${r.needs.map((x) => `<li>A decision on: ${esc(x)}</li>`).join("")}</ul>` : '<p class="flush">Nothing this time. Keep marking leads Contacted, Qualified or Won: it is how we judge which ads bring real customers.</p>'}
    </section>
    <footer class="r-foot">${r.footnotes.map((f) => `<p>${esc(f)}</p>`).join("")}${r.shared_until ? `<p>This link works until ${esc(dayLabel(r.shared_until))}.</p>` : ""}</footer>`;
}

async function load() {
  document.querySelectorAll("#kind [data-kind]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.kind === kind)));
  try {
    const r = token ? await api(`/api/reports/shared?t=${encodeURIComponent(token)}`)
      : await api(`/api/reports?kind=${kind}${start ? `&start=${start}` : ""}`);
    $("report").innerHTML = reportHtml(r);
    document.title = `${r.account} · ${r.kind === "week" ? "Week" : "Month"} of ${dayLabel(r.start)} | Report`;
  } catch (err) { $("report").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

$("pdf").addEventListener("click", () => window.print());
if (token) {
  // A shared link: no sign-in, no menu, just the report.
  document.documentElement.classList.add("shared-report");
  document.querySelector(".rail").remove();
  $("kind").remove();
  document.querySelector(".page-head h1").textContent = "Ads report";
  load();
} else {
  const me = await boot({ page: "report" });
  if (me) {
    if (me.role === "member") { location.href = "/home.html"; }
    $("share").hidden = me.role !== "admin";
    $("kind").addEventListener("click", (e) => {
      const b = e.target.closest("[data-kind]");
      if (!b) return;
      kind = b.dataset.kind; start = "";
      history.replaceState(null, "", `?kind=${kind}`);
      load();
    });
    $("share").addEventListener("click", async () => {
      try {
        const r = await api("/api/reports/share", { method: "POST", body: { kind, start: start || null } });
        try { await navigator.clipboard.writeText(r.url); toast(`Link copied. It works until ${dayLabel(r.expires)}.`); }
        catch (err) { prompt("Copy this link", r.url); }
      } catch (err) { toast(err.message, "bad"); }
    });
    load();
  }
}
