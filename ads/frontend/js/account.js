import { api } from "./api.js";
import { applyTheme, boot, currentTheme, fieldError, toast } from "./ui.js";

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
