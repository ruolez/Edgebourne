import { api } from "./api.js";
import { fieldErrors } from "./ui.js";

// Only a page of this console. Resolved the way the browser will (it drops tabs and newlines, so
// "/\t/evil.com" means "//evil.com") and returned whole, so a path like "/.//evil.com" stays on this site.
function sameSiteNext(next) {
  try {
    const u = new URL(next || "/home.html", location.origin);
    if (u.origin === location.origin) return u.href;
  } catch (e) { /* not an address */ }
  return "/home.html";
}

// The same field checks the server makes (auth.login_problems), so a blank field doesn't use up a sign-in try.
function problems(email, password) {
  const out = [];
  const [name, ...rest] = email.trim().split("@");
  if (!email.trim()) out.push({ field: "email", message: "Type the email you sign in with." });
  else if (!name || rest.length !== 1 || !rest[0] || /\s/.test(email.trim())) out.push({ field: "email", message: "Check the email: it looks like name@example.com." });
  if (!password) out.push({ field: "password", message: "Type your password." });
  return out;
}

const form = document.getElementById("login");
const note = document.getElementById("login-error");

// What isn't about one field (wrong email or password, too many tries, no connection) sits above the button.
function formError(message, { both = false } = {}) {
  note.textContent = message;
  note.hidden = !message;
  for (const input of [form.email, form.password]) {
    if (both && message) { input.setAttribute("aria-invalid", "true"); input.setAttribute("aria-describedby", "login-error"); }
    else if (!input.closest(".field.error")) { input.removeAttribute("aria-invalid"); input.removeAttribute("aria-describedby"); }
  }
}

// Typing in a field takes its own error away (and the form's, which may have been about it).
form.addEventListener("input", (e) => {
  const field = e.target.closest(".field.error");
  if (field) {
    field.classList.remove("error");
    field.querySelector(".err")?.remove();
    e.target.removeAttribute("aria-invalid");
    e.target.removeAttribute("aria-describedby");
  }
  if (!note.hidden) formError("");
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError("");
  const local = problems(form.email.value, form.password.value);
  if (fieldErrors(form, local)) return;
  const btn = form.querySelector("button[type=submit]");
  btn.disabled = true;
  try {
    const me = await api("/api/auth/login", {
      method: "POST",
      body: { email: form.email.value, password: form.password.value, remember: form.remember.checked },
    });
    location.href = me.must_change_password ? "/account.html?first=1" : sameSiteNext(new URLSearchParams(location.search).get("next"));
  } catch (err) {
    btn.disabled = false;
    if (err.body.errors || err.body.field) { fieldErrors(form, err.body.errors || [{ field: err.body.field, message: err.message }]); return; }
    if (err.status === 401) {
      formError("That email and password don't match. Check both and try again.", { both: true });
      form.password.select();
      form.password.focus();
    } else if (err.status === 429) {
      formError("Too many tries from this device. Wait a minute, then try again.");
    } else {
      formError(err.message);
    }
  }
});
