import { api } from "./api.js";
import { applyTheme, boot, confirmDialog, currentTheme, esc, fieldError, toast } from "./ui.js";

const me = await boot({ page: "account" });
if (me) {
  const choice = document.getElementById("theme-choice");
  const mark = () => choice.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === currentTheme())));
  mark();
  choice.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-theme-choice]");
    if (!b) return;
    applyTheme(b.dataset.themeChoice);
    mark();
    const btn = document.getElementById("theme-btn");
    if (btn) btn.textContent = { system: "Theme: auto", light: "Theme: light", dark: "Theme: dark" }[currentTheme()];
  });
  document.getElementById("account-signout").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    location.href = "/login.html";
  });
  const first = new URLSearchParams(location.search).get("first") === "1" || me.must_change_password;
  document.getElementById("first-note").hidden = !first;
  const notify = document.getElementById("notify");
  notify.checked = me.notify_new_leads;
  notify.addEventListener("change", async () => {
    try {
      await api("/api/auth/me", { method: "PATCH", body: { notify_new_leads: notify.checked } });
      toast(notify.checked ? "You'll get an email for each new lead" : "Lead emails turned off");
    } catch (err) { toast(err.message, "bad"); }
  });
  const remind = document.getElementById("remind");
  remind.checked = me.notify_reminders;
  remind.addEventListener("change", async () => {
    try {
      await api("/api/auth/me", { method: "PATCH", body: { notify_reminders: remind.checked } });
      toast(remind.checked ? "You'll be reminded about leads nobody has contacted" : "Reminders turned off");
    } catch (err) { toast(err.message, "bad"); }
  });

  // Telegram: connect once, then new leads and reminders arrive on the phone.
  const tg = document.getElementById("tg");
  let tgPoll;
  const renderTg = (t) => {
    clearTimeout(tgPoll);
    if (!t.bot) {
      tg.innerHTML = `<p class="muted">Telegram alerts: ${me.role === "admin" ? 'add the bot in <a href="/settings.html">Settings → Telegram</a> first.' : "an admin sets up the bot first."}</p>`;
    } else if (t.linked) {
      tg.innerHTML = `<label class="check"><input type="checkbox" id="tg-on" ${t.enabled ? "checked" : ""}> Send new leads and reminders to my Telegram <span class="muted">(${esc(t.name || "connected")})</span></label>
        <div class="row"><button class="btn" type="button" id="tg-test">Send a test</button><button class="btn btn-danger-text" type="button" id="tg-off">Disconnect Telegram</button></div>`;
    } else if (t.pending) {
      tg.innerHTML = `<p>Open Telegram and tap <b>Start</b> in the chat with @${esc(t.bot)}. This page notices by itself.</p>
        <div class="row"><a class="btn btn-primary" id="tg-open" href="${esc(t.link)}" target="_blank" rel="noopener noreferrer">Open Telegram</a><span class="muted">Waiting for you to tap Start…</span></div>`;
      tgPoll = setTimeout(async () => {
        const next = await api("/api/me/telegram").catch(() => t);
        if (next.linked) toast("Telegram connected. Check your phone.");
        renderTg(next);
      }, 3000);
    } else {
      tg.innerHTML = `<p>Get each new lead on your phone, seconds after it arrives.</p>
        <div class="row"><button class="btn btn-primary" type="button" id="tg-link">Connect Telegram</button></div>`;
    }
  };
  tg.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    b.disabled = true;
    try {
      if (b.id === "tg-link") renderTg(await api("/api/me/telegram/link", { method: "POST" }));
      if (b.id === "tg-test") { await api("/api/me/telegram/test", { method: "POST" }); toast("Sent. Check Telegram."); }
      if (b.id === "tg-off" && await confirmDialog({ title: "Disconnect Telegram?", body: "New leads and reminders stop going to your Telegram. You can connect again any time.", confirm: "Disconnect", danger: true })) {
        renderTg(await api("/api/me/telegram", { method: "DELETE" }));
        toast("Telegram disconnected");
      }
    } catch (err) { toast(err.message, "bad"); } finally { b.disabled = false; }
  });
  tg.addEventListener("change", async (e) => {
    if (e.target.id !== "tg-on") return;
    try {
      renderTg(await api("/api/me/telegram", { method: "PATCH", body: { enabled: e.target.checked } }));
      toast(e.target.checked ? "New leads go to your Telegram" : "Telegram alerts paused");
    } catch (err) { toast(err.message, "bad"); }
  });
  api("/api/me/telegram").then(renderTg).catch(() => { tg.hidden = true; });

  const form = document.getElementById("pw-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    fieldError(form);
    try {
      await api("/api/auth/password", { method: "POST", body: { current: form.current.value, new: form.new.value } });
      form.reset();
      toast("Password changed");
      if (first) location.href = "/home.html";
    } catch (err) {
      if (err.body.field) fieldError(form, err.body.field, err.message); else toast(err.message, "bad");
    }
  });
}
