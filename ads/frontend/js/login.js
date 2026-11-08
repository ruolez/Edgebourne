import { api } from "./api.js";
import { fieldError } from "./ui.js";

const form = document.getElementById("login");
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = form.querySelector("button[type=submit]");
  btn.disabled = true;
  try {
    const me = await api("/api/auth/login", {
      method: "POST",
      body: { email: form.email.value, password: form.password.value, remember: form.remember.checked },
    });
    const next = new URLSearchParams(location.search).get("next");
    location.href = me.must_change_password ? "/account.html?first=1" : (next && next.startsWith("/") ? next : "/leads.html");
  } catch (err) {
    fieldError(form, "password", err.message);
    btn.disabled = false;
  }
});
