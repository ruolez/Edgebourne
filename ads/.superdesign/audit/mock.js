// Phase 9 mockup: sample data only, no network.
const $ = (id) => document.getElementById(id);
const I = {
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
  leads: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  ads: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
  chart: '<path d="M3 3v18h18"/><path d="M8 17v-5M13 17V7M18 17v-8"/>',
  spark: '<path d="m12 3 1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 2.9-1.2V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.9h.1a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
  alert: '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z"/><path d="M12 9v4M12 17h.01"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};
const svg = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[n]}</svg>`;

const CREATIVES = [
  { id: "N2", name: "N2 - Order portal", spent: 29.97, leads: 7, cpl: 4.28, hook: 25.6, q: 1, hookTag: "Outcome promise", angle: "Orders without calling", who: "Wholesalers", days: 13 },
  { id: "N1", name: "N1 - One simple system", spent: 26.18, leads: 5, cpl: 5.24, hook: 30.6, q: 0, hookTag: "Pain statement", angle: "Spreadsheets everywhere", who: "Small business owners", days: 13 },
  { id: "N4", name: "N4 - Weekly report", spent: 27.30, leads: 5, cpl: 5.46, hook: 30.6, q: 0, hookTag: "Question", angle: "Reports by hand", who: "Owners and managers", days: 13 },
  { id: "N3", name: "N3 - Same work twice", spent: 30.96, leads: 5, cpl: 6.19, hook: 29.3, q: 0, hookTag: "Command", angle: "Retyping between tools", who: "Shops with books", days: 13, tired: true },
  { id: "N5", name: "N5 - Quote to invoice", spent: 31.69, leads: 5, cpl: 6.34, hook: 32.8, q: 0, hookTag: "Outcome promise", angle: "Quote to invoice", who: "Service businesses", days: 3, launched: true },
];
const INBOX = [
  { id: 1, need: true, icon: "alert", tone: "bad", t: "Meta rejected “N3 - Same work twice”", p: "Personal attributes (also on Instagram)", at: "8:23 PM", body: "Ads can't imply knowledge of personal attributes. Fix the words or picture and Meta reviews it again.", acts: [["Ask Claude for a fixed version", "ai"], ["Open the ad", "", "ad"]] },
  { id: 2, need: true, icon: "alert", tone: "warn", t: "The spending limit runs out in about 2 days", p: "Every ad stops around Thu Nov 12", at: "8:18 PM", body: "$108.80 is left of the $150 limit at about $46 a day. Raise it in Meta's billing settings to keep ads running.", acts: [["Open Meta billing", ""]] },
  { id: 3, need: true, icon: "spark", tone: "ai", t: "Claude suggests a shorter headline for N5", p: "Shorter hook. Review before it goes to Meta", at: "8:22 PM", body: "You'll see the old and new words side by side before anything changes. Meta reviews the ad again once you accept.", acts: [["Review and accept", "ai solid"], ["Ask to change", ""]] },
  { id: 4, need: true, icon: "phone", tone: "bad", t: "New lead: Tom Alvarez", p: "Landscaping, 2 crews. Waiting 3 days", at: "Nov 7", body: "From N1 - One simple system.", acts: [["Call", "primary"], ["Open the lead", ""]] },
  { id: 5, need: true, icon: "phone", tone: "bad", t: "New lead: Priya Nair", p: "Freight brokerage. Waiting 2 days", at: "Nov 8", body: "From N3 - Same work twice.", acts: [["Call", "primary"], ["Open the lead", ""]] },
  { id: 6, need: false, icon: "ads", tone: "", t: "N5 - Quote to invoice was approved", p: "Started delivering", at: "1:36 PM", body: "Meta approved the ad and it is delivering.", acts: [["Open the ad", "", "ad"]] },
  { id: 7, need: false, icon: "ads", tone: "", t: "Ad set “SoCal” was changed in Ads Manager", p: "Nothing to do if that was you", at: "8:22 PM", body: "Someone changed it outside this console. Nothing to do if that was you.", acts: [["Open the ad set", ""]] },
  { id: 8, need: false, icon: "ads", tone: "", t: "N1 rejection was fixed", p: "Fixed since. Delivering again", at: "8:23 PM", body: "This one sorted itself out, so it no longer counts as needing you.", acts: [["Open the ad", "", "ad"]] },
];
const SWIPES = [
  { id: 1, who: "Acme Business Software", ran: "Ran 97 days: likely working", text: "One app for quotes and invoices.", tag: "Outcome promise" },
  { id: 2, who: "Blitz Mobile Apps", ran: "Running 45 days: likely working", text: "Still running your shop on spreadsheets? We build software around how you work.", tag: "Question" },
  { id: 3, who: "Acme Business Software", ran: "Found by Claude", text: "Stop retyping orders.", tag: "Command" },
];
const SETTINGS = [["This account", ["Meta connection", "Targets", "Alerts", "Clients and reports", "Lead replies", "Tracking health", "Lead stages to Meta", "Meta A/B tests", "Activity"]], ["Whole console", ["Meta app", "Automatic refresh", "Email", "Telegram", "Accounts", "Team"]]];
const NAV = [["Work", [["today", "Today", "sun"], ["inbox", "Inbox", "inbox", "5"], ["leads", "Leads", "leads", "7", "bad"]]], ["Run", [["ads", "Ads", "ads"], ["gallery", "Creative", "image", null, null, true], ["insights", "Insights", "chart"], ["claude", "Claude", "spark", "1", "claude"]]]];
const CREATIVE_TABS = [["gallery", "Gallery"], ["ideas", "Ideas"], ["research", "Research"]];
const SECTION = { today: "today", inbox: "inbox", leads: "leads", ads: "ads", ad: "ads", gallery: "gallery", ideas: "gallery", research: "gallery", insights: "insights", claude: "claude", settings: "settings" };
const TITLE = { today: "Today", inbox: "Inbox", leads: "Leads", ads: "Ads", ad: "N3 - Same work twice", gallery: "Creative", ideas: "Creative", research: "Creative", insights: "Insights", claude: "Claude", settings: "Settings" };

const state = { view: location.hash.slice(1) || "today", box: "need", sel: 1, read: new Set(), gview: "top", tag: null, picked: new Set(), swipes: new Set(), dim: "hookTag", setting: "Targets", adtab: "Overview" };
const money = (n) => "$" + n.toFixed(2);
const track = (c) => `<span class="track" aria-label="Delivering ${c.days} of the last 14 days">${Array.from({ length: 14 }, (_, i) => `<i class="${i < 14 - c.days ? "off" : (c.launched && i === 14 - c.days ? "rev" : "")}"></i>`).join("")}</span>`;
const go = (v) => { state.view = v; state.picked.clear(); state.swipes.clear(); $("peek").hidden = true; location.hash = v; render(); };

function rail() {
  const cur = SECTION[state.view];
  const link = ([v, l, ic, n, tone, isNew]) => `<button class="nav" data-go="${v}" ${cur === v ? 'aria-current="page"' : ""}>${svg(ic)}<span class="l">${l}</span>${isNew ? '<span class="new">New</span>' : ""}${n ? `<span class="badge ${tone || ""}">${n}</span>` : ""}</button>`;
  $("rail").innerHTML = `<div class="brand"><span class="mark">EB</span>Edge Bourne Ads</div>
    <button class="acct"><span>Edge Bourne</span></button>
    <button class="jump" data-palette>${svg("search").replace("<svg", '<svg width="15" height="15"')}<span>Search or jump to…</span><kbd>⌘K</kbd></button>
    ${NAV.map(([g, items]) => `<div class="group"><small>${g}</small>${items.map(link).join("")}</div>`).join("")}
    <div class="foot">
      <div class="mini"><span class="dot"></span>Mac offline<br>Claude picks up work when it's back</div>
      ${link(["settings", "Settings", "gear"])}
      <div class="mini"><b class="num">$41.20 / $150</b><div class="meter"><i></i></div>Runs out around Thu Nov 12</div>
    </div>`;
  const tabs = [["today", "Today", "sun"], ["leads", "Leads", "leads", "7", "bad"], ["ads", "Ads", "ads"], ["inbox", "Inbox", "inbox", "5"]];
  $("tabbar").innerHTML = tabs.map(([v, l, ic, n, tone]) => `<button data-go="${v}" ${cur === v ? 'aria-current="page"' : ""}>${svg(ic)}${l}${n ? `<span class="badge ${tone || ""}">${n}</span>` : ""}</button>`).join("") + `<button data-more ${["gallery", "insights", "claude", "settings"].includes(cur) ? 'aria-current="page"' : ""}>${svg("menu")}More<span class="badge claude">1</span></button>`;
  const deep = state.view === "ad";
  $("topbar").innerHTML = `${deep ? '<button class="up" data-go="ads" aria-label="Back to Ads">←</button>' : '<span class="mark">EB</span>'}<span>${TITLE[state.view]}</span><span class="grow"></span><button class="up" data-palette aria-label="Search">${svg("search").replace("<svg", '<svg width="20" height="20"')}</button>`;
  $("more").innerHTML = [["claude", "Claude", "spark", "1", "claude"], ["gallery", "Creative", "image"], ["insights", "Insights", "chart"], ["settings", "Settings", "gear"]].map(link).join("");
}
const crumbs = (items) => `<div class="topline">${items.map((c, i) => i === items.length - 1 ? `<b>${c[0]}</b>` : `<button data-go="${c[1]}">${c[0]}</button><span>/</span>`).join("")}<span class="grow"></span><span>Updated just now</span></div>`;

const views = {
  today() {
    const lead = (n, b, via, w) => `<div class="q"><span class="wait">${w}</span><div class="who"><b>${n}</b><p>${b} · from <button class="link" data-go="ad">${via}</button></p></div><button class="btn primary">${svg("phone")}Call</button></div>`;
    const fix = (ic, tone, t, p, act, v) => `<div class="q"><span class="sticon ${tone}">${svg(ic)}</span><div class="who"><b>${t}</b><p>${p}</p></div><button class="btn ${tone === "ai" ? "ai" : ""}" ${v ? `data-go="${v}"` : ""}>${act}</button></div>`;
    return crumbs([["Today"]]) + `<div class="page"><div class="head"><div class="t"><h1>Good evening, Eugene</h1><p class="lede">4 people to call and 3 things to decide. Your ads are delivering.</p></div><button class="btn ai">${svg("spark")}Ask Claude</button><button class="btn primary">${svg("plus")}New ad</button></div>
    <div class="today"><div><div class="queue">
      <div class="qh">Call first <small>longest wait on top</small></div>${lead("Tom Alvarez", "Landscaping, 2 crews", "N1", "3d")}${lead("Priya Nair", "Freight brokerage", "N3", "2d")}${lead("Daniel Kim", "HVAC service, 3 trucks", "N5", "2d")}${lead("Maria Lopez", "Wholesale bakery", "N2", "2d")}
      <div class="qh">Fix</div>${fix("alert", "bad", "Meta rejected N3", "Personal attributes. Claude can write a fixed version.", "Open", "inbox")}${fix("alert", "warn", "Spending limit runs out Thu Nov 12", "$108.80 left at about $46 a day.", "Open billing")}
      <div class="qh">Decide</div>${fix("spark", "ai", "Claude suggests a shorter headline for N5", "See old and new before anything changes.", "Review", "inbox")}
    </div>
    <div class="advice"><div class="big">96</div><div class="t"><b>Meta's advice: add a 9:16 video for Reels</b><p class="muted small">Could lower cost per result by about 8%. Needs a 9:16 cut of each ad.</p></div><button class="btn ai">${svg("spark")}Fix with Claude</button></div></div>
    <div class="side"><section><div class="sec-t">Money</div><div class="big">$12.34</div><p class="muted xs">today so far, of $46.00 a day</p><div class="stat"><span>Yesterday</span><b>$42.55</b></div><div class="stat"><span>Leads, last 7 days</span><b>52</b></div><div class="stat"><span>Cost per lead</span><b>$5.58</b></div><div class="stat"><span>Per qualified lead</span><b>$290.02</b></div></section>
    <section><div class="sec-t">On air <button class="link" data-go="gallery">Open Creative</button></div><div class="onair">${CREATIVES.map((c) => `<button data-go="ad"><img src="img/${c.id}.jpg" alt="${c.name}">${c.leads} leads</button>`).join("")}</div></section></div></div></div>`;
  },
  inbox() {
    const items = INBOX.filter((x) => x.need === (state.box === "need"));
    const sel = items.find((x) => x.id === state.sel) || items[0];
    const need = INBOX.filter((x) => x.need && !state.read.has(x.id)).length;
    return crumbs([["Inbox"]]) + `<div class="page"><div class="head"><div class="t"><h1>Inbox</h1><p class="lede">${need} need you. Everything else is for your information.</p></div><button class="btn">Mark all read</button></div>
    <div class="bar"><button class="chip" data-box="need" aria-pressed="${state.box === "need"}">Needs action ${need}</button><button class="chip" data-box="fyi" aria-pressed="${state.box === "fyi"}">FYI ${INBOX.length - INBOX.filter((x) => x.need).length}</button></div>
    <div class="split"><div class="list">${items.map((x) => `<button class="row ${state.read.has(x.id) ? "" : "unread"}" data-sel="${x.id}" aria-selected="${sel && x.id === sel.id}"><span class="sticon ${x.tone}">${svg(x.icon)}</span><span class="b"><b>${x.t}</b><p>${x.p}</p></span><small>${x.at}</small></button>`).join("")}</div>
    <div class="detail">${sel ? `<span class="sticon ${sel.tone}">${svg(sel.icon)}</span><h2>${sel.t}</h2><p class="muted">${sel.body}</p><div class="acts">${sel.acts.map(([l, c, v]) => `<button class="btn ${c}" ${v ? `data-go="${v}"` : ""}>${l}</button>`).join("")}<button class="btn" data-done="${sel.id}">Mark read</button></div><p class="hint">Keyboard: J and K to move, E to mark read. Anything that spends money still opens its confirmation.</p>` : ""}</div></div></div>`;
  },
  gallery() {
    const list = CREATIVES.filter((c) => (state.gview === "launched" ? c.launched : state.gview === "tired" ? c.tired : true) && (!state.tag || c.hookTag === state.tag));
    const chip = (v, l) => `<button class="chip" data-gv="${v}" aria-pressed="${state.gview === v}">${l}</button>`;
    return crumbs([["Creative", "gallery"], ["Gallery"]]) + tabs() + `<div class="page"><div class="head"><div class="t"><h1>Gallery</h1><p class="lede">Every ad as people see it, with what it earned. Copies of the same ad count once.</p></div><button class="btn primary">${svg("plus")}New ad</button></div>
    <div class="bar">${chip("top", "Top")}${chip("launched", "Just launched")}${chip("tired", "Tired")}<span class="grow"></span>${state.tag ? `<button class="chip" data-tag="" aria-pressed="true">Hook: ${state.tag} ×</button>` : ""}<select class="select" aria-label="Period"><option>Last 7 days</option><option>Last 14 days</option><option>Last 30 days</option></select></div>
    <p class="note">Too early to name a winner: an ad needs 3 leads and twice your target cost in spend. Sorted by cost per lead for now.</p>
    <div class="grid">${list.map((c) => `<article class="card ${state.picked.has(c.id) ? "picked" : ""}"><button class="open" data-peek="${c.id}" aria-label="Quick look at ${c.name}"><img src="img/${c.id}.jpg" alt=""></button><label class="tick"><input type="checkbox" data-pick="${c.id}" aria-label="Select ${c.name}" ${state.picked.has(c.id) ? "checked" : ""}></label><div class="body"><h3>${c.name}</h3><div class="status">${track(c)}<span><span class="dot ${c.tired ? "warn" : "on"}"></span>${c.tired ? "Tired" : c.launched ? "Just launched" : "Delivering"}</span></div><div class="kpi"><span class="muted xs">Cost per lead</span><b>${money(c.cpl)}</b></div><div class="kpis"><span><b>${money(c.spent)}</b>Spent</span><span><b>${c.leads}</b>Leads</span><span><b>${c.hook}%</b>Hook rate</span></div><div><button class="tag" data-tag="${c.hookTag}">${c.hookTag}</button></div></div></article>`).join("") || `<p class="muted">Nothing here yet.</p>`}</div></div>`;
  },
  ideas() {
    const groups = {};
    CREATIVES.forEach((c) => { (groups[c[state.dim]] ||= []).push(c); });
    const dim = (k, l) => `<button class="chip" data-dim="${k}" aria-pressed="${state.dim === k}">${l}</button>`;
    return crumbs([["Creative", "gallery"], ["Ideas"]]) + tabs() + `<div class="page"><div class="head"><div class="t"><h1>Ideas</h1><p class="lede">Which messages work, across every ad that uses them.</p></div></div><div class="bar">${dim("hookTag", "Hook")}${dim("angle", "Angle")}${dim("who", "Who it's for")}</div>
    <p class="note"><b>Question</b> is cheapest so far, but the difference could be chance. Keep the ideas running side by side.</p>
    <div class="panel">${Object.entries(groups).map(([k, cs]) => { const sp = cs.reduce((a, c) => a + c.spent, 0), ld = cs.reduce((a, c) => a + c.leads, 0); return `<div class="idea"><div><h3>${k}</h3><button class="link xs" data-go="gallery">See ${cs.length} in Gallery</button></div><div class="thumbs">${cs.map((c) => `<img src="img/${c.id}.jpg" alt="${c.name}">`).join("")}</div><div class="nums"><span><b>${money(sp / ld)}</b>Cost per lead</span><span><b>${ld}</b>Leads</span><span><b>${money(sp)}</b>Spent</span></div></div>`; }).join("")}</div></div>`;
  },
  research() {
    return crumbs([["Creative", "gallery"], ["Research"]]) + tabs() + `<div class="page"><div class="head"><div class="t"><h1>Research</h1><p class="lede">Competitor ads worth learning from, and a straight path to your next ad.</p></div><button class="btn">Search Ad Library</button><button class="btn ai">${svg("spark")}Ask Claude to research</button></div>
    <div class="bar"><button class="chip" aria-pressed="true">Saved 3</button><button class="chip" aria-pressed="false">Running 30+ days 2</button><button class="chip" aria-pressed="false">Found by Claude 1</button><button class="chip" aria-pressed="false">Watched Pages 1</button></div>
    <div class="swipes">${SWIPES.map((s) => `<article class="swipe ${state.swipes.has(s.id) ? "picked" : ""}"><label class="tick"><input type="checkbox" data-swipe="${s.id}" aria-label="Select ad from ${s.who}" ${state.swipes.has(s.id) ? "checked" : ""}></label><b>${s.who}</b><span class="muted xs">${s.ran}</span><q>${s.text}</q><div><span class="tag">${s.tag}</span></div><div class="acts"><button class="btn ai" data-brief="${s.id}">${svg("spark")}Make something like this</button><button class="btn">Ad Library</button></div></article>`).join("")}</div></div>`;
  },
  ad() {
    const t = ["Overview", "Polish", "Audience", "Video", "Comments", "History"];
    return crumbs([["Ads", "ads"], ["Edge Bourne - Free intro call", "ads"], ["SoCal business owners", "ads"], ["N3 - Same work twice"]]) + `<div class="page"><div class="head"><div class="t"><h1>N3 - Same work twice</h1><p class="lede"><span class="dot on"></span>Delivering · $31.00 a day, shared by the campaign</p></div><button class="btn">Compare</button><button class="btn">Duplicate</button><button class="btn ai solid">${svg("spark")}Polish</button></div>
    <div class="subnav" role="tablist">${t.map((x) => `<button role="tab" data-adtab="${x}" aria-selected="${state.adtab === x}">${x}</button>`).join("")}</div>
    <div class="adgrid" style="margin-top:20px"><div class="stick"><div class="phoneprev"><div class="prevtabs"><button aria-pressed="true">Feed</button><button aria-pressed="false">Stories</button><button aria-pressed="false">Reels</button></div><img src="img/N3.jpg" alt="Ad preview"></div></div>
    <div class="stack"><div class="figs"><div><b>$54.75</b>Spent</div><div><b>10</b>Leads</div><div><b>$5.48</b>Cost per lead</div><div><b>29.6%</b>Hook rate</div></div>
    <div class="sugg"><div class="sec-t"><span><span class="dot ai"></span>Claude suggests a new headline</span></div><div class="diff"><div><small>Now</small>Stop typing the same thing twice</div><div><small>Suggested</small>Type it once. We connect the rest.</div></div><p class="muted small" style="margin-top:8px">Meta reviews the ad again once you accept. Results stay with this ad.</p><div class="acts"><button class="btn ai solid">Update this ad</button><button class="btn">Edit first</button><button class="btn">Decline</button></div></div>
    <details class="fold"><summary>Where it runs <small>Edge Bourne - Free intro call · SoCal business owners</small></summary><div><dl class="facts"><dt>Campaign</dt><dd><button class="link" data-go="ads">Edge Bourne - Free intro call</button></dd><dt>Ad set</dt><dd><button class="link" data-go="ads">SoCal business owners</button></dd><dt>Leads</dt><dd><button class="link" data-go="leads">10 leads from this ad</button></dd><dt>Tests</dt><dd><button class="link" data-go="insights">In 1 test</button></dd></dl></div></details>
    <details class="fold"><summary>Words <small>Stop typing the same thing twice</small></summary><div><p class="small">Your shop software and your books don't talk, so someone retypes everything.</p></div></details>
    <details class="fold"><summary>Versions <small>3 versions, version 3 running</small></summary><div><p class="small muted">Too early to judge between versions.</p></div></details>
    <details class="fold"><summary>The idea <small>Command · Retyping between tools</small></summary><div><button class="tag" data-go="ideas">Command</button></div></details>
    <details class="fold"><summary>Meta's automatic changes <small>Image touch-ups on</small></summary><div><p class="small muted">Switches for what Meta may change on its own.</p></div></details></div></div></div>`;
  },
  settings() {
    const panel = state.setting === "Targets" ? `<div class="field"><label for="t1">Cost per qualified lead</label><input id="t1" value="$60.00"><small>The number that matters most. Ads are judged against it.</small></div><div class="field"><label for="t2">Cost per lead</label><input id="t2" placeholder="Not set"><small>Turns on the "leads cost too much" alert.</small></div><div class="field"><label for="t3">Highest daily budget</label><input id="t3" value="$100.00"><small>No budget can go above this. Raising it asks you to confirm.</small></div><button class="btn primary">Save targets</button><p class="adv">Other sections keep what you typed when you save this one.</p>` : `<p class="muted">The ${state.setting} controls move here unchanged. Only this section shows at a time, and links from alerts land directly on it.</p><p class="adv">Technical fields fold under Advanced.</p>`;
    return crumbs([["Settings"]]) + `<div class="page"><div class="head"><div class="t"><h1>Settings</h1></div></div><div class="sets"><nav class="setnav" aria-label="Settings sections">${SETTINGS.map(([g, xs]) => `<small>${g}</small>${xs.map((x) => `<button class="nav" data-set="${x}" ${state.setting === x ? 'aria-current="page"' : ""}>${x}</button>`).join("")}`).join("")}</nav><section class="panel pad"><h2 style="font-size:16px;font-weight:600;margin-bottom:14px">${state.setting}</h2>${panel}</section></div></div>`;
  },
};
const stub = (name, what) => crumbs([[name]]) + `<div class="page stub"><div><h1>${name}</h1><p>${what}</p></div></div>`;
views.leads = () => stub("Leads", "Same page you have, with the same urgency colors as Today, campaign links and Undo on a stage change.");
views.ads = () => stub("Ads", "Same manager table, with a sticky header and name column, the On switch no longer cut off, and a legend for the delivery track.");
views.insights = () => stub("Insights", "Results, Compare, Tests and Reports stay. The period carries between them and test winners get a next step.");
views.claude = () => stub("Claude", "Conversations, By ad and Schedules. Research moved to Creative.");
function tabs() { return `<div class="subnav" role="tablist">${CREATIVE_TABS.map(([v, l]) => `<button role="tab" data-go="${v}" aria-selected="${state.view === v}">${l}</button>`).join("")}</div>`; }

function tray() {
  const t = $("tray");
  if (state.view === "gallery" && state.picked.size) { t.hidden = false; t.innerHTML = `${state.picked.size} selected <button class="btn">Compare</button><button class="btn" data-brief="many">Make more like these</button><button class="btn" data-clear>Clear</button>`; }
  else if (state.view === "research" && state.swipes.size) { t.hidden = false; t.innerHTML = `${state.swipes.size} selected <button class="btn" data-brief="many">Write a brief</button><button class="btn" data-clear>Clear</button>`; }
  else t.hidden = true;
}
function render() { rail(); $("main").innerHTML = (views[state.view] || views.today)(); tray(); window.scrollTo(0, 0); }

function openBrief(key) {
  const picked = key === "many" ? (state.view === "research" ? SWIPES.filter((s) => state.swipes.has(s.id)).map((s) => `${s.who}: "${s.text}"`) : CREATIVES.filter((c) => state.picked.has(c.id)).map((c) => c.name)) : SWIPES.filter((s) => s.id === Number(key)).map((s) => `${s.who}: "${s.text}"`);
  const d = $("brief");
  d.innerHTML = `<h2 style="font-size:16px;font-weight:600">Ask Claude for a brief</h2><p class="muted small">Edit anything first. Claude's ideas come back as suggestions; nothing goes to Meta until you accept.</p><textarea aria-label="Brief">Write a creative brief for Edge Bourne's free intro call, inspired by:\n\n${picked.map((p) => "- " + p).join("\n")}\n\nKeep our voice, avoid personal attributes, and suggest 3 concepts.</textarea><div class="end"><button class="btn" data-close>Cancel</button><button class="btn ai solid" data-close>Send to Claude</button></div>`;
  d.showModal();
}
function openPalette() {
  const d = $("palette");
  const items = [["Today", "today"], ["Inbox", "inbox"], ["Leads", "leads"], ["Ads", "ads"], ["Creative: Gallery", "gallery"], ["Creative: Ideas", "ideas"], ["Creative: Research", "research"], ["Insights: Results", "insights"], ["Claude", "claude"], ["Settings", "settings"], ["N3 - Same work twice", "ad"]];
  const draw = (q) => { d.querySelector("ul").innerHTML = items.filter(([l]) => l.toLowerCase().includes(q.toLowerCase())).map(([l, v]) => `<li><button data-go="${v}" data-close>${l}<small>Go to</small></button></li>`).join(""); };
  d.innerHTML = '<input placeholder="Search or jump to…" aria-label="Search"><ul></ul>';
  draw(""); d.showModal();
  d.querySelector("input").addEventListener("input", (e) => draw(e.target.value));
}

document.addEventListener("click", (e) => {
  const k = e.target.closest("[data-go],[data-more],[data-palette],[data-box],[data-sel],[data-done],[data-gv],[data-tag],[data-dim],[data-set],[data-adtab],[data-peek],[data-brief],[data-close],[data-clear],[data-size],[data-theme-set]");
  if (e.target.tagName === "DIALOG") { e.target.close(); return; }
  if (!k) return;
  const d = k.dataset;
  if (d.close !== undefined) k.closest("dialog").close();
  if (d.go) { document.querySelectorAll("dialog[open]").forEach((x) => x.close()); go(d.go); return; }
  if (d.more !== undefined) return $("more").showModal();
  if (d.palette !== undefined) return openPalette();
  if (d.box) { state.box = d.box; state.sel = null; return render(); }
  if (d.sel) { state.sel = Number(d.sel); state.read.add(state.sel); return render(); }
  if (d.done) { state.read.add(Number(d.done)); return render(); }
  if (d.gv) { state.gview = d.gv; return render(); }
  if (d.tag !== undefined) { state.tag = d.tag || null; return render(); }
  if (d.dim) { state.dim = d.dim; return render(); }
  if (d.set) { state.setting = d.set; return render(); }
  if (d.adtab) { state.adtab = d.adtab; return render(); }
  if (d.brief) return openBrief(d.brief);
  if (d.clear !== undefined) { state.picked.clear(); state.swipes.clear(); return render(); }
  if (d.peek) {
    const c = CREATIVES.find((x) => x.id === d.peek), p = $("peek");
    p.innerHTML = `<header><h2>${c.name}</h2><button class="x" data-closepeek aria-label="Close">×</button></header><img src="img/${c.id}.jpg" alt=""><div class="status">${track(c)}<span>Delivering</span></div><div class="stat"><span>Spent</span><b>${money(c.spent)}</b></div><div class="stat"><span>Leads</span><b>${c.leads}</b></div><div class="stat"><span>Cost per lead</span><b>${money(c.cpl)}</b></div><div class="stat"><span>Hook rate</span><b>${c.hook}%</b></div><div class="acts"><button class="btn primary" data-go="ad">Open the ad</button><button class="btn" data-go="leads">Its leads</button><button class="btn ai" data-brief="many">Make more like this</button></div>`;
    p.hidden = false; p.querySelector(".x").focus(); p.querySelector(".x").onclick = () => { p.hidden = true; k.focus(); };
    return;
  }
  if (d.size) {
    document.querySelectorAll("#size button").forEach((b) => b.setAttribute("aria-pressed", b === k));
    const phone = d.size === "phone";
    $("device").hidden = !phone; $("app").hidden = phone;
    if (phone) $("frame").src = `index.html?framed=1&t=${document.documentElement.dataset.theme || "light"}#${state.view}`;
    return;
  }
  if (d.themeSet) {
    document.documentElement.dataset.theme = d.themeSet;
    document.querySelectorAll("#theme button").forEach((b) => b.setAttribute("aria-pressed", b === k));
    if (!$("device").hidden) $("frame").src = `index.html?framed=1&t=${d.themeSet}#${state.view}`;
  }
});
document.addEventListener("change", (e) => {
  const d = e.target.dataset;
  if (d.pick) { state.picked[e.target.checked ? "add" : "delete"](d.pick); render(); }
  if (d.swipe) { state.swipes[e.target.checked ? "add" : "delete"](Number(d.swipe)); render(); }
});
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
  if (e.key === "Escape") $("peek").hidden = true;
  if (state.view !== "inbox" || /INPUT|TEXTAREA/.test(e.target.tagName)) return;
  const list = INBOX.filter((x) => x.need === (state.box === "need"));
  const i = Math.max(0, list.findIndex((x) => x.id === state.sel));
  if (e.key === "j") { state.sel = list[Math.min(list.length - 1, i + 1)].id; render(); }
  if (e.key === "k") { state.sel = list[Math.max(0, i - 1)].id; render(); }
  if (e.key === "e") { state.read.add(list[i].id); render(); }
});
window.addEventListener("hashchange", () => { const v = location.hash.slice(1); if (v && v !== state.view) { state.view = v; render(); } });

const params = new URLSearchParams(location.search);
document.documentElement.dataset.theme = params.get("t") || "light";
if (params.get("framed")) document.body.classList.add("framed");
document.querySelectorAll("#theme button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.themeSet === document.documentElement.dataset.theme));
render();
