import { api } from "./api.js";
import { boot, esc, onRefresh, toast } from "./ui.js";
import { ACTIVE, taskCard, wireTaskActions } from "./tasks.js";

const $ = (id) => document.getElementById(id);
const QUICK = ["custom software", "business automation", "QuickBooks integration", "inventory software", "IT consulting Los Angeles", "AI for small business"];
const openReports = new Set();
let timer;
let lastJson = "";

function libraryUrl(q, country, active) {
  const p = new URLSearchParams({ active_status: active ? "active" : "all", ad_type: "all", country, q, search_type: "keyword_unordered", media_type: "all" });
  return `https://www.facebook.com/ads/library/?${p}`;
}

async function load() {
  try {
    const d = await api("/api/desk");
    $("mac-line").textContent = d.bridge.online ? "Your Mac is connected: Claude starts right away." : "Your Mac is offline: this waits until it's on.";
    const tasks = d.tasks.filter((t) => t.kind === "research");
    const json = JSON.stringify(tasks);
    if (json !== lastJson) {
      lastJson = json;
      if (tasks[0]) tasks[0].reports.forEach((r) => openReports.add(r.id));
      $("tasks").innerHTML = tasks.length ? tasks.map((t) => taskCard(t, openReports)).join("")
        : '<section class="panel empty"><h3>No research yet</h3><p>Ask Claude what competitors are running, which angles repeat and what\'s worth testing. Reports land here.</p></section>';
    }
    clearTimeout(timer);
    timer = setTimeout(load, tasks.some((t) => ACTIVE.has(t.status)) ? 4000 : 30000);
  } catch (err) { toast(err.message, "bad"); }
}

const me = await boot({ page: "research", admin: true });
if (me) {
  $("quick").innerHTML = QUICK.map((q) => `<button type="button" class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
  $("quick").addEventListener("click", (e) => { const b = e.target.closest("[data-q]"); if (b) { $("q").value = b.dataset.q; $("lib-form").requestSubmit(); } });
  $("lib-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("q").value.trim();
    if (!q) { $("q").focus(); return; }
    window.open(libraryUrl(q, $("country").value, $("active").checked), "_blank", "noopener");
  });
  $("ask-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = $("prompt").value.trim();
    if (!prompt) { $("prompt").focus(); return; }
    try {
      await api("/api/desk/tasks", { method: "POST", body: { kind: "research", prompt } });
      $("prompt").value = "";
      toast("Sent to Claude");
      lastJson = "";
      load();
    } catch (err) { toast(err.message, "bad"); }
  });
  wireTaskActions($("tasks"), () => { lastJson = ""; load(); }, openReports);
  onRefresh(load);
  load();
}
