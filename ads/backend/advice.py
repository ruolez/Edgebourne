"""Meta's own advice (roadmap 5.3): Opportunity Score and recommendations, in plain words, with
which ones this dashboard applies itself. Pure: reading Meta's two response shapes, labels,
what applying would do, and the +20% budget rule for "spend more on a good campaign"."""

# type (upper-cased, version suffix dropped): (plain label, what applying does here or None, note)
TYPES = {
    "REELS_PC_RECOMMENDATION": ("Add a vertical 9:16 video for Reels", None,
                                "Needs a 9:16 video with sound for each ad."),
    "ADVANTAGE_PLUS_AUDIENCE": ("Let Meta find people beyond your audience settings", "Turns on Advantage+ audience for the ad sets named.", None),
    "AUTOMATIC_PLACEMENTS": ("Show the ads in every placement", "Turns on Advantage+ placements.", None),
    "SCALE_GOOD_CAMPAIGN": ("Spend more on a campaign that's doing well", "Raises the budget by the amount Meta suggests.", None),
    "CREATIVE_FATIGUE": ("Refresh ads people have seen too often", None, "Make new versions of the tired ads."),
    "CREATIVE_LIMITED": ("Add more ads to an ad set", None, "Add 2-4 genuinely different ideas."),
    "MUSIC": ("Add music to the ads", "Lets Meta add music it picks.",
              "The meta-ads advice for brand ads is to choose the music yourself."),
    "CBO": ("Use one budget for the whole campaign", None, "Your campaign already shares one budget; check in Ads Manager."),
    "FRAGMENTATION": ("Combine similar ad sets", None, "Split ad sets compete with each other; merge them in Ads Manager."),
    "SIGNALS_GROWTH_CAPI": ("Send more signals with the Conversions API", None, "Lead stages to Meta (Settings) is how this dashboard does it."),
}
APPLY_HERE = {"ADVANTAGE_PLUS_AUDIENCE", "AUTOMATIC_PLACEMENTS", "SCALE_GOOD_CAMPAIGN"}
# What "Fix with Claude" does for advice the console can't apply itself (a Desk run, kind 'advice').
CLAUDE_FIX = {
    "REELS_PC_RECOMMENDATION": "Claude makes a 9:16 version with sound of each running ad on your Mac and sends each "
                               "back for a yes or no. Approving one updates that ad: 4:5 in feeds, 9:16 in Reels and Stories.",
    "CREATIVE_FATIGUE": "Claude finds the tired ads and makes new versions on your Mac, each sent back for a yes or no.",
    "CREATIVE_LIMITED": "Claude writes 2-4 genuinely different ad ideas for this ad set; approving one creates it switched off.",
    "FRAGMENTATION": "Claude checks which ad sets overlap and proposes how to combine them, for a yes or no.",
}
DEFAULT_FIX = ("Claude checks the suggestion against your numbers and the playbook, says whether it fits, "
               "and proposes the changes for a yes or no.")
BIG_STEP = 0.20


def type_key(t):
    t = str(t or "").upper()
    for suffix in ("_V2", "_V3"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    return t


def fix_key(rec):
    """Stable id of one piece of advice (Meta gives no signature for most): type + the objects it names."""
    ids = sorted(str(i) for i in rec.get("object_ids") or [])
    return f"{type_key(rec.get('type') or rec.get('recommendation_name'))}:{','.join(ids)}"


def fix_prompt(r):
    points = f" (+{r['points']} points)" if r.get("points") else ""
    lift = f" {r['lift']}" if r.get("lift") else ""
    return f"Meta's advice: {r['label']}{points}.{lift}\nFix it: {r['fix']}"


def human(t):
    return type_key(t).replace("_", " ").capitalize()


def flatten(body):
    """Account response: {"data": [{"recommendations": [...]}]} or a bare list."""
    if isinstance(body, list):
        items = body
    else:
        items = []
        for d in (body or {}).get("data") or []:
            items += d.get("recommendations") or ([d] if d.get("type") or d.get("recommendation_name") else [])
    return items


def normalize(rec, budgets=None):
    """One recommendation in the dashboard's words. `budgets` maps campaign/ad set id → daily cents."""
    content = rec.get("recommendation_content") or {}
    key = type_key(rec.get("type") or rec.get("recommendation_name"))
    label, applies, note = TYPES.get(key, (human(key), None, None))
    points = rec.get("opportunity_score_lift") or content.get("opportunity_score_lift")
    try:
        points = int(float(points)) if points not in (None, "") else None
    except ValueError:
        points = None
    out = {"type": key, "label": label, "body": content.get("body"), "lift": content.get("lift_estimate"),
           "points": points, "url": rec.get("url"), "object_ids": [str(i) for i in rec.get("object_ids") or []],
           "signature": rec.get("recommendation_signature"), "stage": rec.get("recommendation_stage"),
           "applies": applies, "note": note, "can_apply": bool(rec.get("recommendation_signature")) and key in APPLY_HERE,
           "budget": None, "key": fix_key(rec), "fix": CLAUDE_FIX.get(key, DEFAULT_FIX)}
    if key == "SCALE_GOOD_CAMPAIGN":
        out["budget"] = budget_step(rec, budgets or {})
        if out["budget"]["to"] is None and out["can_apply"]:
            out["can_apply"] = False
            out["note"] = "Meta didn't give an amount the console can show you first, so apply it in Ads Manager."
    out["can_fix"] = not out["can_apply"]
    return out


def budget_step(rec, budgets):
    """What Meta proposes to add, against today's budget: {from, add, to, pct, big}."""
    extra = (rec.get("recommendation_data") or {}).get("additional_budget") or (rec.get("recommendation_content") or {}).get("additional_budget")
    ids = [str(i) for i in rec.get("object_ids") or []]
    current = next((budgets[i] for i in ids if budgets.get(i)), None)
    import money_rules
    add = money_rules.recommendation_amount(extra)  # whole cents only; anything else isn't guessed
    if not add or not current:
        return {"from": current, "add": add, "to": None, "pct": None, "big": None}
    pct = add / current
    return {"from": current, "add": add, "to": current + add, "pct": round(pct * 100), "big": pct > BIG_STEP}


def ranked(recs, budgets=None):
    out = [normalize(r, budgets) for r in recs]
    out.sort(key=lambda r: (-(r["points"] or 0), r["label"]))
    return out


def extra_data(rec):
    """POST extra_data for the types applied here (object_selection = the objects Meta named)."""
    if rec["type"] in ("ADVANTAGE_PLUS_AUDIENCE", "AUTOMATIC_PLACEMENTS"):
        return {}
    return {"object_selection": ",".join(rec["object_ids"])} if rec["object_ids"] else {}
