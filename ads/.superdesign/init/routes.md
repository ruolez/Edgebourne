# Routes (static HTML pages served by nginx at ads.<domain>, JS module per page)

| Path | HTML | JS | What it renders |
|---|---|---|---|
| /home.html | frontend/home.html | js/home.js | Greeting + date; Needs attention list; figures row (spent today, yesterday, last 7 days cost per lead, ads on/off); grid: Newest leads, Claude panel (Mac status, Ask Claude, recent desk tasks), Recent changes |
| /leads.html | frontend/leads.html | js/leads.js | Inbox: status tabs with counts (Open/New/Contacted/Qualified/Won/Lost/All), search, Only mine; two panes: lead list (left) + lead detail (answers, ad, notes, stage, owner, call/email) |
| /ads.html | frontend/ads.html | js/ads.js | Campaign → ad set → ad cards with media thumbnails, on/off switches, budgets, filters, sort, cards/table toggle, sparklines |
| /ad.html?id= | frontend/ad.html | js/ad.js | Ad detail with tabs Overview (Meta previews iframes, results, words), Polish (audit passes, scorecard), Audience, Video, Comments, History |
| /new-ad.html | frontend/new-ad.html | js/new-ad.js | Form: starting ad, media upload/library, name/headline/text/CTA; creates the ad off |
| /performance.html | frontend/performance.html | js/performance.js | Range tabs 7/14/30, spending-limit meter, figures, spend/leads column charts, per-ad table, breakdowns |
| /desk.html | frontend/desk.html | js/desk.js | Ask Claude box with kinds, task cards with reports (markdown), proposals with approve/decline, Mac key |
| /research.html | frontend/research.html | js/research.js | Ads Library research requests and results |
| /team.html, /settings.html, /account.html, /login.html | … | … | Admin forms |
