"""Bridge unit tests (host Python, stdlib only): cd ads/bridge && python3 -m unittest test_bridge"""
import importlib.machinery
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
bridge = importlib.machinery.SourceFileLoader("bridge", os.path.join(HERE, "bridge.py")).load_module()
desk = bridge.desk

HOME = "/Users/someone"
WORKDIR = f"{HOME}/Desktop/Dev/meta-ads"
SKILL = f"{HOME}/.claude/skills/ads-desk"


def tools(kind, web=True):
    return bridge.allowed_tools(SKILL, WORKDIR, kind, web=web)


class AllowedToolsTests(unittest.TestCase):
    def test_files_are_read_only_in_the_workspace_and_the_skills(self):
        readers = [t for t in tools("render") if t.split("(")[0] in ("Read", "Glob", "Grep")]
        self.assertEqual(readers, [f"Read(/{WORKDIR}/**)", f"Read(/{HOME}/.claude/skills/**)"])

    def test_the_web_only_for_an_owners_reading_runs(self):
        cases = [("research", True), ("question", True), ("review", True), ("research", False),
                 ("polish", True), ("render", True), ("advice", True)]
        self.assertEqual([("WebFetch" in tools(k, w), "WebSearch" in tools(k, w)) for k, w in cases],
                         [(True, True)] * 3 + [(False, False)] * 4)

    def test_node_only_where_a_creative_is_rendered(self):
        kinds = ["question", "research", "polish", "render", "advice"]
        self.assertEqual(["Bash(node:*)" in tools(k) for k in kinds], [False, False, False, True, True])

    def test_a_diagnosis_is_listed_as_read_only_and_gets_only_the_read_tools(self):
        """Diagnose with Claude (W1): Meta's read tools, the workspace and `desk`; no web, no shell, no edits but
        its own JSON files, never a write tool."""
        got = tools("diagnose")
        self.assertEqual(("diagnose" in bridge.READ_ONLY_KINDS, [t for t in got if t.startswith(("Bash(", "Edit(", "Web"))],
                          [t for t in got if t.startswith("mcp__") and not any(t.endswith("__" + r) for r in bridge.READ_TOOLS)]),
                         (True, [f"Bash({SKILL}/desk:*)", "Bash(~/.claude/skills/ads-desk/desk:*)", "Edit(reports/desk/**)",
                                 f"Edit(/{WORKDIR}/reports/desk/**)"], []))

    def test_a_read_only_kind_never_gets_render_tools_even_if_listed_as_rendering(self):
        """READ_ONLY_KINDS decides: a kind put on both lists by mistake stays read only, and the lists don't overlap."""
        saved = bridge.RENDER_KINDS
        try:
            bridge.RENDER_KINDS = saved + ("diagnose",)
            leaked = [t for t in tools("diagnose") if t.startswith(("Bash(node", "Bash(ffmpeg", "Edit(creatives"))]
        finally:
            bridge.RENDER_KINDS = saved
        self.assertEqual((leaked, set(bridge.READ_ONLY_KINDS) & set(bridge.RENDER_KINDS)), ([], set()))

    def test_polish_runs_get_no_shell_but_desk(self):
        """ffmpeg, ffprobe and ls open any path on the Mac (ffmpeg also sends over http): a polish run
        cuts frames with `desk frames`, which checks the file first (review of audit A3-4)."""
        shells = [t for t in tools("polish") if t.startswith("Bash(")]
        self.assertEqual(shells, [f"Bash({SKILL}/desk:*)", "Bash(~/.claude/skills/ads-desk/desk:*)"])

    def test_secrets_are_denied_even_inside_allowed_folders(self):
        denied = bridge.denied_tools(WORKDIR, HOME)
        self.assertTrue({"Read(**/.env)", "Read(**/.env.*)", f"Read(/{HOME}/.config/**)", f"Read(/{HOME}/.ssh/**)"} <= set(denied),
                        denied)


class PrivatePathsTests(unittest.TestCase):
    """A run whose answer someone other than the owner reads can't open the other businesses' files
    in the shared workspace (review of audit A3-7)."""
    BRIEFS = ["edgebourne.md", "burdanovahair.md", "notes.txt"]
    SHARED = ["state/**", "reports/*.html", "reports/desk/*.md"]

    def paths(self, **task):
        return bridge.private_paths({"kind": "question", "account_id": 1, "from_owner": True,
                                     "account_name": "Edge Bourne", **task}, self.BRIEFS)

    def test_the_owners_own_account_reads_everything(self):
        self.assertEqual(self.paths(), [])

    def test_another_business_reads_only_its_own_brief(self):
        self.assertEqual(self.paths(account_id=2, account_name="BURDANOVA Hair"),
                         ["briefs/edgebourne.md", "briefs/notes.txt"] + self.SHARED + ["reports/*.md"])

    def test_a_teammates_request_keeps_the_other_briefs_and_the_log_closed(self):
        self.assertEqual(self.paths(from_owner=False),
                         ["briefs/burdanovahair.md", "briefs/notes.txt"] + self.SHARED + ["reports/*.md"])

    def test_an_unknown_business_gets_no_brief(self):
        self.assertEqual(self.paths(account_id=2, account_name=None)[:3],
                         ["briefs/edgebourne.md", "briefs/burdanovahair.md", "briefs/notes.txt"])

    def test_a_render_run_keeps_the_upload_log_it_must_append_to(self):
        self.assertEqual(self.paths(account_id=2, account_name="Burdanova Hair", kind="render"),
                         ["briefs/edgebourne.md", "briefs/notes.txt"] + self.SHARED)

    def test_denials_are_absolute_paths_in_the_workspace(self):
        denied = bridge.denied_tools(WORKDIR, HOME, ["state/**"])
        self.assertEqual(denied[-1], f"Read(/{WORKDIR}/state/**)")


class MediaInputTests(unittest.TestCase):
    """`desk frames` / `desk probe` open only a video inside the workspace, by its real path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = os.path.realpath(self.tmp.name)
        self.work, self.outside = os.path.join(root, "work"), os.path.join(root, "secret.mp4")
        os.makedirs(os.path.join(self.work, "creatives"))
        for path in (os.path.join(self.work, "creatives", "a.mp4"), os.path.join(self.work, "creatives", "b.webm"),
                     os.path.join(self.work, ".env"), self.outside):
            open(path, "w").close()
        os.symlink(self.outside, os.path.join(self.work, "creatives", "link.mp4"))

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, rel):
        try:
            return desk.media_input(self.work, os.path.join(self.work, rel))
        except ValueError:
            return None

    def test_videos_in_the_workspace_with_their_container(self):
        self.assertEqual([self.check("creatives/a.mp4"), self.check("creatives/b.webm")],
                         [(os.path.join(self.work, "creatives", "a.mp4"), "mov"),
                          (os.path.join(self.work, "creatives", "b.webm"), "matroska")])

    def test_nothing_outside_the_workspace_or_that_isnt_a_video(self):
        self.assertEqual([self.check(p) for p in ("../secret.mp4", "creatives/link.mp4", ".env", "creatives/missing.mp4")],
                         [None, None, None, None])

    def test_ffmpeg_reads_only_local_files_in_the_named_container(self):
        frames, sheet = desk.frames_args("/w/a.mp4", "mov", "/w/reports/desk/tmp/task3-frames", 0.3)
        probe = desk.probe_args("/w/a.mp4", "mov")
        heads = [cmd[:cmd.index("-i") + 2][-6:] for cmd in (frames, sheet, probe)]
        self.assertEqual(heads, [["-protocol_whitelist", "file", "-f", "mov", "-i", "/w/a.mp4"]] * 3)


class EndsRunTests(unittest.TestCase):
    def test_a_refused_keepalive_ends_claude_unless_the_run_finished_or_the_dashboard_is_unreachable(self):
        states = ["done", "cancelled", "failed", "queued", "gone", None]
        self.assertEqual([bridge.ends_run(s) for s in states], [False, True, True, True, True, False])


if __name__ == "__main__":
    unittest.main()
