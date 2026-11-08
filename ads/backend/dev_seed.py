"""Local development only: sample campaign and leads for designing the screens.
Run: docker compose exec backend python dev_seed.py"""
import json
from datetime import datetime, timedelta, timezone

import db

now = datetime.now(timezone.utc)
db.execute("""INSERT INTO campaigns (id, name, status, effective_status, objective, daily_budget_cents)
              VALUES ('120252638288040312', 'Edge Bourne - Free intro call - Leads', 'ACTIVE', 'ACTIVE',
                      'OUTCOME_LEADS', 2000) ON CONFLICT (id) DO NOTHING""")
samples = [
    ("Maria Lopez", "+16195550101", "maria@lopezbakery.example", "Wholesale bakery, 14 staff", "N2 - Order portal", 6, "new"),
    ("Daniel Kim", "+13105550144", "dan@kimhvac.example", "HVAC service, 3 trucks", "N5 - Quote to invoice", 42, "new"),
    ("Priya Nair", "+19495550188", "priya@nairlogistics.example", "Freight brokerage", "N3 - Same work twice", 190, "new"),
    ("Tom Alvarez", "+17605550123", "tom@alvarezlandscape.example", "Landscaping, 2 crews", "N1 - One simple system", 1650, "new"),
    ("Grace Chen", "+16265550199", "grace@chencpa.example", "Accounting practice", "N4 - Weekly report", 2900, "contacted"),
    ("Robert Hayes", "+18185550111", "rob@hayesparts.example", "Auto parts distributor", "N2 - Order portal", 7400, "qualified"),
    ("Sofia Ramirez", "+16195550177", "sofia@ramirezcleaning.example", "Commercial cleaning", "N5 - Quote to invoice", 12000, "won"),
    ("Kevin Brooks", "+19515550155", "kevin@brooksfit.example", "Gym, one location", "N1 - One simple system", 15000, "lost"),
]
for i, (name, phone, email, biz, ad, mins, status) in enumerate(samples):
    answers = [{"name": "full_name", "values": [name]}, {"name": "email", "values": [email]},
               {"name": "phone_number", "values": [phone]},
               {"name": "what_kind_of_business_do_you_run?", "values": [biz]}]
    db.execute("""INSERT INTO leads (meta_lead_id, created_time, form_id, form_name, ad_id, ad_name, campaign_id,
                                     campaign_name, full_name, email, phone, business_type, answers, status)
                  VALUES (%s,%s,'1132280359202136','EB | Free intro call | Higher intent',%s,%s,
                          '120252638288040312','Edge Bourne - Free intro call - Leads',%s,%s,%s,%s,%s,%s)
                  ON CONFLICT (meta_lead_id) DO NOTHING""",
               (f"demo-{i}", now - timedelta(minutes=mins), f"ad-{i}", ad, name, email, phone, biz,
                json.dumps(answers), status))
print("seeded")

# Sample performance: 5 ads over 30 days, and a spending cap (local only).
import random
from datetime import date

import settings_store

random.seed(7)
ads = [("ad-0", "N2 - Order portal"), ("ad-1", "N5 - Quote to invoice"), ("ad-2", "N3 - Same work twice"),
       ("ad-3", "N1 - One simple system"), ("ad-4", "N4 - Weekly report")]
for ad_id, name in ads:
    db.execute("""INSERT INTO ads (id, name, campaign_id, status, effective_status)
                  VALUES (%s,%s,'120252638288040312','ACTIVE','ACTIVE') ON CONFLICT (id) DO NOTHING""", (ad_id, name))
for back in range(1, 31):
    day = date.today() - timedelta(days=back)
    for k, (ad_id, name) in enumerate(ads):
        spend = random.randint(150, 650) if back <= 9 else 0
        impressions = spend * random.randint(6, 11) // 10
        db.execute("""INSERT INTO ad_daily (day, ad_id, campaign_id, ad_name, spend_cents, impressions, link_clicks, leads)
                      VALUES (%s,%s,'120252638288040312',%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                   (day, ad_id, name, spend, impressions, impressions // 90, random.choice([0, 0, 0, 1]) if spend else 0))
settings_store.set("account_snapshot", json.dumps({"currency": "USD", "spend_cap_cents": 15000,
                                                   "amount_spent_cents": 11240, "timezone": "America/Los_Angeles"}))
print("seeded performance")
