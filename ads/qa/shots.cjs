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
      page.on('console', (m) => { if (m.type() === 'error') errors.push(`${tag} ${m.text()}`); });
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
      for (const p of ['home', 'ads', 'ad.html?id=120252672230740312', 'ad.html?id=120252672230740312#tab=polish', 'ad.html?id=120252672230740312#tab=audience', 'ad.html?id=120252672230740312#tab=video', 'ad.html?id=120252672230740312#tab=comments', 'new-ad', 'research', 'desk', 'performance', 'team', 'settings', 'account']) {
        await page.goto(p.includes('.html') ? `${BASE}/${p}` : `${BASE}/${p}.html`);
        if (p.includes('#')) await page.reload();
        await page.waitForTimeout(600);
        await page.waitForTimeout(p.includes('#tab') ? 900 : 0);
        await page.screenshot({ path: `${OUT}/${p.split('.')[0]}${(p.match(/tab=(\w+)/) || ['', ''])[1] ? '-' + p.match(/tab=(\w+)/)[1] : ''}-${tag}-${scheme}.png`, fullPage: true });
      }
      await ctx.close();
    }
  }
  await browser.close();
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})();
