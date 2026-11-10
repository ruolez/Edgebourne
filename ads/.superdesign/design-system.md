# Edge Bourne Ads console: design system

## Product
Private web console (desktop + phone) for a one-person consulting business owner (Eugene, not a developer) and possibly a teammate, to watch and manage Meta (Facebook/Instagram) lead ads. Jobs to be done:
1. See instantly whether anything needs attention (rejected ads, leads waiting, spend limit).
2. Work new leads fast: call/email, set stage (new → contacted → qualified → won / lost), notes.
3. See if ads are working: spend, leads, cost per lead, cost per qualified lead, per ad.
4. Control ads safely: turn on/off, change budget (always confirm current → new in dollars), preview ads, create new ads (created off).
5. Ask Claude (AI on his Mac) for reviews, polish audits, new versions; approve or decline its proposals.

Pages: Home (today overview), Leads (inbox), Ads (campaign → ad set → ad cards), Ad detail (tabs: Overview, Polish, Audience, Video, Comments, History), New ad, Performance (charts, tables), Desk (Ask Claude, tasks, proposals), Research, Team, Settings, Account, Login.

## Voice
Plain, calm, specific words. No jargon where a plain word works ("Turned off", "Cost per lead", "Needs attention"). Money always in dollars.

## Visual identity: "Signal" (chosen 2026-11-10, replaces Seal & ledger)
Source of truth: `.superdesign/redesign/a.css` (tokens, light + dark) and `base.css` (structure); mockups `a.html`. Graphite neutrals (#F6F6F4 canvas, #141619 ink), one signal green #16A34A = delivering/on air, warn #D99A0B (in review), bad #C8372D, violet #6A4FD8 = Claude only. Geist (UI) + Geist Mono (numbers), 13–13.5px dense tables, 46px rows, 32px controls, radius 6/8/10, borders-only depth (rgba hairlines), dark mode first-class. Signature: 14-day delivery track (one bar per day: green live, striped amber in review, red rejected, empty off) beside a dot + word status. Sidebar 232px, groups Work (Today, Inbox, Leads) / Run (Ads, Insights, Claude) / Settings; ⌘K jump field at top; selection → black floating bulk bar with creative thumbnails.

## Previous identity: "Seal & ledger" (2026-11-09 to 2026-11-10)
- Font: Plus Jakarta Sans only (variable 400-800), self-hosted. Titles 600-700 with -0.02em tracking; body 15-16px; tabular numbers everywhere money or counts appear.
- Page (paper) #F4F6F5; cards white with a layered hairline shadow (0 0 0 1px rgba(28,43,51,.06), 0 1px 2px -1px rgba(28,43,51,.08), 0 2px 6px rgba(28,43,51,.04)); inset fields #EBEFED.
- Ink #1C2B33 / #4B5A63 / #5F6E77; hairline rgba(28,43,51,.10).
- Brand + primary action: seal teal #0D7468 (hover #0A5C53, soft #E1F0EC). Focus ring teal 2px.
- Semantic: rust #B4412E (soft #F8E3DD, deep #8E2F20) = waiting too long / bad; amber deep #7A4E05 on #FAEFD8 = warning; pine #2F7D5B = good; violet #6B4FD8 on #EEEAFC = Claude only.
- Signature: the lead clock chip (clock icon + "47 h waiting"): teal under 5 min, amber 5-60 min, rust over 1 h.
- Desktop: light sidebar 248px on the page color with hairline divider, 44px nav items, active = teal on soft teal, spending-limit meter pinned at the bottom of the sidebar. Page header: date, h1, then Refresh (with "Updated X ago"), search, Ask Claude (violet outline), New ad (teal).
- Phone: sticky top bar (logo, page name, Refresh, Search, avatar), bottom tab bar (Today, Leads with count, Ads, Results, More), 48px buttons, cards stacked.
- A Refresh control is on every screen (desktop header, phone top bar) and shows when data was last updated.
- Radius: 8px controls, 12px chips/pills, 16px cards. No gradients, no ALL-CAPS labels, no colored side borders.
- Light and dark themes (dark to be derived: ink surfaces, same teal/rust/violet slightly lifted).
Design files: .superdesign/tmp/a-final-desktop.html, a-final-mobile.html.

## Usability requirements (the redesign goals)
- Readability: body 15–16px, labels never below 13px, strong contrast (WCAG AA), numbers in tabular figures.
- Big targets: buttons and nav items ≥ 44px tall on touch, ≥ 36px on desktop; generous spacing.
- Navigation: desktop = left sidebar (collapsible to icons); phone = bottom tab bar (Home, Leads, Ads, Results, More) with the new-leads badge, sticky page header with the main action.
- Status always = color + icon + word (never color alone).
- Every money move goes through a confirm dialog showing current → new in dollars.
- Light + dark, responsive from 360px phones to wide desktops; no horizontal scroll on phones (tables become stacked cards).
- Radius 10–14px cards, 8px controls; soft layered shadows only on raised surfaces (dialogs, popovers).
