# CL: the Claude page as a conversation (2026-11-14)

Eugene: "focus on the claude page and the whole user experience … modern, intuitive and comfortable … show previews of
images or videos or pages … remove any redundant repeated information". His two answers before the build: pages =
**pages Claude builds** and **what's already in the account**; his own files = **images and videos**.

## What was wrong (from the code and screenshots before the pass)

- The Mac's status in up to five places on one screen (sidebar, list header, list footer, reply box, inside a waiting
  message); a conversation's first question three times (header, bubble, list row); Clear, Cancel and the working timer
  two or three times each.
- Three bars above the chat (breadcrumbs, Conversations / By ad / Schedules, the conversation header), then a
  full-access line and a hint line around the reply box. Every answer said "Claude · took 6 min · Ran with the usual
  tools". On a phone the reply box with its two lines took a third of the screen.
- A message appeared only after the server answered; the view did not follow a new answer; a long run listed every step.
- Claude could show only JPG/PNG/WebP/MP4 it made, in a small grid with no larger view. No page, no ad or form from
  the account, no way to send it a file.

## Rule of the page: everything is said once

| Thing | Where it is said |
|---|---|
| Which conversation is open | The list beside it (wide screens); the header on phones. The `<h1>` stays for screen readers. |
| The Mac's status | The sidebar's status row, on every page. On the Claude page it is repeated only where it explains a wait: by the line in the list when something waits there, else under the reply box, and under a message that hasn't started. The Mac button by New conversation carries the light and opens the set-up dialog (`#mac` in the address opens it; the sidebar's row links there while the Mac can't work). |
| That a message waits | Under the message itself (`.cv-wait`: why, Run next, Cancel). No separate line above the reply box. |
| How an answer went | One quiet row under it (`.cv-meta`): when · how long · "N steps" (opens in place) · "Full access" only when it ran so, a note only when it was meant to and didn't · Copy · Remove. |
| Suggestions | The cards. The heading is the count; accepting always goes through the Accept sheet, which says what changes. |
| Full access | One control in the reply box (`#fa-bar`: "Read-only tools" / "Full access · until 9:40 PM" + Lock). The password dialog explains it. |

## Layout

- Wide: one bar. `renderSubnav()` moves Claude's views into `.topline` after the crumbs (`body[data-claude-views]`
  hides the last crumb); phones keep the pills under the top bar. List 300 px, chat column 760 px.
- List (`conversation.js listHtml`): the count to decide, then **Working now** / **In line** only while there is
  something, then the days. A row is its title and time; a second line only for a state (to decide, didn't finish,
  stopped, progress) or an origin nobody typed (Scheduled, Polish, Diagnosis). New answer = bold + green dot. A
  finished row's Clear takes the time's place on hover; phones clear from inside the conversation or a whole day.
- Turn: your bubble (sent files as tiles, "Only <campaign>" / "About: …" notes), then the answer with no label:
  summary, what it shows, chips for the ads it names, report, suggestions, the meta row. While it works: "Working
  0:42" and the last three steps (earlier ones fold).
- Reply box: attach · campaign (new only) · access · Send (an arrow; Stop while Claude works and the box is empty).
  A hint under it only when it changes what you'd do.
- Scroll: reading the end keeps following live steps and a finished answer is brought to its first line; scrolled up,
  you stay put and "New below" appears; "Latest" while the newest message is out of view. A sent message shows at
  once (`showSending`) and comes back into the box if the send fails.

## What a conversation can show and take

`desk_attachments` (migration 050): `kind` image | video | **page**, `source` claude | **user**, `task_id` NULL while a
person's file waits for its message. `desk_tasks.shows` = `[{type: ad|form, id, name, caption, placement}]`.

| What | How it gets there | How it is shown |
|---|---|---|
| Claude's picture / video | `desk attach <id> file` (as before) | `attach.js`: one large, two side by side, more as a grid; Upload as draft, Change it |
| **A page Claude built** | `desk attach <id> page.html`: `desk` puts the page's own pictures, fonts and stylesheets inside it (files of the request's folder only, ≤ 3 MB), leaves scripts, `<base>` and meta refresh out, sends `kind=page` | A small browser frame in the answer (`iframe sandbox=""` on `/api/desk/attachments/<id>/page`); Phone / Desktop widths in the viewer; Change it |
| **An ad from the account** | `desk show <id> --ad <id> [--placement feed\|reels\|stories] [--caption]` | `shows.js`: Meta's own preview, large, with placements, name, status, Open the ad. It is left out of the chips |
| **A lead form** | `desk show <id> --form <id>` | The phone sketch the form builder uses (`formsketch.js`), step by step |
| **Your files** | Reply box: the paperclip, paste, or drop on the conversation → `POST /api/desk/uploads` at once (`filebox.js`), ids go with the message (`files`) | Tiles in your message; the Mac gets them with `desk fetch <id>` into `reports/desk/inbox/task<id>/` |

Everything above opens in one viewer (`lightbox.js`): ← → through all the conversation shows, a filmstrip, zoom to
real size, Download, Change it and Upload as draft for Claude's own.

## Safety decisions

- A page is HTML somebody else's words may have reached. It is stored only when the Mac declares it (`kind=page`;
  `attachments.sniff` never says HTML), never served from the plain attachment address (that would be HTML on the
  console's own origin), and its own address answers with `attachments.PAGE_CSP`: `sandbox` (no origin, no scripts,
  no forms, no popups), `default-src 'none'`, inline styles and `data:` pictures only, `frame-ancestors 'self'`. nginx
  sends that one path without the console's "never in a frame" headers and the console's `frame-src` gains `'self'`
  for it. The frame's own navigations are held by the console's `frame-src`.
- `desk attach` never reads a file outside the request's own folder into a page (`page_part`: a page naming
  `../../.env` gets nothing), and only pictures, fonts and stylesheets.
- A person's file is typed from its bytes (JPG, PNG, WebP, MP4, MOV), size-capped like Claude's previews, tied to a
  message only by the person who added it, removed after a day if never sent. Claude's own previews stay JPG / PNG /
  WebP / MP4 (Meta's library).
- The Mac's inbox is emptied before every run (`bridge.empty_inbox`): the workspace is shared by every business. A run
  reaches only its own conversation's files, with its pass.
- `desk show` takes only an ad in the account's synced ads or a form on its Page.
- A helper before desk 3.2 leaves a message with files in line (`claim_skip`), and the page says to update
  (`bridge.can_show`).

## Tests

- Unit: `test_attachments_logic` (QuickTime, pages, file ids, the policy), `test_desk_view_logic` (shows, transcript
  files), `test_desk_logic` (the helper gate, reply files); bridge `PageHtmlTests`, `InboxTests`.
- Against the database: `dev/qa_desk_media.py` (17 checks: who may send, fetch, show and look).
- `qa/flows.cjs`: the Claude block follows the new markup, plus 12 checks under "The Claude page shows and takes
  media" (one bar, tiles, shown ad and form, the page's frame and policy, the viewer, sending a file, 44 px on a phone).
- `dev/seed_media.py`: one conversation that uses all of it, for screenshots and QA.

## Owed on real devices and real Meta

1. A full-access run that builds a page and attaches it (`desk attach page.html`): the page's pictures inside, under
   3 MB, readable at phone width.
2. `desk show --ad` with a real ad: Meta's preview frame loads inside the answer for Feed, Reels and Stories.
3. `desk show --form` with the real form: the sketch matches the form's questions.
4. A real clip from an iPhone (.mov) sent with a message: uploads, the Mac fetches it, `desk frames` reads it, a cut
   comes back attached. 60 MB is about half a minute of 1080p; larger clips need AirDrop to the Mac for now.
5. Paste a screenshot (⌘V) and drag a file in Safari and Chrome; the viewer's swipe on a phone.
6. The page frame in Safari (a sandboxed frame with the session cookie).
