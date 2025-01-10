#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Provides useful utilities for the other modules as well as for general use.
"""
from bs4 import BeautifulSoup
from datetime import datetime
from lxml import etree
from pathlib import Path
from pyparlaclarin.refine import format_texts
from tqdm import tqdm
from trainerlog import get_logger
import base58
import hashlib
import os
import requests
import uuid
import warnings
import xmlschema
import zipfile




LOGGER = get_logger("pyriksdagen")
XML_NS = "{http://www.w3.org/XML/1998/namespace}"
TEI_NS = "{http://www.tei-c.org/ns/1.0}"


def fetch_ns():
    return {"tei_ns": TEI_NS,
            "xml_ns": XML_NS}


def elem_iter(root, ns="{http://www.tei-c.org/ns/1.0}"):
    """
    Return an iterator of the elements (utterances, notes, pbs) in a protocol body

    Args:
        root (lxml.etree.Element): the protocol data as an lxml tree root
        ns (str): TEI namespace, defaults to TEI v1.0.

    """
    for body in root.findall(".//" + ns + "body"):
        for div in body.findall(ns + "div"):
            for ix, elem in enumerate(div):
                if elem.tag == ns + "u":
                    yield "u", elem
                elif elem.tag == ns + "note":
                    yield "note", elem
                elif elem.tag == ns + "pb":
                    yield "pb", elem
                #elif elem.tag == ns + "seg": # Code doesn't return segs anyway (2023-09-20), but
                #    yield "seg", elem        # commenting out in case of catastrophy -- fully delete after
                elif elem.tag == "u":
                    elem.tag = ns + "u"
                    yield "u", elem
                else:
                    LOGGER.warning(f"Encountered unknown tag: {elem.tag}")
                    yield None


def infer_metadata(filename):
    """
    Heuristically infer metadata from a protocol id or filename.

    Args:
        filename (str): the protocols filename. Agnostic wrt. dashes and underscores. Can be relative or absolute.

    Returns a dict with keys "protocol", "chamber", "year", and "number"
    """
    metadata = dict()
    filename = filename.replace("-", "_")
    metadata["protocol"] = filename.split("/")[-1].split(".")[0]
    split = filename.split("/")[-1].split("_")
    metadata["document_type"] = split[0]

    # Year
    for s in split:
        yearstr = s[:4]
        if yearstr.isdigit():
            year = int(yearstr)
            if year > 1800 and year < 2100:
                metadata["year"] = year
                metadata["sitting"] = str(year)

                # Protocol ids of format 197879 have two years, eg. 1978 and 1979
                if s[4:6].isdigit() or "urtima" in metadata["protocol"]:
                    metadata["secondary_year"] = year + 1
                    metadata["sitting"] += f"{s[4:6]}"

    # Chamber
    metadata["chamber"] = "Enkammarriksdagen"
    if "_ak_" in filename:
        metadata["chamber"] = "Andra kammaren"
    elif "_fk_" in filename:
        metadata["chamber"] = "Första kammaren"

    try:
        metadata["number"] = int(split[-1])
    except:
        pass  # print("Number parsing unsuccesful", filename)

    return metadata


def clean_html(s):
    """
    Read a HTML file and turn it into valid XML

    Args:
        s (str): original HTML as a string

    Returns:
        tree (lxml.etree.tree): XML tree
    """
    soup = BeautifulSoup(s)
    pretty_html = soup.prettify()
    return etree.fromstring(pretty_html)


def validate_xml_schema(xml_path, schema_path, schema=None):
    """
    Validate an XML file against a schema.

    Args:
        xml_path (str): path to the XML file
        schema_path (str): path to the schema file

    Returns:
        is_valid (bool): whether the XML is valid according to the schema
    """
    xml_file = etree.parse(xml_path)
    xml_file.xinclude()

    if schema is None:
        schema = xmlschema.XMLSchema(schema_path)

    try:
        schema.validate(xml_file)
        return True
    except Exception as err:
        print(err)
        return False

    return is_valid


def corpus_iterator(document_type, corpus_root=None, start=None, end=None):
    """
    Returns an iterator of document paths in a corpus.

    Args:
        document_type (str): type of document (prot, mot, etc.). Valid types:
                            - records | prot
                            - motions | mot
                            - interpellations | ipq
        corpus_root (str): path to the corpus root. If None, the function looks for the default location (see get_data_location()) based on the doctype
        start (int): start year
        end (int): end year

    Returns:
        iterator of the protocols as relative paths to current location
    """
    doctypes = {
        "interpellations": "interpellations",
        "ipq": "interpellations",
        "motions":"motions",
        "mot": "motions",
        "prot": "records",
        "records": "records"
    }
    if document_type not in doctypes:
        raise ValueError(f"{document_type} not valid")
    if corpus_root is None:
        corpus_root = get_data_location(doctypes[document_type])
    folder = Path(corpus_root)
    if folder.is_absolute():
        folder = folder.relative_to(Path(".").resolve(), walk_up=True)
    docs = folder.glob("*/*.xml")
    for doc in sorted(docs):
        if start is not None:
            metadata = infer_metadata(doc.name)
            if "year" not in metadata:
                continue
            year = metadata["year"]
            secondary_year = metadata.get("secondary_year", year)
            if start <= year and end >= secondary_year:
                yield str(doc.relative_to("."))
        else:
            yield str(doc.relative_to("."))


def protocol_iterators(corpus_root=None, document_type=None, start=None, end=None):
    """
    Deprecate - Use corpus_iterator() instead.
    Returns an iterator of protocol paths in a corpus.

    Args:
        corpus_root (str): path to the corpus root. If env variable RECORDS_PATH exists, uses that as a default
        document_type (str): type of document (prot, mot, etc.). If None, fetches all types
        start (int): start year
        end (int): end year

    Returns:
        iterator of the protocols as relative paths to current location
    """
    warnings.warn("protocol_iterators is replaced by corpus_iterator() and may be removed in future versions -- use that instead.", DeprecationWarning, stacklevel=2)
    return corpus_iterator("prot", corpus_root=corpus_root, start=start, end=end)


def parse_date(s):
    """
    Parse datetimes with special error handling

    Args:
        s (str): datetime as a string

    Returns:
        date (datetime.datetime): date as a datetime
    """
    try:
        return datetime.strptime(s, "%Y-%m-%d")

    except ValueError:
        if len(s) == 4:
            if int(s) > 1689 and int(s) < 2261:
                return datetime(int(s), 6, 15)
            else:
                return None
        else:
            return None


def get_formatted_uuid(seed=None):
    """
    Generate a UUID and format it in base58.
    The formatted UUID is prepended bu 'i-' so that it can be used as an XML ID

    Args:
        seed (str): Random seed. Optional.

    Returns:
        id (str): formatted UUID
    """
    if seed is None:
        x = uuid.uuid4()
    else:
        m = hashlib.md5()
        m.update(seed.encode('utf-8'))
        x = uuid.UUID(m.hexdigest())

    return f"i-{str(base58.b58encode(x.bytes), 'UTF8')}"


def _download_with_progressbar(url, fname, chunk_size=1024):
    resp = requests.get(url, stream=True)
    total = int(resp.headers.get('content-length', 0))
    with open(fname, 'wb') as file, tqdm(
        desc=fname,
        total=total,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in resp.iter_content(chunk_size=chunk_size):
            size = file.write(data)
            bar.update(size)


def download_corpus(path="./", partitions=["records"]):
    """
    Downloads the full corpus.
    Does not return anything, just downloads the corpus ZIP and unzips it.

    Args:
        path (str): path for the download
    """
    p = Path(path)
    for partition in partitions:
        url = f"https://github.com/swerik-project/riksdagen-{partition}/releases/latest/download/{partition}.zip"
        zip_path = p / f"{partition}.zip"
        corpus_path = p / "data"
        if corpus_path.exists():
            LOGGER.warning(f"data already exists at the path '{corpus_path}'. It will be overwritten once the download is finished.")

        zip_path_str = str(zip_path.relative_to("."))
        extraction_path = str(p.relative_to("."))

        # Download file and display progress
        _download_with_progressbar(url, zip_path_str)
        with zipfile.ZipFile(zip_path_str, "r") as zip_ref:
            LOGGER.debug(f"Extract to {corpus_path} ...")
            zip_ref.extractall()

        zip_path.unlink()


def get_doc_dates(protocol):
    """
    Gets the content of <docDate> elements.

    Args:
        protocol: str or etree.Element

    Returns:

        match_error (bool):  True when the value of the "when" attribte doesn't match the element's text value.
        dates (list): a list of dates.
    """
    match_error = False
    dates = []
    if type(protocol) == str:
        root, ns = parse_tei(protocol)
    elif type(protocol) == etree._Element:
        root = protocol
        ns = fetch_ns()
    else:
        raise TypeError(f"You need to pass a string or etree Element, not {type(protocol)}")
    date_elems = root.findall(f".//{ns['tei_ns']}docDate")
    for de in date_elems:
        when_attrib = de.get("when")
        elem_text = de.text
        if not when_attrib == elem_text:
            match_error = True
        dates.append(when_attrib)
    return match_error, dates


def write_tei(elem, dest_path) -> None:
    """
    Write a corpus document to disk.

    Args:
        elem (etree._Element): tei root element
        dest_path (str): protocol path
    """
    elem = format_texts(elem, padding=10)
    b = etree.tostring(
        elem,
        pretty_print=True,
        encoding="utf-8",
        xml_declaration=True
    )
    with open(dest_path, "wb") as f:
        f.write(b)


def write_protocol(prot_elem, prot_path) -> None:
    """
    Write the protocol to a file.

    Args:
        prot_elem (etree._Element): protocol root element
        prot_path (str): protocol path
    """
    warnings.warn("write_protocol is replaced by write_tei() and may be removed in future versions -- use that instead.", DeprecationWarning, stacklevel=2)
    write_tei(prot_elem, prot_path)


def parse_tei(_path, get_ns=True) -> tuple:
    """
    Parse a protocol, return root element (and namespace defnitions).

    Args:
        _path (str): path to tei-xml doc
        get_ns (bool): also return namespace dict

    Returns:
        tuple/etree._Element: root and an optional namespace dict
    """
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.parse(_path, parser).getroot()
    if get_ns:
        ns = fetch_ns()
        return root, ns
    else:
        return root


def parse_protocol(protocol_path, get_ns=False) -> tuple:
    """
    Parse a protocol, return root element (and namespace defnitions).

    Args:
        protocol_path (str): protocol path
        get_ns (bool): also return namespace dict

    Returns:
        tuple/etree._Element: root and an optional namespace dict
    """
    warnings.warn("parse_protocol is replaced by parse_tei() and may be removed in future versions -- use that instead.", DeprecationWarning, stacklevel=2)
    return parse_tei(protocol_path, get_ns=get_ns)


def get_data_location(partition):
    """
    Get data location for a specific path. Tries the env variables
    RECORDS_PATH, MOTIONS_PATH and METADATA_PATH. If those do not exist
    returns the defaults data/, data/, data/
    """
    d = {}
    d["records"] = os.environ.get("RECORDS_PATH", "data")
    d["motions"] = os.environ.get("MOTIONS_PATH", "data")
    d["motions-alto"] = os.environ.get("MOTIONS_ALTO_PATH", "data")
    d["metadata"] = os.environ.get("METADATA_PATH", "data")
    d["metadata_db"] = os.environ.get("METADATA_DB", "data")               # path to csv or pkl of compiled Corpus()
    d["interpellations"] = os.environ.get("INTERPELLATIONS_PATH", "data")
    assert partition in d, f"Provide valid partition of the dataset ({list(d.keys())})"
    return d[partition]


def get_gh_link(_file,
                elem=None,
                line_number=None,
                username='swerik-project',
                repo='riksdagen-records',
                branch='dev'):
    """
    return a formatted github link to an lxml element or specified line in _file

    Args:
    - _file: the path (from root) of the file in question
    - elem: the element
    - username: the username of the repo owner
    - reponame: the repository containing the _file
    - branch: the branch you want to link to

    Returns:
        gh (str): formatted github link
    """
    if not (elem is not None or line_number is not None) and elem != line_number:
        raise ValueError("You have to pass an elem or a line number")

    if _file.startswith(repo):
        _file = _file.replace(f"{repo}/", "")
    if elem is not None:
        line_number = elem.sourceline
    gh = f"https://github.com/{username}/{repo}/blob/{branch}/{_file}/#L{line_number}"
    return gh


def remove_whitespace_from_sequence(text):
    """
    Remove repeated whitespace and replace all whitespace with spaces
    Input is string and output is string.
    """
    text_seq = text.split()
    text_seq = [s for s in text_seq if s != '']
    return ' '.join(text_seq)

  
def get_sequence_from_elem_list(elem_list):
    """
    Get sequence from first elem in list.
    Returns string. If list is empty, returns empty string. 
    """
    if len(elem_list) > 0:
        return str(elem_list[0].text)
    return ""

  
def extract_context_sequence(elem, context_type, target_length = 128, separator = '/n'):
    """
    Get sequence with context from xml element. Returns string. 
    """
    sequence_to_list_by_punctuation = lambda sequence_string: list(filter(None, re.split(r'([.!?])', sequence_string)))
    
    current_sequence = remove_whitespace_from_sequence(elem.text)
    
    previous_elem_list = elem.xpath("preceding::*[local-name() = 'note' or local-name() = 'seg'][1]")
    previous_sequence = remove_whitespace_from_sequence(get_sequence_from_elem_list(previous_elem_list))
    previous_sequence_as_list = sequence_to_list_by_punctuation(previous_sequence)
    previous_last_sentence = ''.join(previous_sequence_as_list[-2:]).lstrip('.!? ')
    
    if context_type == 'left_context':
        max_previous_length = target_length//2
    elif context_type == 'full_context':
        max_previous_length = target_length//3
        next_elem_list = elem.xpath("following::*[local-name() = 'note' or local-name() = 'seg'][1]")
        next_sequence = remove_whitespace_from_sequence(get_sequence_from_elem_list(next_elem_list))
        next_sequence_as_list = sequence_to_list_by_punctuation(next_sequence)
        next_first_sentence = ''.join(next_sequence_as_list[:2])
    
    previous_last_sentence = ' '.join(previous_last_sentence.split(' ')[-max_previous_length:]) # truncate sequence if too long
    left_context_sequence = previous_last_sentence + f' {separator} ' + current_sequence

    if context_type == 'left_context':
        return left_context_sequence
    elif context_type == 'full_context':
        return left_context_sequence + f' {separator} ' + next_first_sentence

 
def get_context_sequences_for_protocol(protocol, context_type, target_length = 128, separator = '/n'):
    """
    Gets context sequences for a protocol. Returns dictionary with ids and corresponding context sequences. 
    """
    id_list, texts_with_contexts = [], []
    
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.parse(protocol, parser).getroot()
    
    for tag, elem in elem_iter(root):
        if tag == 'note':
            elem_id = elem.get(f'{XML_NS}id')
            id_list.append(elem_id)
            context_sequence = extract_context_sequence(elem, context_type = context_type, target_length = target_length, separator = separator)
            texts_with_contexts.append(context_sequence)
        elif tag == 'u':
            for child in elem:
                child_id = child.get(f'{XML_NS}id')
                id_list.append(child_id)
                context_sequence = extract_context_sequence(child, context_type=context_type, target_length = target_length, separator = separator)
                texts_with_contexts.append(context_sequence)
    
    output_dict = {'id' : id_list,
                   'text' : texts_with_contexts}
    return output_dict


def pathize_protocol_id(protocol_id):
    """
    Turn the protocol id into a path string from riksdagen-records root. Handles 'unpadded' protocol numbers.
    """

    spl = protocol_id.split('-')
    parliament_year = spl[1]
    suffix = ""
    if len(spl) == 4:
        nr = spl[3]
        pren = '-'.join(spl[:3])
    else:
        nr = spl[5]
        pren = '-'.join(spl[:5])
        if len(spl) == 7:
            suffix = f"-{spl[-1]}"
    path_ = f"data/{parliament_year}/{pren}-{nr:0>3}{suffix}.xml"
    if os.path.exists(path_):
        # if path_ exists, return path_
        return path_
    else:
        # try to remove strings like "extra" and "höst" from path_ ...
        #    (these were removed from some of the protocol filenames after goldstandard annotation)
        #    check again if new path_ exists and return
        path_ = re.sub(f'((extra)?h[^-]+st|")', '', path_)
        if os.path.exists(path_):
            return path_
    raise FileNotFoundError(f"Can't find {path_}")
