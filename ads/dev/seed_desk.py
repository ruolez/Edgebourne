"""Local development only: replace the Desk with a copy shaped like the real one on
2026-11-09 (research, a polish of N1 with four ideas, the N1 v2 render). Never run on the
server. docker exec edgebourne-ads-backend python /app/dev/seed_desk.py"""
import json
import sys

sys.path.insert(0, "/app")
import db  # noqa: E402

N1, V2, HEAD = "120252672229040312", "120252690325970312", "120252689507540312"
BODY = ("Notepads, spreadsheets, sticky notes, sales reports by hand. It works until the business grows.\n"
        "We bring it all into one simple system your team can use. AI can handle the routine updates, if you want it. You own it.\n"
        "Free intro call for Southern California businesses. We'll be in touch in a few business days.")

db.execute("DELETE FROM desk_tasks")
db.execute("DELETE FROM meta_changes WHERE proposal_id IS NOT NULL")
ad = db.query("SELECT * FROM ads WHERE id = %s", (N1,), one=True)
for aid, name, status in ((V2, "N1 - One simple system · v2", "ACTIVE"), (HEAD, "N1 - One simple system · headline Run it all", "PAUSED")):
    db.execute("""INSERT INTO ads (id, name, campaign_id, adset_id, status, effective_status, thumbnail_url, image_url, object_type, created_time)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                  ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status, effective_status = EXCLUDED.effective_status""",
               (aid, name, ad["campaign_id"], ad["adset_id"], status, status, ad["thumbnail_url"], ad["image_url"], ad["object_type"]))
db.execute("UPDATE ads SET status = 'PAUSED', effective_status = 'PAUSED' WHERE id = %s", (N1,))


def task(kind, prompt, summary, at, options=None, scorecard=None):
    return db.execute("""INSERT INTO desk_tasks (kind, prompt, campaign_id, status, summary, created_at, finished_at, options, scorecard, created_by)
                         VALUES (%s,%s,%s,'done',%s,%s,%s,%s,%s,1) RETURNING id""",
                      (kind, prompt, ad["campaign_id"], summary, at, at, json.dumps(options or {}),
                       json.dumps(scorecard) if scorecard else None), returning=True)["id"]


def report(tid, title, body):
    db.execute("INSERT INTO desk_reports (task_id, title, body) VALUES (%s,%s,%s)", (tid, title, body))


def proposal(tid, kind, title, status, rationale, payload=None, **kw):
    cols = {"task_id": tid, "kind": kind, "title": title, "status": status, "rationale": rationale,
            "payload": json.dumps(payload) if payload else None, **kw}
    if status != "pending":
        cols["decided_at"] = kw.get("decided_at", "2026-11-09T12:18:00-08:00")
        cols["decided_by"] = 1
    keys = ", ".join(cols)
    return db.execute(f"INSERT INTO desk_proposals ({keys}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                      list(cols.values()), returning=True)["id"]


def created(pid, ad_id, name):
    db.execute("""INSERT INTO meta_changes (user_id, level, entity_id, entity_name, campaign_id, action, new_value, ok, proposal_id)
                  VALUES (1, 'ad', %s, %s, %s, 'create', %s, true, %s)""", (ad_id, name, ad["campaign_id"], name, pid))


t1 = task("research", "what are it consultants and software agencies in southern california running right now on facebook and meta? what kinds of ads?",
          "Almost no Southern California IT or software firms could be confirmed advertising; only Blitz Mobile Apps possibly (Los Angeles, unconfirmed). Nationally the category runs plain-money headlines: skip the big quote, drop subscriptions, one fixed price, more profit without more payroll. Local founder-built and code ownership look open for your next creative round.",
          "2026-11-09T10:59:00-08:00")
report(t1, "What IT and software firms are running on Meta", "## Southern California\nAlmost nobody local is advertising.\n\n## Nationally\nPlain-money headlines dominate.")
card = {"overall": 3.5, "headline": "N1 is a solid ad that needs small fixes: the offer shows up too late, the tap note is in the wrong corner and not bold, and the headline field is short and not an outcome. Too early to judge results ($1.32 spent).",
        "passes": [{"id": "hook", "label": "Hook", "score": 4, "verdict": "The opening stops the scroll and works muted; the only real flaw is that the solution line arrives before the problem has landed.", "findings": [], "fixes": []},
                   {"id": "headline", "label": "Headline", "score": 3, "verdict": "The headline on the image is right, but the headline field is two characters under the range and names a feature instead of a result.", "findings": [], "fixes": []},
                   {"id": "cta", "label": "Call to action", "score": 3, "verdict": "The offer is honest and the button is allowed, but the tap note is neither big and bold nor at the exit corner, and most viewers leave before it appears.", "findings": [], "fixes": []},
                   {"id": "message", "label": "Message & intent", "score": 4, "verdict": "One clear idea for the right owner, different from the other four; only a small overlap with N4 to clean up.", "findings": [], "fixes": []}]}
t2 = task("polish", "Polish “N1 - One simple system”: Hook, Headline, Call to action, Message & intent.",
          "N1 is solid and needs small fixes (3.5 of 5): show the offer from the start, put a bold Tap below at bottom right, use an outcome headline. Too early to judge results at $1.32 spent.",
          "2026-11-09T11:02:00-08:00", {"ad_id": N1, "ad_name": "N1 - One simple system"}, card)
report(t2, "Polish N1: small fixes, too early to judge", "## Hook 4/5\nThe opening works muted.\n\n## Headline 3/5\nTwo characters short.")
base = {"template_ad_id": N1, "cta_type": "BOOK_TRAVEL", "media": {"kind": "same"}, "adset_id": None}
p1 = proposal(t2, "creative", "New headline: Run it all from one screen", "applied",
              "Fixes two Headline checks: 26 characters (now 24, minimum 26, Facebook feed shows about 27) and a concrete outcome in place of a feature. Same video, same text, so it isolates the headline.",
              {**base, "title": "Run it all from one screen", "body": BODY, "name": "N1 - One simple system · headline Run it all"})
created(p1, HEAD, "N1 - One simple system · headline Run it all")
proposal(t2, "creative", "New angle: where everything lives", "pending",
         "Makes the problem more concrete than a list of tools, with a first line of 113 characters that fits before See more. The headline is 27 characters and states the outcome, so it fixes both Headline checks.",
         {**base, "title": "No more digging for numbers", "name": "N1 - One simple system · angle where it lives",
          "body": "The stock count is on a sticky note, the books are in a spreadsheet, and the sales numbers are in someone's head.\nWe bring it all into one simple system your team can use. AI can handle the routine updates, if you want it. You own it.\nFree intro call for Southern California businesses. We'll be in touch in a few business days."})
proposal(t2, "creative", "New angle: the next hire", "pending",
         "Speaks to the owner who is growing and shows what \"until the business grows\" looks like in practice. First line is 94 characters; the headline is 27 and names who benefits.",
         {**base, "title": "One place your team can use", "name": "N1 - One simple system · angle next hire",
          "body": "Every new hire has to learn where the notepad is, which spreadsheet is current and who to ask.\nWe bring it all into one simple system, so anyone on the team can find the answer. AI can handle the routine updates, if you want it. You own it.\nFree intro call for Southern California businesses. We'll be in touch in a few business days."})
p4 = proposal(t2, "other", "Make a new version: offer from the start, tap note bold at bottom right, solution line after the pile", "approved",
              "These need new pixels. Average play time was 3 s on N1 and 1 to 4 s across the five ads (Meta, Nov 8, small sample), and the offer starts at 5.6 s. The tap note also misses your big-and-bold rule and the bottom-right exit.",
              entity_type="ad", entity_id=N1, entity_name="N1 - One simple system", field="video",
              current_value="Offer bar at 5.6 s, bottom-left; tap note 33 px regular italic", proposed_value="Offer bar from frame 0, bottom-right; \"Tap below ↓\" 40 px bold; solution line at 3.2 s",
              expected="Use 'Make a new version' on the ad page; Claude rebuilds the creative and sends it back for approval.",
              rollback="N1 stays as it is until a new version is approved, and that version is created switched off.")
t3 = task("render", "Make a new version of “N1 - One simple system”.\nDirection: These need new pixels.\nApply the fixes from polish run #2.",
          "N1 v2 is rendered and uploaded with the polish fixes: offer on screen from frame 0 at bottom right, bold Tap below, solution line at 3.2 s, Updates drafted. One proposal is waiting for approval and creates the ad switched off.",
          "2026-11-09T12:18:20-08:00", {"ad_id": N1, "ad_name": "N1 - One simple system", "from_task": t2, "from_proposal": p4})
report(t3, "N1 v2: offer from the first frame", "## What changed\n| Fix | Before | After |\n|---|---|---|\n| Offer timing | 5.6 s | frame 0 |")
p5 = proposal(t3, "creative", "New video: N1 v2, offer from the start", "applied",
              "Applies the pixel fixes from polish run #2. Same words, button and music as N1, so only the video changes.",
              {**base, "title": "Everything in one system", "body": BODY, "name": "N1 - One simple system · v2",
               "media": {"kind": "video", "video_id": "1030340833422294"}}, decided_at="2026-11-09T12:40:00-08:00")
created(p5, V2, "N1 - One simple system · v2")
print("desk seeded")
