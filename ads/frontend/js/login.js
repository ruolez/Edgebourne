import { api } from "./api.js";
import { fieldError } from "./ui.js";

// Only a page of this console. Resolved the way the browser will (it drops tabs and newlines, so
// "/\t/evil.com" means "//evil.com") and returned whole, so a path like "/.//evil.com" stays on this site.
function sameSiteNext(next) {
  try {
    const u = new URL(next || "/home.html", location.origin);
    if (u.origin === location.origin) return u.href;
  } catch (e) { /* not an address */ }
  return "/home.html";
}

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
    location.href = me.must_change_password ? "/account.html?first=1" : sameSiteNext(new URLSearchParams(location.search).get("next"));
  } catch (err) {
    fieldError(form, "password", err.message);
    btn.disabled = false;
  }
});
