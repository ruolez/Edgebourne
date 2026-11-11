"""Concept tags (roadmap 5.1): each ad carries one value per dimension (hook, angle, format,
persona, offer); results are summed per value so a question like "which hook wins across ads"
has an answer. Pure: grouping and the minimum-data rule (a group is judged only once it has
spent twice the target cost per lead and has 3 or more leads)."""

DIMENSIONS = {
    "hook": ("Hook", "The first thing people see or read"),
    "angle": ("Angle", "The problem or promise the ad is about"),
    "persona": ("Who it's for", "The kind of business or person it speaks to"),
    "format": ("Format", "Video, image, length, shape"),
    "offer": ("Offer", "What people get for filling in the form"),
}
MIN_LEADS = 3
SPEND_TIMES = 2
UNTAGGED = "Not tagged"


def clean_value(v):
    v = " ".join(str(v or "").split())[:80]
    return v[:1].upper() + v[1:] if v else ""


def group(ads, tags, dimension, target_cents=None):
    """ads: [{id, spend_cents, impressions, leads, qualified, video_3s, thruplays, video_impressions}]
    (video_impressions: the impressions of video ads, so image ads don't dilute the hook rate);
    tags: {ad_id: {dimension: value}}. One row per value, cheapest judged group first."""
    groups = {}
    for a in ads:
        value = (tags.get(a["id"]) or {}).get(dimension) or UNTAGGED
        g = groups.setdefault(value, {"value": value, "ads": 0, "spend_cents": 0, "impressions": 0, "leads": 0,
                                      "qualified": 0, "video_3s": 0, "thruplays": 0, "video_impressions": 0})
        g["ads"] += 1
        for k in ("spend_cents", "impressions", "leads", "qualified", "video_3s", "thruplays", "video_impressions"):
            g[k] += a.get(k) or 0
    total_leads = sum(g["leads"] for g in groups.values())
    target = target_cents or (round(sum(g["spend_cents"] for g in groups.values()) / total_leads) if total_leads else None)
    out = []
    for g in groups.values():
        g["cpl_cents"] = round(g["spend_cents"] / g["leads"]) if g["leads"] else None
        g["hook_rate"] = g["video_3s"] / g["video_impressions"] if g["video_impressions"] else None
        g["hold_rate"] = g["thruplays"] / g["video_3s"] if g["video_3s"] else None
        g["qualified_rate"] = g["qualified"] / g["leads"] if g["leads"] else None
        g["enough"] = g["leads"] >= MIN_LEADS and (not target or g["spend_cents"] >= SPEND_TIMES * target)
        out.append(g)
    out.sort(key=lambda g: (g["value"] == UNTAGGED, not g["enough"], g["cpl_cents"] is None, g["cpl_cents"] or 0, -g["spend_cents"]))
    judged = [g for g in out if g["enough"] and g["cpl_cents"] is not None and g["value"] != UNTAGGED]
    best = judged[0]["value"] if len(judged) >= 2 else None
    sure = None
    if best:
        import experiments
        sure = experiments.confidence("cpl", judged[0], judged[1])
    for g in out:
        g["best"] = g["value"] == best
    return {"groups": out, "target_cents": target, "best": best, "best_confidence": sure,
            "best_is_clear": sure is not None and sure >= experiments_win()}


def experiments_win():
    import experiments
    return experiments.WIN


def merge(existing, changes, source):
    """New tag rows for an ad: changes {dim: value}; '' removes. Returns (upserts, deletes)."""
    up, down = [], []
    for dim, value in (changes or {}).items():
        if dim not in DIMENSIONS:
            continue
        v = clean_value(value)
        if v:
            if (existing or {}).get(dim) != v:
                up.append((dim, v, source))
        elif dim in (existing or {}):
            down.append(dim)
    return up, down
