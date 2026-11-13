"""Side-by-side compare of 2–6 ads (or ad sets, campaigns): one row per metric, the best cell marked,
and a verdict that refuses to name a winner before there is enough data (hard rule 7: spend at least
2× the target and at least 3 results each). Pure."""

ROWS = (  # key, label, direction (+1 higher is better, -1 lower is better, 0 no best)
    ("spend_cents", "Spent", 0),
    ("leads", "Leads", 1),
    ("cpl_cents", "Cost per lead", -1),
    ("qualified", "Qualified leads", 1),
    ("cpq_cents", "Cost per qualified lead", -1),
    ("booked", "Calls booked", 1),
    ("cpb_cents", "Cost per booked call", -1),
    ("ctr", "Click rate", 1),
    ("hook", "Hook rate", 1),
    ("hold", "Hold rate", 1),
    ("frequency", "Views per person", 0),
    ("cpm_cents", "Cost per 1,000 views", -1),
)


def _div(a, b):
    return a / b if b else None


def rates(t):
    spend, leads, q = t.get("spend_cents", 0), t.get("leads", 0), t.get("qualified", 0)
    imp = t.get("impressions", 0)
    out = dict(t)
    out["cpl_cents"] = round(spend / leads) if leads else None
    out["cpq_cents"] = round(spend / q) if q else None
    out["cpb_cents"] = round(spend / t["booked"]) if t.get("booked") else None
    out["ctr"] = _div(t.get("link_clicks", 0), imp)
    # Video impressions only: an image ad has no hook rate, and doesn't pull a mixed group's down (audit A3-65).
    out["hook"] = _div(t.get("video_3s", 0), t.get("video_impressions", 0))
    out["hold"] = _div(t.get("thruplays", 0), t.get("video_3s", 0))
    out["frequency"] = _div(imp, t.get("reach", 0))
    out["cpm_cents"] = round(spend * 1000 / imp) if imp else None
    return out


def _best(values, direction):
    present = [(v, i) for i, v in enumerate(values) if v is not None]
    if not direction or len(present) < 2:
        return None
    top = max(present) if direction > 0 else min(present)
    return None if sum(1 for v, _ in present if v == top[0]) > 1 else top[1]


def _delta(now, before):
    if now is None or not before:
        return None
    return round((now - before) * 100 / before)


BOOKED_ROWS = ("booked", "cpb_cents")


def shape(items, target_cents, lead_target_cents=None, booked=False):
    """booked: the account books calls (L1), so Calls booked and Cost per booked call get rows. They are shown,
    never judged: the verdict stays on qualified leads or leads. An item's `cmp` (FU-C) is its complete days when
    the figures include today so far: the verdict and the deltas read it; `cmp` None: today alone, no verdict."""
    cur = [rates(i["m"]) for i in items]
    today_only = any("cmp" in i and i["cmp"] is None for i in items)
    judged = [rates(i["cmp"]) if i.get("cmp") is not None else c for i, c in zip(items, cur)]
    prev = [rates(i["prev"]) if i.get("prev") else None for i in items]
    rows = []
    for key, label, direction in ROWS:
        if key in BOOKED_ROWS and not booked:
            continue
        values = [c.get(key) for c in cur]
        rows.append({"key": key, "label": label, "best": _best(values, direction),
                     "cells": [{"value": v, "delta_pct": _delta(j.get(key), p.get(key) if p else None)} for v, j, p in zip(values, judged, prev)]})
    if target_cents:
        metric, result, target = "cpq_cents", "qualified", target_cents
    else:
        metric, result, target = "cpl_cents", "leads", lead_target_cents
    need = 2 * target if target else None
    ready = not today_only and bool(need) and all(c["spend_cents"] >= need and c.get(result, 0) >= 3 for c in judged)
    leader = None
    if ready:
        idx = _best([c.get(metric) for c in judged], -1)
        leader = items[idx]["id"] if idx is not None else None
    return {"rows": rows, "verdict": {"ready": ready, "leader": leader, "metric": metric, "need_spend_cents": need,
                                      "need_results": 3, "result": result, "today_only": today_only}}
