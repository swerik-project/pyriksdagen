"""Unit tests for pyriksdagen"""
import unittest

from pyriksdagen.utils import infer_metadata
from pyriksdagen.utils import get_formatted_uuid
from pyriksdagen.utils import get_data_location
from pyriksdagen.segmentation import intro_to_dict
from pyriksdagen.date_handling import yearize_date
from pyriksdagen.metadata import load_Corpus_metadata
from pyriksdagen.metadata import increase_date_precision

import polars as pl
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
        metadata_path = get_data_location("metadata")
        self.assertIsNotNone(metadata_path)
        riksmote_path = Path(metadata_path) / "riksdag-year.csv"
        riksmote = pl.read_csv(riksmote_path)

        self.assertEqual(yearize_date("1982-04-13", riksmote), 198182)
        self.assertEqual(yearize_date("1982-12-05", riksmote), 198283)
        self.assertEqual(yearize_date("1882-04-13", riksmote), 1882)
        self.assertEqual(yearize_date("1882-12-05", riksmote), 1882)
        self.assertEqual(yearize_date("1932-04-13", riksmote), 1932)
        self.assertEqual(yearize_date("1942-12-05", riksmote), 1942)

    def test_load_Corpus_metadata(self):
        db = load_Corpus_metadata()
        print(db)

        db.write_csv("test/result/metadata_output.csv")
        MIN_LEN = 10000
        self.assertGreaterEqual(len(db), MIN_LEN, f"Persons database should be at least {MIN_LEN} rows, got {len(db)}")

    @unittest.skipIf(
        os.getenv("RUN_METADATA_REFERENCE_COMPARISON") != "1",
        "Check metadata output ONLY if reference is properly specified"
    )
    def test_load_Corpus_metadata_w_ref(self):
        """
        Guarantee: load_Corpus_metadata perfectly replicates its reference behavior on real data.

        The environtment variable RUN_METADATA_REFERENCE_COMPARISON needs to be set for this to run.
        The environtment variable METADATA_PATH needs to be set to path/to/riksdagen-persons/data 
        for this to run properly, and riksdagen-persons needs to be checked out to the commit
        with the hash 0104e06fade5b561a95ca9ec043c2f013a78848e for an apples-to-apples comparison.

        As the output is written to test/result/metadata_output.csv, git diff test/result/metadata_output.csv
        enumerates all differing rows between the reference output and the obtained output.
        """
        db = load_Corpus_metadata()
        db = db.sort(db.columns)
        db.write_csv("test/result/metadata_output.csv")
        db = pl.read_csv("test/result/metadata_output.csv")
        db = db.sort(db.columns)
        db_ref = pl.read_csv("test/result/reference_metadata_output.csv")
        db_ref = db_ref.sort(db_ref.columns)
        is_equal = db.equals(db_ref)
        orig_columns = list(db.columns)
        db = db.with_columns(pl.lit("generated").alias("reference")).sort(db.columns)
        db_ref = db_ref.with_columns(pl.lit("reference").alias("reference")).sort(db.columns)

        diff_dfs = pl.concat([db, db_ref])
        diff_dfs = diff_dfs.filter(~diff_dfs.select(orig_columns).is_duplicated()).sort(orig_columns)

        diff_ids = set(diff_dfs["person_id"])

        all_rows = pl.concat([db, db_ref])
        all_rows = all_rows.filter(pl.col("person_id").is_in(diff_ids)).sort(orig_columns)

        self.assertTrue(is_equal, f"Persons database should equal to reference, got\n{db}\nvs ref:\n{db_ref}\n{diff_dfs}\nAll people with inconsistencies:\n{all_rows}")

    def test_increase_date_precision(self):
        """Guarantee: date precision is increased correctly for year and month levels, while not altering full dates."""
        test_values = {("1918", True): "1918-01-01",
                        ("1918", False): "1918-12-31",
                        ("1900-02",False): "1900-02-28",
                        ("1920-02",False): "1920-02-29",
                        ("2025-07",True): "2025-07-01",
                        ("1999-02-15",True): "1999-02-15",
                        ("1973-11-30",False): "1973-11-30"
                        }
        for input, start in test_values:
            ref_output = test_values[(input,start)]
            output = increase_date_precision(input, start=start)
            self.assertEqual(output, ref_output, f"Mismatch between output {output} and correct value {ref_output} (input: {input}, start: {start})")


if __name__ == "__main__":
    unittest.main()
