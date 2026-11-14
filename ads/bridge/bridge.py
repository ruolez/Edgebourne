#!/usr/bin/env python3
"""ads-desk bridge: keeps the Ads console Desk connected to Claude Code on this Mac.

Run by launchd (~/Library/LaunchAgents/com.edgebourne.ads-desk.plist, KeepAlive).
It long-polls the dashboard (costs nothing while idle: no AI runs), and when a
request arrives it starts one headless Claude Code run in the meta-ads workspace:

    claude -p "/ads-desk run <id>" --permission-mode dontAsk --allowedTools <read-only list>
              --disallowedTools <secrets>

dontAsk + the allow list mean the run can read ads, insights, the workspace and the
skill library and talk to the Desk about its own request, and nothing else: no budget,
status, publish or delete tools, no files outside the workspace and ~/.claude/skills, and
for another business's or a teammate's request not the other businesses' files either.
Anything that should change comes back as a proposal.
"""
import datetime
import importlib.machinery
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
desk = importlib.machinery.SourceFileLoader("desk", os.path.join(HERE, "desk")).load_module()
try:  # AM-A (desk 3.1): the Mac's own read-only link to Meta's Ads MCP server; an older install has no amlink.py
    amlink = importlib.machinery.SourceFileLoader("amlink", os.path.join(HERE, "amlink.py")).load_module()
except (OSError, ImportError):
    amlink = None

RUN_LIMIT_SECONDS = 25 * 60
RENDER_LIMIT_SECONDS = 50 * 60
ADVICE_LIMIT_SECONDS = 90 * 60  # an advice run may cut a 9:16 version of every running ad
KEEPALIVE_SECONDS = 5  # also how quickly Stop on the Claude page reaches a run
LINK_LIMIT_SECONDS = 10 * 60  # one fallback link pass through Claude
RESUME_FAIL_SECONDS = 45  # a resumed run that dies this fast couldn't load its session: start fresh
LOG_DIR = os.path.expanduser("~/Library/Logs/ads-desk")

READ_TOOLS = [
    "ads_get_ad_accounts", "ads_get_ad_entities", "ads_get_ad_preview", "ads_get_ad_preview_screenshot",
    "ads_get_ad_images", "ads_get_ad_videos", "ads_get_creatives", "ads_get_creative_ads",
    "ads_get_ad_account_pages", "ads_get_pages_for_business", "ads_get_user_pages", "ads_get_ig_accounts",
    "ads_get_ig_media", "ads_get_errors", "ads_get_field_context", "ads_get_help_article",
    "ads_get_opportunity_score", "ads_get_async_result", "ads_get_datasets", "ads_get_dataset_details",
    "ads_get_dataset_quality", "ads_get_dataset_stats", "ads_get_customconversions",
    "ads_get_ad_account_custom_audiences", "ads_get_custom_audience", "ads_get_custom_audience_adsets",
    "ads_insights_advertiser_context", "ads_insights_anomaly_signal", "ads_insights_auction_ranking_benchmarks",
    "ads_insights_industry_benchmark", "ads_insights_performance_trend", "ads_insights_performance_vs_peers",
    "ads_library_search", "ads_account_get_activity_logs", "ads_experiment_list_tests",
    "ads_experiment_abtest_get_test", "ads_experiment_lift_get_test", "ads_experiment_check_eligibility",
    "ads_pixel_event_read", "ads_pixel_parameter_read",
]
# FU-D: every other tool the meta-ads server lists (2026-11-13), catalog reads included (lead ads don't use them).
# Denied by name in full runs, on top of not being allowed: only Accept on the console writes to Meta.
META_WRITE_TOOLS = [
    "ads_activate_entity", "ads_boost_ig_post", "ads_catalog_create", "ads_catalog_create_feed_rule",
    "ads_catalog_create_product_feed", "ads_catalog_create_product_feed_upload_session",
    "ads_catalog_create_product_set", "ads_catalog_delete_product", "ads_catalog_event_source_connect",
    "ads_catalog_event_source_disconnect", "ads_catalog_event_source_get", "ads_catalog_event_source_get_catalogs",
    "ads_catalog_event_source_get_health", "ads_catalog_event_source_get_recommendations",
    "ads_catalog_get_businesses", "ads_catalog_get_data_sources", "ads_catalog_get_diagnostics",
    "ads_catalog_get_dynamic_ads_health", "ads_catalog_get_feed_rules", "ads_catalog_get_product_feed_upload_sessions",
    "ads_catalog_list_catalogs", "ads_catalog_list_dpa_eligible_catalogs", "ads_catalog_list_partner_integrations",
    "ads_catalog_list_product_feeds", "ads_catalog_list_product_sets", "ads_catalog_list_products",
    "ads_catalog_product_create", "ads_catalog_product_feed_delete", "ads_catalog_product_feed_delete_rule",
    "ads_catalog_product_set_delete", "ads_catalog_update_catalog", "ads_catalog_update_feed_rule",
    "ads_catalog_update_product", "ads_catalog_update_product_feed", "ads_catalog_update_product_set", "ads_create_ad",
    "ads_create_ad_set", "ads_create_campaign", "ads_create_creative", "ads_create_custom_audience",
    "ads_creative_create_image_variations", "ads_creative_delete", "ads_creative_update",
    "ads_creative_update_image_elements", "ads_creative_upload_local_image", "ads_creative_upload_media",
    "ads_delete_custom_audience", "ads_delete_local_ad_image", "ads_experiment_abtest_create_test",
    "ads_experiment_abtest_update_test", "ads_experiment_lift_create_test", "ads_finalize_local_ad_image_upload",
    "ads_log_ui_interaction", "ads_pixel_event_create", "ads_pixel_event_delete", "ads_pixel_event_update",
    "ads_pixel_parameter_create", "ads_pixel_parameter_delete", "ads_pixel_parameter_update",
    "ads_update_custom_audience", "ads_update_entity", "offer_report",
]
META_PREFIXES = ("meta-ads", "claude_ai_Meta_Ads")
# FU-D: a full-access run (the owner's own typed request in his own account, unlocked on the console with his password)
# gets the terminal's tools. It still runs in dontAsk mode, so every `ask` rule in ~/.claude/settings.json and the
# meta-ads guard hook's prompts are denied, and the Meta write tools are denied by name. Files are written only in the
# workspace (Edit rules cover Write), and Bash runs inside Claude Code's own OS sandbox (full_settings).
FULL_TOOLS = ["Bash", "Read", "Glob", "Grep", "WebFetch", "WebSearch", "Skill", "ToolSearch", "Task", "TodoWrite"]
# Eugene's other servers, allowed whole. Not Playwright or Claude in Chrome: MCP servers run outside the Bash sandbox
# and a browser reaches Meta's sites (security review).
FULL_MCP_SERVERS = ("brave-search",)
FULL_DENIED_SERVERS = ("playwright", "claude-in-chrome")
# Meta's and Anthropic's hosts: never from a full run's Bash (no host is allowed anyway) or WebFetch.
META_DOMAINS = ["facebook.com", "*.facebook.com", "graph.facebook.com", "mcp.facebook.com", "*.facebook.net", "*.fbcdn.net",
                "instagram.com", "*.instagram.com"]
CLAUDE_DOMAINS = ["anthropic.com", "*.anthropic.com", "claude.ai", "*.claude.ai", "claude.com", "*.claude.com"]


WEB_KINDS = ("question", "review", "research", "creative")  # runs that read the web; render runs don't need it
# Read-only runs: Meta's read tools, the workspace, the skills and `desk`, nothing else. Listed one by one
# (a kind this helper doesn't know also gets only these, but a new kind is never left to that default).
READ_ONLY_KINDS = ("question", "review", "research", "creative", "polish", "diagnose")
RENDER_KINDS = ("render", "advice")  # these also render video on this Mac (node, ffmpeg, files under creatives/)


def allowed_tools(skill_dir, workdir, kind="question", web=False, access="sandbox"):
    """Read-only by default. Permission paths: `//abs/path` is absolute, a bare path is
    relative to the working directory (`/path` would mean relative to a settings file).
    Files are read only in the workspace and ~/.claude/skills (Read rules also cover Glob and
    Grep there), never elsewhere on the Mac (audit A3-4). The web only for a reading run an
    owner asked for (`web`): text from teammates or clients never meets WebFetch (A3-7).
    access "full" (FU-D, decided by the server at claim): the terminal's tools and Meta's read tools."""
    if access == "full":
        return (FULL_TOOLS + [f"Edit(/{workdir}/**)"] + [f"mcp__{s}" for s in FULL_MCP_SERVERS]
                + [f"mcp__{p}__{n}" for n in READ_TOOLS for p in META_PREFIXES])
    def files(rel):
        return [f"Edit({rel}/**)", f"Edit(/{workdir}/{rel}/**)"]
    tools = [f"Read(/{workdir}/**)", f"Read(/{os.path.dirname(skill_dir)}/**)", "ToolSearch", "Skill",
             f"Bash({skill_dir}/desk:*)", "Bash(~/.claude/skills/ads-desk/desk:*)"]
    if web and kind in WEB_KINDS:
        tools += ["WebSearch", "WebFetch"]
    # JSON for scorecards and proposals is written to files here and passed with --file
    # (heredocs with JSON get refused by the permission checker).
    tools += files("reports/desk")
    # Applied budget, on/off and spending-limit suggestions reach reports/log.md through `desk log-applied` (fixed
    # lines from the dashboard's record), so a run reading outside text can't rewrite the change log (FU-B).
    for name in READ_TOOLS:
        tools += [f"mcp__meta-ads__{name}", f"mcp__claude_ai_Meta_Ads__{name}"]
    # Polish looks at video frames through `desk frames` / `desk probe`, which open only videos in the
    # workspace: ffmpeg, ffprobe and ls themselves open any path on the Mac.
    # A kind on READ_ONLY_KINDS (Diagnose with Claude among them) never renders, whatever else lists it;
    # an unknown kind (a newer server) is read only too.
    if kind in RENDER_KINDS and kind not in READ_ONLY_KINDS:
        tools += ["Bash(ffmpeg:*)", "Bash(ffprobe:*)", "Bash(mkdir:*)", "Bash(ls:*)"]
        # "Make a new version" (and Meta's advice, e.g. a 9:16 cut for Reels): the ad-creative-render pipeline (Node + headless Chrome +
        # ffmpeg) inside the workspace's creatives folder. Still no Meta write tools: the
        # result goes back through `desk upload` and a proposal Eugene approves.
        tools += files("creatives") + ["Bash(node:*)", "Bash(cp:*)", "Bash(sips:*)", "Bash(shasum:*)", "Bash(cd:*)"]
        # Every upload is a write to the ad account, and every write is logged.
        tools += ["Edit(reports/log.md)", f"Edit(/{workdir}/reports/log.md)"]
    return tools


def denied_tools(workdir, home, private=(), access="sandbox"):
    """Secrets stay unreadable even inside the allowed folders (the workspace keeps the Meta CLI
    token in .env), and so do `private` workspace paths (see private_paths). Deny rules win over
    allow rules and also apply to Glob and Grep. A full run (FU-D) also may not write to Meta by any
    road (MCP write tools, the `meta` CLI), touch the Keychain or LaunchAgents, or edit Claude's own
    settings, hooks or this skill. These rules guard the obvious paths; Bash reaches past file rules
    (README "Claude on the Mac")."""
    base = ["Read(**/.env)", "Read(**/.env.*)", f"Read(/{workdir}/.env)", f"Read(/{workdir}/.env.*)",
            f"Read(/{home}/.config/**)", f"Read(/{home}/.ssh/**)", f"Read(/{home}/.aws/**)",
            f"Read(/{home}/.gnupg/**)", f"Read(/{home}/Library/Keychains/**)"]
    if access != "full":
        return base + [f"Read(/{workdir}/{p})" for p in private]
    return (base + [f"mcp__{p}__{n}" for n in META_WRITE_TOOLS for p in META_PREFIXES]
            + [f"mcp__{s}" for s in FULL_DENIED_SERVERS]
            + [f"WebFetch(domain:{d})" for d in META_DOMAINS]
            + ["Bash(meta:*)", "Bash(security:*)", "Bash(/usr/bin/security:*)", "Bash(env:*)", "Bash(command security:*)",
               "Bash(exec security:*)", "Bash(xcrun security:*)", "Bash(launchctl:*)", "Bash(claude:*)",
               f"Read(/{home}/.claude/.credentials.json)", f"Read(/{home}/.claude.json)",
               f"Edit(/{home}/.claude/settings.json)", f"Edit(/{home}/.claude/settings.local.json)",
               f"Edit(/{home}/.claude/hooks/**)", f"Edit(/{home}/.claude/skills/ads-desk/**)",
               f"Edit(/{home}/Library/LaunchAgents/**)"])


def full_settings(workdir, home, skill_dir):
    """`--settings` for a full run: Bash inside Claude Code's OS sandbox (macOS Seatbelt). Tool names don't stop a
    script (`python3 x.py` that reads a token and posts to Meta), the sandbox does: no network at all (dontAsk refuses
    every host not allowed, and Meta's and Anthropic's are denied by name as well), no reads of the Keychain files,
    Claude's credentials, ~/.ssh, ~/.config or the workspace .env, the Claude token unset, writes only in the workspace
    and the temp folder (the sandbox's default), and no way to retry outside it. Only `desk` runs outside: a fixed
    script that checks its own paths and talks to the console. If the sandbox can't start, the run doesn't either."""
    return {"sandbox": {
        "enabled": True,
        "failIfUnavailable": True,
        "allowUnsandboxedCommands": False,
        "autoAllowBashIfSandboxed": True,
        "excludedCommands": [f"{skill_dir}/desk *", "~/.claude/skills/ads-desk/desk *"],
        "network": {"allowedDomains": [], "deniedDomains": META_DOMAINS + CLAUDE_DOMAINS, "allowLocalBinding": False},
        "filesystem": {"denyRead": [f"{home}/Library/Keychains", f"{home}/.claude/.credentials.json", f"{home}/.claude.json",
                                    f"{home}/.ssh", f"{home}/.aws", f"{home}/.gnupg", f"{home}/.config", f"{home}/.netrc",
                                    f"{workdir}/.env"]},
        "credentials": {"envVars": [{"name": n, "mode": "deny"} for n in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")]},
    }}


def run_access(task, confirm):
    """"full" only when the claim answer says so for a request claimed with a pass AND a fresh read of the
    request with that pass (`confirm`) says so too; anything else is the sandbox (FU-D: the server decides)."""
    return "full" if task.get("claim_token") and task.get("access") == "full" and confirm == "full" else "sandbox"


def claude_command(cfg, task, access, home, briefs):
    """The headless run's command line. The sandbox is byte for byte what it was before full access existed."""
    kind = task.get("kind")
    render = kind in ("render", "advice")
    skill_dir = os.path.join(home, ".claude", "skills", "ads-desk")
    full = access == "full"
    tools = allowed_tools(skill_dir, cfg["workdir"], kind, web=task.get("from_owner") is True, access=access)
    denied = denied_tools(cfg["workdir"], home, [] if full else private_paths(task, briefs), access=access)
    return [cfg["claude"], "-p", f"/ads-desk run {task['id']}",
            "--permission-mode", "dontAsk",
            "--allowedTools", ",".join(tools),
            "--disallowedTools", ",".join(denied),
            "--max-turns", "200" if full else "300" if kind == "advice" else "200" if render else "80"] + (
        ["--settings", json.dumps(full_settings(cfg["workdir"], home, skill_dir))] if full else [])


def link_guard_settings(skill_dir):
    """`--settings` for a fallback link run: a PreToolUse hook (`desk link-guard`) checks every MCP call against the pass
    outside the model: only the link's read tools, only the pass's ad account (ADS_LINK_ACT), only their fixed
    arguments. Text Meta returns can't steer the run to another ad account."""
    return {"hooks": {"PreToolUse": [{"matcher": "mcp__.*", "hooks": [{"type": "command", "command": f"{skill_dir}/desk link-guard"}]}]}}


def link_fallback_command(cfg, run, home):
    """AM-A fallback, when Meta won't take the Mac's own link client: a cheap headless Claude run that calls exactly the
    link's read tools and hands each answer to `desk link-push` with the pass in ADS_LINK_PASS. No other Bash, no web,
    files only in reports/desk/tmp/link/, every Meta write tool denied by name, and the guard hook binding each call
    to the pass's ad account (link_guard_settings)."""
    skill_dir = os.path.join(home, ".claude", "skills", "ads-desk")
    link_dir = f"/{cfg['workdir']}/reports/desk/tmp/link/**"
    tools = [f"mcp__{p}__{t}" for t in sorted(set(amlink.LINK_TOOLS.values())) for p in META_PREFIXES]
    for d in (skill_dir, "~/.claude/skills/ads-desk"):
        tools += [f"Bash({d}/desk link-plan:*)", f"Bash({d}/desk link-push:*)", f"Bash({d}/desk link-finish:*)"]
    tools += [f"Edit({link_dir})", f"Read({link_dir})", "Skill", "ToolSearch"]
    denied = (denied_tools(cfg["workdir"], home) + [f"mcp__{p}__{n}" for n in META_WRITE_TOOLS for p in META_PREFIXES]
              + ["WebFetch", "WebSearch", "Bash(meta:*)", "Bash(security:*)"])
    return [cfg["claude"], "-p", f"/ads-desk link {int(run['run_id'])}", "--model", "haiku", "--permission-mode", "dontAsk",
            "--max-turns", "40", "--allowedTools", ",".join(tools), "--disallowedTools", ",".join(denied),
            "--settings", json.dumps(link_guard_settings(skill_dir))]


def run_link_fallback(cfg, token, run):
    """One link pass through Claude on this Mac (10 minutes at most). A pass Claude left open is closed as failed."""
    os.makedirs(os.path.join(cfg["workdir"], "reports", "desk", "tmp", "link"), exist_ok=True)
    env = dict(os.environ)
    for name in ("DESK_CLAIM", "DESK_ACCOUNT"):
        env.pop(name, None)
    env["ADS_LINK_PASS"] = run["pass"]
    env["ADS_LINK_ACT"] = f"act_{int(run['ad_account_id'])}"  # the guard hook allows this ad account only
    claude_token = claude_oauth_token()
    if claude_token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = claude_token
    env["PATH"] = os.pathsep.join([os.path.dirname(cfg["claude"]), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", env.get("PATH", "")])
    out_path = os.path.join(LOG_DIR, f"link-{int(run['run_id'])}.log")
    code = None
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(out_path, "w") as out:
            proc = subprocess.Popen(link_fallback_command(cfg, run, os.path.expanduser("~")), cwd=cfg["workdir"], stdout=out,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        try:
            code = proc.wait(timeout=LINK_LIMIT_SECONDS)
        except subprocess.TimeoutExpired:
            end_process(proc)
    except OSError as exc:
        log(f"link pass {run['run_id']}: Claude Code could not start: {exc}")
    pass_header = {"X-Link-Pass": run["pass"]}
    try:
        _, now = desk.call("GET", f"/api/agent/link/runs/{int(run['run_id'])}", cfg=cfg, token=token, extra_headers=pass_header)
        if (now or {}).get("status") == "open":
            desk.call("POST", "/api/agent/link/finish", {"status": "failed", "error": f"Claude stopped without finishing (exit code {code})"},
                      cfg=cfg, token=token, extra_headers=pass_header)
    except (desk.DeskError, urllib.error.URLError, OSError):
        pass


def link_loop(cfg):
    """AM-A: asks the console every minute what to read from Ads Manager (a long poll, nothing runs while idle) and does
    it: connect, disconnect, or one pass per account, directly or through Claude. Never starts a desk task."""
    backoff = 5
    while True:
        try:
            token = desk.key(cfg)
        except SystemExit:
            time.sleep(120)
            continue
        try:
            status, plan = desk.call("GET", "/api/agent/link/plan?timeout=25", cfg=cfg, token=token, timeout=45)
            backoff = 5
            if status == 200 and plan:
                state = amlink.handle_plan(cfg, token, plan, log=log, fallback=lambda run: run_link_fallback(cfg, token, run))
                if state == "connecting":
                    time.sleep(60)  # Meta couldn't be reached: the console hands the login out again in a minute
                elif state == "unconfirmed":
                    time.sleep(30)  # the console didn't take the result: don't repeat a disconnect or a login at once
        except desk.DeskError as exc:
            log(f"link: the console refused ({exc})")
            time.sleep(600 if exc.status == 404 else 120 if exc.status == 401 else 30)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
        except Exception as exc:  # noqa: BLE001 - the link must never take the bridge down
            log(f"link: {exc}")
            time.sleep(60)


def squash(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def private_paths(task, briefs):
    """Workspace paths a run can't read when its answer goes to someone other than the owner: a request
    for another business (its admins and clients read the answer) or one a teammate wrote. The workspace
    is shared, so those runs see only their own business's brief (`briefs/<name>.md`), never the
    owner's state, workspace reports or the local copies of every account's Desk answers (review of
    audit A3-7). Render and advice runs keep `reports/log.md`, where they log uploads; node reaches past
    every file rule anyway, see README "Claude on the Mac"."""
    if task.get("account_id") in (None, 1) and task.get("from_owner") is True:
        return []
    own = squash(task.get("account_name"))
    paths = [f"briefs/{b}" for b in briefs
             if not (own and squash(os.path.splitext(b)[0]) and own.startswith(squash(os.path.splitext(b)[0])))]
    paths += ["state/**", "reports/*.html", "reports/desk/*.md"]
    if task.get("kind") not in ("render", "advice"):
        paths.append("reports/*.md")
    return paths


def workspace_briefs(workdir):
    try:
        return sorted(os.listdir(os.path.join(workdir, "briefs")))
    except OSError:
        return []


def claude_oauth_token():
    """Optional long-lived token from `claude setup-token`, kept in the Keychain by
    install.sh. Without it, runs use this Mac's normal sign-in, which expires."""
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", "ads-desk-claude", "-w"],
                             capture_output=True, text=True)
    except OSError:
        return None
    return out.stdout.strip() or None


def log(msg):
    print(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}", flush=True)


def post_status(cfg, token, task_id, claim, **body):
    try:
        desk.call("POST", f"/api/agent/tasks/{task_id}/status", body, cfg=cfg, token=token, claim=claim)
        return True
    except (desk.DeskError, urllib.error.URLError, OSError) as exc:
        log(f"task {task_id}: status update refused: {exc}")
        return False


def end_process(proc):
    """Ends the Claude run and everything it started. It may already be gone."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        time.sleep(5)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def read_task(cfg, token, task_id, claim):
    """The request as the dashboard has it now; "gone" when it is no longer this run's (requeued after a
    lost answer, or deleted); None when the dashboard can't be reached."""
    try:
        _, current = desk.call("GET", f"/api/agent/tasks/{task_id}", cfg=cfg, token=token, claim=claim)
    except desk.DeskError as exc:
        return "gone" if exc.status in (403, 404, 409) else None
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return current or "gone"


def task_state(cfg, token, task_id, claim):
    """The request's status on the dashboard ("gone" / None as read_task)."""
    current = read_task(cfg, token, task_id, claim)
    return current["status"] if isinstance(current, dict) else current


def ends_run(state):
    """After the dashboard refused a keep-alive: end Claude unless it finished the request itself
    (it is just exiting) or the dashboard can't be reached (try again). Stopped from the page,
    expired while the Mac slept, failed or picked up again: Claude stops now (audit A3-29)."""
    return state is not None and state != "done"


def session_id(cfg, task_id):
    """Each task's Claude session has a known id, so a follow-up can continue it."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{cfg['base_url']}/desk-task/{task_id}"))


def session_file(cfg, sid):
    project = re.sub(r"[^A-Za-z0-9]", "-", cfg["workdir"])
    return os.path.expanduser(f"~/.claude/projects/{project}/{sid}.jsonl")


def session_args(cfg, task):
    """A follow-up continues the last turn's session; without one it starts fresh and reads the
    conversation from `desk task`."""
    own = session_id(cfg, task["id"])
    previous = task.get("resume_from")
    if previous and os.path.exists(session_file(cfg, session_id(cfg, previous))):
        return ["--resume", session_id(cfg, previous), "--fork-session", "--session-id", own]
    return ["--session-id", own]


def run_task(cfg, token, task):
    task_id = task["id"]
    claim = task.get("claim_token")  # this run's pass: only it can use the task from now on
    # FU-D: full access only when the claim answer says so and a fresh read with this run's pass agrees.
    confirm = read_task(cfg, token, task_id, claim) if claim and task.get("access") == "full" else None
    access = run_access(task, confirm.get("access") if isinstance(confirm, dict) else None)
    log(f"task {task_id} ({task['kind']}{', full access' if access == 'full' else ''}): starting Claude")
    post_status(cfg, token, task_id, claim, status="running", progress="Claude is starting on your Mac")
    out_path = os.path.join(LOG_DIR, f"task-{task_id}.log")
    render = task.get("kind") in ("render", "advice") or access == "full"  # long runs: they render video on this Mac
    cmd = claude_command(cfg, task, access, os.path.expanduser("~"), workspace_briefs(cfg["workdir"]))
    session = session_args(cfg, task)
    env = dict(os.environ)
    env["DESK_ACCOUNT"] = str(task.get("account_id") or 1)  # the task's ad account (agency mode)
    env.pop("DESK_CLAIM", None)
    if claim:
        env["DESK_CLAIM"] = claim  # every `desk` call of the run sends it
    claude_token = claude_oauth_token()
    if claude_token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = claude_token
    env["PATH"] = os.pathsep.join([os.path.dirname(cfg["claude"]), "/opt/homebrew/bin", "/usr/local/bin",
                                   "/usr/bin", "/bin", "/usr/sbin", "/sbin", env.get("PATH", "")])
    def launch(extra):
        with open(out_path, "a") as out:
            return subprocess.Popen(cmd + extra, cwd=cfg["workdir"], stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, start_new_session=True)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        open(out_path, "w").close()
        started = time.monotonic()
        proc = launch(session)
    except OSError as exc:
        # A moved Claude Code (reinstall, Homebrew path change) or an unwritable log (audit A3-81).
        log(f"task {task_id}: Claude Code could not start: {exc}")
        post_status(cfg, token, task_id, claim, status="failed",
                    error=f"Claude Code could not start on the Mac ({exc}). Re-run ads/bridge/install.sh on the Mac.")
        return
    live = {"proc": proc}
    stop = threading.Event()

    def keepalive():
        while not stop.wait(KEEPALIVE_SECONDS):
            try:
                desk.call("POST", f"/api/agent/tasks/{task_id}/status", {"status": "running"}, cfg=cfg, token=token, claim=claim)
            except desk.DeskError as exc:
                if exc.status == 409:
                    # Finished by the skill (Claude is just exiting), stopped from the page, or
                    # expired while the Mac slept: only the first lets Claude carry on.
                    state = task_state(cfg, token, task_id, claim)
                    if state is None:
                        continue
                    if ends_run(state):
                        log(f"task {task_id}: the dashboard closed it ({state}); ending Claude")
                        end_process(live["proc"])
                    return
                log(f"task {task_id}: keepalive refused: {exc}")
            except (urllib.error.URLError, OSError) as exc:
                log(f"task {task_id}: keepalive failed: {exc}")

    threading.Thread(target=keepalive, daemon=True).start()
    limit = ADVICE_LIMIT_SECONDS if task.get("kind") == "advice" else RENDER_LIMIT_SECONDS if render else RUN_LIMIT_SECONDS
    try:
        proc.wait(timeout=limit)
        if ("--resume" in session and proc.returncode != 0 and time.monotonic() - started < RESUME_FAIL_SECONDS
                and not stop.is_set() and task_state(cfg, token, task_id, claim) in ("claimed", "running")):
            log(f"task {task_id}: could not continue the earlier session; starting fresh")
            proc = live["proc"] = launch(["--session-id", str(uuid.uuid4())])
            proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        end_process(live["proc"])
        log(f"task {task_id}: stopped after the time limit")
    finally:
        stop.set()

    if task_state(cfg, token, task_id, claim) in ("claimed", "running"):
        try:
            with open(out_path) as fh:
                tail = fh.read()[-600:].strip()
        except OSError:
            tail = ""
        reason = (f"Claude stopped without finishing (exit code {proc.returncode})."
                  + (f" Last output: {tail}" if tail else "") + f" Full log on the Mac: {out_path}")
        post_status(cfg, token, task_id, claim, status="failed", error=reason[:1900])
    log(f"task {task_id}: finished, exit code {proc.returncode}")


def main():
    cfg = desk.config()
    log(f"ads-desk bridge {desk.VERSION} watching {cfg['base_url']}")
    if amlink:
        threading.Thread(target=link_loop, args=(cfg,), name="ads-manager-link", daemon=True).start()
    if not os.access(cfg.get("claude") or "", os.X_OK):
        log(f"Claude Code isn't at {cfg.get('claude')} any more: requests will fail until ads/bridge/install.sh runs again")
    backoff = 5
    while True:
        try:
            token = desk.key(cfg)
        except SystemExit as exc:
            log(str(exc))
            time.sleep(120)
            continue
        try:
            status, task = desk.call("GET", "/api/agent/wait?timeout=25", cfg=cfg, token=token, timeout=45)
            backoff = 5
            if status == 200 and task:
                run_task(cfg, token, task)
        except desk.DeskError as exc:
            log(f"dashboard refused: {exc}")
            time.sleep(120 if exc.status == 401 else 30)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            log(f"dashboard unreachable ({exc}); retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
