from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree as ET

import yaml

from pyriksdagen.repository_info import write_dcat_rdf


class RepositoryInfoDcatTest(unittest.TestCase):
    def test_write_dcat_rdf(self):
        info = {
            "repository": {
                "name": "riksdagen-records",
                "url": "https://github.com/swerik-project/riksdagen-records",
            },
            "dataset": {
                "identifier": "riksdagen-records",
                "title": {
                    "en": "The Swedish Parliament Corpus: Riksdagen Records",
                    "sv": "Sveriges riksdagskorpus: Riksdagsprotokollen",
                },
                "description": {
                    "en": "Parliamentary Records of the Swedish Riksdag.",
                    "sv": "Riksdagsprotokoll från Sveriges riksdag.",
                },
                "languages": ["sv"],
                "keywords": {"en": ["parliamentary records"], "sv": ["riksdagsprotokoll"]},
                "themes": ["http://publications.europa.eu/resource/authority/data-theme/GOVE"],
                "type": "dataset",
                "landing_page_url": "https://github.com/swerik-project/the-swedish-parliament-corpus",
                "license": "",
                "temporal_coverage": {"start": "1867"},
            },
            "publisher": {
                "name": {"en": "Uppsala University", "sv": "Uppsala universitet"},
                "url": "https://www.uu.se/",
            },
            "contact": {
                "name": "SWERIK project",
                "url": "https://github.com/orgs/swerik-project/discussions",
            },
            "documentation": {
                "readme_url": "https://github.com/swerik-project/riksdagen-records#readme",
            },
            "citation": {
                "cff_url": "https://github.com/swerik-project/riksdagen-records/blob/main/CITATION.cff",
            },
            "relations": {
                "related_repositories": ["https://github.com/swerik-project/riksdagen-persons"],
            },
            "distributions": [
                {
                    "name": "records.zip",
                    "access_url": "https://github.com/swerik-project/riksdagen-records/releases/latest/download/records.zip",
                    "download_url": "https://github.com/swerik-project/riksdagen-records/releases/latest/download/records.zip",
                    "media_type": "application/zip",
                    "format": "ZIP",
                }
            ],
        }

        with TemporaryDirectory() as tmpdir:
            info_path = Path(tmpdir) / "repository-info.yml"
            output_path = Path(tmpdir) / "repository-info.rdf"
            with info_path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(info, handle, sort_keys=False)
            write_dcat_rdf(info_path, output_path)
            root = ET.parse(output_path).getroot()

        self.assertEqual(root.tag, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF")
        self.assertEqual(len(root.findall("{http://www.w3.org/ns/dcat#}Catalog")), 1)
        self.assertEqual(len(root.findall("{http://www.w3.org/ns/dcat#}Dataset")), 1)
        self.assertEqual(len(root.findall("{http://www.w3.org/ns/dcat#}Distribution")), 1)
        periods = root.findall("{http://purl.org/dc/terms/}PeriodOfTime")
        self.assertEqual(len(periods), 1)
        start_date = periods[0].find("{http://www.w3.org/ns/dcat#}startDate")
        self.assertEqual(start_date.text, "1867")
        self.assertEqual(
            start_date.attrib["{http://www.w3.org/1999/02/22-rdf-syntax-ns#}datatype"],
            "http://www.w3.org/2001/XMLSchema#gYear",
        )


if __name__ == "__main__":
    unittest.main()
