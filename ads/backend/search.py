"""Search across the console (the command menu): pure helpers."""

SWIPE_WORDS = 44


def fair_share(groups, limit):
    """Cuts several lists of results (campaigns, ad sets, ads, leads…) to `limit` in all, one place per
    kind in turn, so a kind listed last is never pushed out by the ones before it. Places a short kind
    leaves unused go to the others; each list keeps its own order."""
    take = [0] * len(groups)
    left = limit
    while left > 0:
        moved = False
        for i, g in enumerate(groups):
            if left > 0 and take[i] < len(g):
                take[i] += 1
                left -= 1
                moved = True
        if not moved:
            break
    return [list(g[:n]) for g, n in zip(groups, take)]


def like_pattern(q):
    """A contains-match for ILIKE where %, _ and \\ typed by a person mean themselves."""
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def swipe_title(row):
    """A saved competitor ad named by its Page and the start of its words."""
    text = " ".join(str(row.get("title") or row.get("body") or "").split())
    if not text:
        return row["page_name"]
    if len(text) > SWIPE_WORDS:
        cut = text[:SWIPE_WORDS + 1]
        cut = cut.rsplit(" ", 1)[0] if " " in cut else text[:SWIPE_WORDS]
        text = cut.rstrip(" ,.;:-–") + "…"
    return f"{row['page_name']}: {text}"
