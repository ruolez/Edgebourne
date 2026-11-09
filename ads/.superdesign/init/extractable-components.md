# Extractable components

## Rail (Sidebar)
- Source: `frontend/js/ui.js` (`boot()`), CSS `.rail`, `.nav`, `.brand`, `.rail-foot` in `frontend/css/app.css`
- Category: layout
- Description: Dark left sidebar with logo + "Edge Bourne Ads", nav links with icons (Home, Leads + new-count badge, Ads, Performance, Desk, Research, Team, Settings), account block, theme + sign-out buttons
- Extractable props: activeItem (string, default "home"), newLeads (number, default 0)
- Hardcoded: logo image, labels, SVG icons from ICONS, CSS

## PageHead
- Source: `.page-head` markup in each `frontend/*.html`
- Category: layout
- Description: Page title (h1, display font) with meta text and right-side actions
- Extractable props: title (string), meta (string)

## Panel
- Source: `.panel`, `.panel-head`, `.panel-body` in app.css
- Category: basic
- Description: White card with header (h2 + actions) and body

## Figures
- Source: `.figures`, `.figure`, `.figure.hero` in app.css; used by home.js and performance.js
- Category: basic
- Description: Row of KPI tiles (label, big value, sub line)

## Pill / Switch / Button
- Source: `.pill`, `.switch` (switchHtml in ui.js), `.btn` variants in app.css
- Category: basic
