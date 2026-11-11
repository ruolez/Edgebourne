"""Local development only: on top of dev/seed_desk.py, a busy Claude page: an audit across categories,
a run in progress, a stacked queue, a failed run and finished ones. Never run on the server."""
import json
import sys

sys.path.insert(0, "/app")
import db  # noqa: E402

CAMP, ADSET = "120252638288040312", "120252672227950312"
N2, N3, N4 = "120252672229400312", "120252672230740312", "120252672232030312"


def task(kind, prompt, status="done", summary=None, error=None, progress=None, options=None, seen=True, mins_ago=30):
    return db.execute(
        """INSERT INTO desk_tasks (kind, prompt, status, summary, error, progress, options, created_by, created_at, claimed_at, finished_at, seen_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,1, now() - %s * interval '1 minute',
                   CASE WHEN %s <> 'queued' THEN now() - %s * interval '1 minute' END,
                   CASE WHEN %s IN ('done','failed') THEN now() - (%s - 6) * interval '1 minute' END,
                   CASE WHEN %s THEN now() END) RETURNING id""",
        (kind, prompt, status, summary, error, progress, json.dumps(options or {}), mins_ago, status, mins_ago, status, mins_ago, seen), returning=True)["id"]


def proposal(tid, kind, title, rationale, payload=None, **kw):
    cols = {"task_id": tid, "kind": kind, "title": title, "rationale": rationale, "payload": json.dumps(payload) if payload else None, **kw}
    db.execute(f"INSERT INTO desk_proposals ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", list(cols.values()))


audit = task("review", "Audit the whole account for the last 7 days against a $60 target and tell me everything you'd change.",
             summary="Two ads carry the account and N4 is burning money. Pause N4, give the campaign +20%, and turn N2 back on; labels and one test are ready.", mins_ago=50)
proposal(audit, "budget", "Raise the campaign budget 20%", "7-day cost per lead $31 against a $60 target, 11 leads.", entity_type="campaign", entity_id=CAMP,
         entity_name="Edge Bourne - Free intro call - Leads", field="daily budget", current_value="$20/day", proposed_value="$24/day", rollback="$20/day")
proposal(audit, "status", "Pause N4 - Weekly report", "$38 spent, 0 leads in 7 days.", entity_type="ad", entity_id=N4, entity_name="N4 - Weekly report", field="status", current_value="ACTIVE", proposed_value="PAUSED", rollback="ACTIVE")
proposal(audit, "status", "Turn N2 back on", "It had the best cost per lead before it was switched off.", entity_type="ad", entity_id=N2, entity_name="N2 - Order portal", field="status", current_value="PAUSED", proposed_value="ACTIVE", rollback="PAUSED")
proposal(audit, "tags", "Tag N3 - Same work twice", "It opens with a command.", {"ad_id": N3, "tags": {"hook": "Command", "format": "9 s motion video, 4:5"}})
proposal(audit, "experiment", "Test the order portal against the weekly report", "Same people, hook rate decides.",
         {"name": "Portal vs report", "metric": "hook", "start_day": "2026-11-10", "arms": [{"label": "Portal", "ad_ids": [N2], "adset_ids": [], "names": ["N2 - Order portal"]}, {"label": "Report", "ad_ids": [N4], "adset_ids": [], "names": ["N4 - Weekly report"]}]})
proposal(audit, "targeting", "Narrow the age range to 30-60", "Leads under 30 never qualified.", expected="Change it in Ads Manager after approving.")

polish = task("polish", "Polish “N3 - Same work twice”: Hook, Headline, Primary text, Call to action.", summary="N3 hooks people but loses them at 2.5 s; a new version should fill the gap.", options={"ad_id": N3, "ad_name": "N3 - Same work twice"}, mins_ago=26)
proposal(polish, "other", "Make a new version: something new on screen from 2.5 s", "Only 24% of those who reach a quarter reach halfway.", entity_type="ad", entity_id=N3, entity_name="N3 - Same work twice", expected="Claude rebuilds it and sends it back.")

task("question", "Which ad is getting the most qualified leads this week?", summary="N1 v2, with 4 of the 7 qualified leads this week at $22 each.", seen=False, mins_ago=18)
task("research", "What are Southern California bookkeepers running right now?", status="failed", error="Meta's Ad Library didn't answer after three tries. Ask again in a few minutes.", seen=False, mins_ago=14)
task("render", "Make a new version of “N2 - Order portal · v3”.\nDirection: slower opening.", status="running", progress="Rendering the 4:5 video", options={"ad_id": N2, "ad_name": "N2 - Order portal"}, mins_ago=7)
task("question", "Why did cost per lead jump yesterday?", status="queued", mins_ago=4)
task("creative", "Three new ideas for restaurant owners, same free intro call offer.", status="queued", mins_ago=3)
task("review", "Scheduled: Optimizer review", status="queued", options={"schedule": "Optimizer review"}, mins_ago=2)


# A conversation's worth of shape: a report with sections, a follow-up, the live steps, ads Claude found.
def report(tid, title, body):
    db.execute("INSERT INTO desk_reports (task_id, title, body) VALUES (%s, %s, %s)", (tid, title, body))


report(audit, "Account audit, last 7 days", """Two ads carry the account and N4 is burning money. Pause N4, give the campaign +20%, and turn N2 back on; labels and one test are ready.

## What the numbers say
| Ad | Spend | Leads | Per lead |
|---|---|---|---|
| N1 - One simple system · v2 | $58.10 | 4 | $14.53 |
| N3 - Same work twice | $44.20 | 2 | $22.10 |
| N4 - Weekly report | $37.70 | 0 | none |

N4 has spent 63% of the $60 target with no lead yet.

## What I'd do
1. Pause N4 now. It has the weakest hook rate of the five.
2. Give the campaign +20%. Cost per lead is well under target.
3. Narrow the age range only if lead quality stays low next week.

## Data used
Last 7 complete days, Meta insights; lead stages from the dashboard inbox.""")

N1 = "120252672229040312"
first = task("creative", "Two headlines for N1 that are less formal.", summary="Two options; “Type it once” is the one I’d run.", options={"ad_id": N1, "ad_name": "N1 - One simple system"}, mins_ago=30)
proposal(first, "creative", "New headline: Stop typing it twice", "Fixes the length check.", {"template_ad_id": N1, "media": {"kind": "same"}, "name": "N1 · short headline", "title": "Stop typing it twice", "body": "Same work, entered twice. One system fixes that."}, status="revised")
reply = task("creative", "Shorter, and keep it under 20 characters.", summary="Shorter, same offer. “Type it once” is 12 characters.", options={"ad_id": N1, "ad_name": "N1 - One simple system", "reply": True, "about": {"id": 0, "title": "New headline: Stop typing it twice"}}, mins_ago=22)
db.execute("UPDATE desk_tasks SET thread_id = %s, steps = %s WHERE id = %s", (first, json.dumps([{"text": "Reading the earlier headline", "at": "2026-11-10T20:01:00Z"}, {"text": "Writing two shorter ones", "at": "2026-11-10T20:02:12Z"}]), reply))
proposal(reply, "creative", "New headline: Type it once", "12 characters, and it says the benefit.", {"template_ad_id": N1, "media": {"kind": "same"}, "name": "N1 · Type it once", "title": "Type it once", "body": "Same work, entered twice. One system fixes that."})

db.execute("""UPDATE desk_tasks SET steps = %s WHERE status = 'running'""", (json.dumps([
    {"text": "Reading your ads", "at": "2026-11-11T00:00:00Z"}, {"text": "Rebuilding the opening", "at": "2026-11-11T00:01:30Z"}, {"text": "Rendering the 4:5 video", "at": "2026-11-11T00:03:00Z"}]),))

found = task("research", "What are IT consultants in Southern California running?", summary="Eleven local firms run ads. Nine lead with fear of downtime and none offer a free review.", seen=False, mins_ago=11)
report(found, "Competitor scan", "Eleven local firms run ads.\n\n## What they run\nFear of downtime: 9 of 11. Static images with a phone number.\n\n## Worth testing\nA short video of the review itself.")
ids = []
for i, page in enumerate(["Coastline IT", "SoCal Tech Partners", "Harbor Managed Services"]):
    r = db.execute("""INSERT INTO swipes (library_id, page_name, body, title, cta, started_on, platforms, tags, source)
                      VALUES (%s, %s, %s, %s, 'Learn more', current_date - %s, '["facebook"]', '{}', 'claude')
                      ON CONFLICT DO NOTHING RETURNING id""", (f"qa{i}{found}", page, "One outage can cost a week of revenue.", "Downtime is expensive", 12 + 25 * i), returning=True)
    if r:
        ids.append(r["id"])
db.execute("UPDATE desk_tasks SET swipe_ids = %s WHERE id = %s", (ids, found))
print("board seeded")
