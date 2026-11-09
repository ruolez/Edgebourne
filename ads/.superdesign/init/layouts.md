# Layouts

Every app page uses the same shell: `<div class="app"><aside class="rail"></aside><main class="main"><header class="page-head">…</header><div class="content">…</div></main></div>`. The rail (left sidebar, dark) is filled by `boot()` in `frontend/js/ui.js` (brand logo /img/favicon.svg + 'Edge Bourne Ads', nav: Home, Leads (new-count badge), Ads, Performance, and admin-only Desk, Research, Team, Settings; footer: avatar + name/role, Theme toggle, Sign out). On narrow screens the rail CSS collapses (see app.css media queries).

## Page shell example `frontend/home.html`
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Home | Edge Bourne Ads</title>
  <link rel="icon" href="/img/favicon.svg">
  <script src="/js/theme.js"></script>
  <link rel="stylesheet" href="/css/app.css">
</head>
<body>
  <div class="app">
    <aside class="rail"></aside>
    <main class="main">
      <header class="page-head">
        <h1 id="hello">Today</h1>
        <span class="perf-head-meta" id="today-date"></span>
      </header>
      <div class="content stack" id="home"></div>
    </main>
  </div>
  <script type="module" src="/js/home.js"></script>
</body>
</html>
```

## Rail render (`boot()` in `frontend/js/ui.js`)
```js
export async function boot({ page, admin = false }) {
  let me;
  try { me = await api("/api/auth/me"); } catch (e) { return null; }
  if (!me) { location.href = "/login.html"; return null; }
  if (me.must_change_password && page !== "account") {
    location.href = "/account.html?first=1";
    return null;
  }
  if (admin && me.role !== "admin") { location.href = "/home.html"; return null; }
  const links = [
    { id: "home", href: "/home.html", label: "Home", icon: "home" },
    { id: "leads", href: "/leads.html", label: "Leads", icon: "leads" },
    { id: "ads", href: "/ads.html", label: "Ads", icon: "ads" },
    { id: "performance", href: "/performance.html", label: "Performance", icon: "chart" },
    ...(me.role === "admin" ? [
      { id: "desk", href: "/desk.html", label: "Desk", icon: "spark" },
      { id: "research", href: "/research.html", label: "Research", icon: "research" },
      { id: "team", href: "/team.html", label: "Team", icon: "team" },
      { id: "settings", href: "/settings.html", label: "Settings", icon: "settings" },
    ] : []),
  ];
  const rail = document.querySelector(".rail");
  const initials = me.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  rail.innerHTML = `
    <a class="brand" href="/home.html"><img src="/img/favicon.svg" alt=""><span>Edge Bourne Ads</span></a>
    <nav class="nav" aria-label="Main">
      ${links.map((l) => `<a href="${l.href}" ${l.id === page ? 'aria-current="page"' : ""}>${icon(l.icon)}<span class="label">${l.label}</span>${l.id === "leads" ? '<span class="count" id="nav-new" hidden></span>' : ""}</a>`).join("")}
    </nav>
    <div class="rail-foot">
      <a class="me" href="/account.html" ${page === "account" ? 'aria-current="page"' : ""}>
        <span class="avatar" aria-hidden="true">${esc(initials)}</span>
        <span class="who"><b>${esc(me.name)}</b><small>${me.role === "admin" ? "Admin" : "Team member"}</small></span>
      </a>
      <div class="rail-actions">
        <button type="button" id="theme-btn">${themeLabel(currentTheme())}</button>
        <button type="button" id="signout-btn">Sign out</button>
      </div>
    </div>`;
  document.getElementById("theme-btn").addEventListener("click", (e) => {
    const next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
    applyTheme(next);
    e.currentTarget.textContent = themeLabel(next);
  });
  document.getElementById("signout-btn").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    location.href = "/login.html";
  });
  return me;
}
```

## Shell CSS (frontend/css/app.css)
```css
/* ---------- App frame ---------- */
.app { display: grid; grid-template-columns: 232px 1fr; min-height: 100vh; }
.rail {
  background: var(--rail);
  color: var(--rail-ink);
  display: flex;
  flex-direction: column;
  padding: 18px 12px;
  position: sticky;
  top: 0;
  height: 100vh;
}
.brand { display: flex; align-items: center; gap: 10px; padding: 4px 8px 22px; text-decoration: none; }
.brand img { width: 30px; height: 30px; }
.brand span { font: 600 17px/1.1 var(--font-display); letter-spacing: -.01em; }
.nav { display: flex; flex-direction: column; gap: 2px; }
.nav a {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 10px; border-radius: var(--radius-s);
  color: var(--rail-ink-2); text-decoration: none; font-weight: 600;
}
.nav a:hover { color: var(--rail-ink); background: var(--rail-active); }
.nav a[aria-current="page"] { color: var(--rail-ink); background: var(--rail-active); }
.nav svg { width: 18px; height: 18px; flex: none; }
.nav .count {
  margin-left: auto; min-width: 22px; padding: 1px 7px; border-radius: 99px;
  background: var(--amber); color: #2B1B00; font-size: 12px; font-weight: 800; text-align: center;
}
.rail-foot { margin-top: auto; border-top: 1px solid var(--rail-active); padding-top: 12px; }
.me { display: flex; align-items: center; gap: 10px; padding: 6px 8px; }
.me .avatar {
  width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center;
  background: var(--rail-active); font-weight: 800; font-size: 13px;
}
.me .who { line-height: 1.2; min-width: 0; }
.me .who b { display: block; font-size: 14px; }
.me .who small { color: var(--rail-ink-2); font-size: 12px; }
.rail-actions { display: flex; gap: 4px; padding: 6px 4px 0; }
.rail-actions button, .rail-actions a {
  flex: 1; background: none; border: 0; border-radius: var(--radius-s);
  color: var(--rail-ink-2); padding: 7px 6px; cursor: pointer; font-size: 13px; font-weight: 600;
  text-decoration: none; text-align: center;
}
.rail-actions button:hover, .rail-actions a:hover { background: var(--rail-active); color: var(--rail-ink); }

.main { min-width: 0; display: flex; flex-direction: column; }
.page-head {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 24px 32px 16px;
}
.page-head h1 { font: 650 30px/1.1 var(--font-display); letter-spacing: -.02em; margin: 0; }
.page-head .spacer { flex: 1; }
.content { padding: 0 32px 40px; }

/* ---------- Controls ---------- */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border: 1px solid var(--line-strong); background: var(--surface); color: var(--ink);
  padding: 8px 14px; border-radius: var(--radius-s); font-weight: 700; cursor: pointer;
  text-decoration: none; white-space: nowrap;
}
.btn:hover { border-color: var(--ink-3); }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.btn-primary { background: var(--ink); border-color: var(--ink); color: var(--surface); }
.btn-primary:hover { opacity: .9; }
.btn-call { background: var(--pine); border-color: var(--pine); color: var(--on-pine); }
.btn-danger { color: var(--rust); }
.btn-quiet { border-color: transparent; background: transparent; }
.btn svg { width: 16px; height: 16px; }

.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-weight: 700; font-size: 13px; color: var(--ink-2); }
.field .hint { font-size: 13px; color: var(--ink-3); }
.input, select.input, textarea.input {
  width: 100%; border: 1px solid var(--line-strong); background: var(--surface);
  border-radius: var(--radius-s); padding: 9px 11px; min-height: 40px;
}
textarea.input { min-height: 84px; resize: vertical; }
.input:focus { border-color: var(--focus); outline: none; box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 25%, transparent); }
.field.error .input { border-color: var(--rust); }
.field .err { color: var(--rust); font-size: 13px; font-weight: 600; }
.check { display: flex; gap: 10px; align-items: flex-start; font-weight: 600; }
.check input { margin-top: 3px; width: 16px; height: 16px; accent-color: var(--ink); }

.segmented {
  display: inline-flex; background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius-m); padding: 3px; gap: 2px; flex-wrap: wrap;
}
.segmented button {
  border: 0; background: none; padding: 6px 12px; border-radius: 7px; font-weight: 700;
  color: var(--ink-2); cursor: pointer; display: inline-flex; gap: 6px; align-items: baseline;
}
.segmented button:hover { color: var(--ink); }
.segmented button[aria-pressed="true"] { background: var(--ink); color: var(--surface); }
.segmented .n { font-size: 12px; opacity: .75; font-variant-numeric: tabular-nums; }

.search { position: relative; }
.search svg { position: absolute; left: 10px; top: 50%; width: 16px; height: 16px; transform: translateY(-50%); color: var(--ink-3); }
.search .input { padding-left: 34px; width: 260px; }

/* ---------- Panels ---------- */
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-m); }
.panel-head { display: flex; align-items: baseline; gap: 12px; padding: 18px 20px 6px; }
.panel-head h2 { font: 650 19px/1.2 var(--font-display); margin: 0; letter-spacing: -.01em; }
.panel-head p { margin: 0; color: var(--ink-3); font-size: 14px; }
.panel-body { padding: 12px 20px 20px; }
.stack { display: flex; flex-direction: column; gap: 16px; }
.row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }

.pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; border-radius: 99px;
  font-size: 12px; font-weight: 800; background: var(--surface-2); color: var(--ink-2);
  white-space: nowrap;
}
.pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.pill.new { background: var(--amber-soft); color: var(--amber-ink); }
.pill.contacted { background: var(--surface-2); color: var(--ink-2); }
.pill.qualified { background: var(--violet-soft); color: var(--violet); }
.pill.won { background: var(--pine-soft); color: var(--pine); }
```
