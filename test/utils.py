"""Tests for pyriksdagen utility metadata inference."""
from __future__ import annotations

import unittest

from pyriksdagen.utils import infer_metadata
from pyriksdagen.utils import get_formatted_uuid
from pyriksdagen.segmentation import intro_to_dict
from pyriksdagen.date_handling import yearize_date
from pyriksdagen.metadata import load_Corpus_metadata

import pandas as pd
from pathlib import Path
import os

class TestUtils(unittest.TestCase):
    def test_infer_metadata(self):
        metadata = infer_metadata("data/200809/prot-200809--041.xml")

        self.assertEqual(metadata["number"], 41)
        self.assertIsNone(metadata["part"])

        metadata = infer_metadata("data/200809/prot-200809---041.xml")

        self.assertEqual(metadata["number"], 41)
        self.assertIsNone(metadata["part"])

        metadata = infer_metadata("data/1958/prot-1958-a-ak--017-02.xml")

        self.assertEqual(metadata["number"], 17)
        self.assertEqual(metadata["part"], 2)

        metadata = infer_metadata("data/motions/mot-2024-25--123.xml")

        self.assertEqual(metadata["number"], 123)
        self.assertIsNone(metadata["part"])

    def test_uuid_creation(self):
        seed1 = "test1"
        seed2 = "test2"

        uuid1a = get_formatted_uuid(seed1)
        uuid1b = get_formatted_uuid(seed1)
        uuid2 = get_formatted_uuid(seed2)
        uuid3 = get_formatted_uuid()
        uuid4 = get_formatted_uuid()

        for uuid in [uuid1a, uuid1b, uuid2, uuid3, uuid4]:
            self.assertEqual(uuid[:2], "i-", f"Incorrect format in the UUID: {uuid}")

        self.assertEqual(uuid1a, uuid1b, "Same seed should yield same UUID")
        self.assertNotEqual(uuid1a, uuid2, "Different seed should yield different UUID")
        self.assertNotEqual(uuid3, uuid4, "No seed should yield different UUIDs")

    def test_intro_to_dict(self):
        intro = "Herr Anderson i Stockholm"
        d = intro_to_dict(intro)
        self.assertEqual(d.get("name"), "Anderson", f"'name' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("specifier"), "Stockholm", f"'specifier' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("gender"), "man", f"'gender' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("other"), None, f"No 'other' should be found in '{intro}' ({d})")

        intro = "Elving Andersson (c)"
        d = intro_to_dict(intro)
        self.assertEqual(d.get("name"), "Andersson", f"'name' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("party"), "(c)", f"'Party' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("specifier"), None, f"No 'specifier' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("gender"), None, f"'gender' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("other"), None, f"No 'other' should be found in '{intro}' ({d})")

        intro = "NILS BERNDTSON (vpk) i Linköping"
        d = intro_to_dict(intro)
        self.assertEqual(d.get("name"), "NILS BERNDTSON", f"'name' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("party"), "(vpk)", f"'Party' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("specifier"), "Linköping", f"'specifier' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("gender"), None, f"No 'gender' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("other"), None, f"No 'other' should be found in '{intro}' ({d})")

        intro = "K. G. Ewerlöf"
        d = intro_to_dict(intro)
        self.assertEqual(d.get("name"), "Ewerlöf", f"'name' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("party"), None, f"'Party' should be found in '{intro}' ({d})")
        self.assertEqual(d.get("other"), None, f"No 'other' should be found in '{intro}' ({d})")

    def test_yearize_date(self):
        metadata_path = os.environ.get("METADATA_PATH")
        self.assertIsNotNone(metadata_path)
        riksmote_path = Path(metadata_path) / "riksdag-year.csv"
        riksmote = pd.read_csv(riksmote_path)

        self.assertEqual(yearize_date("1982-04-13", riksmote), 198182)
        self.assertEqual(yearize_date("1982-12-05", riksmote), 198283)
        self.assertEqual(yearize_date("1882-04-13", riksmote), 1882)
        self.assertEqual(yearize_date("1882-12-05", riksmote), 1882)
        self.assertEqual(yearize_date("1932-04-13", riksmote), 1932)
        self.assertEqual(yearize_date("1942-12-05", riksmote), 1942)

    def test_load_Corpus_metadata(self):
        db = load_Corpus_metadata()
        print(db)
        MIN_LEN = 10000
        self.assertGreaterEqual(len(db), MIN_LEN, f"Persons database should be at least {MIN_LEN} rows, got {len(db)}")

if __name__ == "__main__":
    unittest.main()
