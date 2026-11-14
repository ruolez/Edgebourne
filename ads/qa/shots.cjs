// Local design review: screenshots of each screen in light and dark.
// AS=client node qa/shots.cjs <dir>: the same as a read-only client of Edge Bourne (files named client-…), only the
// screens a client opens; a QA client user is made for the run and switched off after it.
// ONLY=am-link node qa/shots.cjs <dir>: only Settings → Ads Manager link (AM-A) connected, through Claude, waiting for the Mac and not connected.
// ONLY=drafts node qa/shots.cjs <dir>: only the drafts from Ads Manager (AM-B): Ads → Campaigns with the panel, the Drafts view
// (open, finished and staged-edit drafts) and New campaign filled in from a draft.
// ONLY=audiences node qa/shots.cjs <dir>: only AM-D: Ads → Audiences, the New audience dialog (each step: website and lookalike
// details), the pickers in New ad set and in an ad set's Edit (nothing is made).
// ONLY=edit node qa/shots.cjs <dir>: only AM-C: the Edit panel of the ad set (folded, then every section open), the review
// with a money question (the campaign's spending cap removed), the copy dialog and the delete dialog.
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
  // FU-D: a conversation that ran with full access and came back with an image and a video preview.
  const sh = (cmd, input) => require('child_process').execSync(cmd, input ? { input } : {}).toString();
  sh(`docker cp ${__dirname}/../dev/media/preview.png edgebourne-ads-backend:/tmp/qa-preview.png && docker cp ${__dirname}/../dev/media/preview.mp4 edgebourne-ads-backend:/tmp/qa-preview.mp4`);
  const fudTask = Number(sh('docker exec -i -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -', `import hashlib, account_ctx, attachments, db
with account_ctx.use(1):
    t = db.execute("""INSERT INTO desk_tasks (kind, prompt, status, summary, created_by, claimed_at, finished_at, access)
                      VALUES ('creative', 'Shots FU-D: design a 4:5 static for N2 with a bigger headline and show me a preview', 'done',
                              'Two previews: the 4:5 static and a 9:16 motion cut. Tap Upload as draft to make one an ad (switched off), or Change it.',
                              1, now() - interval '6 minutes', now(), 'full') RETURNING id""", returning=True)["id"]
    db.execute("INSERT INTO desk_reports (task_id, title, body) VALUES (%s, 'Previews', 'Bigger headline (64 px), same layout and colours.')", (t,))
    for path, name, cap in (('/tmp/qa-preview.png', 'n2-static.png', '4:5 static, version A'), ('/tmp/qa-preview.mp4', 'n2-reel.mp4', '9:16 motion, version A')):
        data = open(path, 'rb').read()
        mime = attachments.sniff(data[:attachments.HEAD])
        m = attachments.measure(mime, data)
        db.execute("""INSERT INTO desk_attachments (task_id, kind, mime, name, caption, size_bytes, sha256, width, height, duration_ms, body)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                   (t, attachments.MIMES[mime], mime, name, cap, len(data), hashlib.sha256(data).hexdigest(), m['width'], m['height'], m['duration_ms'], data))
print(t)
`).trim().split('\n').pop());
  const asClient = process.env.AS === 'client';
  const login = asClient ? ['qa-shots-client@example.com', 'shots-client-123'] : ['eugene@edgebourne.com', 'localdev-pass-123'];
  const tag0 = asClient ? 'client-' : '';
  if (asClient) {
    sh('docker exec -i -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -', `import db
from werkzeug.security import generate_password_hash as h
db.execute("""INSERT INTO users (email, name, password_hash, role, account_id) VALUES (%s, 'Shots client', %s, 'client', 1)
              ON CONFLICT (email) DO UPDATE SET is_active = TRUE, password_hash = EXCLUDED.password_hash, role = 'client', account_id = 1, must_change_password = FALSE""",
           ('${login[0]}', h('${login[1]}')))
`);
  }
  const CLIENT_PAGES = ['home', 'inbox', 'ads', 'campaign.html?id=120252638288040312', 'adset.html?id=120252672227950312', 'compare.html#pick',
    'ad.html?id=120252672230740312', 'ad.html?id=120252672230740312#tab=audience', 'ad.html?id=120252672230740312#tab=video',
    'ad.html?id=120252672230740312#tab=history', 'gallery', 'ideas', 'performance', 'report', 'account', 'leads.html?due=today', 'performance.html?range=today'];
  const OWNER_PAGES = ['home', 'inbox', 'ads', 'ads.html?level=campaign', 'campaign.html?id=120252638288040312', 'adset.html?id=120252672227950312', 'compare.html?ids=120252672232030312,120252672233160312,120252672230740312', 'compare.html#pick', 'ad.html?id=120252672230740312', 'ad.html?id=120252672230740312#tab=polish', 'ad.html?id=120252672230740312#tab=audience', 'ad.html?id=120252672230740312#tab=video', 'ad.html?id=120252672230740312#tab=comments', 'ad.html?id=120252672230740312#tab=history', 'ads.html?level=adset', 'new-ad', 'new-adset.html?campaign=120252638288040312', 'gallery', 'gallery.html?view=launched', 'ideas', 'research', 'research.html#tab=search', 'research.html#tab=watched', 'research.html#tab=past', 'audiences', 'desk', 'desk.html#ads', 'desk.html#schedules', 'performance', 'experiments', 'report', 'forms', 'new-campaign', 'team', 'settings', 'account', 'accounts', 'offline', 'missing-page.html',
        'inbox.html?box=fyi', 'inbox.html?box=all', 'gallery.html?view=tired', 'leads.html?due=today',
        // FU-C: today so far (Results and Ads on Today, the ad page's daily charts with today's bar).
        'performance.html?range=today', 'ads.html?range=today', 'ad.html?id=120252672232030312&range=7',
        ...['targets', 'alerts', 'reports-panel', 'replies', 'lead-quality', 'tracking', 'am-link', 'crm', 'ab', 'activity-panel', 'meta-app', 'auto', 'telegram', 'email', 'accounts-panel'].map((s) => `settings.html#${s}`)];
  const onlyAm = process.env.ONLY === 'am-link';
  const onlyDrafts = process.env.ONLY === 'drafts';
  const onlyEdit = process.env.ONLY === 'edit';
  const onlyAud = process.env.ONLY === 'audiences';
  const fakeGet = (path) => sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001${path}').read().decode())"`);
  // AM-C: the Edit panel, the review with a money line, the copy dialog and the delete dialog (nothing is saved).
  const editShots = async (page, tag, scheme) => {
    const C = '120252638288040312', S = '120252672227950312';
    await page.goto(`${BASE}/adset.html?id=${S}`);
    await page.waitForSelector('#ed-open');
    await page.click('#ed-open');
    await page.waitForSelector('dialog.ed-panel .ed-sec');
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/edit-adset-${tag}-${scheme}.png` });
    await page.evaluate(() => {
      document.querySelectorAll('dialog.ed-panel details.ed-sec').forEach((d) => { d.open = true; });
      const dlg = document.querySelector('dialog.ed-panel');
      dlg.style.height = 'auto'; dlg.style.maxHeight = 'none'; dlg.style.position = 'absolute';
      dlg.querySelector('.ed-secs').style.overflow = 'visible';
    });
    await page.waitForTimeout(300);
    await page.locator('dialog.ed-panel').screenshot({ path: `${OUT}/edit-adset-open-${tag}-${scheme}.png` });
    await page.keyboard.press('Escape');
    fakeGet(`/fake/_outside?id=${C}&spend_cap=50000`);
    await page.goto(`${BASE}/campaign.html?id=${C}`);
    await page.waitForSelector('#ed-open');
    await page.click('#ed-open');
    await page.waitForSelector('dialog.ed-panel #ed-sec-cap');
    await page.click('#ed-sec-cap summary');
    await page.check('#ed-cap-none');
    await page.click('#ed-save');
    await page.waitForSelector('dialog.ed-review [data-ed-q]');
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}/edit-review-${tag}-${scheme}.png` });
    await page.click('dialog.ed-review #cd-cancel');
    await page.keyboard.press('Escape');
    fakeGet(`/fake/_outside?id=${C}&clear=spend_cap`);
    await page.goto(`${BASE}/campaign.html?id=${C}`);
    await page.waitForSelector('#ed-more');
    await page.click('#ed-more summary');
    await page.click('#cp-open');
    await page.waitForSelector('dialog.cp-dialog #cp-go');
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}/copy-dialog-${tag}-${scheme}.png` });
    await page.click('dialog.cp-dialog #cp-cancel');
    await page.goto(`${BASE}/adset.html?id=${S}`);
    await page.waitForSelector('#ed-more');
    await page.click('#ed-more summary');
    await page.screenshot({ path: `${OUT}/edit-more-${tag}-${scheme}.png` });
    await page.click('#ed-delete');
    await page.waitForSelector('dialog.ed-del-first');
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}/delete-dialog-${tag}-${scheme}.png` });
    await page.keyboard.press('Escape');
  };
  // AM-D: the audiences list, the three steps of New audience (website, then a lookalike's details), the pickers (nothing is made).
  const audienceShots = async (page, tag, scheme) => {
    await page.goto(`${BASE}/audiences.html`);
    await page.waitForSelector('#aud-list table');
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/audiences-${tag}-${scheme}.png`, fullPage: true });
    await page.click('#aud-new');
    await page.waitForSelector('dialog.aud-dialog [data-aud-k]');
    await page.click('[data-aud-k="website"]');
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}/aud-new-1-${tag}-${scheme}.png` });
    await page.click('#aud-next');
    await page.waitForSelector('#aud-days');
    await page.screenshot({ path: `${OUT}/aud-new-2-${tag}-${scheme}.png` });
    await page.click('#aud-next');
    await page.waitForSelector('#aud-name');
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}/aud-new-3-${tag}-${scheme}.png` });
    await page.click('#aud-back');
    await page.click('#aud-back');
    await page.click('[data-aud-k="lookalike"]');
    await page.click('#aud-next');
    await page.waitForSelector('#aud-origin');
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}/aud-new-look-${tag}-${scheme}.png` });
    await page.keyboard.press('Escape');
    await page.goto(`${BASE}/new-adset.html?campaign=120252638288040312`);
    await page.waitForSelector('#aud-inc-chips [data-aud-chip]');
    await page.click('#aud-exc-q');
    await page.waitForTimeout(300);
    await page.locator('#audiences-field').scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${OUT}/aud-pick-newset-${tag}-${scheme}.png` });
    await page.goto(`${BASE}/adset.html?id=120252672227950312`);
    await page.waitForSelector('#ed-open');
    await page.click('#ed-open');
    await page.waitForSelector('dialog.ed-panel #ed-sec-who');
    await page.click('#ed-sec-who > summary');
    await page.locator('#ed-aud').scrollIntoViewIfNeeded();
    await page.click('#ed-aud-inc-q');
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/aud-pick-edit-${tag}-${scheme}.png` });
    await page.keyboard.press('Escape');
  };
  // AM-B: the fake's drafts stored for account 1 as a link read 12 minutes ago would (kept as they are when QA left some).
  if (!asClient) sh('docker exec -i -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -', `import json, urllib.request, datetime as dt, account_ctx, am_drafts, db, drafts_api
with account_ctx.use(1):
    raw = json.loads(urllib.request.urlopen('http://fake-meta:5001/fake/_mcp_drafts').read())
    run = db.execute("""INSERT INTO am_link_runs (account_id, pass_hash, ad_account_id, kinds, mode, status, created_at, finished_at)
                        VALUES (1, 'shots-am-drafts', '1025971549903293', '{drafts}', 'direct', 'done', now() - interval '12 minutes', now() - interval '12 minutes')
                        ON CONFLICT (pass_hash) DO UPDATE SET created_at = EXCLUDED.created_at RETURNING id, created_at""", returning=True)
    at = run['created_at']
    n = drafts_api.store(run, am_drafts.normalize(raw), True, at)
    db.execute("""INSERT INTO am_snapshots (kind, scope, data, fetched_at, run_id, via) VALUES ('drafts', '', %s, %s, %s, 'direct')
                  ON CONFLICT (account_id, kind, scope) DO UPDATE SET data = EXCLUDED.data, fetched_at = EXCLUDED.fetched_at, run_id = EXCLUDED.run_id""",
               (json.dumps({'drafts': n, 'complete': True}), at, run['id']))
`);
  const DRAFT_PAGES = ['ads.html?level=campaign', 'ads.html?level=campaign&view=drafts', 'new-campaign.html?draft=120252756936450312', 'new-adset.html?draft=120252756936460030'];
  // AM-A: the link in three states for its shots, with reads from 12 minutes ago (put back as it was afterwards).
  const psql = (q) => sh(`docker exec edgebourne-postgres psql -U edgebourne -d ebads -tAc "${q}"`).trim();
  const amWas = psql('SELECT row_to_json(l) FROM am_link l');
  const amState = (state) => psql(`UPDATE am_link SET state = '${state}', connected_as = ${state === 'connected' ? "'Eugene Ramirez'" : 'NULL'},
    client_kind = ${state === 'connected' ? "'dcr'" : state === 'fallback' ? "'claude'" : 'NULL'}, last_ok_at = ${state === 'not_connected' ? 'NULL' : "now() - interval '12 minutes'"},
    fallback_reason = ${state === 'fallback' ? "'Meta didn''t accept the Mac''s helper as a client (redirect_uris are not registered).'" : 'NULL'}, last_error = NULL,
    scope = ${state === 'connected' ? "'ads_read'" : 'NULL'}, connect_requested_at = ${state === 'connecting' ? 'now()' : 'NULL'} WHERE id = 1`);
  psql(`DELETE FROM am_link_runs WHERE pass_hash LIKE 'shots-am-%'; INSERT INTO am_link_runs (account_id, pass_hash, ad_account_id, kinds, mode, status, pushed, created_at, finished_at)
    VALUES (1, 'shots-am-1', '1025971549903293', '{ad_errors,benchmarks}', 'direct', 'done', jsonb_build_object('ad_errors', 1, 'benchmarks', 2), now() - interval '12 minutes', now() - interval '12 minutes')`);
  const amKinds = ['ad_errors', 'benchmarks', 'peers', 'auction_ranking', 'anomalies', 'trend', 'dataset_quality', 'advertiser_context'];
  const amSnapsBefore = psql("SELECT count(*) FROM am_snapshots WHERE account_id = 1 AND scope = '' AND kind <> 'drafts'");
  if (amSnapsBefore === '0') psql(`INSERT INTO am_snapshots (account_id, kind, scope, data, fetched_at, via) SELECT 1, k, '', jsonb_build_object('rows', jsonb_build_array()), now() - interval '12 minutes', 'direct' FROM unnest('{${amKinds.join(',')}}'::text[]) k`);
  const fullAccess = (on) => sh(`docker exec edgebourne-postgres psql -U edgebourne -d ebads -tAc "UPDATE user_sessions SET full_until = ${on ? "now() + interval '8 hours'" : 'NULL'} WHERE user_id = 1"`);
  for (const scheme of ['light', 'dark']) {
    for (const [vw, vh, tag] of [[1440, 900, 'desk'], [390, 844, 'phone']]) {
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, colorScheme: scheme, deviceScaleFactor: 2 });
      const page = await ctx.newPage();
      // The missing page's own 404 is the point of that shot, not an error.
      page.on('console', (m) => { if (m.type() === 'error' && !(/status of 404/.test(m.text()) && /missing-page/.test(page.url()))) errors.push(`${tag} ${m.text()}`); });
      page.on('pageerror', (e) => errors.push(`${tag} ${e.message}`));
      await page.goto(BASE + '/login.html');
      if (!asClient) await page.screenshot({ path: `${OUT}/login-${tag}-${scheme}.png` });
      await page.fill('#email', login[0]);
      await page.fill('#password', login[1]);
      await Promise.all([page.waitForURL('**/home.html**'), page.click('button[type=submit]')]);
      await page.goto(BASE + '/leads.html');
      await page.waitForSelector('.lead-row');
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/${tag0}leads-${tag}-${scheme}.png` });
      if (tag === 'phone') {
        await page.click('.lead-row');
        await page.waitForSelector('#stages');
        await page.screenshot({ path: `${OUT}/${tag0}lead-detail-${tag}-${scheme}.png`, fullPage: true });
      }
      if (onlyEdit) { await editShots(page, tag, scheme); await ctx.close(); continue; }
      if (onlyAud) { await audienceShots(page, tag, scheme); await ctx.close(); continue; }
      for (const p of (asClient ? CLIENT_PAGES : onlyAm ? [] : onlyDrafts ? DRAFT_PAGES : [...OWNER_PAGES, ...DRAFT_PAGES.slice(1)])) {
        await page.goto(p.includes('.html') ? `${BASE}/${p}` : `${BASE}/${p}.html`);
        if (p.includes('#')) await page.reload();
        await page.waitForTimeout(600);
        await page.waitForTimeout(p.includes('#') ? 900 : 0);
        const variant = [...p.matchAll(/(?:#tab=|#|level=|view=|box=|due=|range=|draft=)([\w-]+)/g)].map((m) => m[1]).join('-');
        await page.screenshot({ path: `${OUT}/${tag0}${p.split('.')[0]}${variant ? '-' + variant : ''}-${tag}-${scheme}.png`, fullPage: true });
      }
      if (asClient) { await ctx.close(); continue; }
      if (onlyDrafts) { await ctx.close(); continue; }
      for (const state of ['connected', 'fallback', 'connecting', 'not_connected']) {
        amState(state);
        await page.goto(`${BASE}/settings.html#am-link`);
        await page.reload();
        await page.waitForSelector('#am-link:not([hidden]) #am-acct');
        if (state === 'fallback') await page.click('#am-why summary');
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/settings-am-${state}-${tag}-${scheme}.png`, fullPage: true });
      }
      if (onlyAm) { await ctx.close(); continue; }
      await editShots(page, tag, scheme);
      await audienceShots(page, tag, scheme);
      // FU-D: full access on, and a conversation with an image and a video preview.
      fullAccess(true);
      await page.goto(`${BASE}/desk.html#new`);
      await page.reload();
      await page.waitForSelector('#fa-bar.fa-on');
      await page.screenshot({ path: `${OUT}/fud-new-${tag}-${scheme}.png` });
      await page.goto(`${BASE}/desk.html#r/${fudTask}`);
      await page.reload();
      await page.waitForSelector('.att-list video');
      await page.waitForTimeout(900);
      await page.screenshot({ path: `${OUT}/fud-conv-${tag}-${scheme}.png`, fullPage: true });
      fullAccess(false);
      // FU-A: the ad account picker (Settings → Accounts → Add ad account).
      await page.goto(`${BASE}/settings.html#accounts-panel`);
      await page.reload();
      await page.waitForSelector('#acp-open');
      await page.click('#acp-open');
      await page.waitForSelector('dialog.acp .acp-row, dialog.acp #acp-none');
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/acp-picker-${tag}-${scheme}.png` });
      await page.keyboard.press('Escape');
      // FU-finish: the Gallery's tray with one card picked (Make more like this, Compare waiting), then two picked
      // and Make more like these (the brief to edit before it goes).
      await page.goto(`${BASE}/gallery.html?range=30`);
      await page.waitForSelector('.gal-card [data-pick]');
      await page.locator('.gal-card [data-pick]').first().check();
      await page.waitForSelector('#gal-tray [data-tray="more"]');
      await page.screenshot({ path: `${OUT}/gallery-picked-one-${tag}-${scheme}.png` });
      await page.keyboard.press('Escape');
      await page.waitForSelector('#gal-tray .bk', { state: 'detached' });
      for (const box of (await page.locator('.gal-card [data-pick]').all()).slice(0, 2)) await box.check();
      await page.waitForSelector('#gal-tray [data-tray="more"]');
      await page.screenshot({ path: `${OUT}/gallery-picked-${tag}-${scheme}.png` });
      await page.click('#gal-tray [data-tray="more"]');
      await page.waitForSelector('dialog.confirm.wide #cd-input');
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/gallery-more-${tag}-${scheme}.png` });
      await page.click('#cd-cancel');
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
  if (!asClient) {
    const was = JSON.parse(amWas);
    psql(`UPDATE am_link SET state = '${was.state}', connected_as = ${was.connected_as ? `'${was.connected_as.replace(/'/g, "''")}'` : 'NULL'}, client_kind = ${was.client_kind ? `'${was.client_kind}'` : 'NULL'},
      last_ok_at = ${was.last_ok_at ? `'${was.last_ok_at}'` : 'NULL'}, fallback_reason = NULL WHERE id = 1; DELETE FROM am_link_runs WHERE pass_hash LIKE 'shots-am-%'`);
    if (amSnapsBefore === '0') psql("DELETE FROM am_snapshots WHERE account_id = 1 AND scope = '' AND run_id IS NULL");
  }
  if (asClient) sh(`docker exec edgebourne-postgres psql -U edgebourne -d ebads -tAc "UPDATE users SET is_active = FALSE WHERE email = '${login[0]}'"`);
  sh(`docker exec edgebourne-postgres psql -U edgebourne -d ebads -tAc "DELETE FROM desk_reports WHERE task_id = ${fudTask}; DELETE FROM desk_tasks WHERE id = ${fudTask}"`);
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})();
