// Design-system guards shared by flows.cjs: token contrast in both themes and 44px phone targets.

// [text token, background token, minimum ratio]. 4.5 for text, 3 for marks that carry meaning next to a word.
const PAIRS = [
  ['--ink', '--canvas', 4.5], ['--ink', '--surface', 4.5], ['--ink-2', '--surface', 4.5], ['--ink-2', '--surface-2', 4.5],
  ['--ink-3', '--canvas', 4.5], ['--ink-3', '--surface', 4.5], ['--ink-3', '--surface-2', 4.5],
  ['--signal-ink', '--surface', 4.5], ['--signal-ink', '--canvas', 4.5], ['--signal-ink', '--signal-soft', 4.5],
  ['--on-signal', '--signal-fill', 4.5],
  ['--amber-ink', '--amber-soft', 4.5], ['--amber-ink', '--surface', 4.5],
  ['--bad-ink', '--bad-soft', 4.5], ['--bad-ink', '--surface', 4.5], ['--bad-ink', '--canvas', 4.5], ['--on-bad', '--bad', 4.5],
  ['--violet', '--violet-soft', 4.5], ['--violet', '--surface', 4.5], ['--on-violet', '--violet', 4.5],
  ['--info', '--info-soft', 4.5], ['--info', '--surface', 4.5],
  ['--on-primary', '--primary', 4.5], ['--canvas', '--ink', 4.5], ['--surface', '--ink', 4.5],
  ['--rail-ink-2', '--rail', 4.5],
  ['--signal', '--surface', 3], ['--bad', '--surface', 3], ['--focus', '--surface', 3], ['--focus', '--canvas', 3],
];

// Every pair in light and dark, measured from the live stylesheet (tokens resolved by the browser).
async function tokenContrast(page) {
  return page.evaluate((pairs) => {
    const probe = document.createElement('i');
    document.body.append(probe);
    const rgb = (token) => {
      probe.style.color = `var(${token})`;
      const m = getComputedStyle(probe).color.match(/[\d.]+/g);
      return m ? m.slice(0, 3).map(Number) : null;
    };
    const lum = (c) => c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
      .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
    const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
    const had = document.documentElement.getAttribute('data-theme');
    const bad = [];
    for (const theme of ['light', 'dark']) {
      document.documentElement.setAttribute('data-theme', theme);
      for (const [fg, bg, min] of pairs) {
        const a = rgb(fg), b = rgb(bg);
        const r = a && b ? ratio(a, b) : 0;
        if (r < min) bad.push(`${theme} ${fg} on ${bg} ${r.toFixed(2)} < ${min}`);
      }
    }
    if (had) document.documentElement.setAttribute('data-theme', had); else document.documentElement.removeAttribute('data-theme');
    probe.remove();
    return bad;
  }, PAIRS);
}

// Retired names nobody may use any more (tokens.css no longer defines them, so a use would silently drop).
async function retiredTokens(page) {
  return page.evaluate(() => {
    const hits = [];
    for (const sheet of document.styleSheets) {
      let rules;
      try { rules = sheet.cssRules; } catch (e) { continue; }
      const text = [...rules].map((r) => r.cssText).join('\n');
      const m = text.match(/--(seal|seal-deep|seal-soft|on-seal|rust|rust-ink|rust-soft|pine|pine-soft|on-pine|fog|lift)\b/g);
      if (m) hits.push(`${(sheet.href || 'inline').split('/').pop()}: ${[...new Set(m)].join(' ')}`);
    }
    return hits;
  });
}

// Phone controls smaller than 44 × 44 px (inline links inside a sentence are exempt, as in WCAG 2.5.5).
function smallTargets() {
  const SEL = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [role=switch], [tabindex="0"]';
  const shown = (el) => {
    if (el.closest('[hidden], [inert], dialog:not([open]), .sr-only, .skip-link')) return false;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const inlineInText = (el) => el.tagName === 'A' && getComputedStyle(el).display === 'inline'
    && el.parentElement && el.parentElement.textContent.trim() !== el.textContent.trim();
  const area = (el) => {
    const label = (el.matches('input[type=checkbox], input[type=radio]') && (el.closest('label') || (el.id && document.querySelector(`label[for="${el.id}"]`)))) || null;
    return (label || el).getBoundingClientRect();
  };
  const out = [];
  for (const el of document.querySelectorAll(SEL)) {
    if (el.disabled || !shown(el) || inlineInText(el)) continue;
    const r = area(el);
    if (r.width < 43.5 || r.height < 43.5) {
      const name = (el.getAttribute('aria-label') || el.textContent || el.id || el.className || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 24);
      out.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : el.classList.length ? '.' + [...el.classList].join('.') : ''} "${name}" ${Math.round(r.width)}×${Math.round(r.height)}`);
    }
  }
  return out;
}

const TARGET_PAGES = ['/home.html', '/inbox.html', '/leads.html', '/ads.html', '/performance.html', '/ad.html?id=120252672229400312', '/campaign.html?id=120252638288040312', '/desk.html', '/settings.html'];

module.exports = { PAIRS, tokenContrast, retiredTokens, smallTargets, TARGET_PAGES };
