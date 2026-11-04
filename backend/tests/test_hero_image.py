import io
import itertools
import json
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

import hero_image

SIZES = [(2400, 1600), (1536, 1024), (1344, 768), (1024, 1024), (900, 1600), (1601, 999)]
RATIOS = [hero_image.PORTRAIT, hero_image.LANDSCAPE, hero_image.OG_SIZE]
FOCI = [0.0, 0.25, 0.5, 0.75, 1.0]


class CropBoxTest(unittest.TestCase):
    def test_box_has_the_requested_ratio_and_fills_one_side(self):
        for (w, h), (rw, rh), fx in itertools.product(SIZES, RATIOS, FOCI):
            left, top, right, bottom = hero_image.crop_box(w, h, rw, rh, fx)
            cw, ch = right - left, bottom - top
            with self.subTest(size=(w, h), ratio=(rw, rh), focus=fx):
                self.assertTrue(0 <= left and right <= w and 0 <= top and bottom <= h)
                self.assertTrue(cw == w or ch == h)
                self.assertLessEqual(abs(cw * rh - ch * rw), max(rw, rh))

    def test_focus_slides_the_box_from_left_edge_to_right_edge(self):
        w, h = 2400, 1600
        rw, rh = hero_image.PORTRAIT
        crop_w = round(h * rw / rh)
        self.assertEqual(hero_image.crop_box(w, h, rw, rh, 0.0), (0, 0, crop_w, h))
        self.assertEqual(hero_image.crop_box(w, h, rw, rh, 1.0), (w - crop_w, 0, w, h))
        left = (w - crop_w) // 2
        self.assertEqual(hero_image.crop_box(w, h, rw, rh, 0.5), (left, 0, left + crop_w, h))

    def test_taller_image_is_cropped_vertically_around_the_middle(self):
        w, h = 1000, 1600
        rw, rh = hero_image.LANDSCAPE
        crop_h = round(w * rh / rw)
        top = (h - crop_h) // 2
        self.assertEqual(hero_image.crop_box(w, h, rw, rh, 0.5), (0, top, w, top + crop_h))


class RenditionWidthsTest(unittest.TestCase):
    def test_widths_never_exceed_the_crop_and_end_at_its_size(self):
        widths = hero_image.PORTRAIT_WIDTHS
        cases = {
            500: [500],
            640: [640],
            1280: [640, 1040, 1280],
            1560: [640, 1040, 1560],
            2133: [640, 1040, 1560],
        }
        for crop_w, expected in cases.items():
            with self.subTest(crop_w=crop_w):
                self.assertEqual(hero_image.rendition_widths(crop_w, widths), expected)


class LoadTest(unittest.TestCase):
    def test_anything_but_a_stored_cut_reads_as_no_photo(self):
        for value in ["", None, "not json", "[]", '{"portrait": []}', '"x"']:
            with self.subTest(value=value):
                self.assertIsNone(hero_image.load(value))

    def test_a_stored_cut_round_trips(self):
        info = {"portrait": [{"src": "/uploads/hero/a-p-640.webp", "w": 640, "h": 800}]}
        self.assertEqual(hero_image.load(json.dumps(info)), info)


class _Upload:
    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw


def _png(size):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 190, 170)).save(buf, "PNG")
    return buf.getvalue()


class MasterAndCutTest(unittest.TestCase):
    """Writes real files, into a throwaway uploads directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(hero_image.config, "UPLOADS_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _files(self):
        return sorted(os.listdir(os.path.join(self.tmp.name, hero_image.SUBDIR)))

    def test_cut_writes_every_rendition_at_its_stated_size(self):
        master, warning = hero_image.save_master(_Upload(_png((2400, 1600))))
        info = hero_image.cut(master, "right")

        self.assertIsNone(warning)
        self.assertEqual(
            [(r["w"], r["h"]) for r in info["portrait"]], [(640, 800), (1040, 1300), (1280, 1600)]
        )
        self.assertEqual([(r["w"], r["h"]) for r in info["landscape"]], [(800, 600), (1200, 900)])
        for r in info["portrait"] + info["landscape"]:
            with Image.open(os.path.join(self.tmp.name, r["src"][len("/uploads/"):])) as im:
                self.assertEqual(im.size, (r["w"], r["h"]))
        with Image.open(os.path.join(self.tmp.name, info["og"][len("/uploads/"):])) as im:
            self.assertEqual((im.format, im.size), ("JPEG", hero_image.OG_SIZE))

    def test_delete_cut_keeps_only_the_master(self):
        master, _ = hero_image.save_master(_Upload(_png((1600, 1200))))
        info = hero_image.cut(master)
        hero_image.delete_cut(info)
        self.assertEqual(self._files(), [os.path.basename(master)])
        hero_image.delete_cut(info, keep_master=False)
        self.assertEqual(self._files(), [])

    def test_a_master_shipped_under_static_is_cut_into_uploads(self):
        static = os.path.join(self.tmp.name, "static")
        os.makedirs(os.path.join(static, "media", "hero"))
        Image.new("RGB", (1536, 1024)).save(os.path.join(static, "media", "hero", "m.webp"))
        with mock.patch.object(hero_image, "STATIC_DIR", static):
            info = hero_image.cut("/static/media/hero/m.webp")
            hero_image.delete_cut(info, keep_master=False)

        self.assertEqual([r["w"] for r in info["portrait"]], [640, 819])
        self.assertTrue(os.path.exists(os.path.join(static, "media", "hero", "m.webp")))
        self.assertEqual(self._files(), [])

    def test_small_images_are_refused_and_soft_ones_warned_about(self):
        with self.assertRaises(ValueError):
            hero_image.save_master(_Upload(_png((1200, hero_image.MIN_SHORT_SIDE - 1))))
        _, warning = hero_image.save_master(_Upload(_png((1344, 768))))
        self.assertIsNotNone(warning)

    def test_non_images_are_refused(self):
        for raw in [b"", b"plain text, not an image"]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                hero_image.save_master(_Upload(raw))


if __name__ == "__main__":
    unittest.main()
