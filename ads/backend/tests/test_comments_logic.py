import unittest

import comments as cm

STORY = "1404203629446490_122098377903541159"


class BelongsTests(unittest.TestCase):
    def test_only_comments_on_the_ads_own_post(self):
        self.assertEqual([cm.belongs("122098377903541159_8812", STORY), cm.belongs("999_8812", STORY),
                          cm.belongs("122098377903541159_abc", STORY), cm.belongs("122098377903541159_8812", None), cm.belongs("", STORY)],
                         [True, False, False, False, False])


class ReplyTests(unittest.TestCase):
    def test_reply_text(self):
        self.assertEqual([cm.clean_reply("  Thanks!  "), cm.clean_reply(" "), cm.clean_reply("x" * 8001)[1]],
                         [("Thanks!", None), (None, "Write the reply first"), "Keep it under 8,000 characters"])


class ShapeTests(unittest.TestCase):
    def test_a_comment_answered_by_the_page(self):
        c = {"id": "1_2", "message": "How much?", "from": {"name": "Daniel K.", "id": "55"}, "like_count": 1, "comment_count": 1,
             "is_hidden": False, "can_hide": True,
             "comments": {"data": [{"id": "1_3", "message": "We'll DM you", "from": {"name": "Edge Bourne", "id": "PAGE"}}]}}
        s = cm.shape(c, "PAGE")
        self.assertEqual((s["answered"], s["hidden"], s["thread"][0]["from_page"], s["replies"]), (True, False, True, 1))


if __name__ == "__main__":
    unittest.main()
