"""Local development only: "Did it work?" (D3) changes with known results, for qa/flows.cjs. Never run on the server.

Three changes in account 1, each on a tree of its own so they don't cut each other's windows:
- worked: a campaign in the fake Meta, budget $20 → $24 twelve days ago, from an applied Claude suggestion that expected
  cost per lead under $40; cost per lead $46.67 → $14.00 over 7 days ("Worked", expectation met).
- worse:  a campaign in the fake Meta (budget $24 there now), budget $20 → $24 ten days ago; cost per lead $17.50 → $70.00
  ("Didn't help", Put it back goes to $20.00).
- pause:  an ad turned off nine days ago in an ad set of its own (console only), measured on that ad set, from an applied
  suggestion on the ad that expected cheaper leads in words only.
The daily results are written straight into ad_daily for ids only this script uses, so a sync never rewrites them.
`--clean` only removes them (qa/run.sh at the start, flows.cjs after its D3 checks). Prints JSON with the ids and each window's sums (by construction, not by the code under test)."""
import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")
import account_ctx  # noqa: E402
import account_info  # noqa: E402
import change_checks_db  # noqa: E402
import db  # noqa: E402
import requests  # noqa: E402
import settings_store  # noqa: E402

FAKE = "http://fake-meta:5001/v24.0"
ACT = "act_1025971549903293"
PAUSE_CAMP, PAUSE_SET, PAUSE_AD1, PAUSE_AD2 = "qa-d3-pcamp", "qa-d3-pset", "qa-d3-pad1", "qa-d3-pad2"


def fake_campaign(name, cents):
    r = requests.post(f"{FAKE}/{ACT}/campaigns", data={"name": name, "status": "PAUSED", "objective": "OUTCOME_LEADS",
                                                         "daily_budget": str(cents), "access_token": "x"}, timeout=10)
    r.raise_for_status()
    return r.json()["id"]


def days(rows, ad, camp, adset, start, n, spend, leads):
    """n days of results from `start`; `leads` is one number per day."""
    for i in range(n):
        rows.append((start + timedelta(days=i), ad, camp, adset, spend, leads[i]))


with account_ctx.use(1), db.reusing():
    tz = account_info.tz()
    today = account_info.today()
    now = datetime.now(timezone.utc)
    admin = db.query("SELECT id, name FROM users WHERE email = 'eugene@edgebourne.com'", one=True)
    # A fresh start: earlier runs' QA D3 rows go (their checks and Inbox items with them). `--clean` stops here, so the
    # rest of QA never sees these campaigns or their spend.
    old = [r["id"] for r in db.query("SELECT id FROM campaigns WHERE name LIKE 'QA D3 %%' OR id = %s", (PAUSE_CAMP,))]
    olds = [r["id"] for r in db.query("SELECT id FROM meta_changes WHERE campaign_id = ANY(%s) OR entity_id = ANY(%s)",
                                      (old + [PAUSE_CAMP], old + [PAUSE_AD2]))]
    db.execute("DELETE FROM alerts WHERE rule = 'change_result' AND (campaign_id = ANY(%s) OR campaign_id IS NULL)", (old + [PAUSE_CAMP],))
    db.execute("UPDATE meta_changes SET undo_of = NULL WHERE undo_of = ANY(%s)", (olds,))
    db.execute("DELETE FROM meta_changes WHERE id = ANY(%s)", (olds,))
    db.execute("DELETE FROM ad_daily WHERE ad_id LIKE 'qa-d3-%%'")
    db.execute("DELETE FROM ads WHERE id LIKE 'qa-d3-%%'")
    db.execute("DELETE FROM adsets WHERE id LIKE 'qa-d3-%%'")
    db.execute("DELETE FROM campaigns WHERE id = ANY(%s)", (old + [PAUSE_CAMP],))
    db.execute("DELETE FROM desk_proposals WHERE title IN ('QA D3: raise the budget 20%%', 'QA D3: turn off ad 2')")
    db.execute("DELETE FROM desk_tasks WHERE prompt = 'QA D3: should the budget go up?'")
    if "--clean" in sys.argv:
        print(json.dumps({"cleaned": len(olds)}))
        sys.exit(0)

    worked, worse = fake_campaign("QA D3 worked", 2400), fake_campaign("QA D3 worse", 2400)
    for cid, name in ((worked, "QA D3 worked"), (worse, "QA D3 worse")):
        db.execute("""INSERT INTO campaigns (id, name, status, effective_status, configured_status, daily_budget_cents, objective)
                      VALUES (%s, %s, 'PAUSED', 'PAUSED', 'PAUSED', 2400, 'OUTCOME_LEADS')
                      ON CONFLICT (id) DO UPDATE SET daily_budget_cents = 2400""", (cid, name))
    db.execute("""INSERT INTO campaigns (id, name, status, effective_status, configured_status, objective)
                  VALUES (%s, 'QA D3 paused ad', 'ACTIVE', 'ACTIVE', 'ACTIVE', 'OUTCOME_LEADS')""", (PAUSE_CAMP,))
    db.execute("""INSERT INTO adsets (id, name, campaign_id, status, effective_status, configured_status)
                  VALUES (%s, 'QA D3 one ad set', %s, 'ACTIVE', 'ACTIVE', 'ACTIVE')""", (PAUSE_SET, PAUSE_CAMP))
    for aid, name, st in ((PAUSE_AD1, "QA D3 ad 1", "ACTIVE"), (PAUSE_AD2, "QA D3 ad 2", "PAUSED")):
        db.execute("""INSERT INTO ads (id, name, adset_id, campaign_id, status, effective_status, configured_status, created_time)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, now() - interval '30 days')""", (aid, name, PAUSE_SET, PAUSE_CAMP, st, st, st))

    def local_noon(days_ago):
        d = today - timedelta(days=days_ago)
        return datetime(d.year, d.month, d.day, 12, tzinfo=tz).astimezone(timezone.utc), d

    rows = []
    # worked: change day D-12; before D-19..D-13, after D-11..D-5.
    w_at, w_day = local_noon(12)
    days(rows, "qa-d3-wad", worked, "qa-d3-wset", w_day - timedelta(days=7), 7, 2000, [1, 0, 0, 1, 0, 1, 0])
    days(rows, "qa-d3-wad", worked, "qa-d3-wset", w_day + timedelta(days=1), 7, 2400, [2, 2, 2, 2, 1, 2, 1])
    # worse: change day D-10; before D-17..D-11, after D-9..D-3.
    x_at, x_day = local_noon(10)
    days(rows, "qa-d3-xad", worse, "qa-d3-xset", x_day - timedelta(days=7), 7, 3000, [2, 2, 2, 1, 2, 2, 1])
    days(rows, "qa-d3-xad", worse, "qa-d3-xset", x_day + timedelta(days=1), 7, 3000, [0, 1, 0, 0, 1, 0, 1])
    # pause: change day D-9 on ad 2; its ad set before D-16..D-10 (both ads), after D-8..D-2 (ad 1 only).
    p_at, p_day = local_noon(9)
    days(rows, PAUSE_AD1, PAUSE_CAMP, PAUSE_SET, p_day - timedelta(days=7), 7, 1500, [1, 0, 1, 0, 0, 1, 0])
    days(rows, PAUSE_AD2, PAUSE_CAMP, PAUSE_SET, p_day - timedelta(days=7), 7, 1500, [0, 1, 0, 1, 0, 0, 1])
    days(rows, PAUSE_AD1, PAUSE_CAMP, PAUSE_SET, p_day + timedelta(days=1), 7, 2000, [1, 1, 0, 1, 1, 0, 1])
    for day, ad, camp, adset, spend, leads in rows:
        db.execute("""INSERT INTO ad_daily (day, ad_id, campaign_id, adset_id, ad_name, spend_cents, impressions, leads)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", (day, ad, camp, adset, f"QA D3 {ad}", spend, spend // 2, leads))

    task = db.execute("""INSERT INTO desk_tasks (kind, prompt, status, summary, created_by, created_at, claimed_at, finished_at, seen_at)
                         VALUES ('question', 'QA D3: should the budget go up?', 'done', 'Raise it 20%%: cost per lead is under target.', %s,
                                 %s, %s, %s, now()) RETURNING id""", (admin["id"], w_at - timedelta(hours=2), w_at - timedelta(hours=2), w_at - timedelta(hours=1)),
                      returning=True)["id"]
    proposal = db.execute("""INSERT INTO desk_proposals (task_id, kind, title, entity_type, entity_id, entity_name, field, current_value,
                                                         proposed_value, rationale, expected, rollback, status, decided_at, decided_by, expect, payload)
                             VALUES (%s, 'budget', 'QA D3: raise the budget 20%%', 'campaign', %s, 'QA D3 worked', 'daily budget', '$20/day',
                                     '$24/day', 'Cost per lead $46 against a $60 target.', 'CPL under $40 within 7 days', '$20/day',
                                     'applied', %s, %s, %s, %s) RETURNING id""",
                          (task, worked, w_at, admin["id"], json.dumps({"metric": "cpl", "op": "<", "cents": 4000, "days": 7}),
                           json.dumps({"proposed_cents": 2400})), returning=True)["id"]

    # The ad's own applied suggestion (no structured expectation), so the ad page's earlier suggestions show the result.
    off = db.execute("""INSERT INTO desk_proposals (task_id, kind, title, entity_type, entity_id, entity_name, field, current_value,
                                                    proposed_value, rationale, expected, status, decided_at, decided_by)
                        VALUES (%s, 'status', 'QA D3: turn off ad 2', 'ad', %s, 'QA D3 ad 2', 'status', 'ACTIVE', 'PAUSED',
                                'Ad 1 brings leads cheaper in the same ad set.', 'Cheaper leads on the ad set', 'applied', %s, %s)
                        RETURNING id""", (task, PAUSE_AD2, p_at, admin["id"]), returning=True)["id"]

    def change(level, entity, name, camp, action, old, new, at, proposal_id=None):
        return db.execute("""INSERT INTO meta_changes (user_id, level, entity_id, entity_name, campaign_id, action, old_value, new_value, ok,
                                                       proposal_id, created_at)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s) RETURNING id""",
                          (admin["id"], level, entity, name, camp, action, old, new, proposal_id, at), returning=True)["id"]

    ids = {"worked": change("campaign", worked, "QA D3 worked", worked, "budget", "2000", "2400", w_at, proposal),
           "worse": change("campaign", worse, "QA D3 worse", worse, "budget", "2000", "2400", x_at),
           "pause": change("ad", PAUSE_AD2, "QA D3 ad 2", PAUSE_CAMP, "status", "ACTIVE", "PAUSED", p_at, off)}
    # The results are judged only once Meta's numbers cover the window (a stale sync waits).
    synced = settings_store.get("last_performance_sync")
    if not synced or datetime.fromisoformat(synced.replace("Z", "+00:00")) < now - timedelta(hours=12):
        settings_store.set("last_performance_sync", now.isoformat().replace("+00:00", "Z"))
    ctx = change_checks_db.context()
    for cid in ids.values():
        change_checks_db.raise_results(change_checks_db.load_change(cid), change_checks_db.compute(cid, ctx=ctx))
    change_checks_db.run()
    print(json.dumps({**ids, "worked_campaign": worked, "worse_campaign": worse, "pause_adset": PAUSE_SET, "pause_ad": PAUSE_AD2, "proposal": proposal, "task": task,
                      "admin": admin["name"], "change_day": {"worked": w_day.isoformat(), "worse": x_day.isoformat()},
                      "sums": {"worked": {"before": {"spend": 14000, "leads": 3}, "after": {"spend": 16800, "leads": 12}},
                               "worse": {"before": {"spend": 21000, "leads": 12}, "after": {"spend": 21000, "leads": 3}}}}))
