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
- **Previous / next** (the commit after the QA follow-ups): an ad, ad set or campaign opened from a list offers the
  one before and after it in that list, "‹ 3 of 14 ›" beside its name (`orderNav()` in `ui.js`; the list's order
  is kept per level in this browser tab when a link is followed). An ad keeps its tab while stepping.

### Insights and Creative (`e98a186`)
- **Results:** the totals the pickers control come first, the month's pace after; each count sits above its cost;
  a row of chips jumps to each of the eight sections; the change list shows its newest eight until asked.
- **Compare:** "Ask Claude which to keep" opens the question already written.
- **Gallery:** cost per lead at the same height on every card.
- **Tests:** an empty page has one button.
- The quick look closes with an X; the ad page has Its leads.

### Second round, from the leftovers (Eugene, same day: "what about left overs?")
- **Ads list:** the Ads / Ad sets / Campaigns switch sits in the toolbar next to the table it changes, and the
  toolbar keeps two fixed rows (what to show; then find, narrow, dates, columns). Campaign rows are two lines: the
  objective line is gone, and + New ad set shows on the row in hand.
- **Campaign and ad set headers:** the on/off switch and budget lead, as on the ad page. On phones Its leads, Results
  and Ask Claude go into More (`moreMenuHtml(first)`), so the header is two rows, not three.
- **Ad page:** the header keeps On/Off, Its leads, Compare and Polish; the two ways to copy ("Exact copy, switched
  off", "New ad starting from this"), Archive and Delete are in a More menu (`#cr-more`). The Polish button hides on
  the Polish tab. History has "This ad only" and starts with its newest 20.
- **⌘K:** opened empty it leads with things to do (Ask Claude, New ad, Suggestions waiting, Inbox: Needs action, Ads
  that need attention), then the places; once names are found, pages and actions keep to five rows.
- **Compare:** "+ Add an ad" lives in the table's corner, next to the columns and their Remove.
- **Reports:** with nobody to send to and nothing to decide, the review box is one line (Add a client, Add a note or
  preview the email) and the report starts under it.
- **Gallery on phones:** the three pickers share a row; on Gallery and Ideas the page's description gives way to
  the cards. **Research:** after Send to Claude the page shows Past research, where the report lands.
- **Your account:** Lead alerts and This device come before Appearance and Password (a forced first change of
  password still comes first).
- **Settings › Alerts:** the 26 rules sit under five headings (Review and delivery, Spend, Leads and what they
  cost, Changes made in Ads Manager, Tracking and connection; `RULE_GROUPS` in `settings.js`), snoozed alerts come
  above them, and Save stays in reach while the list scrolls.
- **Claude › By ad:** each ad shows its two newest runs and any run with a suggestion still waiting; earlier runs
  fold behind "N earlier" (the open state survives the page's polling).
- **Compare → Tests:** "Track as a test" (admins, two to four ads) opens New test with those ads as its sides
  (`/experiments.html#new=ad:<id>,ad:<id>`).
- **Polish tab:** Run sits in the panel's head, not under the eleven checks.

### Third round: one map (Eugene, same evening: "a lot of stuff in our app is all over and hard to navigate, remove clutter and organize all functionality")
The first two rounds kept the structure (seven sections, a second row of pills per section, a flat Settings list) and
polished it. That was the wrong level: twelve pages were still a click behind a section, Settings was sixteen
sections sorted by who they apply to rather than what they are for, and the sidebar's foot held five rows of chrome.
Eugene chose all three changes from previews.

- **The sidebar is the whole map.** Today, Inbox, Leads, Claude; then Ads (Campaigns and ads, Lead forms,
  Audiences), Creative (Gallery, Ideas, Research), Insights (Results, Compare, Tests, Reports). Every page is one
  click from anywhere, so wide screens have no pill row (phones, which have no sidebar, keep it). A group folds from
  its heading and stays folded; the group of the open page never does. In a short window only the list scrolls.
- **A quiet corner.** Claude's line and the spending limit are two slim rows instead of a card (the limit turns amber
  and speaks up past 80%). Under them Settings, then your name: Your account, All accounts, Keyboard shortcuts, Theme
  and Sign out open from it. With several ad accounts the switcher sits beside the logo in place of the console's name.
- **Settings by what you are doing.** An overview first, then Account, Leads, People, Connections, History
  (`js/setnav.js`). Sections that are one job are one page: Meta (connection + app), Email and Telegram, Preferences
  (automatic refresh + A/B tests on Meta). Team is one of its pages. The overview shows what is set on every page
  and counts what needs a look; on phones it is the menu and the sideways strip is gone. Whole-console settings are
  marked "Every account" only where there is more than one account.
- **Each thing counted once.** The Inbox badge no longer repeats the waiting leads (Leads badge) or, for admins,
  Claude's suggestions (Claude badge).
- **Team rows:** Edit stays; Reset password and Deactivate are behind the row's More button, so the table fits beside
  the Settings list and a red button no longer repeats down the page.

Decisions worth keeping: the group is still called Insights (a group named Results holding a page named Results reads
twice), the Ads page is "Campaigns and ads" in the sidebar only (its group is already called Ads), and Settings'
first page is "Targets and limits" because alerts and messages all over the console say "Settings → Targets".

## Left to pick from (not built)

1. **Builders:** "Who sees it" folded when copying an ad set. Left out on purpose: `qa/flows.cjs` fills those fields
   directly in dozens of steps, so folding them by default means rewriting a large part of the suite for a modest
   gain. Worth doing together with a QA helper that opens the fold.
2. ~~Settings on phones~~: done in the third round (the overview is the menu).
3. **Compare's picker:** ads with no spend folded under the ones worth comparing.
4. **Smaller:** one place for the date picker on every page; one class set for page headers; the wordings of links
   to leads ("Its leads" / "All leads" / "All in Leads"); Tests and Audiences filters in the address; deactivated
   teammates and closed accounts folded; Research's phone tab labels; the Gallery's sorting sentence and the
   Schedules explanation behind a disclosure.

## QA

The full `qa/run.sh` after the pass: every check passes except one, "on a phone a tap on a marked day shows its
changes", which also failed before any of these changes in the same setup and passes when run by itself. The setup
is the reason to distrust it: this round ran through a headless Chrome in Docker (Linux, software rendering), because
the session it was done in could not start a browser on the Mac. Run `sh qa/run.sh` once on the Mac's own Chrome
to settle it. New checks cover the sidebar's theme switch and order, the More sheet's groups, the folded phone Ads
list, an open Inbox item on a phone, the landing after a delete, the builders' breadcrumbs and previous / next.

The second round's first commit (`f83b557`) and everything after it were not put through the full suite: the run
that reached them stopped two thirds of the way on a real fault (the Reports box hid its numbers warning; fixed), and
the last batch was checked with 21 targeted browser checks of exactly what changed (all passing) plus a load of every
page at both sizes. `qa/flows.cjs` was updated for the ad page's More menu, but those steps have not run since. A full
`sh qa/run.sh` on the Mac is owed before relying on the suite again.

## Notes for whoever continues

- The phone Back arrow relies on `document.referrer` and a `sessionStorage` flag set by menu clicks; unverified in the
  installed app on a real iPhone and Android.
- `.main:has(.leads-layout.showing-detail)` and the Inbox equivalent need `:has()` (Safari 15.4+, Chrome 105+).
- The Inbox still counts each waiting lead in its badge (the grouping is on the page only); taking `new_lead` out of
  `need_unread` in `backend/inbox.py` would stop the double badge with Leads. Left as is: it changes what the badge
  means.
