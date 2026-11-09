// Local E2E of the Ads controls against the fake Meta server (docker-compose.dev.yml).
// node ads/qa/flows.cjs <out-dir>
const { chromium } = require('/Users/ruolez/Desktop/Dev/meta-ads/creatives/2026-11-07-new5/src/node_modules/playwright-core');
const EXE = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const BASE = process.env.BASE || 'http://ads.localhost:8090';
const OUT = process.argv[2] || 'qa/out';
const IMG = process.argv[3];
const results = [];
const check = (name, ok, extra = '') => { results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };

(async () => {
  require('fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await (await browser.newContext({ viewport: { width: 1360, height: 900 } })).newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/facebook\.com|preview_iframe/.test(m.text())) errors.push(m.text()); });
  await page.goto(BASE + '/login.html');
  await page.fill('#email', 'eugene@edgebourne.com');
  await page.fill('#password', 'localdev-pass-123');
  await Promise.all([page.waitForURL('**/home.html**'), page.click('button[type=submit]')]);

  // 1. Turn N2 off from the Ads page, through the confirm dialog.
  await page.goto(BASE + '/ads.html');
  const n2 = page.locator('[data-toggle="ad:120252672231040312"]');
  await n2.waitFor();
  const before = await n2.getAttribute('aria-checked');
  await n2.click();
  await page.waitForSelector('dialog.confirm');
  await page.screenshot({ path: `${OUT}/flow-1-confirm-off.png` });
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('[data-toggle="ad:120252672231040312"]')?.getAttribute('aria-checked') === 'false');
  check('switch turns an ad off after confirming', before === 'true');
  // Cancel leaves it alone.
  await page.locator('[data-toggle="ad:120252672231040312"]').click();
  await page.click('dialog.confirm #cd-cancel');
  await page.waitForTimeout(400);
  check('cancel changes nothing', (await page.locator('[data-toggle="ad:120252672231040312"]').getAttribute('aria-checked')) === 'false');
  // Back on.
  await page.locator('[data-toggle="ad:120252672231040312"]').click();
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('[data-toggle="ad:120252672231040312"]')?.getAttribute('aria-checked') === 'true');
  check('switch turns it back on', true);

  // 2. Budget: validation, +20% warning, then a real change.
  await page.click('[data-budget^="campaign:"]');
  await page.waitForSelector('dialog.confirm #cd-input');
  await page.fill('#cd-input', '0.5');
  await page.click('dialog.confirm #cd-ok');
  check('budget below $1 is refused in the dialog', await page.isVisible('#cd-err'));
  await page.fill('#cd-input', '40');
  const hint = await page.textContent('#cd-hint');
  check('a big jump shows the learning warning', /Bigger than \+20%/.test(hint), hint.trim());
  await page.screenshot({ path: `${OUT}/flow-2-budget.png` });
  await page.fill('#cd-input', '26');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /\$26\.00\/day/.test(document.querySelector('[data-budget^="campaign:"]')?.textContent || ''));
  check('campaign budget changes to $26/day', true);

  // 3. Ad page: format switch, duplicate.
  await page.goto(BASE + '/ad.html?id=120252672233040312');
  await page.waitForSelector('#formats button');
  await page.click('#formats button[data-format="INSTAGRAM_STORY"]');
  await page.waitForSelector('#preview-frame iframe');
  check('preview loads an iframe for Instagram Stories', /INSTAGRAM_STORY/.test(await page.getAttribute('#preview-frame iframe', 'src')));
  await page.click('#dup');
  await page.waitForSelector('dialog.confirm #cd-input');
  await page.fill('#cd-input', 'N4 - Weekly report (flow copy)');
  await Promise.all([page.waitForURL('**created=1**'), page.click('dialog.confirm #cd-ok')]);
  await page.waitForSelector('.claude-note');
  check('duplicate opens the new ad with the "created, off" note', (await page.textContent('#ad-name')).includes('flow copy'));
  await page.screenshot({ path: `${OUT}/flow-3-duplicate.png`, fullPage: true });

  // 4. New ad with an uploaded image.
  if (IMG) {
    await page.goto(BASE + '/new-ad.html');
    await page.waitForSelector('#template option', { state: 'attached' });
    await page.selectOption('#template', '120252672230040312');
    await page.setInputFiles('#file', IMG);
    await page.waitForSelector('#chosen:not([hidden]) .ok-text');
    await page.fill('#name', 'N7 - Flow test image ad');
    await page.fill('#title', 'One system for the whole shop');
    await page.screenshot({ path: `${OUT}/flow-4-new-ad.png`, fullPage: true });
    await Promise.all([page.waitForURL('**/ad.html?id=**created=1**'), page.click('#create')]);
    await page.waitForSelector('#ad-status .pill');
    check('new image ad is created and opens off', (await page.textContent('#ad-status')).includes('Off'), await page.textContent('#ad-name'));
  }

  // 5. Approve Claude's on/off proposal from the Desk; decline the budget one.
  await page.goto(BASE + '/desk.html');
  await page.waitForSelector('#tasks .task, #tasks .empty');
  const approve = page.locator('.proposal', { hasText: 'Turn off N1' }).locator('[data-approve]');
  if (!(await approve.count())) {
    results.push('SKIP proposal steps — no pending test proposal (seed one through the agent API to rerun them)');
    await browser.close();
    console.log(results.join('\n'));
    console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
    return;
  }
  await approve.click();
  await page.waitForSelector('dialog.confirm');
  await page.screenshot({ path: `${OUT}/flow-5-approve.png` });
  await page.click('dialog.confirm #cd-ok');
  await page.waitForSelector('.proposal:has-text("Turn off N1") .pill.ok');
  check('approving applies the proposal', (await page.textContent('.proposal:has-text("Turn off N1")')).includes('Approved and applied'));
  await page.locator('.proposal', { hasText: 'Raise the campaign budget' }).locator('[data-decline]').click();
  await page.click('dialog.confirm #cd-ok');
  await page.waitForSelector('.proposal:has-text("Raise the campaign budget"):has-text("Declined")');
  check('declining records it', true);
  await page.screenshot({ path: `${OUT}/flow-6-desk.png`, fullPage: true });

  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('[data-toggle="ad:120252672230040312"]');
  check('N1 shows off on the Ads page after the approval', (await page.getAttribute('[data-toggle="ad:120252672230040312"]', 'aria-checked')) === 'false');
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.changes');
  check('Home lists the changes', (await page.textContent('.changes')).includes('Turned off ad'));

  await browser.close();
  console.log(results.join('\n'));
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})().catch((e) => { console.log(results.join('\n')); console.error(e); process.exit(1); });
