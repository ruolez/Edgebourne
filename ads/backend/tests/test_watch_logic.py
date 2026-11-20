"""Watch (the ad player): which video links are fetched, where a video is kept, how the keep is trimmed, how ?ids= is read."""
import os
import tempfile
import time
import unittest

import watch

CDN = "https://video-lax3-1.xx.fbcdn.net/o1/v/t2/f2/m69/clip.mp4?efg=x&oh=y"
VIDEO_ID = "1287634412290345"


class AllowedSource(unittest.TestCase):
    def test_meta_cdn_links_over_https_are_fetched(self):
        for url in (CDN, "https://scontent.cdninstagram.com/v/clip.mp4", "https://lookaside.fbsbx.com/x.mp4"):
            self.assertEqual(watch.allowed_source(url), True, url)

    def test_other_hosts_plain_http_and_lookalikes_are_refused(self):
        for url in ("http://video.xx.fbcdn.net/clip.mp4", "https://example.com/clip.mp4", "https://fbcdn.net.evil.com/clip.mp4",
                    "https://evilfbcdn.net/clip.mp4", "file:///etc/passwd", "", None, "not a url"):
            self.assertEqual(watch.allowed_source(url), False, url)

    def test_with_a_fake_graph_api_any_http_link_is_fetched_but_not_other_schemes(self):
        self.assertEqual([watch.allowed_source(u, dev=True) for u in ("http://fake-meta:5001/fake/_video/1.mp4", "file:///x", "ftp://h/x")],
                         [True, False, False])


class CacheFile(unittest.TestCase):
    def test_a_video_id_is_kept_as_its_own_mp4(self):
        self.assertEqual(watch.cache_file("/cache", VIDEO_ID), f"/cache/{VIDEO_ID}.mp4")

    def test_anything_but_digits_gets_no_file(self):
        self.assertEqual([watch.cache_file("/cache", v) for v in ("../etc/passwd", "12a", "", None)], [None, None, None, None])


class Prune(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def make(self, name, size, age):
        p = os.path.join(self.dir.name, name)
        with open(p, "wb") as f:
            f.write(b"x" * size)
        t = time.time() - age
        os.utime(p, (t, t))
        return p

    def test_the_least_recently_watched_go_first_until_the_keep_fits(self):
        old, mid, new = self.make("1.mp4", 400, 300), self.make("2.mp4", 400, 200), self.make("3.mp4", 400, 100)
        self.assertEqual(watch.prune(self.dir.name, limit=800), [old])
        self.assertEqual(sorted(os.listdir(self.dir.name)), ["2.mp4", "3.mp4"])
        self.assertEqual((os.path.exists(mid), os.path.exists(new)), (True, True))

    def test_the_video_just_fetched_stays_even_when_it_is_the_oldest(self):
        kept, other = self.make("1.mp4", 500, 900), self.make("2.mp4", 500, 100)
        self.assertEqual(watch.prune(self.dir.name, limit=600, keep=(kept,)), [other])

    def test_lock_and_part_files_are_left_alone_and_a_missing_folder_is_nothing_to_do(self):
        self.make("1.mp4.lock", 0, 10)
        self.make("2.mp4.part", 900, 10)
        self.assertEqual(watch.prune(self.dir.name, limit=0), [])
        self.assertEqual(watch.prune(os.path.join(self.dir.name, "none")), [])


class ParseIds(unittest.TestCase):
    def test_digits_in_order_without_repeats(self):
        self.assertEqual(watch.parse_ids(" 3,1,3,x,,2;9,1 "), ["3", "1"])

    def test_nothing_named_is_an_empty_list_and_the_list_is_capped(self):
        many = ",".join(str(i) for i in range(watch.IDS_LIMIT + 50))
        self.assertEqual((watch.parse_ids(None), len(watch.parse_ids(many))), ([], watch.IDS_LIMIT))


class Routes(unittest.TestCase):
    def test_the_list_and_the_video_need_someone_signed_in(self):
        import auth
        import watch_api
        login = auth.login_required(lambda: None).__code__
        self.assertEqual([watch_api.watch_list.__code__, watch_api.ad_video.__code__], [login, login])


if __name__ == "__main__":
    unittest.main()
