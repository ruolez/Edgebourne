"""Links into the console's own pages that more than one module builds. Pure."""
from urllib.parse import quote

PAGES = {"campaign": "/campaign.html", "adset": "/adset.html", "ad": "/ad.html"}


def history_href(level, entity_id, check=None):
    """The History tab of a campaign, ad set or ad. Campaign and ad set pages keep their tab in the query
    (UrlState), the ad page in the hash; ui.js historyHref says the same."""
    page = PAGES[level]
    q = f"?id={quote(str(entity_id), safe='')}"
    extra = f"&check={int(check)}" if check is not None else ""
    if level == "ad":
        return f"{page}{q}{extra}#tab=history"
    return f"{page}{q}&tab=history{extra}"
