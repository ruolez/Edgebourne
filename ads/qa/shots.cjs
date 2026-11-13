// Local design review: screenshots of each screen in light and dark.
// Playwright: $PLAYWRIGHT_CORE, else the first intact copy on this Mac (the render pipeline's copy lost
// its package files on 2026-11-10; any 1.64 drives the Chromium 1248 below).
const PW = [process.env.PLAYWRIGHT_CORE, '/Users/ruolez/Desktop/Dev/meta-ads/creatives/2026-11-07-new5/src/node_modules/playwright-core',
  ...require('fs').readdirSync(process.env.HOME + '/.npm/_npx').map((d) => `${process.env.HOME}/.npm/_npx/${d}/node_modules/playwright-core`)]
  .filter(Boolean).find((p) => require('fs').existsSync(p + '/package.json') && /"version": "1\.6[4-9]/.test(require('fs').readFileSync(p + '/package.json', 'utf8')));
const { chromium } = require(PW);
const EXE = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const OUT = process.argv[2] || 'qa/out';
const BASE = process.env.BASE || 'http://ads.localhost:8090';
(async () => {
  require('fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const errors = [];
  for (const scheme of ['light', 'dark']) {
    for (const [vw, vh, tag] of [[1440, 900, 'desk'], [390, 844, 'phone']]) {
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, colorScheme: scheme, deviceScaleFactor: 2 });
      const page = await ctx.newPage();
      // The missing page's own 404 is the point of that shot, not an error.
      page.on('console', (m) => { if (m.type() === 'error' && !(/status of 404/.test(m.text()) && /missing-page/.test(page.url()))) errors.push(`${tag} ${m.text()}`); });
      page.on('pageerror', (e) => errors.push(`${tag} ${e.message}`));
      await page.goto(BASE + '/login.html');
      await page.screenshot({ path: `${OUT}/login-${tag}-${scheme}.png` });
      await page.fill('#email', 'eugene@edgebourne.com');
      await page.fill('#password', 'localdev-pass-123');
      await Promise.all([page.waitForURL('**/home.html**'), page.click('button[type=submit]')]);
      await page.goto(BASE + '/leads.html');
      await page.waitForSelector('.lead-row');
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/leads-${tag}-${scheme}.png` });
      if (tag === 'phone') {
        await page.click('.lead-row');
        await page.waitForSelector('#stages');
        await page.screenshot({ path: `${OUT}/lead-detail-${tag}-${scheme}.png`, fullPage: true });
      }
      for (const p of ['home', 'inbox', 'ads', 'ads.html?level=campaign', 'campaign.html?id=120252638288040312', 'adset.html?id=120252672227950312', 'compare.html?ids=120252672232030312,120252672233160312,120252672230740312', 'compare.html#pick', 'ad.html?id=120252672230740312', 'ad.html?id=120252672230740312#tab=polish', 'ad.html?id=120252672230740312#tab=audience', 'ad.html?id=120252672230740312#tab=video', 'ad.html?id=120252672230740312#tab=comments', 'ad.html?id=120252672230740312#tab=history', 'ads.html?level=adset', 'new-ad', 'new-adset.html?campaign=120252638288040312', 'gallery', 'gallery.html?view=launched', 'ideas', 'research', 'research.html#tab=search', 'research.html#tab=watched', 'research.html#tab=past', 'desk', 'desk.html#ads', 'desk.html#schedules', 'performance', 'experiments', 'report', 'forms', 'new-campaign', 'team', 'settings', 'account', 'accounts', 'offline', 'missing-page.html',
        'inbox.html?box=fyi', 'inbox.html?box=all', 'gallery.html?view=tired', 'leads.html?due=today',
        ...['targets', 'alerts', 'reports-panel', 'replies', 'lead-quality', 'tracking', 'crm', 'ab', 'activity-panel', 'meta-app', 'auto', 'telegram', 'email', 'accounts-panel'].map((s) => `settings.html#${s}`)]) {
        await page.goto(p.includes('.html') ? `${BASE}/${p}` : `${BASE}/${p}.html`);
        if (p.includes('#')) await page.reload();
        await page.waitForTimeout(600);
        await page.waitForTimeout(p.includes('#') ? 900 : 0);
        const variant = (p.match(/(?:#tab=|#|level=|view=|box=|due=)([\w-]+)/) || ['', ''])[1];
        await page.screenshot({ path: `${OUT}/${p.split('.')[0]}${variant ? '-' + variant : ''}-${tag}-${scheme}.png`, fullPage: true });
      }
      // FU-A: the ad account picker (Settings → Accounts → Add ad account).
      await page.goto(`${BASE}/settings.html#accounts-panel`);
      await page.reload();
      await page.waitForSelector('#acp-open');
      await page.click('#acp-open');
      await page.waitForSelector('dialog.acp .acp-row, dialog.acp #acp-none');
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/acp-picker-${tag}-${scheme}.png` });
      await page.keyboard.press('Escape');
      // The command menu, the shortcuts and (phones) the More sheet and the bulk bar.
      await page.goto(`${BASE}/home.html`);
      await page.waitForTimeout(600);
      await page.click(tag === 'phone' ? '.topbar [data-palette]' : '.rail [data-palette]');
      await page.fill('dialog.palette input', 'set');
      await page.waitForTimeout(600);
      await page.screenshot({ path: `${OUT}/palette-${tag}-${scheme}.png` });
      await page.keyboard.press('Escape');
      if (tag === 'desk') {
        await page.keyboard.press('Shift+Slash');
        await page.waitForSelector('dialog.confirm .keys-list');
        await page.screenshot({ path: `${OUT}/shortcuts-${tag}-${scheme}.png` });
        await page.keyboard.press('Escape');
      } else {
        await page.click('.tabbar [data-more]');
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/more-${tag}-${scheme}.png` });
        await page.keyboard.press('Escape');
        await page.goto(`${BASE}/ads.html`);
        await page.waitForSelector('.pl li');
        await page.locator('.pl li .pick').nth(0).click();
        await page.locator('.pl li .pick').nth(4).click();
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/bulk-${tag}-${scheme}.png` });
      }
      await ctx.close();
    }
  }
  await browser.close();
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})();
