#!/usr/bin/env python3
"""Builds the three redesign direction mockups (a.html, b.html, c.html) from one markup.
Same content and structure in all three; each direction is its own stylesheet + font."""
import random

DIRS = {
    "a": ("Signal", "https://fonts.googleapis.com/css2?family=Geist:wght@400..700&family=Geist+Mono:wght@400..600&display=swap"),
    "b": ("Ledger", "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400..800&family=Newsreader:opsz,wght@6..72,500..600&display=swap"),
    "c": ("Studio", "https://fonts.googleapis.com/css2?family=Manrope:wght@400..800&display=swap"),
}

ICONS = {
 "today": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
 "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
 "leads": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
 "manage": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
 "insights": '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
 "claude": '<path d="M12 3l1.8 4.6L18 9.4l-4.2 1.8L12 16l-1.8-4.8L6 9.4l4.2-1.8z"/><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
 "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
 "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
 "chev": '<path d="m6 9 6 6 6-6"/>',
 "right": '<path d="m9 18 6-6-6-6"/>',
 "compare": '<rect x="3" y="4" width="7" height="16" rx="1.5"/><rect x="14" y="4" width="7" height="16" rx="1.5"/>',
 "power": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>',
 "tag": '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
 "archive": '<rect x="2" y="4" width="20" height="5" rx="1"/><path d="M4 9v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9M10 13h4"/>',
 "plus": '<path d="M12 5v14M5 12h14"/>',
 "cal": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
 "cols": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18"/>',
 "more": '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
 "x": '<path d="M18 6 6 18M6 6l12 12"/>',
 "check": '<path d="M20 6 9 17l-5-5"/>',
 "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
 "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
 "ban": '<circle cx="12" cy="12" r="9"/><path d="m5.7 5.7 12.6 12.6"/>',
 "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
 "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
 "wallet": '<path d="M19 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3"/><path d="M21 11h-5a2 2 0 0 0 0 4h5z"/>',
 "spark": '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
 "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
 "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
 "refresh": '<path d="M21 12a9 9 0 0 1-15.5 6.3L3 16M3 12a9 9 0 0 1 15.5-6.3L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>',
 "down": '<path d="M12 5v14M19 12l-7 7-7-7"/>',
 "up": '<path d="M12 19V5M5 12l7-7 7 7"/>',
 "learn": '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/>',
}
def ic(name, cls="i"):
    return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-{name}"/></svg>'
SPRITE = '<svg class="sprite" xmlns="http://www.w3.org/2000/svg">' + "".join(
    f'<symbol id="i-{k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{v}</symbol>' for k, v in ICONS.items()) + "</svg>"

# --- status vocabulary (one map, colour + icon + word) ---
ST = {
  "live":    ("Delivering", "check", "ok"),
  "learning":("Learning 9/50", "learn", "info"),
  "review":  ("In review · 2 h 14 m", "clock", "warn"),
  "rejected":("Rejected · Instagram", "ban", "bad"),
  "off":     ("Off", "power", "mute"),
  "issues":  ("With issues", "alert", "bad"),
}
def pill(kind, text=None):
    word, icon, tone = ST[kind]
    return f'<span class="pill t-{tone}">{ic(icon,"i pi")}<span>{text or word}</span></span>'

# 14-day delivery track: one cell per day, state letter per day
def track(states):
    cells = "".join(f'<i class="d-{s}"></i>' for s in states)
    return f'<span class="track" aria-label="Last 14 days of delivery">{cells}</span>'

def spark(points, cls="sp"):
    w, h = 84, 24
    mx = max(points) or 1
    if not max(points): points = [0]*len(points)
    step = w / (len(points) - 1)
    pts = " ".join(f"{i*step:.1f},{h - 2 - (p/mx)*(h-4):.1f}" for i, p in enumerate(points))
    return f'<svg class="{cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="{pts}"/></svg>'

random.seed(7)
ADS = [
 # name, short, status, track, spend, leads, cpl, d_cpl, ctr, hook, thumb, sel, extra
 ("N4 – Weekly report", "N4", "live", "L"*14, "$46.45", "11", "$4.22", ("-14%", "good"), "1.08%", "29.7%", 4, True, "best"),
 ("N5 – Quote to invoice", "N5", "live", "L"*14, "$50.17", "10", "$5.02", ("-8%", "good"), "1.08%", "31.2%", 5, True, ""),
 ("N3 – Same work twice", "N3", "live", "LLLLLLLLLLLLLL", "$51.00", "9", "$5.67", ("+12%", "bad"), "1.07%", "29.6%", 3, True, ""),
 ("N2 – Order portal", "N2", "learning", "OOLLLLLLLLLLLL", "$48.68", "10", "$4.87", ("-3%", "good"), "1.07%", "28.2%", 2, False, ""),
 ("N1 · v2 – One simple system", "N1 · v2", "review", "OOOOOOOOOOOOOR", "$0.00", "–", "–", ("new", "mute"), "–", "–", 6, False, ""),
 ("N1 – One simple system", "N1", "off", "LLLLLLLLLLLLOO", "$44.55", "11", "$4.05", ("–", "mute"), "1.05%", "29.8%", 1, False, ""),
 ("TEST e – Image, order portal", "TEST e", "rejected", "OOOOOOOOOOOOXX", "$0.00", "–", "–", ("–", "mute"), "–", "–", 7, False, "test"),
]
SPARKS = {n[1]: ([random.randint(1, 9) for _ in range(14)] if n[5] != "–" else [0]*14) for n in ADS}

def thumb(n, cls="th"):
    return f'<span class="{cls} g{n}" aria-hidden="true"><span class="th-ink">{["","N1","N2","N3","N4","N5","v2","TE"][n]}</span></span>'

def rail(active):
    items = [("Work", [("today","Today",""),("inbox","Inbox","3"),("leads","Leads","2")]),
             ("Run", [("manage","Ads",""),("insights","Insights",""),("claude","Claude","1")])]
    out = ['<aside class="rail"><div class="acct"><span class="mark">EB</span><span class="acct-name"><b>Edge Bourne</b><small>Meta ad account</small></span>' + ic("chev","i acct-chev") + '</div>',
           '<button class="jump" type="button">' + ic("search") + '<span>Search or jump to…</span><kbd>⌘K</kbd></button><nav class="nav">']
    for group, links in items:
        out.append(f'<div class="nav-group"><span class="nav-label">{group}</span>')
        for key, label, badge in links:
            cur = ' aria-current="page"' if key == active else ""
            b = f'<span class="count{" claude" if key=="claude" else ""}">{badge}</span>' if badge else ""
            out.append(f'<a href="#"{cur}>{ic(key)}<span>{label}</span>{b}</a>')
        out.append('</div>')
    out.append('</nav><div class="rail-foot"><a href="#" class="setlink">' + ic("settings") + '<span>Settings</span></a>'
               '<div class="cap"><div class="cap-row"><span>Spending limit</span><b>$114.69 left</b></div><div class="meter"><i class="m-24"></i></div><small>of $150 · runs out about Nov 15</small></div>'
               '<div class="me"><span class="avatar">EU</span><span><b>Eugene</b><small>Owner</small></span></div></div></aside>')
    return "".join(out)

def topline(crumbs, extra=""):
    cr = ' <span class="sep">/</span> '.join(f'<a href="#">{c}</a>' if i < len(crumbs)-1 else f'<span aria-current="page">{c}</span>' for i, c in enumerate(crumbs))
    return f'<div class="topline"><nav class="crumbs" aria-label="Breadcrumb">{cr}</nav><span class="grow"></span>{extra}<span class="fresh">{ic("refresh")}Updated 4 min ago</span></div>'

def manager():
    rows = []
    for (name, short, st, tr, spend, leads, cpl, dcpl, ctr, hook, th, sel, extra) in ADS:
        cb = f'<span class="cb{" on" if sel else ""}" role="checkbox" aria-checked="{"true" if sel else "false"}">{ic("check","i cbi") if sel else ""}</span>'
        best = '<span class="best">Lowest</span>' if extra == "best" else ""
        tg = '<span class="mini-tag">Test</span>' if extra == "test" else ""
        rows.append(f'''<tr class="st-{st}{" sel" if sel else ""}{" dim" if st in ("off",) else ""}">
<td class="c-cb">{cb}</td>
<td class="c-name"><span class="namecell">{thumb(th)}<span class="nm"><b>{name}{tg}</b><small>SoCal business owners · video 4:5</small></span></span></td>
<td class="c-st">{track(tr)}{pill(st)}</td>
<td class="num">{spend}</td><td class="num">{leads}</td>
<td class="num strong">{cpl}{best}</td>
<td class="num"><span class="delta d-{dcpl[1]}">{dcpl[0]}</span></td>
<td class="num">{ctr}</td><td class="num">{hook}</td>
<td class="c-sp">{spark(SPARKS[short])}</td></tr>''')
    figs = [("Spent","$241.30","+9%","mute"),("Leads","51","+21%","good"),("Cost per lead","$4.73","−10%","good"),("Qualified","12","+3","good"),("Per qualified lead","$20.11","target $60","mute")]
    fig = "".join(f'<div class="fig"><span class="fig-l">{l}</span><b class="fig-v">{v}</b><span class="delta d-{t}">{d}</span></div>' for l, v, d, t in figs)
    views = [("All ads","7",True),("Delivering","4",False),("In review","1",False),("Needs attention","1",False),("Learning","1",False),("Tests","2",False)]
    vw = "".join(f'<button class="view{" on" if on else ""}" type="button">{n}<span>{c}</span></button>' for n, c, on in views)
    return f'''<section class="frame desk" id="s-manager" data-title="Ads manager · selection · bulk bar">
{rail("manage")}
<main class="main">
{topline(["Ads","Free intro call – Leads","All ad sets"])}
<header class="pagehead"><div><h1>Ads</h1><p class="sub">1 campaign · 1 ad set · 7 ads</p></div><span class="grow"></span>
<div class="seg" role="tablist"><button class="on">Ads</button><button>Ad sets</button><button>Campaigns</button><button>Lead forms</button></div>
<button class="btn ghost">{ic("claude")}Ask Claude</button><button class="btn primary">{ic("plus")}New{ic("chev","i sm")}</button></header>
<div class="figs">{fig}</div>
<div class="toolbar"><div class="views">{vw}<button class="view add" type="button">{ic("plus","i sm")}Save view</button></div><span class="grow"></span>
<button class="tool">{ic("cal")}Last 14 days <span class="vs">vs previous</span>{ic("chev","i sm")}</button><button class="tool">{ic("cols")}Columns: Results</button></div>
<div class="tablewrap"><table class="grid"><thead><tr><th class="c-cb"><span class="cb some" role="checkbox" aria-checked="mixed"><i></i></span></th><th>Ad</th><th>Delivery <small>last 14 days</small></th><th class="num">Spent</th><th class="num">Leads</th><th class="num sorted">Cost per lead {ic("up","i sm")}</th><th class="num">vs prev</th><th class="num">Click rate</th><th class="num">Hook rate</th><th>Leads / day</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<div class="bulk" role="toolbar" aria-label="3 ads selected"><span class="bulk-n"><b>3</b> selected</span>
<span class="film">{thumb(4,"th xs")}{thumb(5,"th xs")}{thumb(3,"th xs")}</span>
<button class="btn primary sm">{ic("compare")}Compare</button><button class="btn quiet sm">{ic("power")}Turn off</button><button class="btn quiet sm">{ic("tag")}Tag idea</button><button class="btn quiet sm">{ic("claude")}Ask Claude</button><button class="btn quiet sm">{ic("archive")}Archive</button><button class="icon x" aria-label="Clear selection">{ic("x")}</button></div>
</main></section>'''

def adpage():
    tl = [
      ("done","console","9:02 AM","Created from Claude's idea #5","Approved by you · made off · ad id …325970312"),
      ("done","console","9:04 AM","You turned it on","Campaign spends $31.00 a day; nothing else changed"),
      ("done","meta","9:05 AM","Sent to Meta review","Meta checks text, video and the landing form"),
      ("now","meta","Now","In review for 2 h 14 m","Your last 6 ads took 1 h 40 m – 3 h 12 m (median 2 h 40 m)"),
      ("next","meta","Next","Approved → Delivering","You'll get a push and an Inbox item the moment it changes"),
      ("next","meta","Then","Learning: 0 of 50 leads","Ad set exits learning after about 50 leads in 7 days"),
    ]
    items = "".join(f'<li class="ev ev-{s} src-{src}"><span class="ev-dot"></span><span class="ev-time">{t}</span><div class="ev-body"><b>{h}</b><small>{d}</small></div><span class="ev-src">{"Console" if src=="console" else "Meta"}</span></li>' for s, src, t, h, d in tl)
    return f'''<section class="frame desk" id="s-ad" data-title="Ad page · review status timeline">
{rail("manage")}
<main class="main">
{topline(["Ads","Free intro call – Leads","SoCal business owners","N1 · v2"])}
<header class="pagehead"><span class="hero-th">{thumb(6,"th lg")}</span><div><h1>N1 · v2 – One simple system</h1><p class="sub">{pill("review")} <span class="sep-dot">·</span> Video 4:5 + 9:16 · Instant form “Free intro call”</p></div><span class="grow"></span>
<button class="btn quiet">{ic("compare")}Compare</button><button class="btn quiet">{ic("more")}</button><span class="switch on" role="switch" aria-checked="true"><i></i><span>On</span></span></header>
<div class="tabs"><a aria-current="page">Status &amp; history</a><a>Overview</a><a>Polish</a><a>Audience</a><a>Video</a><a>Comments</a></div>
<div class="adgrid">
<div class="card review"><div class="card-h"><h2>Meta review</h2><span class="grow"></span><span class="hint">{ic("spark","i sm")}Live from Meta webhooks</span></div>
<ol class="timeline">{items}</ol></div>
<div class="side">
<div class="card prev"><div class="card-h"><h2>Preview</h2><span class="grow"></span><div class="seg sm"><button class="on">Feed</button><button>Reels</button><button>Stories</button></div></div>
<div class="phoneprev"><div class="pp-head"><span class="mark sm">EB</span><span><b>Edge Bourne Consulting</b><small>Sponsored</small></span></div><p class="pp-text">Running your business on five apps and a spreadsheet? One simple system for quotes, orders and invoices.</p><div class="pp-media g6"><span class="play"></span></div><div class="pp-cta"><span><small>EDGEBOURNE.COM</small><b>Free 30-minute intro call</b></span><span class="pp-btn">Book now</span></div></div></div>
<div class="card fam"><div class="card-h"><h2>Earlier versions</h2></div>
<div class="famrow">{thumb(1,"th sm")}<span><b>N1 – One simple system</b><small>Approved in 3 h 12 m · 11 leads · $4.05 each · off since Nov 9</small></span>{pill("off")}</div></div>
</div></div>
</main></section>'''

def compare():
    cols = [(4,"N4 – Weekly report","live"),(5,"N5 – Quote to invoice","live"),(3,"N3 – Same work twice","live")]
    head = "".join(f'<th><div class="cmp-h">{thumb(n,"th md")}<b>{name}</b>{pill(st)}<span class="swatch s{i}"></span></div></th>' for i,(n,name,st) in enumerate(cols))
    metrics = [
      ("Spent", ["$46.45","$50.17","$51.00"], ["+6%","+9%","+11%"], None),
      ("Leads", ["11","10","9"], ["+38%","+11%","−10%"], 0),
      ("Cost per lead", ["$4.22","$5.02","$5.67"], ["−14%","−8%","+12%"], 0),
      ("Qualified leads", ["3","2","2"], ["+1","0","−1"], 0),
      ("Per qualified lead", ["$15.48","$25.09","$25.50"], ["","",""], 0),
      ("Click rate", ["1.08%","1.08%","1.07%"], ["","",""], None),
      ("Hook rate", ["29.7%","31.2%","29.6%"], ["","",""], 1),
      ("Frequency", ["1.4","1.5","1.6"], ["","",""], None),
    ]
    body = []
    for label, vals, ds, best in metrics:
        cells = []
        for i, v in enumerate(vals):
            d = ds[i]
            dt = "" if not d else f'<span class="delta d-{"good" if (d.startswith("−") and "Cost" in label) or (d.startswith("+") and "Cost" not in label and label!="Spent") else ("mute" if label=="Spent" or d in ("0",) else "bad")}">{d}</span>'
            low = label in ("Cost per lead", "Per qualified lead")
            mark = f'<span class="best">{"Lowest" if low else "Highest"}</span>' if best == i else ""
            cells.append(f'<td class="num{" win" if best==i else ""}"><b>{v}</b><span class="cmp-sub">{dt}{mark}</span></td>')
        body.append(f'<tr><th scope="row">{label}</th>{"".join(cells)}</tr>')
    # chart: 3 lines of leads/day
    series = [[0,1,1,0,1,1,0,1,1,1,0,2,1,1],[1,0,1,1,0,1,1,0,1,0,1,1,1,1],[1,1,0,1,0,0,1,1,0,1,1,0,1,1]]
    W,H = 560,150
    lines = ""
    for i, s in enumerate(series):
        cum=[];t=0
        for v in s: t+=v; cum.append(t)
        pts=" ".join(f"{20+j*(W-40)/13:.1f},{H-18-(c/12)*(H-36):.1f}" for j,c in enumerate(cum))
        lines += f'<polyline class="ln s{i}" points="{pts}"/>'
    grid = "".join(f'<line class="gl" x1="20" x2="{W-20}" y1="{H-18-(k/12)*(H-36):.1f}" y2="{H-18-(k/12)*(H-36):.1f}"/><text class="gt" x="0" y="{H-15-(k/12)*(H-36):.1f}">{k}</text>' for k in (0,4,8,12))
    chart = f'<svg class="cmp-chart" viewBox="0 0 {W} {H}" aria-label="Leads over 14 days, running total">{grid}{lines}</svg>'
    return f'''<section class="frame desk" id="s-compare" data-title="Compare 3 ads side by side">
{rail("insights")}
<main class="main">
{topline(["Insights","Compare"])}
<header class="pagehead"><div><h1>Compare 3 ads</h1><p class="sub">Last 14 days (Oct 27 – Nov 9) vs the 14 days before</p></div><span class="grow"></span>
<button class="btn quiet">{ic("plus")}Add an ad</button><button class="btn quiet">{ic("claude")}Ask Claude which to keep</button><button class="btn primary">Save as test</button></header>
<div class="verdict">{ic("alert","i")}<div><b>Too early to name a winner.</b> N4 has the lowest cost per lead, but no ad has spent $120 yet (2× your $60 target per qualified lead). About 5 more days at today's pace.</div></div>
<div class="cmpwrap"><table class="cmp"><thead><tr><th class="cmp-corner"><span>Last 14 days</span></th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>
<div class="card chartcard"><div class="card-h"><h2>Leads, running total</h2><span class="grow"></span><div class="seg sm"><button class="on">Leads</button><button>Cost per lead</button><button>Spent</button></div></div>{chart}
<div class="tags"><div><span class="tl">Hook</span><span class="chip">Weekly report pain</span><span class="chip">Quote → invoice</span><span class="chip">Double entry</span></div><div><span class="tl">Angle</span><span class="chip">Time saved</span><span class="chip">Cash flow</span><span class="chip">Mistakes</span></div></div></div></div>
</main></section>'''

def inbox():
    items = [
      ("bad","ban","TEST e was rejected on Instagram","Meta: “Personal attributes” in the text. Facebook placements are fine.","10:41 AM",True,True),
      ("lead","leads","New lead: Dana Whitfield, Riverside","From N4 – Weekly report · waiting 4 min","10:37 AM",True,False),
      ("warn","clock","N1 · v2 is in review","Sent to Meta at 9:05 AM after you turned it on","9:05 AM",False,False),
      ("claude","claude","Claude suggests: raise Free intro call to $37/day","+20% · cost per lead 21% under target for 7 days","8:30 AM",True,False),
      ("ok","check","N2 is approved again and delivering","Your edit on Nov 9 passed review in 1 h 52 m","Yesterday",False,False),
      ("info","learn","SoCal business owners is Learning limited","9 of 50 leads in 7 days; budget or audience too small to exit","Yesterday",False,False),
      ("warn","wallet","Spending limit: $114.69 left","At $31/day it stops ads about Nov 15","Yesterday",False,False),
      ("mute","edit","Budget changed in Ads Manager","$20.00 → $31.00 a day, not from this console","Mon",False,False),
    ]
    li = lambda k,i,t,d,w,u,c: f'<li class="it{" unread" if u else ""}{" cur" if c else ""} k-{k}"><span class="it-ic">{ic(i)}</span><div class="it-b"><b>{t}</b><small>{d}</small></div><span class="it-t">{w}</span></li>'
    today_l = "".join(li(*x) for x in items[:4]); earlier_l = "".join(li(*x) for x in items[4:])
    return f'''<section class="frame desk" id="s-inbox" data-title="Inbox · everything that changed">
{rail("inbox")}
<main class="main">
{topline(["Inbox"])}
<header class="pagehead"><div><h1>Inbox</h1><p class="sub">3 unread · approvals, rejections, leads, Claude and alerts in one place</p></div><span class="grow"></span><button class="btn quiet">{ic("check")}Mark all read</button></header>
<div class="toolbar"><div class="views"><button class="view on">Unread<span>3</span></button><button class="view">All</button><button class="view">Ad status<span>3</span></button><button class="view">Leads<span>1</span></button><button class="view">Claude<span>1</span></button><button class="view">Money</button></div></div>
<div class="inboxgrid"><ul class="ilist"><li class="ihead">Today</li>{today_l}<li class="ihead">Earlier</li>{earlier_l}</ul>
<div class="card idetail"><div class="id-head">{thumb(7,"th md")}<div><span class="kicker">Rejected by Meta · 10:41 AM</span><h2>TEST e – Image, order portal</h2>{pill("rejected")}</div></div>
<div class="reasons"><div class="reason"><span class="pl">Instagram feed, Stories, Reels</span><b>Personal attributes</b><p>Ads can't imply knowledge of someone's personal characteristics. Flagged line: “<mark>Are you</mark> still copying orders by hand?”</p></div>
<div class="reason ok"><span class="pl">Facebook placements</span><b>Approved</b><p>Delivering is allowed on Facebook, but the ad is off.</p></div></div>
<div class="id-actions"><button class="btn primary">{ic("claude")}Ask Claude for a fixed version</button><button class="btn quiet">{ic("edit")}Edit text</button><button class="btn quiet">Request another review</button></div>
<div class="id-foot"><b>History</b><span>Created Nov 9 · turned on 10:12 AM · in review 29 min · rejected 10:41 AM</span></div></div></div>
</main></section>'''

def phones():
    tabs = lambda cur: '<nav class="p-tabs">' + "".join(f'<a{" aria-current=\"page\"" if k==cur else ""}>{ic(k)}<span>{l}</span>{f"<i class=count>{b}</i>" if b else ""}</a>' for k,l,b in [("today","Today",""),("leads","Leads","2"),("manage","Ads",""),("inbox","Inbox","3"),("menu","More","")]) + '</nav>'
    today = f'''<div class="phone"><header class="p-top"><span class="mark sm">EB</span><b>Today</b><span class="grow"></span><span class="icon">{ic("search")}</span><span class="avatar sm">EU</span></header>
<div class="p-body"><p class="p-date">Tuesday, Nov 10</p>
<div class="p-figs"><div><small>Spent today</small><b>$18.40</b></div><div><small>Leads</small><b>4</b></div><div><small>Per lead</small><b>$4.60</b></div></div>
<h3 class="p-h">Needs you <span>4</span></h3>
<ul class="p-list"><li class="k-lead"><span class="it-ic">{ic("leads")}</span><div><b>Call Dana Whitfield</b><small>New lead · Riverside · N4</small></div><span class="clock">4 min</span></li>
<li class="k-bad"><span class="it-ic">{ic("ban")}</span><div><b>TEST e rejected on Instagram</b><small>Personal attributes</small></div>{ic("right","i sm")}</li>
<li class="k-claude"><span class="it-ic">{ic("claude")}</span><div><b>Raise budget to $37/day?</b><small>Claude · +20% · under target 7 days</small></div><span class="mini-btn">Review</span></li>
<li class="k-warn"><span class="it-ic">{ic("clock")}</span><div><b>N1 · v2 in review</b><small>2 h 14 m · usually under 3 h</small></div>{ic("right","i sm")}</li></ul></div>{tabs("today")}</div>'''
    rows = "".join(f'<li class="p-ad st-{st}">{thumb(th,"th sm")}<div class="p-ad-b"><b>{short}</b><span>{pill(st)}</span><small>{spend} · {leads} leads · {cpl}</small></div>{('<span class="sel-dot">' + ic("check","i sm") + "</span>") if sel else ""}</li>' for (name, short, st, tr, spend, leads, cpl, d, ctr, hook, th, sel, ex) in ADS[:6])
    manage = f'''<div class="phone"><header class="p-top"><span class="mark sm">EB</span><b>Ads</b><span class="grow"></span><span class="icon">{ic("search")}</span><span class="avatar sm">EU</span></header>
<div class="p-body"><div class="p-views"><span class="view on">All 7</span><span class="view">Delivering 4</span><span class="view">In review 1</span><span class="view">Needs attention 1</span></div>
<ul class="p-ads">{rows}</ul></div>
<div class="p-bulk"><b>3 selected</b><span class="grow"></span><span class="mini-btn primary">{ic("compare","i sm")}Compare</span><span class="mini-btn">{ic("more","i sm")}</span></div>{tabs("manage")}</div>'''
    return f'<section class="frame phones" id="s-phone" data-title="Phone · Today queue and Ads">{today}{manage}</section>'

def page(key):
    name, font = DIRS[key]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} · Ads console redesign</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{font}"><link rel="stylesheet" href="base.css"><link rel="stylesheet" href="{key}.css"></head>
<body class="dir-{key}">{SPRITE}
<div class="sheet-title"><h1>Direction {key.upper()} · {name}</h1></div>
{manager()}{adpage()}{compare()}{inbox()}{phones()}
</body></html>'''

for k in DIRS:
    open(f"{k}.html", "w").write(page(k))
print("ok")
