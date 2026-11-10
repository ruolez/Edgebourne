"""QA helper (audit 2): seed Claude proposals that test the money checks; print ids as JSON."""
import json

import account_ctx
import db
import meta_client

CAMP = "120252638288040312"
live = int(meta_client.get(CAMP, fields="daily_budget")["daily_budget"])
task = db.execute("INSERT INTO desk_tasks (kind, prompt, status, summary) VALUES ('review', 'QA audit2 run', 'done', 'x') RETURNING id",
                  returning=True)["id"]


def prop(kind, title, etype, eid, name, field, cur, new):
    return db.execute(
        """INSERT INTO desk_proposals (task_id, kind, title, entity_type, entity_id, entity_name, field, current_value, proposed_value)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (task, kind, title, etype, eid, name, field, cur, new), returning=True)["id"]


new_dollars = round(live * 1.2 / 100)
out = {"live": live,
       "budget": prop("budget", "QA raise the budget", "campaign", CAMP, "Edge Bourne - Free intro call - Leads", "budget", "x",
                      f"+20% to ${new_dollars}/day"),
       "unclear": prop("budget", "QA unclear budget", "campaign", CAMP, "Edge Bourne - Free intro call - Leads", "budget", "x",
                       "Raise 2x or more"),
       "double": prop("status", "QA pause twice", "ad", "120252672229400312", "N2", "status", "ACTIVE", "PAUSED")}
with account_ctx.all_accounts():
    out["lead2"] = db.query("SELECT id FROM leads WHERE meta_lead_id = 'ACCT2MARKlead'", one=True)["id"]
print(json.dumps(out))
