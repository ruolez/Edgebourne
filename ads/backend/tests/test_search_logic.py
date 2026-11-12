import unittest

import search


def rows(prefix, n):
    return [f"{prefix}{i}" for i in range(n)]


class FairShareTests(unittest.TestCase):
    def test_every_kind_keeps_a_place_when_the_first_kinds_fill_the_limit(self):
        campaigns, adsets, ads, leads = rows("c", 6), rows("s", 6), rows("a", 8), rows("l", 6)
        got = search.fair_share([campaigns, adsets, ads, leads], 20)
        self.assertEqual(got, [rows("c", 5), rows("s", 5), rows("a", 5), rows("l", 5)])

    def test_places_a_kind_leaves_unused_go_to_the_others_in_order(self):
        got = search.fair_share([rows("c", 1), [], rows("a", 12), rows("l", 3)], 10)
        self.assertEqual(got, [rows("c", 1), [], rows("a", 6), rows("l", 3)])

    def test_under_the_limit_everything_is_kept_in_its_order(self):
        groups = [rows("c", 2), rows("s", 1), rows("l", 4)]
        self.assertEqual(search.fair_share(groups, 20), groups)

    def test_never_more_than_the_limit_and_the_order_inside_a_kind_holds(self):
        for limit in range(0, 30):
            got = search.fair_share([rows("c", 6), rows("s", 6), rows("a", 8), rows("l", 6), rows("f", 2)], limit)
            self.assertEqual(sum(len(g) for g in got), min(limit, 28))
            for g, prefix in zip(got, "csalf"):
                self.assertEqual(g, rows(prefix, len(g)))

    def test_a_kind_with_results_is_never_left_out_while_there_is_room_for_one_each(self):
        got = search.fair_share([rows("c", 9), rows("s", 9), rows("a", 9), rows("l", 1)], 4)
        self.assertEqual([len(g) for g in got], [1, 1, 1, 1])


class LikePatternTests(unittest.TestCase):
    def test_wildcards_typed_by_a_person_match_themselves(self):
        self.assertEqual(search.like_pattern("50%_off\\x"), "%50\\%\\_off\\\\x%")

    def test_plain_words_are_wrapped_for_a_contains_match(self):
        self.assertEqual(search.like_pattern("tom"), "%tom%")


class SwipeTitleTests(unittest.TestCase):
    def test_names_the_page_and_the_start_of_its_words(self):
        self.assertEqual(search.swipe_title({"page_name": "Acme", "title": "One app for quotes", "body": "Long text"}),
                         "Acme: One app for quotes")

    def test_falls_back_to_the_body_then_to_the_page_alone(self):
        self.assertEqual(search.swipe_title({"page_name": "Acme", "title": "", "body": "Stop retyping orders"}), "Acme: Stop retyping orders")
        self.assertEqual(search.swipe_title({"page_name": "Acme", "title": None, "body": None}), "Acme")

    def test_long_words_are_cut_on_a_word_with_an_ellipsis(self):
        got = search.swipe_title({"page_name": "Acme", "title": "Still running your shop on spreadsheets and sticky notes every single day?"})
        self.assertEqual(got, "Acme: Still running your shop on spreadsheets and…")
        self.assertLessEqual(len(got), len("Acme: ") + search.SWIPE_WORDS + 1)


if __name__ == "__main__":
    unittest.main()
