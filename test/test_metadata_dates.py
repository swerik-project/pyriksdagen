import unittest

import pandas as pd

from pyriksdagen.metadata import parse_date_interval


class TestMetadataDates(unittest.TestCase):
    def test_parse_date_interval_expands_start_boundaries(self):
        self.assertEqual(
            parse_date_interval("2020", is_end=False),
            (pd.Timestamp(2020, 1, 1), "year", None),
        )
        self.assertEqual(
            parse_date_interval("2020-03", is_end=False),
            (pd.Timestamp(2020, 3, 1), "month", None),
        )
        self.assertEqual(
            parse_date_interval("2020-03-15", is_end=False),
            (pd.Timestamp(2020, 3, 15), "day", None),
        )

    def test_parse_date_interval_expands_end_boundaries_as_exclusive(self):
        self.assertEqual(
            parse_date_interval("2020", is_end=True),
            (pd.Timestamp(2021, 1, 1), "year", None),
        )
        self.assertEqual(
            parse_date_interval("2020-03", is_end=True),
            (pd.Timestamp(2020, 4, 1), "month", None),
        )
        self.assertEqual(
            parse_date_interval("2020-12", is_end=True),
            (pd.Timestamp(2021, 1, 1), "month", None),
        )
        self.assertEqual(
            parse_date_interval("2020-03-15", is_end=True),
            (pd.Timestamp(2020, 3, 15), "day", None),
        )

    def test_parse_date_interval_reports_blank_and_malformed_values(self):
        self.assertEqual(parse_date_interval("", is_end=False), (None, None, "blank"))
        self.assertEqual(
            parse_date_interval("", is_end=True),
            (pd.Timestamp.max.normalize(), None, "blank"),
        )
        self.assertEqual(
            parse_date_interval("2020-13", is_end=False),
            (None, None, "malformed"),
        )
        self.assertEqual(
            parse_date_interval("not-a-date", is_end=False),
            (None, None, "malformed"),
        )


if __name__ == "__main__":
    unittest.main()
