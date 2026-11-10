"""Replying to and hiding comments on an ad's post (roadmap 6.1). Pure checks: a comment id has
to belong to the ad's own post, and replies are plain text Meta accepts. Comments are never
deleted from here; hiding keeps them visible to the person who wrote them and their friends."""
MAX_REPLY = 8000


def post_part(story_id):
    """'<page>_<post>' → '<post>' (comment ids start with the post id)."""
    parts = str(story_id or "").split("_", 1)
    return parts[1] if len(parts) == 2 else None


def belongs(comment_id, story_id):
    post = post_part(story_id)
    return bool(post) and str(comment_id or "").startswith(post + "_") and str(comment_id).split("_", 1)[1].isdigit()


def clean_reply(text):
    t = str(text or "").strip()
    if not t:
        return None, "Write the reply first"
    if len(t) > MAX_REPLY:
        return None, f"Keep it under {MAX_REPLY:,} characters"
    return t, None


def shape(c, page_id):
    """One comment for the page: who, what, hidden, and its replies (the Page's own marked)."""
    replies = [{"id": r["id"], "message": r.get("message"), "created_time": r.get("created_time"),
                "name": (r.get("from") or {}).get("name"), "from_page": (r.get("from") or {}).get("id") == page_id}
               for r in ((c.get("comments") or {}).get("data") or [])]
    return {"id": c["id"], "message": c.get("message"), "created_time": c.get("created_time"),
            "name": (c.get("from") or {}).get("name"), "likes": c.get("like_count", 0), "replies": c.get("comment_count", len(replies)),
            "hidden": bool(c.get("is_hidden")), "can_hide": c.get("can_hide", True), "thread": replies,
            "answered": any(r["from_page"] for r in replies)}
