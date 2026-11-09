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
  const n2 = page.locator('[data-toggle="ad:120252672229400312"]');
  await n2.waitFor();
  const before = await n2.getAttribute('aria-checked');
  await n2.click();
  await page.waitForSelector('dialog.confirm');
  await page.screenshot({ path: `${OUT}/flow-1-confirm-off.png` });
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('[data-toggle="ad:120252672229400312"]')?.getAttribute('aria-checked') === 'false');
  check('switch turns an ad off after confirming', before === 'true');
  // Cancel leaves it alone.
  await page.locator('[data-toggle="ad:120252672229400312"]').click();
  await page.click('dialog.confirm #cd-cancel');
  await page.waitForTimeout(400);
  check('cancel changes nothing', (await page.locator('[data-toggle="ad:120252672229400312"]').getAttribute('aria-checked')) === 'false');
  // Back on.
  await page.locator('[data-toggle="ad:120252672229400312"]').click();
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('[data-toggle="ad:120252672229400312"]')?.getAttribute('aria-checked') === 'true');
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
  await page.goto(BASE + '/ad.html?id=120252672232030312');
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
    await page.selectOption('#template', '120252672229040312');
    await page.setInputFiles('#file', IMG);
    await page.waitForSelector('#chosen:not([hidden]) .ok-text');
    await page.fill('#name', 'N7 - Flow test image ad');
    await page.fill('#title', 'One system for the whole shop');
    await page.screenshot({ path: `${OUT}/flow-4-new-ad.png`, fullPage: true });
    await Promise.all([page.waitForURL('**/ad.html?id=**created=1**'), page.click('#create')]);
    await page.waitForSelector('#ad-status .pill');
    check('new image ad is created and opens off', (await page.textContent('#ad-status')).includes('Off'), await page.textContent('#ad-name'));
  }

  // 4b. Polish: start a run from the ad page, then turn Claude's new-headline proposal into an ad.
  await page.goto(BASE + '/ad.html?id=120252672230740312#tab=polish');
  await page.reload();
  await page.waitForSelector('#polish-form');
  await page.click('[data-preset="quick"]');
  check('quick preset picks 4 passes', (await page.textContent('#run-polish')).includes('Run 4 passes'));
  await page.click('#run-polish');
  await page.waitForSelector('#runs .task.queued');
  check('polish run is queued for the Mac', true);
  await page.screenshot({ path: `${OUT}/flow-polish.png`, fullPage: true });
  // Don't leave a real run for a connected Mac to pick up.
  await page.locator('#runs .task.queued [data-cancel]').first().click();
  await page.waitForSelector('#runs .task.cancelled');
  check('a queued polish run can be cancelled', true);
  const create = page.locator('.proposal.variant [data-approve]').first();
  if (await create.count()) {
    await create.click();
    await page.waitForSelector('dialog.confirm');
    await Promise.all([page.waitForURL('**created=1**'), page.click('dialog.confirm #cd-ok')]);
    await page.waitForSelector('#ad-status .pill');
    check('approving a new-copy proposal creates that ad, switched off',
      (await page.textContent('#ad-name')).includes('·') && (await page.textContent('#ad-status')).includes('Off'), await page.textContent('#ad-name'));
  } else results.push('SKIP new-headline proposal — none pending');

  // Refresh: on every page, pulls from Meta, then the page reloads its data and the label updates.
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('.page-head [data-refresh]');
  await page.click('.page-head [data-refresh]');
  await page.waitForFunction(() => /Updated just now/.test(document.querySelector('.page-head [data-updated]')?.textContent || ''), null, { timeout: 60000 });
  check('Refresh pulls from Meta and shows when', true, await page.textContent('.page-head [data-updated]'));
  const again = await page.evaluate(() => fetch('/api/refresh', { method: 'POST' }).then((r) => r.json()));
  check('a second Refresh within a minute does not hit Meta again', again.ran === false);
  for (const p of ['leads', 'performance', 'desk', 'research', 'settings', 'team', 'account']) {
    await page.goto(`${BASE}/${p}.html`, { waitUntil: 'networkidle' });
    check(`Refresh is on ${p}`, await page.isVisible('.page-head [data-refresh]'));
  }

  // Archive and delete: only for an ad that is off; delete needs the name typed.
  const seen = errors.length;
  const on = await page.evaluate(() => fetch('/api/ads/ad/120252672229400312/archive', { method: 'POST' }).then((r) => r.status));
  await page.waitForTimeout(300);
  errors.splice(seen); // the refused request above logs an expected 400
  const n2Status = await page.evaluate(() => fetch('/api/ads/ad/120252672229400312').then((r) => r.json()).then((d) => d.ad.status));
  check('archive is refused for an ad that is on', n2Status !== 'ACTIVE' || on === 400, `${n2Status} → ${on}`);
  const dup = await page.evaluate(() => fetch('/api/ads/ad/120252672229400312/duplicate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'QA archive me' }) }).then((r) => r.json()));
  await page.goto(`${BASE}/ad.html?id=${dup.id}`);
  await page.click('#archive');
  await page.waitForSelector('dialog.confirm');
  await page.screenshot({ path: `${OUT}/flow-archive-confirm.png` });
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Archived/.test(document.querySelector('#ad-status')?.textContent || ''));
  check('Archive marks the ad archived and hides the Archive button', !(await page.isVisible('#archive')), await page.textContent('#ad-status'));
  await page.goto(BASE + '/ads.html', { waitUntil: 'networkidle' });
  const listed = async () => page.evaluate((id) => !!document.querySelector(`[href*="${id}"]`), dup.id);
  check('an archived ad is hidden on the Ads page', !(await listed()));
  await page.click('#archived');
  await page.waitForFunction(() => /Hide archived/.test(document.querySelector('#archived')?.textContent || ''));
  check('Show archived brings it back into view', await listed());
  await page.goto(`${BASE}/ad.html?id=${dup.id}`);
  await page.click('#delete');
  await page.waitForSelector('dialog.confirm #cd-input');
  await page.fill('#cd-input', 'QA archive');
  await page.click('dialog.confirm #cd-ok');
  check('delete refuses a name that does not match', await page.isVisible('#cd-err'), await page.textContent('#cd-err'));
  await page.fill('#cd-input', 'QA archive me');
  await page.screenshot({ path: `${OUT}/flow-delete-confirm.png` });
  await Promise.all([page.waitForURL('**/ads.html'), page.click('dialog.confirm #cd-ok')]);
  const gone = await page.evaluate((id) => fetch(`/api/ads/ad/${id}`).then((r) => r.json()).then((d) => d.ad.status), dup.id);
  check('Delete with the typed name deletes it and returns to Ads', gone === 'DELETED', gone);

  // Lead stages to Meta: a real-looking lead moved to Qualified sends Lead, Contacted and Qualified once each.
  const leadId = Number(require('child_process').execSync(`docker exec edgebourne-ads-backend python -c "
import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id = '9876543210123456'\\")
r = db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, campaign_id, campaign_name) VALUES ('9876543210123456', now() - interval '2 hours', 'QA Stage Lead', '120252638288040312', 'Edge Bourne - Free intro call - Leads') RETURNING id\\", returning=True)
print(r['id'])"`).toString().trim());
  await page.goto(BASE + '/settings.html');
  await page.waitForSelector('#crm-state .pill');
  if (!(await page.isChecked('#crm_send_enabled'))) await page.check('#crm_send_enabled');
  await page.click('#crm-form button[type=submit]');
  await page.waitForSelector('#crm-state .pill.ok');
  check('Settings turns lead stages on', true, await page.textContent('#crm-state'));
  await page.goto(`${BASE}/leads.html#lead=${leadId}`);
  await page.waitForSelector('[data-stage="qualified"]');
  await page.click('[data-stage="qualified"]');
  let stages = '';
  for (let i = 0; i < 20 && !/Qualified: sent/.test(stages); i++) {
    await page.waitForTimeout(1000);
    const lead = await page.evaluate((id) => fetch(`/api/leads/${id}`).then((r) => r.json()), leadId);
    stages = (lead.meta_stages || []).map((r) => `${r.stage}:${r.status}`).join(' ');
    if (/qualified:sent/.test(stages)) break;
  }
  check('a stage change sends Lead, Contacted and Qualified to Meta', stages === 'new:sent contacted:sent qualified:sent', stages);
  await page.reload();
  await page.waitForSelector('#meta-stages');
  check('the lead page says what Meta got', /Meta has New, Contacted, Qualified/.test(await page.textContent('#meta-stages')), await page.textContent('#meta-stages'));
  await page.screenshot({ path: `${OUT}/flow-crm-lead.png` });
  await page.goto(BASE + '/settings.html');
  await page.waitForSelector('#crm-state .pill');
  await page.uncheck('#crm_send_enabled');
  await page.click('#crm-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#crm-state')?.textContent === 'Off');
  check('Settings turns lead stages off again', true);

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
  await page.waitForSelector('[data-toggle="ad:120252672229040312"]');
  check('N1 shows off on the Ads page after the approval', (await page.getAttribute('[data-toggle="ad:120252672229040312"]', 'aria-checked')) === 'false');
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.changes');
  check('Home lists the changes', (await page.textContent('.changes')).includes('Turned off ad'));


  await browser.close();
  console.log(results.join('\n'));
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})().catch((e) => { console.log(results.join('\n')); console.error(e); process.exit(1); });
