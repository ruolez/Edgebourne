"""One ad, several versions. Meta can't edit a creative, but a running ad can be pointed at a new
one: it keeps its ID and its results. Pure: what a new creative changes, whether Meta stored it
faithfully, and how an ad's daily results divide among its versions."""
import placements

METRICS = ("spend_cents", "impressions", "link_clicks", "leads", "video_3s")
REVIEW_STATES = ("IN_PROCESS", "PENDING_REVIEW", "DISAPPROVED")


def _media(spec):
    return (spec or {}).get("video_data") or (spec or {}).get("link_data") or {}


def _asset(spec):
    if (spec or {}).get("video_data"):
        return "video", str(spec["video_data"].get("video_id"))
    return "image", str(_media(spec).get("image_hash"))


def _headline(spec):
    return " ".join(str(_media(spec).get("title") or _media(spec).get("name") or "").split())


def _text(spec):
    return " ".join(str(_media(spec).get("message") or "").split())


def _button(spec):
    return (_media(spec).get("call_to_action") or {}).get("type")


def change_words(old, new):
    """What a new creative changes, as a short phrase ("New video and headline"), or None."""
    parts = []
    if _asset(old) != _asset(new):
        parts.append(_asset(new)[0])
    if _headline(old) != _headline(new):
        parts.append("headline")
    if _text(old) != _text(new):
        parts.append("text")
    if _button(old) != _button(new):
        parts.append("button")
    if not parts:
        return None
    return "New " + (parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}")


def readback_problem(want, made):
    """What's wrong with the creative Meta stored, or None. Checked before it goes on the ad."""
    got = (made or {}).get("object_story_spec") or {}
    if _asset(want) != _asset(got):
        return f"Meta's copy of the new creative has a different {_asset(want)[0]}."
    if _headline(want) != _headline(got) or _text(want) != _text(got):
        return "Meta's copy of the new creative has different words."
    if placements.form_ids(want) != placements.form_ids(got):
        return "Meta's copy of the new creative lost the lead form, so the button wouldn't open your form."
    return None


def with_live_days(versions, ready, today, in_review):
    """Each version with `live_on`: the day Meta approved it (`ready` = times the ad left review),
    today while the newest is still in review, else the day of the switch."""
    out = []
    for i, v in enumerate(versions):
        if v["started_on"] is None:
            out.append({**v, "live_on": None})
            continue
        following = versions[i + 1]["started_at"] if i + 1 < len(versions) else None
        day = next((r["day"] for r in ready if r["at"] >= v["started_at"] and (following is None or r["at"] < following)), None)
        if day is None:
            day = today if following is None and in_review else v["started_on"]
        out.append({**v, "live_on": day})
    return out


def _zero():
    return {"days": 0, **{m: 0 for m in METRICS}}


def owner_index(day, versions):
    """Which version (its index) a day's results belong to, or None on a changeover day."""
    current = 0
    for i, v in enumerate(versions[1:], 1):
        if day < v["started_on"]:
            break
        if day <= (v.get("live_on") or v["started_on"]):
            return None
        current = i
    return current


def split_results(days, versions):
    """(one total per version, changeover total). Days from a switch until Meta approved it could
    be either version, so they count for neither and are shown apart."""
    totals = [_zero() for _ in versions]
    changeover = _zero()
    for row in days:
        i = owner_index(row["day"], versions)
        total = changeover if i is None else totals[i]
        total["days"] += 1
        for m in METRICS:
            total[m] += int(row.get(m) or 0)
    return totals, changeover
