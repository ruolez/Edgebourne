import random
import unittest
from datetime import date, datetime, timedelta, timezone

import creative_versions as cv

FORM = "1132280359202136"
CTA = {"type": "BOOK_TRAVEL", "value": {"lead_gen_form_id": FORM}}


def video(video_id="v1", title="Type it once", body="Your tools don't talk.", cta=CTA):
    return {"page_id": "p", "video_data": {"video_id": video_id, "title": title, "message": body, "call_to_action": cta}}


def image(image_hash="h1", title="Type it once", body="Your tools don't talk."):
    return {"page_id": "p", "link_data": {"image_hash": image_hash, "name": title, "message": body, "call_to_action": CTA}}


class ChangeWordsTests(unittest.TestCase):
    def test_says_exactly_what_differs(self):
        cases = [
            (video(), video("v2"), "New video"),
            (video(), video(title="Stop retyping"), "New headline"),
            (video(), video(body="Other words"), "New text"),
            (video(), video(cta={**CTA, "type": "SIGN_UP"}), "New button"),
            (video(), video("v2", "Stop retyping"), "New video and headline"),
            (video(), video("v2", "Stop retyping", "Other words"), "New video, headline and text"),
            (image(), image("h2"), "New image"),
            (video(), image(), "New image"),
        ]
        self.assertEqual([cv.change_words(old, new) for old, new, _ in cases], [want for _, _, want in cases])

    def test_nothing_visible_changed_is_none(self):
        self.assertIsNone(cv.change_words(video(), video()))

    def test_spacing_alone_is_not_a_change(self):
        self.assertIsNone(cv.change_words(video(body="One  two\n"), video(body="One two")))


class ReadbackTests(unittest.TestCase):
    def made(self, spec):
        return {"id": "c9", "object_story_spec": spec}

    def test_a_faithful_copy_passes(self):
        self.assertEqual([cv.readback_problem(video(), self.made(video())), cv.readback_problem(image(), self.made(image()))], [None, None])

    def test_each_kind_of_loss_is_caught(self):
        no_form = {"type": "BOOK_TRAVEL", "value": {"link": "http://fb.me/"}}
        cases = [
            (video(), video("other"), "different video"),
            (image(), image("other"), "different image"),
            (video(), video(title="Other"), "different words"),
            (video(), video(body="Other"), "different words"),
            (video(), video(cta=no_form), "lost the lead form"),
        ]
        for want, got, phrase in cases:
            self.assertIn(phrase, cv.readback_problem(want, self.made(got)))

    def test_a_copy_with_no_story_is_caught(self):
        self.assertIn("different video", cv.readback_problem(video(), {"id": "c9"}))

    def test_an_ad_without_a_form_needs_none(self):
        link_cta = {"type": "LEARN_MORE", "value": {"link": "https://x"}}
        self.assertIsNone(cv.readback_problem(video(cta=link_cta), self.made(video(cta=link_cta))))


D = date(2026, 11, 1)


def day(n, **kw):
    return {"day": D + timedelta(days=n), "spend_cents": 100, "impressions": 10, "link_clicks": 1, "leads": 1, "video_3s": 2, **kw}


def version(number, started=None, live=None):
    return {"number": number, "started_on": None if started is None else D + timedelta(days=started),
            "live_on": None if live is None else D + timedelta(days=live)}


class SplitResultsTests(unittest.TestCase):
    def test_days_go_to_the_version_that_was_running(self):
        versions, changeover = cv.split_results([day(n) for n in range(6)], [version(1), version(2, 3, 3)])
        self.assertEqual([(v["days"], v["spend_cents"], v["leads"]) for v in versions], [(3, 300, 3), (2, 200, 2)])
        self.assertEqual((changeover["days"], changeover["spend_cents"]), (1, 100))

    def test_every_day_until_meta_approved_counts_for_neither(self):
        versions, changeover = cv.split_results([day(n) for n in range(6)], [version(1), version(2, 2, 4)])
        self.assertEqual(([v["days"] for v in versions], changeover["days"]), ([2, 1], 3))

    def test_three_versions_each_keep_their_own_days(self):
        versions, changeover = cv.split_results([day(n) for n in range(9)], [version(1), version(2, 2, 2), version(3, 6, 6)])
        self.assertEqual(([v["days"] for v in versions], changeover["days"]), ([2, 3, 2], 2))

    def test_two_switches_on_one_day_leave_the_middle_version_empty(self):
        versions, changeover = cv.split_results([day(n) for n in range(4)], [version(1), version(2, 2, 2), version(3, 2, 2)])
        self.assertEqual(([v["days"] for v in versions], changeover["days"]), ([2, 0, 1], 1))

    def test_missing_numbers_count_as_zero(self):
        versions, _ = cv.split_results([{"day": D, "spend_cents": 5, "impressions": None, "link_clicks": None, "leads": None, "video_3s": None}], [version(1)])
        self.assertEqual(versions[0], {"days": 1, "spend_cents": 5, "impressions": 0, "link_clicks": 0, "leads": 0, "video_3s": 0})

    def test_nothing_is_lost_or_counted_twice(self):
        rng = random.Random(11)
        for _ in range(200):
            rows = [day(n, spend_cents=rng.randint(0, 900), leads=rng.randint(0, 3)) for n in range(rng.randint(0, 30))]
            starts = sorted(rng.randint(0, 30) for _ in range(rng.randint(0, 4)))
            chain = [version(1)] + [version(i + 2, s, s + rng.randint(0, 2)) for i, s in enumerate(starts)]
            versions, changeover = cv.split_results(rows, chain)
            for key in ("spend_cents", "leads"):
                self.assertEqual(sum(v[key] for v in versions) + changeover[key], sum(r[key] for r in rows))
            self.assertEqual(sum(v["days"] for v in versions) + changeover["days"], len(rows))


def at(n, hour=12):
    return datetime(2026, 11, 1, hour, tzinfo=timezone.utc) + timedelta(days=n)


class LiveDaysTests(unittest.TestCase):
    TODAY = D + timedelta(days=9)

    def chain(self, *starts):
        return [{"number": 1, "started_at": at(-5), "started_on": None}] + [
            {"number": i + 2, "started_at": at(s), "started_on": D + timedelta(days=s)} for i, s in enumerate(starts)]

    def lives(self, versions, ready=(), in_review=False):
        return [v["live_on"] for v in cv.with_live_days(versions, list(ready), self.TODAY, in_review)]

    def test_the_first_version_has_no_changeover(self):
        self.assertEqual(self.lives(self.chain()), [None])

    def test_approval_ends_the_changeover(self):
        self.assertEqual(self.lives(self.chain(2), [{"at": at(4), "day": D + timedelta(days=4)}]), [None, D + timedelta(days=4)])

    def test_no_review_seen_means_only_the_switch_day(self):
        self.assertEqual(self.lives(self.chain(2)), [None, D + timedelta(days=2)])

    def test_still_in_review_runs_up_to_today(self):
        self.assertEqual(self.lives(self.chain(2), in_review=True), [None, self.TODAY])

    def test_an_older_version_is_not_held_open_by_the_current_review(self):
        self.assertEqual(self.lives(self.chain(2, 5), in_review=True), [None, D + timedelta(days=2), self.TODAY])

    def test_an_approval_belongs_to_the_version_it_came_after(self):
        ready = [{"at": at(3), "day": D + timedelta(days=3)}, {"at": at(6), "day": D + timedelta(days=6)}]
        self.assertEqual(self.lives(self.chain(2, 5), ready), [None, D + timedelta(days=3), D + timedelta(days=6)])

    def test_an_approval_before_the_switch_is_ignored(self):
        self.assertEqual(self.lives(self.chain(4), [{"at": at(1), "day": D + timedelta(days=1)}]), [None, D + timedelta(days=4)])


if __name__ == "__main__":
    unittest.main()
