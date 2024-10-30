"""
General utilities related to curation of Riksdagen motions.
"""
from pyriksdagen.utils import parse_tei



def fetch_template(loc="input/motions/mot-template.xml" ):
    root, ns = parse_tei(loc)
    return root, ns
