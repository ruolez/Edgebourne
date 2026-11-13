"""FU-D: full access for the console owner's own typed requests (Eugene, 2026-11-12: "Only me, with a re-check").
Pure rules: who may unlock, how long, wrong-password blocks, which requests ask for it, what the Mac gets at claim."""
import unittest
from datetime import datetime, timedelta, timezone

import full_access as fa

NOW = datetime(2026, 11, 13, 17, 40, tzinfo=timezone.utc)
OWNER = {"id": 1, "role": "admin", "account_id": None, "full_access_allowed": True, "is_active": True}
OWNER_NO_FLAG = {**OWNER, "id": 7, "full_access_allowed": False}
ACCOUNT_ADMIN = {"id": 4, "role": "admin", "account_id": 2, "full_access_allowed": False, "is_active": True}
CLIENT = {"id": 5, "role": "client", "account_id": 2, "full_access_allowed": False, "is_active": True}
UNLOCKED = {"user_id": 1, "full_until": NOW + timedelta(hours=3)}
LOCKED = {"user_id": 1, "full_until": None}
TASK = {"kind": "question", "options": {}, "full_session": "abc", "created_by": 1, "account_id": 1}


class MayUnlockTests(unittest.TestCase):
    def test_only_the_flagged_owner_and_everyone_else_hears_the_same_sentence(self):
        got = [fa.may_unlock(u) for u in (OWNER, OWNER_NO_FLAG, ACCOUNT_ADMIN, CLIENT, None)]
        self.assertEqual(got, [None] + [fa.NOT_OWNER] * 4)

    def test_the_sentence_never_hints_at_a_flag(self):
        self.assertNotIn("flag", fa.NOT_OWNER.lower())

    def test_a_temporary_password_someone_else_set_never_unlocks(self):
        # An owner who resets the flagged owner's password must not be able to sign in as him and unlock (security review).
        self.assertEqual([fa.may_unlock({**OWNER, "must_change_password": True}), fa.may_unlock({**OWNER, "must_change_password": False})],
                         [fa.TEMP_PASSWORD, None])

    def test_locking_needs_only_the_person(self):
        self.assertEqual([fa.may_lock({**OWNER, "must_change_password": True}), fa.may_lock(OWNER_NO_FLAG)], [None, fa.NOT_OWNER])

    def test_a_flag_on_an_account_admin_or_a_deactivated_owner_is_not_enough(self):
        self.assertEqual([fa.may_unlock({**ACCOUNT_ADMIN, "full_access_allowed": True}),
                          fa.may_unlock({**OWNER, "is_active": False})], [fa.NOT_OWNER, fa.NOT_OWNER])


class TimingTests(unittest.TestCase):
    def test_an_unlock_lasts_twelve_hours(self):
        self.assertEqual(fa.unlock_until(NOW), NOW + timedelta(hours=12))

    def test_is_on(self):
        self.assertEqual([fa.is_on(None, NOW), fa.is_on(NOW + timedelta(seconds=1), NOW), fa.is_on(NOW - timedelta(seconds=1), NOW),
                          fa.is_on(NOW, NOW)], [False, True, False, False])

    def test_five_wrong_passwords_block_for_fifteen_minutes_from_the_last(self):
        self.assertEqual([fa.fails_block(5, NOW - timedelta(minutes=10), NOW), fa.fails_block(5, NOW - timedelta(minutes=16), NOW),
                          fa.fails_block(4, NOW, NOW), fa.fails_block(0, None, NOW)],
                         [NOW + timedelta(minutes=5), None, None, None])

    def test_counting_wrong_passwords_starts_again_after_the_wait(self):
        self.assertEqual([fa.next_fails(0, None, NOW), fa.next_fails(3, NOW - timedelta(minutes=2), NOW),
                          fa.next_fails(3, NOW - timedelta(minutes=20), NOW), fa.next_fails(5, NOW - timedelta(minutes=16), NOW)],
                         [1, 4, 1, 1])


class RequestFullTests(unittest.TestCase):
    """At creation: only the flagged owner's own typed request, from a sign-in that is unlocked now."""

    def ask(self, user=OWNER, session=UNLOCKED, kind="question", options=None, swipe_ids=None, account=fa.HOME_ACCOUNT):
        return fa.request_full(user, session, kind, options or {}, swipe_ids or [], NOW, account)

    def test_the_owner_unlocked_typing_a_question(self):
        self.assertEqual([self.ask(kind=k) for k in fa.FULL_KINDS], [True] * 4)

    def test_kinds_started_from_elsewhere_never(self):
        self.assertEqual([self.ask(kind=k) for k in ("diagnose", "polish", "render", "advice", "something_new")], [False] * 5)

    def test_automatic_origins_never(self):
        cases = [{"schedule": "Daily"}, {"schedule_id": 3}, {"accepted": {"id": 9, "title": "x"}}, {"alert_key": "x"},
                 {"alert": {"title": "No leads"}}, {"advice": "x"}, {"brief": True}, {"prefill": True}, {"research_page": True}]
        self.assertEqual([self.ask(options=o) for o in cases] + [self.ask(swipe_ids=[3])], [False] * 10)

    def test_only_in_the_owners_own_account(self):
        # Another account's admins read its answers, and its Meta data is written by its own people (security review).
        self.assertEqual([self.ask(account=a) for a in (fa.HOME_ACCOUNT, 2, 3, None)], [True, False, False, False])

    def test_a_reply_or_a_preview_question_still_counts(self):
        self.assertEqual([self.ask(options={"reply": True}), self.ask(options={"reply": True, "about_attachment": 4})], [True, True])

    def test_locked_or_someone_else(self):
        self.assertEqual([self.ask(session=LOCKED), self.ask(session=None), self.ask(user=ACCOUNT_ADMIN), self.ask(user=OWNER_NO_FLAG),
                          self.ask(session={"user_id": 1, "full_until": NOW - timedelta(seconds=1)})], [False] * 5)

    def test_a_session_of_another_person_never(self):
        self.assertFalse(self.ask(session={"user_id": 9, "full_until": NOW + timedelta(hours=1)}))


class ClaimAccessTests(unittest.TestCase):
    """At claim: the server decides again with what holds now; the Mac only reads the answer."""

    def claim(self, task=TASK, session=UNLOCKED, owner_ok=True, others=False, version=(3, 0), automatic=False):
        return fa.claim_access(task, session, owner_ok, others, version, NOW, thread_automatic=automatic)

    def test_all_good_on_a_current_helper(self):
        self.assertEqual([self.claim(), self.claim(version=(3, 2))], [("full", None)] * 2)

    def test_never_meant_to_be_full_says_nothing(self):
        self.assertEqual([self.claim(task={**TASK, "full_session": None}), self.claim(task={**TASK, "kind": "diagnose"}),
                          self.claim(task={**TASK, "options": {"schedule": "Daily"}})], [("sandbox", None)] * 3)

    def test_signed_out_before_the_claim(self):
        access, why = self.claim(session=None)
        self.assertEqual((access, "signed out" in why), ("sandbox", True))

    def test_locked_before_the_claim(self):
        self.assertEqual(self.claim(session={**UNLOCKED, "full_until": NOW - timedelta(minutes=1)}),
                         ("sandbox", "Full access was locked before your Mac picked this up."))
        self.assertEqual(self.claim(session=LOCKED)[0], "sandbox")

    def test_no_longer_the_owner(self):
        access, why = self.claim(owner_ok=False)
        self.assertEqual((access, bool(why)), ("sandbox", True))

    def test_a_session_of_another_person(self):
        self.assertEqual(self.claim(session={**UNLOCKED, "user_id": 9})[0], "sandbox")

    def test_someone_else_wrote_in_the_conversation(self):
        self.assertEqual(self.claim(others=True), ("sandbox", "Someone else wrote in this conversation, so it ran with the usual tools."))

    def test_a_conversation_an_automatic_run_started(self):
        access, why = self.claim(automatic=True)
        self.assertEqual((access, "automatic" in why), ("sandbox", True))

    def test_a_request_in_another_account_even_if_marked(self):
        self.assertEqual([self.claim(task={**TASK, "account_id": 2}), self.claim(task={**TASK, "account_id": None})],
                         [("sandbox", fa.ELSEWHERE)] * 2)

    def test_link_text_and_research_page_origins_say_nothing(self):
        self.assertEqual([self.claim(task={**TASK, "options": {"prefill": True}}), self.claim(task={**TASK, "options": {"research_page": True}})],
                         [("sandbox", None)] * 2)

    def test_a_conversation_started_from_a_link_marks_the_thread_but_the_research_page_does_not(self):
        self.assertEqual(["prefill" in fa.THREAD_AUTOMATIC, "research_page" in fa.THREAD_AUTOMATIC], [True, False])

    def test_an_old_helper(self):
        self.assertEqual([self.claim(version=(2, 6)), self.claim(version=(2, 7))],
                         [("sandbox", "Your Mac helper needs the update for full access (desk 3.0).")] * 2)


class DeviceWordsTests(unittest.TestCase):
    def test_browser_and_system_in_plain_words(self):
        agents = {
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36": "Chrome on Mac",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1": "Safari on iPhone",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0": "Edge on Windows",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.1; rv:132.0) Gecko/20100101 Firefox/132.0": "Firefox on Mac",
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36": "Chrome on Android",
            "": "an unknown browser", None: "an unknown browser"}
        self.assertEqual({ua: fa.device_words(ua) for ua in agents}, agents)


if __name__ == "__main__":
    unittest.main()
