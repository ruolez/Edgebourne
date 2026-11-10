"""Instant Form builder: turn what Eugene fills in into Meta's leadgen_forms request, check
the questions against Meta's lead ads rules first, and read an existing form back into the
same shape so it can be copied (Meta forms can't be edited once created).

Rules (meta-ads skill, references/12 §8.3): no questions asking for financial details, health,
insurance, government IDs, account numbers, criminal history, politics, religion, race,
sexuality, union membership, usernames or passwords, or a child's birth date; no custom
question that repeats a prefilled field (name, email, phone); a privacy policy web page."""
import re

STANDARD = {"FULL_NAME": "Full name", "EMAIL": "Email", "PHONE": "Phone number",
            "COMPANY_NAME": "Company name", "JOB_TITLE": "Job title", "CITY": "City", "ZIP": "ZIP code"}
REQUIRED_STANDARD = ("FULL_NAME", "EMAIL", "PHONE")
MAX_CUSTOM = 3
MAX_OPTIONS = 6
DEFAULT_PRIVACY = "https://edgebourne.com/privacy"
LIMITS = {"name": 200, "intro_title": 60, "bullet": 80, "label": 120, "option": 80, "thanks_title": 60, "thanks_body": 300}

# (pattern, why) checked on every word Eugene writes into the form
PROHIBITED = [
    (r"\b(income|salary|salaries|earn(?:ings)?|net worth|credit score|credit card|debt|bankrupt\w*|loan|mortgage|routing number|bank account|annual revenue|revenue in dollars|how much (?:do you|does your \w+) make)\b",
     "financial details (income, credit, debt, revenue in dollars)"),
    (r"\b(health|medical|diagnos\w*|illness|disease|disabilit\w*|medication|pregnan\w*|mental health)\b", "health information"),
    (r"\b(insurance|insurer|policy number)\b", "insurance details"),
    (r"\b(ssn|social security|driver'?s licen[cs]e|passport|tax id|ein|government id|military id)\b", "a government ID"),
    (r"\b(account number|member(?:ship)? number|loyalty number)\b", "an account number"),
    (r"\b(criminal|arrest\w*|convict\w*|felony)\b", "criminal history"),
    (r"\b(politic\w*|vote|voting|democrat\w*|republican\w*)\b", "politics"),
    (r"\b(religio\w*|church|faith)\b", "religion or beliefs"),
    (r"\b(race|ethnicity|ethnic)\b", "race or ethnicity"),
    (r"\b(sexual\w*|gay|lesbian)\b", "sexual orientation"),
    (r"\b(union member\w*|trade union)\b", "union membership"),
    (r"\b(password|username)\b", "a username or password"),
    (r"\b(child'?s (?:birth|date of birth|age)|kid'?s birthday)\b", "a child's date of birth"),
]
PREFILL_REPEAT = re.compile(r"^\s*(what(?:'s| is) your )?(full )?(name|e-?mail(?: address)?|phone(?: number)?|cell(?: number)?)\??\s*$", re.I)


def policy_problems(spec):
    """[(where, why)] for anything Meta would reject the form or its ads for."""
    out = []
    texts = [("Intro", spec.get("intro_title") or "")] + [("Intro", b) for b in spec.get("intro_bullets") or []]
    for i, q in enumerate(spec.get("custom") or [], 1):
        texts.append((f"Question {i}", q.get("label") or ""))
        texts += [(f"Question {i}", o) for o in q.get("options") or []]
        if PREFILL_REPEAT.match(q.get("label") or ""):
            out.append((f"Question {i}", "it repeats a prefilled field (name, email or phone); Meta already asks for it"))
    for where, text in texts:
        for pattern, why in PROHIBITED:
            if re.search(pattern, text, re.I):
                out.append((where, f"it asks about {why}, which Meta doesn't allow on Instant Forms"))
                break
    url = spec.get("privacy_url") or ""
    if not re.match(r"^https://[^\s/]+\.[^\s]+$", url) or url.lower().endswith(".pdf"):
        out.append(("Privacy policy", "it needs a web page address starting with https:// (not a PDF)"))
    return out


def problems(spec):
    """[(field, message)] for missing or too-long values (before the policy check)."""
    out = []
    if not (spec.get("name") or "").strip():
        out.append(("name", "Give the form a name (only you see it)"))
    if not (spec.get("intro_title") or "").strip():
        out.append(("intro_title", "Write the headline people see first"))
    for key, limit in (("name", LIMITS["name"]), ("intro_title", LIMITS["intro_title"]), ("thanks_title", LIMITS["thanks_title"]),
                       ("thanks_body", LIMITS["thanks_body"])):
        if len(spec.get(key) or "") > limit:
            out.append((key, f"Keep it to {limit} characters"))
    if any(len(b) > LIMITS["bullet"] for b in spec.get("intro_bullets") or []):
        out.append(("intro_bullets", f"Keep each point to {LIMITS['bullet']} characters"))
    custom = spec.get("custom") or []
    if len(custom) > MAX_CUSTOM:
        out.append(("custom", f"At most {MAX_CUSTOM} questions of your own"))
    for i, q in enumerate(custom, 1):
        opts = [o for o in q.get("options") or [] if o.strip()]
        if not (q.get("label") or "").strip():
            out.append(("custom", f"Question {i} needs its wording"))
        elif len(q["label"]) > LIMITS["label"]:
            out.append(("custom", f"Question {i}: keep it to {LIMITS['label']} characters"))
        if len(opts) == 1 or len(opts) > MAX_OPTIONS:
            out.append(("custom", f"Question {i}: give 2 to {MAX_OPTIONS} answers to pick from, or none for a typed answer"))
        if any(len(o) > LIMITS["option"] for o in opts):
            out.append(("custom", f"Question {i}: keep each answer to {LIMITS['option']} characters"))
        if len({o.strip().lower() for o in opts}) != len(opts):
            out.append(("custom", f"Question {i}: two answers are the same"))
    if spec.get("thanks_button") == "website" and not re.match(r"^https://\S+$", spec.get("thanks_url") or ""):
        out.append(("thanks_url", "Give the page the button opens, starting with https://"))
    return out


def payload(spec):
    """The POST /{page_id}/leadgen_forms body (before JSON-encoding the objects)."""
    standard = [t for t in spec.get("standard") or [] if t in STANDARD and t not in REQUIRED_STANDARD]
    questions = [{"type": t, "key": t.lower()} for t in (*REQUIRED_STANDARD, *standard)]
    for i, q in enumerate(spec.get("custom") or [], 1):
        item = {"type": "CUSTOM", "key": f"question_{i}", "label": q["label"].strip()}
        opts = [o.strip() for o in q.get("options") or [] if o.strip()]
        if opts:
            item["options"] = [{"value": o, "key": f"q{i}_option_{j}"} for j, o in enumerate(opts, 1)]
        questions.append(item)
    bullets = [b.strip() for b in spec.get("intro_bullets") or [] if b.strip()]
    website = spec.get("thanks_button") == "website"
    out = {
        "name": spec["name"].strip(),
        "locale": "EN_US",
        "questions": questions,
        "privacy_policy": {"url": spec.get("privacy_url"), "link_text": "Privacy policy"},
        "context_card": {"title": spec["intro_title"].strip(), "style": "LIST_STYLE" if bullets else "PARAGRAPH_STYLE",
                         "content": bullets or [spec["intro_title"].strip()], "button_text": "Continue"},
        "thank_you_page": {"title": (spec.get("thanks_title") or "Thanks, you're all set").strip(),
                           "body": (spec.get("thanks_body") or "").strip(),
                           "button_type": "VIEW_WEBSITE" if website else "NONE",
                           **({"button_text": (spec.get("thanks_button_text") or "Visit our website").strip()[:30],
                               "website_url": spec["thanks_url"]} if website else {})},
        "is_optimized_for_quality": bool(spec.get("higher_intent")),
        "block_display_for_non_targeted_viewer": True,
    }
    if website:
        out["follow_up_action_url"] = spec["thanks_url"]
    return out


def spec_from_meta(form):
    """An existing Meta form back in the builder's shape, for "Copy into a new form"."""
    qs = form.get("questions") or []
    card = form.get("context_card") or {}
    thanks = form.get("thank_you_page") or {}
    content = card.get("content") or []
    url = thanks.get("website_url") or form.get("follow_up_action_url") or ""
    return {
        "name": f"{form.get('name') or 'Form'} (copy)",
        "intro_title": card.get("title") or "",
        "intro_bullets": content if card.get("style") == "LIST_STYLE" else [],
        "standard": [q["type"] for q in qs if q.get("type") in STANDARD and q["type"] not in REQUIRED_STANDARD],
        "custom": [{"label": q.get("label") or "", "options": [o.get("value") for o in q.get("options") or []]}
                   for q in qs if q.get("type") == "CUSTOM"][:MAX_CUSTOM],
        "higher_intent": bool(form.get("is_optimized_for_quality")),
        "privacy_url": (form.get("privacy_policy_url") or (form.get("privacy_policy") or {}).get("url") or ""),
        "thanks_title": thanks.get("title") or "",
        "thanks_body": thanks.get("body") or "",
        "thanks_button": "website" if url and thanks.get("button_type") in (None, "VIEW_WEBSITE") else "none",
        "thanks_button_text": thanks.get("button_text") or "",
        "thanks_url": url,
    }
