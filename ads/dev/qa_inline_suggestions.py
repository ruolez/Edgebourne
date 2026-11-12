"""QA helper (9.2b): seed a budget and a new-copy suggestion that show on an ad's page; print their ids as JSON.

python qa_inline_suggestions.py <campaign id> <ad id> <budget words> <headline>
"""
import json
import sys

import db
import desk_api

camp, ad, budget_words, headline = sys.argv[1:5]
task = db.execute("INSERT INTO desk_tasks (kind, prompt, status, summary) VALUES ('review', 'QA: inline suggestions', 'done', 'x') RETURNING id",
                  returning=True)["id"]
budget = db.execute(
    """INSERT INTO desk_proposals (task_id, kind, title, entity_type, entity_id, entity_name, field, current_value, proposed_value)
       VALUES (%s, 'budget', 'QA inline budget', 'campaign', %s, 'Edge Bourne - Free intro call - Leads', 'budget', 'x', %s) RETURNING id""",
    (task, camp, budget_words), returning=True)["id"]
p = desk_api.clean_proposal({"kind": "creative", "title": "QA inline new copy", "rationale": "A sharper first line.",
                             "payload": {"template_ad_id": ad, "name": "N3 - QA inline copy", "title": headline,
                                         "body": "QA: one system for the whole shop.", "media": {"kind": "same"}}})
creative = db.execute("INSERT INTO desk_proposals (task_id, kind, title, rationale, payload) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                      (task, p["kind"], p["title"], p["rationale"], json.dumps(p["payload"])), returning=True)["id"]
print(json.dumps({"budget": budget, "creative": creative}))
