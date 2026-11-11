"""Regression test for DCAT exports using a self-contained records example.

``data/riksdagen-records-info.yml`` is an example fixture maintained here.
``data/dcat_records_ref.rdf`` was generated with the pre-review writer at
pyriksdagen revision 449e139 and inspected against that YAML.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lxml import etree as ET

from pyriksdagen.repository_info import write_dcat_rdf


class RepositoryInfoDcatTest(unittest.TestCase):
    def test_records_dcat_export_matches_reference(self):
        """Guarantee: the example records YAML exports the reviewed RDF/XML reference.

        Data: reads the YAML and RDF fixtures in ``test/data/`` and writes
        generated output only to a temporary directory. XML canonicalization
        ignores indentation, attribute order, and namespace declaration placement.
        Every exported value and resource link remains part of the comparison.

        Review deliberate metadata or writer changes before updating the RDF
        reference; the test must never regenerate its own expected output.
        """
        data_path = Path(__file__).with_name("data")
        reference_path = data_path / "dcat_records_ref.rdf"
        parser = ET.XMLParser(remove_blank_text=True)
        reference = ET.parse(str(reference_path), parser)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "dcat" / "records.rdf"
            write_dcat_rdf(data_path / "riksdagen-records-info.yml", output_path)
            generated = ET.parse(str(output_path), parser)

        self.assertEqual(
            ET.tostring(generated, method="c14n", exclusive=True),
            ET.tostring(reference, method="c14n", exclusive=True),
            f"DCAT export differs from the reviewed reference at {reference_path}. "
            "Inspect the metadata and writer changes before updating the reference.",
        )


if __name__ == "__main__":
    unittest.main()
