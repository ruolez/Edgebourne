import random
import unittest

import desk_api
import swipes as sw


def swipe(page, body="", **kw):
    return {"page_name": page, "body": body, "title": kw.get("title"), "cta": kw.get("cta"), "notes": kw.get("notes"),
            "tags": kw.get("tags") or {}, "days_running": kw.get("days"), "still_running": kw.get("still", True),
            "long_running": bool(kw.get("days") and kw["days"] >= sw.LONG_RUNNING_DAYS), "library_url": kw.get("url")}


WORDS = ["spreadsheets", "orders", "quotes", "invoices", "retyping", "shop", "software", "built", "around", "how", "you", "work"]


def text_of(n, rnd):
    out = []
    while sum(len(w) + 1 for w in out) < n:
        out.append(rnd.choice(WORDS))
    return " ".join(out)


class FitTests(unittest.TestCase):
    def test_short_text_is_kept_whole(self):
        self.assertEqual(sw.fit("Stop retyping orders.", 40), "Stop retyping orders.")

    def test_long_text_is_cut_at_a_word_with_an_ellipsis_inside_the_limit(self):
        self.assertEqual(sw.fit("alpha beta gamma delta", 12), "alpha beta…")

    def test_one_long_word_is_cut_inside_it(self):
        self.assertEqual(sw.fit("abcdefghijklmnop", 6), "abcde…")

    def test_spacing_is_tidied_but_line_breaks_become_spaces(self):
        self.assertEqual(sw.fit("  One app\n\nfor   quotes  ", 100), "One app for quotes")


class BriefTests(unittest.TestCase):
    def test_the_drafts_stay_under_the_prompt_limit_claude_accepts(self):
        self.assertEqual(sw.PROMPT_LIMIT, desk_api.MAX_PROMPT)
        self.assertLess(sw.DRAFT_MAX, sw.PROMPT_LIMIT)

    def test_make_something_like_this_names_the_ad_and_everything_saved_about_it(self):
        s = swipe("Acme Business Software", "Still running your shop on spreadsheets? We build software around how you work.",
                  title="Software that fits", cta="LEARN_MORE", notes="Same promise as N1", tags={"hook": "Question", "angle": "Spreadsheets"},
                  days=45, url="https://www.facebook.com/ads/library/?id=123456")
        self.assertEqual(sw.brief([s], "like", "Edge Bourne"), {"left_out": 0, "prompt": (
            "Make a new ad for Edge Bourne like this competitor ad from our swipe file. Keep what makes it work (the hook, the angle, "
            "the format), but write it for our offer in our own words: don't copy theirs.\n\n"
            "Acme Business Software · running 45 days, likely working\n"
            "Headline: Software that fits\n"
            "Text: Still running your shop on spreadsheets? We build software around how you work.\n"
            "Button: Learn more\n"
            "Why we kept it: Same promise as N1\n"
            "Tags: hook Question · angle Spreadsheets\n"
            "Ad Library: https://www.facebook.com/ads/library/?id=123456\n\n"
            "Send it back as a new ad suggestion.")})

    def test_missing_parts_leave_no_empty_lines(self):
        p = sw.brief([swipe("Blitz", "One app for quotes and invoices.")], "like", "Edge Bourne")["prompt"]
        self.assertEqual(p.split("\n\n")[1], "Blitz\nText: One app for quotes and invoices.")
        self.assertNotIn("None", p)

    def test_a_stopped_ad_says_how_long_it_ran(self):
        p = sw.brief([swipe("Acme", "Words", days=97, still=False)], "like", "X")["prompt"]
        self.assertIn("Acme · ran 97 days, likely working\n", p)

    def test_a_brief_numbers_the_ads_in_the_order_picked_and_asks_for_three_concepts(self):
        p = sw.brief([swipe("Acme", "One"), swipe("Blitz", "Two")], "brief", "Edge Bourne")["prompt"]
        self.assertTrue(p.startswith("Write a short creative brief for Edge Bourne from these 2 competitor ads in our swipe file"))
        self.assertIn("3 genuinely different ad concepts", p)
        self.assertLess(p.index("1. Acme\nText: One"), p.index("2. Blitz\nText: Two"))

    def test_a_brief_from_one_ad_speaks_of_one_ad_and_is_not_numbered(self):
        p = sw.brief([swipe("Acme", "One")], "brief", "Edge Bourne")["prompt"]
        self.assertTrue(p.startswith("Write a short creative brief for Edge Bourne from this competitor ad in our swipe file:"), p[:120])
        self.assertIn("3 genuinely different ad concepts", p)
        self.assertNotIn("these 1 ", p)
        self.assertEqual(p.split("\n\n")[1], "Acme\nText: One")

    def test_ten_long_ads_fit_each_trimmed_at_a_word(self):
        rnd = random.Random(7)
        items = [swipe(f"Page {i}", text_of(4000, rnd), notes=text_of(2000, rnd), title=text_of(300, rnd)) for i in range(10)]
        r = sw.brief(items, "brief", "Edge Bourne")
        self.assertLessEqual(len(r["prompt"]), sw.DRAFT_MAX)
        self.assertEqual(r["left_out"], 0)
        bodies = [line[len("Text: "):] for line in r["prompt"].split("\n") if line.startswith("Text: ")]
        self.assertEqual(len(bodies), 10)
        for got, s in zip(bodies, items):
            self.assertTrue(got.endswith("…") and s["body"].startswith(got[:-1]) and s["body"][len(got) - 1] == " ", got[-30:])

    def test_more_than_ten_are_left_out_and_counted(self):
        r = sw.brief([swipe(f"Page {i}", "Words") for i in range(13)], "brief", "X")
        self.assertEqual(r["left_out"], 3)
        self.assertIn("Page 9", r["prompt"])
        self.assertNotIn("Page 10", r["prompt"])
        self.assertIn("3 more you picked were left out to keep this short", r["prompt"])

    def test_any_mix_stays_under_the_limit_keeps_the_order_and_counts_every_ad(self):
        rnd = random.Random(11)
        for _ in range(300):
            n = rnd.randint(1, 14)
            items = [swipe(f"Page{i}-" + "P" * rnd.randint(0, 190), text_of(rnd.randint(0, 4000), rnd), title=text_of(rnd.randint(0, 300), rnd),
                           notes=text_of(rnd.randint(0, 2000), rnd), cta=rnd.choice([None, "SIGN_UP"]), days=rnd.choice([None, 3, 40]),
                           tags={k: text_of(rnd.randint(1, 80), rnd)[:80] for k in ("hook", "angle", "format", "offer") if rnd.random() < .5},
                           url=rnd.choice([None, "https://www.facebook.com/ads/library/?id=99999999"])) for i in range(n)]
            r = sw.brief(items, rnd.choice(["like", "brief"]), "Edge Bourne")
            self.assertLessEqual(len(r["prompt"]), sw.DRAFT_MAX)
            self.assertNotIn("these 1 ", r["prompt"])
            shown =[i for i, s in enumerate(items) if f"{s['page_name']}" in r["prompt"]]
            self.assertEqual(shown, list(range(len(shown))))
            self.assertEqual(len(shown) + r["left_out"], n)
            self.assertGreaterEqual(len(shown), 1)


if __name__ == "__main__":
    unittest.main()
