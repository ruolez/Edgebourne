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

RUN_LIMIT_SECONDS = 25 * 60
RENDER_LIMIT_SECONDS = 50 * 60
ADVICE_LIMIT_SECONDS = 90 * 60  # an advice run may cut a 9:16 version of every running ad
KEEPALIVE_SECONDS = 5  # also how quickly Stop on the Claude page reaches a run
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


WEB_KINDS = ("question", "review", "research", "creative")  # runs that read the web; render runs don't need it
# Read-only runs: Meta's read tools, the workspace, the skills and `desk`, nothing else. Listed one by one
# (a kind this helper doesn't know also gets only these, but a new kind is never left to that default).
READ_ONLY_KINDS = ("question", "review", "research", "creative", "polish", "diagnose")
RENDER_KINDS = ("render", "advice")  # these also render video on this Mac (node, ffmpeg, files under creatives/)


def allowed_tools(skill_dir, workdir, kind="question", web=False):
    """Read-only by default. Permission paths: `//abs/path` is absolute, a bare path is
    relative to the working directory (`/path` would mean relative to a settings file).
    Files are read only in the workspace and ~/.claude/skills (Read rules also cover Glob and
    Grep there), never elsewhere on the Mac (audit A3-4). The web only for a reading run an
    owner asked for (`web`): text from teammates or clients never meets WebFetch (A3-7)."""
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


def denied_tools(workdir, home, private=()):
    """Secrets stay unreadable even inside the allowed folders (the workspace keeps the Meta CLI
    token in .env), and so do `private` workspace paths (see private_paths). Deny rules win over
    allow rules and also apply to Glob and Grep."""
    return (["Read(**/.env)", "Read(**/.env.*)", f"Read(/{workdir}/.env)", f"Read(/{workdir}/.env.*)",
             f"Read(/{home}/.config/**)", f"Read(/{home}/.ssh/**)", f"Read(/{home}/.aws/**)",
             f"Read(/{home}/.gnupg/**)", f"Read(/{home}/Library/Keychains/**)"]
            + [f"Read(/{workdir}/{p})" for p in private])


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


def task_state(cfg, token, task_id, claim):
    """The request's status on the dashboard; "gone" when it is no longer this run's (requeued after a
    lost answer, or deleted); None when the dashboard can't be reached."""
    try:
        _, current = desk.call("GET", f"/api/agent/tasks/{task_id}", cfg=cfg, token=token, claim=claim)
    except desk.DeskError as exc:
        return "gone" if exc.status in (403, 404, 409) else None
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return current["status"] if current else "gone"


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
    log(f"task {task_id} ({task['kind']}): starting Claude")
    post_status(cfg, token, task_id, claim, status="running", progress="Claude is starting on your Mac")
    out_path = os.path.join(LOG_DIR, f"task-{task_id}.log")
    skill_dir = os.path.expanduser("~/.claude/skills/ads-desk")
    render = task.get("kind") in ("render", "advice")  # long runs: they render video on this Mac
    tools = allowed_tools(skill_dir, cfg["workdir"], task.get("kind"), web=task.get("from_owner") is True)
    cmd = [cfg["claude"], "-p", f"/ads-desk run {task_id}",
           "--permission-mode", "dontAsk",
           "--allowedTools", ",".join(tools),
           "--disallowedTools", ",".join(denied_tools(cfg["workdir"], os.path.expanduser("~"),
                                                     private_paths(task, workspace_briefs(cfg["workdir"])))),
           "--max-turns", "300" if task.get("kind") == "advice" else "200" if render else "80"]
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
