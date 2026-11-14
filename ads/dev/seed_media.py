"""Local development only: on top of dev/seed_board.py, one conversation that uses everything the Claude page can
show and take: files sent with a message, Claude's pictures and video, a page it built, an ad and a lead form from
the account shown large. Never run on the server. Copy dev/media/preview.png and preview.mp4 to /tmp/qa-preview.*
in the backend container first (qa/shots.cjs does). Prints the conversation's id."""
import base64
import hashlib
import json
import sys

sys.path.insert(0, "/app")
import attachments  # noqa: E402
import db  # noqa: E402

N3, FORM = "120252672230740312", "1132280359202136"
PNG = open("/tmp/qa-preview.png", "rb").read()
MP4 = open("/tmp/qa-preview.mp4", "rb").read()
PAGE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Landing page draft</title>
<style>
  body {{ margin: 0; font: 16px/1.5 -apple-system, "Segoe UI", sans-serif; color: #14201c; background: #f4f1ea; }}
  header {{ padding: 40px 24px 32px; background: #173f38; color: #fff; }}
  h1 {{ margin: 0 0 10px; font-size: 34px; line-height: 1.1; letter-spacing: -.02em; }}
  h1 em {{ font-style: normal; color: #f2b53a; }}
  .cta {{ display: inline-block; margin-top: 18px; padding: 12px 20px; border-radius: 8px; background: #f2b53a; color: #14201c; font-weight: 700; text-decoration: none; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 28px 24px 48px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }}
  .card {{ padding: 16px; border-radius: 10px; background: #fff; box-shadow: 0 0 0 1px rgba(20, 32, 28, .1); }}
  .card b {{ display: block; margin-bottom: 4px; }}
  img {{ display: block; width: 100%; max-width: 360px; margin: 24px auto 0; border-radius: 10px; }}
</style></head>
<body>
<header><h1>Your customers could <em>order without calling.</em></h1><p>We build your own ordering portal. You own it.</p><a class="cta" href="#">Book a free intro call</a></header>
<main>
  <div class="cards">
    <div class="card"><b>Orders any time</b>Customers place and track orders on their phone, 24/7.</div>
    <div class="card"><b>One simple system</b>No more notepads, voicemail and spreadsheets by hand.</div>
    <div class="card"><b>AI is optional</b>It can read email orders in for you, if you want it.</div>
  </div>
  <img alt="The ad this page continues" src="data:image/png;base64,{base64.b64encode(PNG).decode()}">
</main>
</body></html>""".encode()


def attach(task_id, data, name, caption=None, source="claude", mime=None):
    mime = mime or attachments.sniff(data[:attachments.HEAD])
    m = attachments.measure(mime, data)
    db.execute("""INSERT INTO desk_attachments (task_id, kind, mime, name, caption, size_bytes, sha256, width, height, duration_ms, body, source, created_by)
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
               (task_id, attachments.MIMES[mime], mime, name, caption, len(data), hashlib.sha256(data).hexdigest(), m["width"], m["height"],
                m["duration_ms"], data, source, 1 if source == "user" else None))


def task(prompt, summary, mins_ago, thread=None, shows=None, steps=None):
    return db.execute(
        """INSERT INTO desk_tasks (kind, prompt, status, summary, created_by, created_at, claimed_at, finished_at, access, thread_id, options, shows, steps, seen_at)
           VALUES ('creative', %s, 'done', %s, 1, now() - %s * interval '1 minute', now() - %s * interval '1 minute',
                   now() - (%s - 2) * interval '1 minute', 'full', %s, %s, %s, %s, now()) RETURNING id""",
        (prompt, summary, mins_ago, mins_ago, mins_ago, thread, json.dumps({"reply": True} if thread else {}), json.dumps(shows or []),
         json.dumps(steps or [])), returning=True)["id"]


first = task("Here is the clip from yesterday and the ad I like. Show me N3 as it runs now and the lead form, so I can compare.",
             "N3 as it runs in Feed, and the form people fill after tapping it. Your clip is 9:16; N3 is 4:5, so the clip would need a crop to replace it.",
             12, shows=[{"type": "ad", "id": N3, "name": "N3 - Same work twice", "caption": "Running since Nov 8. Switch to Reels to see the crop.", "placement": None},
                        {"type": "form", "id": FORM, "name": "EB | Free AI workflow review", "caption": "Three questions, then the thank-you screen.", "placement": None}])
attach(first, MP4, "yesterday clip.mp4", source="user")
attach(first, PNG, "ad I like.png", source="user")
second = task("Make a 4:5 static from the clip's first frame, a 9:16 cut, and draft the landing page that goes with it.",
              "A 4:5 static, the 9:16 cut and a landing page draft that repeats the ad's promise.", 6, thread=first,
              steps=[{"text": "Reading your clip", "at": "2026-11-14T10:00:00Z"}, {"text": "Rendering the 4:5 static", "at": "2026-11-14T10:01:10Z"},
                     {"text": "Cutting the 9:16 video", "at": "2026-11-14T10:02:30Z"}, {"text": "Building the landing page", "at": "2026-11-14T10:03:40Z"}])
attach(second, PNG, "static-a.png", "4:5 static, version A")
attach(second, MP4, "cut-a.mp4", "9:16 cut, version A")
attach(second, PAGE, "landing.html", "Landing page draft", mime="text/html")
print(first)
