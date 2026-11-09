#!/usr/bin/env python3
"""ads-desk bridge: keeps the Ads console Desk connected to Claude Code on this Mac.

Run by launchd (~/Library/LaunchAgents/com.edgebourne.ads-desk.plist, KeepAlive).
It long-polls the dashboard (costs nothing while idle: no AI runs), and when a
request arrives it starts one headless Claude Code run in the meta-ads workspace:

    claude -p "/ads-desk run <id>" --permission-mode dontAsk --allowedTools <read-only list>

dontAsk + the allow list mean the run can read ads, insights and the skill
library and talk to the Desk, and nothing else: no budget, status, publish or
delete tools. Anything that should change comes back as a proposal.
"""
import datetime
import importlib.machinery
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
desk = importlib.machinery.SourceFileLoader("desk", os.path.join(HERE, "desk")).load_module()

RUN_LIMIT_SECONDS = 25 * 60
RENDER_LIMIT_SECONDS = 50 * 60
KEEPALIVE_SECONDS = 60
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


def allowed_tools(skill_dir, workdir, kind="question"):
    """Read-only by default. Permission paths: `//abs/path` is absolute, a bare path is
    relative to the working directory (`/path` would mean relative to a settings file)."""
    def files(rel):
        return [f"Edit({rel}/**)", f"Edit(/{workdir}/{rel}/**)"]
    tools = ["Read", "Glob", "Grep", "ToolSearch", "Skill", "WebSearch", "WebFetch",
             f"Bash({skill_dir}/desk:*)", "Bash(~/.claude/skills/ads-desk/desk:*)"]
    # JSON for scorecards and proposals is written to files here and passed with --file
    # (heredocs with JSON get refused by the permission checker).
    tools += files("reports/desk")
    for name in READ_TOOLS:
        tools += [f"mcp__meta-ads__{name}", f"mcp__claude_ai_Meta_Ads__{name}"]
    if kind in ("polish", "render"):
        # Polish looks at video frames and contact sheets; render rebuilds the creative.
        tools += ["Bash(ffmpeg:*)", "Bash(ffprobe:*)", "Bash(mkdir:*)", "Bash(ls:*)"]
    if kind == "render":
        # "Make a new version": the ad-creative-render pipeline (Node + headless Chrome +
        # ffmpeg) inside the workspace's creatives folder. Still no Meta write tools: the
        # result goes back through `desk upload` and a proposal Eugene approves.
        tools += files("creatives") + ["Bash(node:*)", "Bash(cp:*)", "Bash(sips:*)", "Bash(shasum:*)", "Bash(cd:*)"]
    return tools


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


def post_status(cfg, token, task_id, **body):
    try:
        desk.call("POST", f"/api/agent/tasks/{task_id}/status", body, cfg=cfg, token=token)
        return True
    except (desk.DeskError, urllib.error.URLError, OSError) as exc:
        log(f"task {task_id}: status update refused: {exc}")
        return False


def run_task(cfg, token, task):
    task_id = task["id"]
    log(f"task {task_id} ({task['kind']}): starting Claude")
    post_status(cfg, token, task_id, status="running", progress="Claude is starting on your Mac")
    os.makedirs(LOG_DIR, exist_ok=True)
    out_path = os.path.join(LOG_DIR, f"task-{task_id}.log")
    skill_dir = os.path.expanduser("~/.claude/skills/ads-desk")
    render = task.get("kind") == "render"
    cmd = [cfg["claude"], "-p", f"/ads-desk run {task_id}",
           "--permission-mode", "dontAsk",
           "--allowedTools", ",".join(allowed_tools(skill_dir, cfg["workdir"], task.get("kind"))),
           "--max-turns", "200" if render else "80"]
    env = dict(os.environ)
    claude_token = claude_oauth_token()
    if claude_token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = claude_token
    env["PATH"] = os.pathsep.join([os.path.dirname(cfg["claude"]), "/opt/homebrew/bin", "/usr/local/bin",
                                   "/usr/bin", "/bin", "/usr/sbin", "/sbin", env.get("PATH", "")])
    with open(out_path, "w") as out:
        proc = subprocess.Popen(cmd, cwd=cfg["workdir"], stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    stop = threading.Event()

    def keepalive():
        while not stop.wait(KEEPALIVE_SECONDS):
            post_status(cfg, token, task_id, status="running")

    threading.Thread(target=keepalive, daemon=True).start()
    try:
        proc.wait(timeout=RENDER_LIMIT_SECONDS if render else RUN_LIMIT_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        time.sleep(5)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        log(f"task {task_id}: stopped after the time limit")
    finally:
        stop.set()

    try:
        _, current = desk.call("GET", f"/api/agent/tasks/{task_id}", cfg=cfg, token=token)
    except (desk.DeskError, urllib.error.URLError, OSError):
        current = None
    if current and current["status"] in ("claimed", "running"):
        try:
            with open(out_path) as fh:
                tail = fh.read()[-600:].strip()
        except OSError:
            tail = ""
        reason = (f"Claude stopped without finishing (exit code {proc.returncode})."
                  + (f" Last output: {tail}" if tail else "") + f" Full log on the Mac: {out_path}")
        post_status(cfg, token, task_id, status="failed", error=reason[:1900])
    log(f"task {task_id}: finished, exit code {proc.returncode}")


def main():
    cfg = desk.config()
    log(f"ads-desk bridge {desk.VERSION} watching {cfg['base_url']}")
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
