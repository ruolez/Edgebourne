"""FU-B: the ad account spending limit (act_<id> spend_cap). Meta reads it in cents and writes it in the currency's
standard unit (dollars), so both conversions live in money_rules and nowhere else. Pure, no database."""
import os
import re
import unittest

import money_rules as mr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SpendCapParamTests(unittest.TestCase):
    """The ONLY place cents become Meta's write unit (Ad Account reference: spend_cap on update is a float in the
    standard denomination, e.g. 23.50 for USD $23.50)."""

    def test_cents_become_the_currencys_standard_unit_with_two_decimals(self):
        cases = [(20000, "USD", "200.00"), (15050, "EUR", "150.50"), (1, "USD", "0.01"), (100, "GBP", "1.00"),
                 (123456789, "USD", "1234567.89")]
        self.assertEqual([mr.spend_cap_param(c, cur) for c, cur, _ in cases], [want for *_, want in cases])

    def test_no_limit_is_written_as_zero(self):
        self.assertEqual(mr.spend_cap_param(None, "USD"), "0")

    def test_refuses_what_would_come_out_wrong(self):
        """A zero-decimal currency (100x off), a negative or fractional amount, a bool, and 0 itself: 0 would remove
        the limit on Meta, so removing is only ever spelled None."""
        for cents, cur in ((20000, "JPY"), (20000, "krw"), (-5, "USD"), (20000.0, "USD"), (True, "USD"), (0, "USD"), ("20000", "USD")):
            with self.subTest(cents=cents, cur=cur):
                with self.assertRaises(ValueError):
                    mr.spend_cap_param(cents, cur)

    def test_round_trip_property(self):
        """Every whole number of cents comes back exactly when Meta's dollars are read as a decimal."""
        bad = [c for c in range(1, 10_000_001, 9973) if round(float(mr.spend_cap_param(c, "USD")) * 100) != c]
        self.assertEqual(bad, [])


class SpendCapCentsTests(unittest.TestCase):
    """Meta's READ value is already in cents (basic unit), as a numeric string."""

    def test_reads(self):
        self.assertEqual([mr.spend_cap_cents(v) for v in ("15000", "0", "", None, 15000, 0)], [15000, None, None, None, 15000, None])

    def test_a_decimal_or_junk_is_never_guessed(self):
        for raw in ("150.00", "abc", "-100", 150.0, True):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    mr.spend_cap_cents(raw)


class ReadbackTests(unittest.TestCase):
    def test_only_the_exact_intended_cents_pass(self):
        cases = [(20000, "20000", True), (20000, "200", False), (20000, "2000000", False), (None, "0", True), (None, "", True),
                 (20000, "abc", False), (20000, None, False), (None, "15000", False), (20000, "20000.00", False)]
        self.assertEqual([mr.readback_ok(want, raw) for want, raw, _ in cases], [ok for *_, ok in cases])


class ChangeTests(unittest.TestCase):
    def test_days_left_now_and_after_at_the_pace(self):
        self.assertEqual(mr.spend_limit_change(15000, 20000, 11240, 2000),
                         {"from": 15000, "to": 20000, "spent": 11240, "remove": False, "left_now": 3760, "left_after": 8760,
                          "days_now": 1, "days_after": 4, "rate": 2000, "currency": "USD", "big": False})

    def test_big_when_the_new_limit_is_more_than_double_the_old_one(self):
        """A raise past twice the current limit works almost like removing it, so it gets its own yes too. Setting a
        limit where there was none, lowering it and removing it (asked separately) are never "big"."""
        cases = [(15000, 30001, True), (15000, 30000, False), (15000, 2500000, True), (None, 2500000, False),
                 (15000, None, False), (30000, 15000, False), (100, 201, True)]
        self.assertEqual([mr.spend_limit_change(o, n, 50, 1000)["big"] for o, n, _ in cases], [b for *_, b in cases])

    def test_without_a_pace_no_days(self):
        out = mr.spend_limit_change(15000, 20000, 11240, 0)
        self.assertEqual((out["days_now"], out["days_after"], out["left_after"]), (None, None, 8760))

    def test_removal_and_no_limit_have_no_left_or_days(self):
        out = mr.spend_limit_change(15000, None, 11240, 2000)
        self.assertEqual((out["remove"], out["left_after"], out["days_after"], out["days_now"]), (True, None, None, 1))
        out = mr.spend_limit_change(None, 20000, 11240, 2000)
        self.assertEqual((out["left_now"], out["days_now"], out["days_after"]), (None, None, 4))

    def test_a_limit_already_passed_has_zero_days_not_negative(self):
        self.assertEqual(mr.spend_limit_change(10000, 20000, 12000, 2000)["days_now"], 0)


class ProblemTests(unittest.TestCase):
    def problem(self, old, new, spent=4120, confirm=False):
        return mr.spend_limit_problem(mr.spend_limit_change(old, new, spent, 1000), confirm)

    def test_at_or_below_what_is_spent_is_refused(self):
        said = [self.problem(15000, n) for n in (4120, 4119, 4121)]
        self.assertEqual([s and "at or below what's already spent ($41.20)" in s for s in said], [True, True, None])
        self.assertIn("Meta would stop every ad at once", said[0])

    def test_removal_needs_its_own_confirmation(self):
        self.assertEqual((self.problem(15000, None), self.problem(15000, None, confirm=True)),
                         ("Removing the limit needs its own confirmation.", None))

    def test_a_raise_past_double_needs_its_own_confirmation(self):
        change = mr.spend_limit_change(15000, 2500000, 4120, 1000)
        self.assertEqual((mr.spend_limit_problem(change, False), mr.spend_limit_problem(change, False, accept_big=True),
                          mr.spend_limit_problem(mr.spend_limit_change(15000, 30000, 4120, 1000), False)),
                         ("Raising the limit to more than double needs its own confirmation.", None, None))

    def test_tiny_and_unchanged(self):
        self.assertEqual((self.problem(15000, 99, spent=0), self.problem(15000, 15000), self.problem(None, None, confirm=True)),
                         ("The new limit must be at least 1.00.", "That's already the limit.", "There's no limit already."))

    def test_order_minimum_before_spent(self):
        self.assertEqual(self.problem(15000, 50, spent=4120), "The new limit must be at least 1.00.")


class LimitWordsTests(unittest.TestCase):
    def test_amounts(self):
        self.assertEqual([mr.limit_words(t) for t in ("$200", "to $200", "200 dollars", "$1,250.50", "from $150 to $200")],
                         [20000, 20000, 20000, 125050, 20000])

    def test_removal(self):
        self.assertEqual([mr.limit_words(t) for t in ("no limit", "remove the limit", "Remove the spending limit", "No limit")], [None] * 4)

    def test_per_day_reads_as_a_budget(self):
        self.assertEqual([mr.limit_words(t) for t in ("$200/day", "$200 a day", "200 daily", "$200 per day")], [mr.LIMIT_DAILY] * 4)

    def test_choices_and_noise_are_not_an_amount(self):
        self.assertEqual([mr.limit_words(t) for t in ("$150 or $200", "$200?", "", None, "raise it", "+20%", "remove the $200 limit")],
                         [mr.LIMIT_UNCLEAR] * 7)


class LimitActionTests(unittest.TestCase):
    """What accepting a spend_limit suggestion does: words and cents must agree, as for budgets."""

    def test_agreeing_words_and_cents(self):
        self.assertEqual(mr.limit_action("$200", {"proposed_cents": 20000}), ("spend_limit", 20000))

    def test_removal_only_with_literal_true_and_removal_words(self):
        self.assertEqual(mr.limit_action("no limit", {"remove": True}), ("spend_limit", None))
        self.assertEqual(mr.limit_action("$200", {"remove": True})[0], "unclear")

    def test_daily_words_name_a_budget(self):
        kind, why = mr.limit_action("$200/day", {"proposed_cents": 20000})
        self.assertEqual((kind, "daily budget" in why), ("unclear", True))

    def test_disagreeing_amounts(self):
        kind, why = mr.limit_action("$200", {"proposed_cents": 25000})
        self.assertEqual((kind, "isn't what its words say" in why), ("unclear", True))

    def test_no_payload_or_tiny_amount(self):
        self.assertEqual([mr.limit_action(w, p)[0] for w, p in (("$200", None), ("$200", {}), ("$0.50", {"proposed_cents": 50}),
                                                               ("no limit", {"proposed_cents": 20000}))], ["unclear"] * 4)


class LimitAccountTests(unittest.TestCase):
    """A suggestion is checked again when it's accepted: the account's ad account may have been changed since."""

    def test_only_the_ad_account_this_account_has_now(self):
        cases = [("act_111", "act_111"), ("act_222", "act_111"), (None, "act_111"), ("", "act_111"), ("act_111", "act_None")]
        said = [mr.limit_account_problem(e, now) for e, now in cases]
        self.assertEqual([s is None or "Decline it and ask again" in s for s in said], [True] * 5)
        self.assertEqual([s is None for s in said], [True, False, False, False, False])
        self.assertIn("act_222", said[1])


class LimitReadWordsTests(unittest.TestCase):
    """What Meta holds, in words, for the alert and the replies: an unreadable read-back is never called "no limit"."""

    def test_amounts_none_and_unreadable(self):
        cases = [("20000", "$200.00"), ("0", "no limit"), ("", "no limit"), ("200.00", "an amount the console can't read ('200.00')"),
                 ("abc", "an amount the console can't read ('abc')"), ("-5", "an amount the console can't read ('-5')")]
        self.assertEqual([mr.limit_read_words(raw, "USD") for raw, _ in cases], [want for _, want in cases])


class InsightsReadTests(unittest.TestCase):
    """insights.sync_account reads the limit through spend_cap_cents too (one read conversion)."""

    def stored(self, raw):
        import json
        from unittest import mock
        import insights
        saved = {}
        row = {"name": "Edge Bourne Consulting", "currency": "USD", "timezone_name": "America/Los_Angeles",
               "spend_cap": raw, "amount_spent": "4120", "account_status": 1}
        with mock.patch.object(insights.meta_client, "get", return_value=row), \
                mock.patch.object(insights.settings_store, "get", return_value="1025"), \
                mock.patch.object(insights.settings_store, "set", side_effect=lambda k, v: saved.__setitem__(k, v)):
            insights.sync_account()
        snap = json.loads(saved["account_snapshot"])
        return snap["spend_cap_cents"], snap["amount_spent_cents"]

    def test_cents_as_meta_reads_them(self):
        self.assertEqual([self.stored(r) for r in ("15000", "0", None)], [(15000, 4120), (None, 4120), (None, 4120)])

    def test_a_decimal_read_is_refused_not_guessed(self):
        with self.assertRaises(ValueError):
            self.stored("150.00")


class RatchetTests(unittest.TestCase):
    """Only spend_limit.py writes an ad account's spend_cap, always through money_rules.spend_cap_param, and nothing
    in the backend ever sends spend_cap's action parameter (its reset zeroes amount_spent, its delete removes the limit)."""

    def sources(self):
        out = {}
        for name in sorted(os.listdir(HERE)):
            if name.endswith(".py"):
                with open(os.path.join(HERE, name), encoding="utf-8") as f:
                    out[name] = f.read()
        return out

    @staticmethod
    def calls(text, name):
        """Every `name(...)` call's full text, parentheses matched."""
        out = []
        for m in re.finditer(re.escape(name) + r"\(", text):
            depth, i = 0, m.end() - 1
            while i < len(text):
                depth += {"(": 1, ")": -1}.get(text[i], 0)
                if depth == 0:
                    break
                i += 1
            out.append(text[m.start():i + 1])
        return out

    def test_only_spend_limit_writes_spend_cap_and_through_the_one_function(self):
        """Keyword or dict form, one write call in the whole backend, and it converts through spend_cap_param."""
        src = self.sources()
        writers = sorted(n for n, text in src.items() if re.search(r"\bspend_cap\s*=(?!=)", text))
        posts = [(n, c) for n, text in src.items() for c in self.calls(text, ".post") if "spend_cap" in c]
        self.assertEqual((writers, [n for n, _ in posts], all("money_rules.spend_cap_param(" in c for _, c in posts)),
                         (["spend_limit.py"], ["spend_limit.py"], True))

    def test_no_dict_spend_cap_key_outside_the_rule_tables(self):
        """`data={"spend_cap": …}` or `**{"spend_cap": …}` would be a second write path: the key appears only where
        "spend_cap" names the alert rule, the stored-column map or a field read from an Ads Manager draft (am_drafts, AM-B:
        a whitelist of what a draft may hold, never sent to Meta)."""
        keyed = sorted(n for n, text in self.sources().items() if re.search(r"[\"']spend_cap[\"']\s*:", text))
        self.assertEqual(keyed, ["alerts.py", "am_drafts.py", "diagnose.py", "inbox.py", "snooze.py", "status_history.py"])

    IMPORT = re.compile(r"^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)", re.M)
    WRITERS = {"meta_client", "requests", "urllib", "http", "httpx", "mcp", "am_link_api", "ads_api", "spend_limit"}

    def local_imports(self, name, src, seen=None):
        """The backend modules `name` imports, directly or through the modules it imports."""
        seen = set() if seen is None else seen
        for m in self.IMPORT.finditer(src.get(name, "")):
            mod = (m.group(1) or m.group(2)).split(".")[0]
            if mod not in seen:
                seen.add(mod)
                self.local_imports(f"{mod}.py", src, seen)
        return seen

    def test_the_draft_whitelist_module_can_never_write_to_meta(self):
        """am_drafts.py is exempt above because it only names spend_cap as a field a draft may hold. Keep it that way:
        neither it nor anything it imports reaches Meta (or an HTTP client) or calls .post(."""
        src = self.sources()
        reach = self.local_imports("am_drafts.py", src)
        local = sorted(m for m in reach if f"{m}.py" in src)
        self.assertEqual((sorted(reach & self.WRITERS), [m for m in ["am_drafts", *local] if ".post(" in src[f"{m}.py"]]), ([], []))

    def test_the_import_walk_sees_a_writer_two_steps_away(self):
        src = {"a.py": "import b\n", "b.py": "    from meta_client import post\n"}
        self.assertEqual(self.local_imports("a.py", src), {"b", "meta_client"})

    def test_the_ratchet_sees_a_dict_write(self):
        bad = 'meta_client.post(f"act_{a}", data={"spend_cap": cents})'
        self.assertEqual([c for c in self.calls(bad, ".post") if "spend_cap" in c], [bad[len("meta_client"):]])

    def test_no_spend_cap_action_anywhere(self):
        self.assertEqual([n for n, text in self.sources().items() if "spend_cap" + "_action" in text], [])


if __name__ == "__main__":
    unittest.main()
