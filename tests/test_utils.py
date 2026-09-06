"""Tests for pyriksdagen utility metadata inference."""
from __future__ import annotations

import unittest

from pyriksdagen.utils import infer_metadata


class TestInferMetadata(unittest.TestCase):
    def test_protocol_number_from_xml_path(self):
        metadata = infer_metadata("data/200809/prot-200809--041.xml")

        self.assertEqual(metadata["number"], 41)
        self.assertIsNone(metadata["part"])

    def test_protocol_number_from_triple_hyphen_suffix(self):
        metadata = infer_metadata("data/200809/prot-200809---041.xml")

        self.assertEqual(metadata["number"], 41)
        self.assertIsNone(metadata["part"])

    def test_split_protocol_uses_protocol_number_and_part(self):
        metadata = infer_metadata("data/1958/prot-1958-a-ak--017-02.xml")

        self.assertEqual(metadata["number"], 17)
        self.assertEqual(metadata["part"], 2)

    def test_motion_number_is_unchanged(self):
        metadata = infer_metadata("data/motions/mot-2024-25--123.xml")

        self.assertEqual(metadata["number"], 123)
        self.assertIsNone(metadata["part"])


if __name__ == "__main__":
    unittest.main()
