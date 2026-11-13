import os
import re
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest import mock

import db
import lead_quality as lq
import lead_quality_store as lqs
import leads
import report_logic


class RaiseMaxTest(unittest.TestCase):
    def test_cases(self):
        cases = [(("new", "contacted"), "contacted"), (("qualified", "lost"), "qualified"), (("won", "contacted"), "won"),
                 (("new", "lost"), "new"), (("contacted", "contacted"), "contacted"), (("new", "won"), "won")]
        self.assertEqual([lq.raise_max(*args) for args, _ in cases], [want for _, want in cases])

    def test_never_lowers(self):
        for cur in lq.FUNNEL:
            for move in lq.FUNNEL + ("lost",):
                self.assertGreaterEqual(lq.RANK[lq.raise_max(cur, move)], lq.RANK[cur])


class MaxFromHistoryTest(unittest.TestCase):
    def test_cases(self):
        self.assertEqual([lq.max_from_history(["new", "qualified", "lost"]), lq.max_from_history([], contacted=True),
                          lq.max_from_history(["lost"]), lq.max_from_history(["won", "contacted"]), lq.max_from_history(["bogus"])],
                         ["qualified", "contacted", "new", "won", "new"])


class UndoMaxTest(unittest.TestCase):
    def test_cases(self):
        change = {"max_before": "contacted", "max_after": "qualified"}
        self.assertEqual([lq.undo_max("qualified", change), lq.undo_max("won", change),
                          lq.undo_max("contacted", {"max_before": "contacted", "max_after": "contacted"})],
                         ["contacted", "won", "contacted"])

    def test_old_event_without_max_keeps_it(self):
        self.assertEqual(lq.undo_max("qualified", {}), "qualified")


class CleanLostTest(unittest.TestCase):
    def test_cases(self):
        self.assertEqual([lq.clean_lost("lost", "price", "  cheaper quote "), lq.clean_lost("lost", None, None),
                          lq.clean_lost("lost", "bogus", ""), lq.clean_lost("contacted", "price", "x"),
                          lq.clean_lost("lost", None, "  ")],
                         [("price", "cheaper quote", None), (None, None, None), (None, None, "Pick one of the reasons"),
                          (None, None, None), (None, None, None)])

    def test_long_note_is_cut_to_500(self):
        reason, note, err = lq.clean_lost("lost", "other", "x" * 600)
        self.assertEqual((reason, len(note), err), ("other", lq.NOTE_MAX, None))


MARIA = {"full_name": "Maria Lopez", "email": "maria@lopezbakery.com", "phone": "+1 (619) 555-7788",
         "answers": [{"name": "full_name", "values": ["Maria Lopez"]}, {"name": "what_kind_of_business?", "values": ["Wholesale bakery"]},
                     {"name": "team_size", "values": ["14"]}]}


def answers(*values):
    return [{"name": f"q{i}", "values": [v]} for i, v in enumerate(values)]


class FlagsTest(unittest.TestCase):
    def test_cases(self):
        cases = [
            (MARIA, []),
            ({"full_name": "a", "email": "test@test.com", "phone": "1234567890"}, ["fake_phone", "test_email", "short_name"]),
            ({"full_name": "Real Person", "email": "real.person@mailinator.com"}, ["throwaway_email"]),
            ({"full_name": "Test User", "email": "maria@lopezbakery.com"}, ["test_words"]),
            ({"full_name": "Jo Li"}, []),
            ({"full_name": "J K"}, ["short_name"]),
            ({"full_name": "123"}, ["short_name"]),
            ({"full_name": "Real Person", "answers": answers("asdf", "asdf")}, ["test_words", "same_answers"]),
            ({"full_name": "Real Person", "answers": answers("Yes", "Yes")}, []),
            ({"full_name": "Real Person", "answers": answers("Bakery", "bakery ")}, ["same_answers"]),
            ({"full_name": "Real Person", "answers": answers("100", "100")}, []),
            ({"full_name": "Real Person", "answers": answers("Bakery")}, []),
            ({"full_name": None, "email": None, "phone": None}, []),
            # the email's own words never count as test words: it is a contact field
            ({"full_name": "Real Person", "answers": [{"name": "email", "values": ["fake@shop.com"]}, {"name": "biz", "values": ["Bakery"]}]}, []),
        ]
        self.assertEqual([lq.flags(lead) for lead, _ in cases], [want for _, want in cases])

    def test_testing_is_a_whole_word_only(self):
        self.assertEqual([lq.flags({"full_name": n}) for n in ("Testa Rossi", "Contest Winner", "testing")], [[], [], ["test_words"]])


class FlagTextTest(unittest.TestCase):
    def test_cases(self):
        self.assertEqual([lq.flag_text(["fake_phone", "test_email"]), lq.flag_text([]),
                          lq.flag_text(["fake_phone", "test_email", "short_name"])],
                         ["The phone number looks made up and the email is a test address.", "",
                          "The phone number looks made up, the email is a test address and the name is a single letter."])

    def test_every_code_has_words(self):
        self.assertEqual([c for c in lq.FLAG_CODES if not lq.flag_text([c])], [])


class MatchKindTest(unittest.TestCase):
    def test_cases(self):
        cases = [({"status": "contacted"}, "repeat"), ({"status": "new"}, "repeat"), ({"status": "qualified"}, "repeat"),
                 ({"status": "lost", "lost_reason": "spam"}, "repeat"), ({"status": "lost", "lost_reason": "duplicate"}, "repeat"),
                 ({"status": "lost", "lost_reason": "no_response"}, "returning"), ({"status": "lost", "lost_reason": None}, "returning"),
                 ({"status": "won"}, "returning")]
        self.assertEqual([lq.match_kind(o) for o, _ in cases], [want for _, want in cases])


class IsJunkTest(unittest.TestCase):
    def test_cases(self):
        flagged = {"junk_flags": ["fake_phone"], "max_stage": "new", "status": "new"}
        cases = [({"lost_reason": "spam", "status": "lost"}, True), (flagged, True), ({**flagged, "max_stage": "contacted"}, False),
                 ({**flagged, "junk_dismissed": True}, False), ({**flagged, "status": "lost", "lost_reason": "price"}, False),
                 ({"junk_flags": [], "status": "lost", "lost_reason": "no_response"}, False),
                 ({**flagged, "status": "lost", "lost_reason": "no_response"}, True)]
        self.assertEqual([lq.is_junk(l) for l, _ in cases], [want for _, want in cases])


def lead(key, max_stage="new", status=None, reason=None, repeat_of=None, flags=(), **kw):
    return {"ad_id": key, "ad_name": f"Ad {key}", "form_id": "f1", "form_name": "Intro call", "max_stage": max_stage,
            "status": status or max_stage, "lost_reason": reason, "repeat_of": repeat_of, "junk_flags": list(flags),
            "junk_dismissed": False, "is_test": False, "is_organic": False, "answers": [], **kw}


class SummarizeTest(unittest.TestCase):
    TARGET = 6000

    def fixture(self):
        a = [lead("A", "qualified"), lead("A", "qualified", "lost", "price"), lead("A"), lead("A", "new", "lost", "spam"),
             lead("A", "contacted"), lead("A", repeat_of=1)]
        b = [lead("B", "qualified"), lead("B", "qualified"), lead("B", "won"), lead("B"), lead("B"), lead("B")]
        return a + b + [lead("A", is_test=True)]

    def test_rows_totals_and_order(self):
        s = lq.summarize(self.fixture(), {"A": 15000, "B": 12000}, "ad", None, self.TARGET, meta_leads=12)
        row_a = {k: s["rows"][1][k] for k in ("key", "leads", "fills", "repeats", "qualified", "won", "junk", "qualified_rate",
                                               "junk_rate", "cpq_cents", "cpq_enough", "rates_enough", "lost", "spend_cents")}
        self.assertEqual(row_a, {"key": "A", "leads": 5, "fills": 6, "repeats": 1, "qualified": 2, "won": 0, "junk": 1,
                                 "qualified_rate": 0.4, "junk_rate": 0.2, "cpq_cents": 7500, "cpq_enough": False,
                                 "rates_enough": True, "lost": {"price": 1, "spam": 1}, "spend_cents": 15000})
        row_b = {k: s["rows"][0][k] for k in ("key", "leads", "qualified", "won", "cpq_cents", "cpq_enough")}
        self.assertEqual(row_b, {"key": "B", "leads": 6, "qualified": 3, "won": 1, "cpq_cents": 4000, "cpq_enough": True})
        self.assertEqual(s["best"], None)
        self.assertEqual(s["totals"], {"fills": 12, "leads": 11, "repeats": 1, "junk": 1, "qualified": 5, "won": 1,
                                       "spend_cents": 27000, "meta_leads": 12, "cpl_meta_cents": 2250, "cpl_real_cents": 2700})

    def test_best_needs_two_judged_rows(self):
        c = [lead("C", "qualified")] * 3 + [lead("C")]
        s = lq.summarize(self.fixture() + c, {"A": 15000, "B": 12000, "C": 15000}, "ad", None, self.TARGET)
        self.assertEqual((s["best"], [r["key"] for r in s["rows"]]), ("B", ["B", "C", "A"]))

    def test_page_row_is_last_without_spend(self):
        organic = lead(None, "qualified", is_organic=True)
        s = lq.summarize(self.fixture() + [organic], {"A": 15000, "B": 12000}, "ad", None, self.TARGET)
        last = s["rows"][-1]
        self.assertEqual((last["key"], last["label"], last["is_page"], last["spend_cents"], last["cpq_cents"]),
                         ("page", "From the Page (no ad)", True, None, None))

    def test_without_a_target_three_qualified_are_enough(self):
        s = lq.summarize([lead("C", "qualified")] * 3, {"C": 100}, "ad", None, None)
        self.assertEqual((s["rows"][0]["cpq_enough"], s["rows"][0]["cpq_cents"]), (True, 33))

    def test_spend_without_leads_is_a_row(self):
        s = lq.summarize([], {"Z": 5000}, "ad", None, self.TARGET, labels={"Z": "N9"})
        self.assertEqual([(r["key"], r["label"], r["leads"], r["cpq_cents"], r["qualified_rate"]) for r in s["rows"]], [("Z", "N9", 0, None, None)])

    def test_rows_and_totals_agree(self):
        s = lq.summarize(self.fixture(), {"A": 15000, "B": 12000}, "ad", None, self.TARGET)
        for key in ("fills", "leads", "repeats", "junk", "qualified", "won"):
            self.assertEqual(sum(r[key] for r in s["rows"]), s["totals"][key], key)

    def test_by_answer_groups_case_blind_and_labels_by_first_seen(self):
        q = [{"name": "biz", "values": ["Bakery"]}]
        leads = [lead("A", answers=q), lead("A", answers=[{"name": "biz", "values": ["bakery"]}]), lead("B", answers=[{"name": "biz", "values": ["Gym"]}])]
        s = lq.summarize(leads, {}, "answer", "biz", self.TARGET, total_spend_cents=9000)
        self.assertEqual([(r["label"], r["leads"], r["spend_cents"]) for r in s["rows"]], [("Bakery", 2, None), ("Gym", 1, None)])
        self.assertEqual((s["answer_question_ok"], s["totals"]["spend_cents"]), (True, 9000))

    def test_by_answer_refuses_typed_answers(self):
        leads = [lead("A", answers=[{"name": "biz", "values": [f"Answer {i}"]}]) for i in range(lq.ANSWER_GROUPS_MAX + 1)]
        s = lq.summarize(leads, {}, "answer", "biz", self.TARGET)
        self.assertEqual((s["answer_question_ok"], s["rows"]), (False, []))

    def test_by_form_uses_the_latest_name(self):
        leads = [lead("A", form_id="f2", form_name=None), lead("A", form_id="f2", form_name="Short form")]
        s = lq.summarize(leads, {}, "form", None, None)
        self.assertEqual([(r["key"], r["label"]) for r in s["rows"]], [("f2", "Short form")])


class FormSpendTest(unittest.TestCase):
    def test_only_ads_with_one_form(self):
        leads = [lead("A", form_id="f1"), lead("A", form_id="f1"), lead("B", form_id="f1"), lead("B", form_id="f2"), lead("C", form_id="f2")]
        self.assertEqual(lq.form_spend(leads, {"A": 100, "B": 200, "C": 300, "D": 400}), {"f1": 100, "f2": 300})


class VerdictTest(unittest.TestCase):
    def test_best(self):
        s = {"by": "ad", "rows": [{"key": "B", "label": "N3 - Same work twice", "cpq_cents": 4000}], "best": "B", "answer_question_ok": True}
        self.assertEqual(lq.verdict(s, 6000), {"name": "N3 - Same work twice", "text": "brings qualified leads cheapest: $40.00 each."})

    def test_too_early(self):
        s = {"by": "ad", "rows": [{"key": "B"}], "best": None, "answer_question_ok": True}
        self.assertEqual([lq.verdict(s, 6000)["text"], lq.verdict(s, None)["text"], lq.verdict({**s, "by": "form"}, 6000)["text"]],
                         ["Too early to compare: an ad needs 3 qualified leads and twice the $60.00 target in spend before its cost per qualified lead means much.",
                          "Too early to compare: an ad needs 3 qualified leads first. Set a target in Settings → Targets to judge against it.",
                          "Too early to compare: a form needs 3 qualified leads and twice the $60.00 target in spend before its cost per qualified lead means much."])

    def test_answers_and_empty(self):
        self.assertEqual([lq.verdict({"by": "answer", "rows": [], "best": None, "answer_question_ok": False}, None)["text"],
                          lq.verdict({"by": "answer", "rows": [{"key": "x"}], "best": None, "answer_question_ok": True}, None)["text"],
                          lq.verdict({"by": "ad", "rows": [], "best": None, "answer_question_ok": True}, None)["text"]],
                         ["This question has typed answers, so they can't be grouped. Pick a question with set choices.",
                          "Spend can't be split by answer, so cost per qualified lead shows for ads and forms only.",
                          "No leads in this period yet."])


class JunkNoteTest(unittest.TestCase):
    def test_cases(self):
        t = {"fills": 31, "leads": 29, "junk": 4, "repeats": 2, "spend_cents": 37510, "meta_leads": 31, "cpl_meta_cents": 1210, "cpl_real_cents": 1500}
        self.assertEqual([lq.junk_note(t), lq.junk_note({**t, "junk": 0, "repeats": 0}), lq.junk_note({**t, "junk": 1, "repeats": 0}),
                          lq.junk_note({**t, "junk": 0, "repeats": 1, "cpl_meta_cents": None})],
                         ["4 of 31 leads look like junk and 2 were repeats. Meta counts all of them, so its cost per lead ($12.10) is lower than the cost per real lead ($15.00).",
                          "No junk or repeats in this period.",
                          "1 of 31 leads looks like junk. Meta counts all of them, so its cost per lead ($12.10) is lower than the cost per real lead ($15.00).",
                          "1 of 31 leads was a repeat."])


class LostCountsTest(unittest.TestCase):
    def test_counted_leads_only_in_list_order(self):
        leads = [lead("A", "new", "lost", r) for r in ("no_response", "no_response", None, "spam")] + [lead("A", "new", "lost", "price", repeat_of=4)]
        out = lq.lost_counts(leads)
        self.assertEqual((out, list(out)), ({"no_response": 2, "spam": 1, "none": 1}, ["no_response", "spam", "none"]))


class LostLineTest(unittest.TestCase):
    def test_cases(self):
        self.assertEqual([report_logic.lost_line({"no_response": 2, "not_fit": 1, "spam": 1}), report_logic.lost_line({}),
                          report_logic.lost_line({"none": 2}), report_logic.lost_line({"none": 0})],
                         ["Lost: 4 (2 no response, 1 not a fit, 1 spam or fake).", None, "Lost: 2 (no reason given).", None])


class SnapshotTest(unittest.TestCase):
    def test_counts_only_never_people(self):
        maria = {**lead("A", "qualified", "lost", "price", flags=["fake_phone"]), "full_name": "Maria Lopez", "email": "maria@lopezbakery.com",
                 "phone": "+16195557788", "lost_note": "went with a cheaper quote"}
        rows, totals = lq.snapshot([maria, lead("A", repeat_of=1)])
        self.assertEqual(rows, [{"ad_id": "A", "ad_name": "Ad A", "leads": 1, "repeats": 1, "junk": 0, "qualified": 1, "won": 0,
                                 "lost": {"price": 1}, "junk_flags": {"fake_phone": 1}}])
        self.assertEqual(totals, {"leads": 1, "repeats": 1, "junk": 0, "qualified": 1, "won": 0, "lost": {"price": 1}})
        self.assertNotRegex(repr((rows, totals)), "Maria|lopezbakery|5557788|cheaper")


class AlertWordsTest(unittest.TestCase):
    TZ = timezone.utc
    ROOT = {"id": 3, "status": "contacted", "lost_reason": None, "created_time": datetime(2026, 9, 2, 15, tzinfo=timezone.utc)}
    LEAD = {"full_name": "Maria Lopez", "business_type": "Wholesale bakery", "ad_name": "N3 - Same work twice"}

    def test_asked_again(self):
        self.assertEqual(lq.asked_again(self.LEAD, self.ROOT, "Eugene", True),
                         ("Asked again: Maria Lopez, Wholesale bakery",
                          "Maria Lopez asked again (from N3 - Same work twice). Their first request is with Eugene, stage Contacted."))
        self.assertEqual(lq.asked_again({**self.LEAD, "ad_name": None}, self.ROOT, None, False)[1],
                         "Maria Lopez asked again (from the Page, no ad). They asked before in another campaign.")
        self.assertEqual(lq.asked_again(self.LEAD, self.ROOT, None, True)[1],
                         "Maria Lopez asked again (from N3 - Same work twice). Their first request has no owner yet, stage Contacted.")

    def test_asked_before(self):
        self.assertEqual([lq.asked_before({**self.ROOT, "status": "lost", "lost_reason": "no_response"}, self.TZ),
                          lq.asked_before({**self.ROOT, "status": "won", "status_changed_at": datetime(2026, 9, 9, tzinfo=timezone.utc)}, self.TZ),
                          lq.asked_before({**self.ROOT, "status": "lost"}, self.TZ)],
                         ["Asked before: Sep 2, Lost (No response).", "Already a client: Won on Sep 9.", "Asked before: Sep 2, Lost (no reason given)."])


class FragmentsTest(unittest.TestCase):
    def test_fragments(self):
        self.assertEqual([lq.counted(), lq.qualified("x"), lq.won(), lq.contacted("o")],
                         ["NOT l.is_test AND l.repeat_of IS NULL", "x.max_stage IN ('qualified','won')", "l.max_stage = 'won'",
                          "o.max_stage <> 'new'"])

    def test_contacted_is_stage_based(self):
        self.assertNotIn("first_contacted_at", lq.contacted())


BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# A count that keeps repeats on purpose (what Meta charges for, the New badge, speed to first try) says so in
# the query itself with this SQL comment, so a reader sees it where it is.
EVERY_FILL = "/* every fill */"
# The only counts allowed to keep repeats: Meta's fill count on alerts and forms, and the backfill's activity line.
EVERY_FILL_ALLOWED = {"alerts.py": 1, "forms_api.py": 1, "lead_quality_store.py": 1}


class LeadCountsRatchetTest(unittest.TestCase):
    """Every count of leads says which leads count (lead_quality.counted / repeat_of) and how far they got
    (max_stage); nobody reads today's stage as 'qualified' any more."""

    def files(self):
        for name in sorted(os.listdir(BACKEND)):
            if name.endswith(".py"):
                with open(os.path.join(BACKEND, name)) as f:
                    yield name, f.read()

    def queries(self, text):
        return re.findall(r'(?:f?"""(?:.|\n)*?"""|f?"[^"\n]*")', text)

    def test_no_current_stage_counts(self):
        bad = [name for name, text in self.files() for q in self.queries(text)
               if "leads" in q and re.search(r"status\s+IN\s*\(\s*'qualified'|status\s*=\s*'won'", q)]
        self.assertEqual(bad, [])

    def test_every_leads_count_names_its_scope(self):
        bad = []
        for name, text in self.files():
            for q in self.queries(text):
                if (re.search(r"FROM leads\b", q) and "COUNT(" in q
                        and not any(m in q for m in ("repeat_of", "counted(", "LEAD_SCOPE", EVERY_FILL))):
                    bad.append((name, q[:90]))
        self.assertEqual(bad, [])

    def test_every_fill_marker_only_where_allowed(self):
        found = {name: text.count(EVERY_FILL) for name, text in self.files() if EVERY_FILL in text}
        self.assertEqual(found, EVERY_FILL_ALLOWED)


class TransactionGuardTest(unittest.TestCase):
    """db.query/execute commit on their own: inside a transaction() block on the same connection they would commit
    half of it and release the lead-match lock, so they are refused."""

    def setUp(self):
        self.conn = mock.MagicMock()
        for p in (mock.patch.object(db, "get_db", return_value=self.conn), mock.patch.object(db, "_scope"),
                  mock.patch.object(db.account_ctx, "seeing_all", return_value=False)):
            p.start()
            self.addCleanup(p.stop)

    def test_query_inside_a_block_is_refused_and_nothing_commits_early(self):
        with self.assertRaises(db.TransactionOpen), db.transaction():
            db.query("SELECT 1")
        self.assertEqual((self.conn.commit.call_count, self.conn.rollback.call_count), (0, 1))

    def test_a_nested_block_on_the_same_connection_is_refused(self):
        with self.assertRaises(db.TransactionOpen), db.transaction(), db.transaction():
            pass

    def test_queries_work_again_after_the_block(self):
        with db.transaction():
            pass
        db.query("SELECT 1")
        self.assertEqual(self.conn.commit.call_count, 2)


class StoreLeadSettingsTest(unittest.TestCase):
    def test_settings_are_read_before_the_transaction_opens(self):
        state = {"open": False}

        @contextmanager
        def tx():
            state["open"] = True
            try:
                yield cur
            finally:
                state["open"] = False

        def setting(key, *_a, **_k):
            if state["open"]:
                raise AssertionError(f"settings_store.get({key!r}) inside the transaction")
            return None

        cur = mock.MagicMock()
        cur.fetchone.side_effect = [{"id": 5}, None, {"id": 5, "max_stage": "new"}]
        cur.fetchall.return_value = []
        data = {"id": "L5", "ad_id": "A1", "created_time": "2026-11-01T10:00:00+0000",
                "field_data": [{"name": "email", "values": ["sam@realshop.com"]}]}
        with mock.patch.object(leads.db, "transaction", tx), mock.patch.object(lqs.settings_store, "get", side_effect=setting) as get, \
                mock.patch.object(lqs.account_ctx, "current", return_value=1), mock.patch.object(leads.crm_events, "enqueue"), \
                mock.patch.object(leads.lead_history, "record"), mock.patch.object(lqs.lead_history, "record"):
            self.assertEqual(leads.store_lead(data), (5, True))
        self.assertEqual(sorted({c.args[0] for c in get.call_args_list}), ["lead_junk_flags", "lead_repeat_check"])
        self.assertTrue(any("email_key" in c.args[0] for c in cur.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
