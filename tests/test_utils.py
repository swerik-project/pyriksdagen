"""
Unit tests for filename-derived protocol date metadata.

These tests document the reusable contract behind early protocol date repair:
pre-1875 protocol filenames with a final MMDD component encode the expected
sitting date, while later protocol numbers and malformed dates must not be
treated as dates. The fixtures are inline filenames so the test stays fast,
deterministic, and independent of the full corpus checkout.
"""

# Include a pathlib to check that also pathobject can parse dates
from pathlib import Path
import unittest

from pyriksdagen.utils import expected_pre_1875_date_from_filename


class ExpectedPre1875DateFromFilenameTest(unittest.TestCase):
    def test_pre_1875_protocol_filename_date_is_returned_as_iso_date(self):
        """Pre-1875 protocol filenames with MMDD suffix should yield ISO dates."""
        cases = {
            "data/1867/prot-1867--ak--0204.xml": "1867-02-04",
            "data/1871/prot-1871-urtima-fk--1007.xml": "1871-10-07",
            Path("data/1872/prot_1872_ak_0229.xml"): "1872-02-29",
        }

        for filename, expected_date in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    expected_pre_1875_date_from_filename(filename),
                    expected_date,
                    "Expected pre-1875 protocol filename MMDD suffix to "
                    "become an ISO date",
                )

    def test_explicit_year_can_supply_protocol_year(self):
        """Callers with trusted metadata can pass the protocol year explicitly."""
        self.assertEqual(
            expected_pre_1875_date_from_filename(
                "prot-unknown--fk--1231.xml",
                year="1868",
            ),
            "1868-12-31",
            "Explicit year should be used when the filename does not expose "
            "a parseable year",
        )

    def test_non_date_protocol_filenames_return_none(self):
        """Modern protocol numbers and non-MMDD filenames should not yield dates."""
        cases = [
            "data/1875/prot-1875--ak--0204.xml",
            "data/198081/prot-198081--0123.xml",
            "data/1867/prot-1867--ak--007.xml",
            "data/1871/prot-1871--ak--0230.xml",
            "data/1867/mot-1867--ak--0204.xml",
        ]

        for filename in cases:
            with self.subTest(filename=filename):
                self.assertIsNone(
                    expected_pre_1875_date_from_filename(filename),
                    "Filename must not be interpreted as a pre-1875 protocol date",
                )


if __name__ == "__main__":
    unittest.main()
