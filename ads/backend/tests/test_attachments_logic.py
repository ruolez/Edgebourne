"""FU-D: previews Claude made in a conversation (desk_attachments). Their size read from the bytes, and which old
bodies go when an account's previews would pass the 1 GB budget."""
import struct
import unittest
from datetime import datetime, timedelta, timezone

import attachments


def box(kind, payload):
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def mp4(width, height, timescale, duration, moov_last=False):
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isommp41")
    mvhd = box(b"mvhd", b"\x00\x00\x00\x00" + b"\x00" * 8 + struct.pack(">II", timescale, duration) + b"\x00" * 80)
    audio = box(b"trak", box(b"tkhd", b"\x00\x00\x00\x07" + b"\x00" * 72 + struct.pack(">II", 0, 0)))
    video = box(b"trak", box(b"tkhd", b"\x00\x00\x00\x07" + b"\x00" * 72 + struct.pack(">II", width << 16, height << 16)))
    moov = box(b"moov", mvhd + audio + video)
    mdat = box(b"mdat", b"\x00" * 64)
    return ftyp + (mdat + moov if moov_last else moov + mdat)


class MeasureTests(unittest.TestCase):
    def test_png(self):
        data = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1080, 1350) + b"\x08\x06\x00\x00\x00"
        self.assertEqual(attachments.measure("image/png", data), {"width": 1080, "height": 1350, "duration_ms": None})

    def test_jpeg_reads_the_frame_header_past_other_segments(self):
        app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
        sof = b"\xff\xc2" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", 1920, 1080) + b"\x03" + b"\x00" * 9
        self.assertEqual(attachments.measure("image/jpeg", b"\xff\xd8" + app0 + sof + b"\xff\xd9"),
                         {"width": 1080, "height": 1920, "duration_ms": None})

    def test_webp_extended_lossy_and_lossless(self):
        vp8x = b"RIFF\x00\x00\x00\x00WEBPVP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00" + (1079).to_bytes(3, "little") + (1349).to_bytes(3, "little")
        vp8 = b"RIFF\x00\x00\x00\x00WEBPVP8 " + struct.pack("<I", 10) + b"\x00\x00\x00\x9d\x01\x2a" + struct.pack("<HH", 640, 480)
        bits = (99) | (49 << 14)
        vp8l = b"RIFF\x00\x00\x00\x00WEBPVP8L" + struct.pack("<I", 5) + b"\x2f" + struct.pack("<I", bits)
        self.assertEqual([attachments.measure("image/webp", d) for d in (vp8x, vp8, vp8l)],
                         [{"width": 1080, "height": 1350, "duration_ms": None}, {"width": 640, "height": 480, "duration_ms": None},
                          {"width": 100, "height": 50, "duration_ms": None}])

    def test_mp4_size_from_the_video_track_and_length_from_the_movie_header(self):
        self.assertEqual([attachments.measure("video/mp4", mp4(1080, 1920, 1000, 9000)),
                          attachments.measure("video/mp4", mp4(720, 1280, 600, 5400, moov_last=True))],
                         [{"width": 1080, "height": 1920, "duration_ms": 9000}, {"width": 720, "height": 1280, "duration_ms": 9000}])

    def test_a_phones_mov_is_measured_like_an_mp4(self):
        self.assertEqual(attachments.measure("video/quicktime", mp4(1920, 1080, 600, 3000)), {"width": 1920, "height": 1080, "duration_ms": 5000})

    def test_a_page_has_no_size_of_its_own(self):
        self.assertEqual(attachments.measure("text/html", b"<!doctype html><html></html>"), {"width": None, "height": None, "duration_ms": None})

    def test_unreadable_bytes_give_nothing_rather_than_a_guess(self):
        empty = {"width": None, "height": None, "duration_ms": None}
        self.assertEqual([attachments.measure("image/png", b"\x89PNG\r\n\x1a\n"), attachments.measure("video/mp4", b"\x00\x00\x00\x18ftyp"),
                          attachments.measure("image/jpeg", b"\xff\xd8\xff\xe0\x00"), attachments.measure("image/gif", b"GIF89a")], [empty] * 4)


class PageTests(unittest.TestCase):
    """A page Claude built: one HTML document in UTF-8, taken only when the Mac says it is a page."""

    def test_an_html_document_passes_with_or_without_a_byte_order_mark(self):
        pages = [b"<!doctype html><html><body>Hi</body></html>", b"\xef\xbb\xbf\n  <!DOCTYPE HTML>\n<html>", b"<html lang='en'><p>x</p></html>"]
        self.assertEqual([attachments.page_problem(p) for p in pages], [None, None, None])

    def test_other_bytes_and_oversize_pages_are_refused_in_words(self):
        cases = [b"\x89PNG\r\n\x1a\n", b"just some text", b"<svg xmlns='http://www.w3.org/2000/svg'>", b"<!doctype html>\xff\xfe", b"",
                 b"<!doctype html>" + b"x" * attachments.MAX_BYTES["page"]]
        self.assertEqual([bool(attachments.page_problem(c)) for c in cases], [True] * len(cases))

    def test_a_shown_page_gets_no_origin_no_scripts_no_requests_and_only_the_console_frames_it(self):
        parts = [p.strip() for p in attachments.PAGE_CSP.split(";")]
        self.assertEqual(("sandbox" in parts, "default-src 'none'" in parts, "frame-ancestors 'self'" in parts, "form-action 'none'" in parts,
                          any("script" in p or "allow-" in p or "http" in p or "connect" in p for p in parts)), (True, True, True, True, False))

    def test_html_is_never_one_of_the_types_read_from_bytes(self):
        """A page can't arrive by accident: sniff never says text/html, so only the declared path stores one."""
        self.assertEqual(attachments.sniff(b"<!doctype html><html></html>" + b" " * 40), None)


class FileIdTests(unittest.TestCase):
    """The ids of the files sent with a message, from the request body."""

    def test_whole_numbers_once_each_in_order(self):
        self.assertEqual([attachments.clean_file_ids(v) for v in ([3, 1, 3, 2], [], None, "")], [[3, 1, 2], [], [], []])

    def test_anything_else_or_too_many_is_refused(self):
        cases = ["3", [True], [1.5], ["7"], [0], [-2], {"id": 1}, [[1]], list(range(1, attachments.MAX_FILES + 2))]
        self.assertEqual([attachments.clean_file_ids(c) for c in cases], [None] * len(cases))


class PruneTests(unittest.TestCase):
    T = datetime(2026, 11, 13, tzinfo=timezone.utc)

    def rows(self, *sizes):
        return [{"id": i + 1, "size_bytes": s, "created_at": self.T + timedelta(minutes=i)} for i, s in enumerate(sizes)]

    def test_the_oldest_go_first_until_the_new_one_fits(self):
        self.assertEqual([attachments.to_prune(self.rows(40, 30, 20), 30, 100), attachments.to_prune(self.rows(40, 30, 20), 10, 100),
                          attachments.to_prune(self.rows(40, 30, 20), 75, 100)], [[1], [], [1, 2]])

    def test_order_comes_from_the_time_not_the_list(self):
        rows = self.rows(40, 30, 20)[::-1]
        self.assertEqual(attachments.to_prune(rows, 30, 100), [1])


if __name__ == "__main__":
    unittest.main()
