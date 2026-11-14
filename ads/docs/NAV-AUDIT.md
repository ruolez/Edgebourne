# Ads Console: navigation and ease-of-use pass (2026-11-14)

Eugene, 2026-11-14: "the nav bar is not very comfortable to use… better organize it", then "go through the whole ads
console app and improve navigation, UI/UX design… ease of use, flow, intuitiveness".

This is the record of that pass: how the console was checked, what was found, what was built, and what is left to
pick from. It follows Phase 9 (`UX-AUDIT.md`); nothing decided there was reopened (Signal look, vanilla multi-page,
every feature stays, money confirmations untouched, "Got it…" for snooze, the phone tab order).

## How it was checked

1. A code read of the frame and every page for wayfinding: the map in `js/ui.js` (sidebar, breadcrumbs, section tabs,
   phone top bar, tab bar, More sheet), `js/palette.js`, every page header, every tab mechanism, dead ends.
2. Screenshots of 38 screens at 1440 px and 390 px (light), with a map of each screen's breadcrumbs, tabs, header
   buttons and height, reviewed in three parts: the daily loop (Today, Inbox, Leads, Claude, ⌘K, More, accounts),
   running ads (lists, campaign / ad set / ad pages, builders, forms, audiences), and Creative, Insights, Settings.
3. Each fix looked at again in the browser at both sizes, a load of every page for errors and sideways overflow,
   then the full `qa/run.sh`.

About 80 findings came back. The ones built are below; the rest are listed at the end, most valuable first.

## What was built

### The sidebar (`968fab4`)
Head (console, ad account with its initial, search), the nav (Work / Run, 36 px rows), one status card (Claude's line
and the spending limit), then one corner under a hairline: Settings, Theme, you, Sign out. The theme switch (Light /
Dark / Match my device) is in the sidebar and the phone's More sheet. Settings has a real gear (it was drawn like
Today's sun). 248 px wide; shorter windows tighten the rows so it fits without scrolling down to about 700 px.

### Getting around (`40dd20e`)
- **One map for every menu.** The phone's More sheet is built from `SECTIONS` / `SUBNAV`, grouped as the sidebar is:
  Claude, then Creative, Insights, More in Ads, Settings, You. Lead forms, Audiences, Team and All accounts were
  missing from it.
- **A real Back on phones.** The installed app has no browser Back. A top page reached by drilling in (Its leads,
  Results from a campaign, Compare from an ad) now shows the arrow and it goes back where you were; moving by the
  menus shows none (`cameFrom()` / `viaNav()` in `ui.js`).
- **Honest breadcrumbs.** A section's name above its own first page (Insights / Results) is plain text, not a link
  to the page you are on. The phone's title is a title; only the logo goes to Today. Claude's three views name
  themselves. The builders' trails start at the section they were opened from and name the campaign, ad set or ad.
- **Section pages are pills**, so they stop reading as a second row of the page's own tabs (Research).
- **Section tabs reopen each page as it was last filtered** (it was only Insights).
- **Messages survive a page move** (`toastNext()`): deleted, test saved, "that page is for admins". A deleted ad
  lands on its ad set.
- **Links that open the thing:** `/forms.html#new`, `/experiments.html#new`, `/team.html#new`; the ad page's tabs
  follow a `#tab=` link while it is open; Today's Claude buttons open the suggestions or a new question.
- **⌘K:** New test, Add teammate, Ads Manager drafts, Gallery: Top, Leads: No next step / Due today.
- **One name per thing:** "New lead form" everywhere; ads named as trial copies are "QA copies", so "Tests" means
  A/B tests; "Compare"; "New test".
- **Jumps:** `g r` Results (`g n` still works), `g f` Lead forms, `g y` Your account, `g o` All accounts; the sidebar
  shows each letter as its link's tip.
- Empty states name the next step; the hidden "‹ Ads" links are gone; the sidebar's spending limit opens Settings,
  where it is changed.

### The daily loop (`d630e9e`)
- **Leads, wide:** the list keeps its place and scrolls by itself; a lead picked far down opens from its name. The
  phone-only back buttons no longer show on wide screens (Inbox too).
- **Leads, phone:** an open lead is the whole screen and starts at its top, and the list returns where it was.
  The less-used filters fold behind "Filters · n on": six leads on the first screen, not three.
- **A lead's answers** come right after the ways to reach them.
- **Inbox, Needs action:** what only the Inbox shows comes first; four or more waiting leads follow as one group
  with Call them and Show all. On phones an open item hides the list's chrome.
- **Today:** the mail button opens the console's email form (the lead moves to Contacted), "N more leads waiting"
  opens Leads on New, and the Money card carries the spending limit on phones.
- **Claude's list** starts with what waits for a decision.
- **More sheet:** ends with Theme, not Sign out, and ignores taps in the first moment after it opens.
- **Phones:** a heading that only repeats the top bar's title is kept for screen readers only.

### Running ads (`dc8ce2a`)
- **Campaign and ad set pages:** figures, then the list of what is inside (with the dates that drive the page), then
  the charts. The list used to start below the first screen. History shows its newest 15 until asked.
- **Tables:** Spent, Leads, Cost per lead, vs before first; a Budget column of dashes is left out; rows that open
  the quick look show a pointer.
- **Phone Ads list:** three key figures (All figures shows the rest) and "Dates, sort, filters" behind one button:
  the first ad is on the first screen instead of 1.3 screens down.
- **Phones:** an ad says which ad set and campaign it is in; a waiting suggestion comes before the tall preview.

### Insights and Creative (`e98a186`)
- **Results:** the totals the pickers control come first, the month's pace after; each count sits above its cost;
  a row of chips jumps to each of the eight sections; the change list shows its newest eight until asked.
- **Compare:** "Ask Claude which to keep" opens the question already written.
- **Gallery:** cost per lead at the same height on every card.
- **Tests:** an empty page has one button.
- The quick look closes with an X; the ad page has Its leads.

## Left to pick from (not built)

Most valuable first. Each is a contained piece of work.

1. **Previous / next ad** on the ad, ad set and campaign pages (`‹ 3 of 14 ›` from the list you came from).
2. **Ads list:** the Ads / Ad sets / Campaigns switch inside the toolbar, next to the table it changes, with the
   toolbar in two fixed rows (it reshuffles per level today).
3. **Phone campaign / ad set header:** eight controls in three rows with the On switch last; switch and budget
   first, Its leads / Results / Ask Claude into More.
4. **Settings on phones:** sixteen sections in a sideways strip; a section picker instead. **Alerts:** 26 rules in
   one list with Save at the end; group headings and a Save that stays in reach.
5. **⌘K:** opened empty it repeats the sidebar; lead with actions, and stop ten page rows going ahead of the
   campaign or lead that was typed.
6. **Ad page:** the header's Polish button only switches tab (Run sits under eleven cards); one Copy menu instead of
   Duplicate + New ad from this; Archive / Delete into the More menu like campaign pages; History filtered to
   "This ad".
7. **Reports:** the send-review box fills the first screen even with no clients to send to.
8. **Compare:** Add an ad next to the columns; "Track as a test" from the verdict; ads with no spend folded in the
   picker.
9. **Gallery / Research on phones:** filters on one row, the sorting sentence behind a disclosure; Research lands on
   Past research after Send to Claude.
10. **Claude By ad:** six screens with nothing folded; a filter, two newest runs per ad, the rest folded.
11. **Builders:** "Who sees it" folded when copying an ad set.
12. **Your account:** lead alerts and this device before the password form.
13. **Smaller:** one place for the date picker on every page; one class set for page headers; the wordings of links
    to leads ("Its leads" / "All leads"); Tests and Audiences filters in the address; Team and closed accounts
    folded when inactive; campaign rows on one line.

## Notes for whoever continues

- The phone Back arrow relies on `document.referrer` and a `sessionStorage` flag set by menu clicks; unverified in the
  installed app on a real iPhone and Android.
- `.main:has(.leads-layout.showing-detail)` and the Inbox equivalent need `:has()` (Safari 15.4+, Chrome 105+).
- The Inbox still counts each waiting lead in its badge (the grouping is on the page only); taking `new_lead` out of
  `need_unread` in `backend/inbox.py` would stop the double badge with Leads. Left as is: it changes what the badge
  means.
