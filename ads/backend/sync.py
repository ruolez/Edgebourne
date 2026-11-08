"""Mirror the ad account's campaigns so teammates can be assigned to them."""
import db
import meta_client
import settings_store


def sync_campaigns():
    account = settings_store.get("meta_ad_account_id")
    seen = 0
    for c in meta_client.paged(f"act_{account}/campaigns",
                               fields="id,name,status,effective_status,objective,daily_budget",
                               limit=100):
        budget = c.get("daily_budget")
        db.execute(
            """INSERT INTO campaigns (id, name, status, effective_status, objective,
                                      daily_budget_cents, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status,
                   effective_status = EXCLUDED.effective_status, objective = EXCLUDED.objective,
                   daily_budget_cents = EXCLUDED.daily_budget_cents, synced_at = now()""",
            (c["id"], c["name"], c.get("status"), c.get("effective_status"), c.get("objective"),
             int(budget) if budget else None),
        )
        seen += 1
    settings_store.set("last_campaign_sync", __import__("datetime").datetime.utcnow().isoformat() + "Z")
    return seen
