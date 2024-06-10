#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Provides useful utilities for the other modules as well as for general use.
"""

import lxml
from lxml import etree
import xmlschema
from bs4 import BeautifulSoup
from pathlib import Path, PurePath
from pyparlaclarin.refine import format_texts
from datetime import datetime
import hashlib, uuid, base58, requests, tqdm
import zipfile
import os
from trainerlog import get_logger
import re

LOGGER = get_logger("pyriksdagen")
XML_NS = "{http://www.w3.org/XML/1998/namespace}"
TEI_NS = "{http://www.tei-c.org/ns/1.0}"

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
                if s[4:6].isdigit():
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
    xml_file = lxml.etree.parse(xml_path)
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


def protocol_iterators(corpus_root=None, document_type=None, start=None, end=None):
    """
    Returns an iterator of protocol paths in a corpus.

    Args:
        corpus_root (str): path to the corpus root. If env variable RECORDS_PATH exists, uses that as a default
        document_type (str): type of document (prot, mot, etc.). If None, fetches all types
        start (int): start year
        end (int): end year

    Returns:
        iterator of the protocols as relative paths to current location
    """
    folder = Path(corpus_root)
    if folder.is_absolute():
        folder = folder.relative_to(Path(".").resolve(), walk_up=True)
    docs = folder.glob("**/*.xml")
    if document_type is not None:
        docs = folder.glob(f"**/{document_type}*.xml")
    for protocol in sorted(docs):
        metadata = infer_metadata(protocol.name)
        if "year" not in metadata:
            continue
        _path = protocol.relative_to(".")
        assert (start is None) == (
            end is None
        ), "Provide both start and end year or neither"
        if start is not None and end is not None:
            metadata = infer_metadata(protocol.name)
            year = metadata["year"]
            if not year:
                continue
            secondary_year = metadata.get("secondary_year", year)
            if start <= year and end >= secondary_year:
                yield str(protocol.relative_to("."))
        else:
            yield str(protocol.relative_to("."))

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
    with open(fname, 'wb') as file, tqdm.tqdm(
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

    - match_error is True when the value of the "when" attribte doesn't match the element's text value.

    - dates is a list of dates.
    """
    match_error = False
    dates = []
    tei_ns = ".//{http://www.tei-c.org/ns/1.0}"
    xml_ns = "{http://www.w3.org/XML/1998/namespace}"
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.parse(protocol, parser).getroot()
    date_elems = root.findall(f"{tei_ns}docDate")
    for de in date_elems:
        when_attrib = de.get("when")
        elem_text = de.text
        if not when_attrib == elem_text:
            match_error = True
        dates.append(when_attrib)
    return match_error, dates

def write_protocol(prot_elem, prot_path) -> None:
    """
    Write the protocol to a file.

    Args:
        prot_elem (etree._Element): protocol root element
        prot_path (str): protocol path

    """
    prot_elem = format_texts(prot_elem, padding=10)
    b = etree.tostring(
        prot_elem,
        pretty_print=True,
        encoding="utf-8",
        xml_declaration=True
    )
    with open(prot_path, "wb") as f:
        f.write(b)

def parse_protocol(protocol_path, get_ns=False) -> tuple:
    """
    Parse a protocol, return root element (and namespace defnitions).

    Args:
        protocol_path (str): protocol path
        get_ns (bool): also return namespace dict

    Returns:
        tuple/etree._Element: root and an optional namespace dict
    """
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.parse(protocol_path, parser).getroot()
    if get_ns:
        tei_ns = "{http://www.tei-c.org/ns/1.0}"
        xml_ns = "{http://www.w3.org/XML/1998/namespace}"
        return root, {"tei_ns":tei_ns, "xml_ns":xml_ns}
    else:
        return root

def get_data_location(partition):
    """
    Get data location for a specific path. Tries the env variables
    RECORDS_PATH, MOTIONS_PATH and METADATA_PATH. If those do not exist
    returns the defaults data/, data/, data/
    """
    valid_partitions = ["records", "motions", "metadata"]
    assert partition in valid_partitions, f"Provide valid partition of the dataset ({valid_partitions})"
    d = {}
    d["records"] = os.environ.get("RECORDS_PATH", "data")
    d["motions"] = os.environ.get("MOTIONS_PATH", "data")
    d["metadata"] = os.environ.get("METADATA_PATH", "data")
    return d[partition]

def remove_whitespace_from_sequence(text_seq):
    # function to remove whitespace from string to get comparable text between corpus and kblab
    text_seq = text_seq.split()
    text_seq_list = [s for s in text_seq if s != '']
    text_seq_string = ' '.join(text_seq_list)
    return text_seq_string

def add_context_to_sequence(previous_sequence, current_sequence, next_sequence, context_type, target_length = 120):
    # if previous sequence is long, we want it to truncate the sequence so that the
    # current sequence is not unecessarily 
    if context_type == 'left_context':
        max_previous_length = target_length//2
    elif context_type == 'full_context':
        max_previous_length = target_length//3
    
    # remove whitespace from sequences
    previous_sequence = remove_whitespace_from_sequence(str(previous_sequence))
    current_sequence = remove_whitespace_from_sequence(str(current_sequence))
    next_sequence = remove_whitespace_from_sequence(str(next_sequence))
    
    
    previous_as_list = re.split(r'([.!?])', previous_sequence)
    if (previous_as_list[-1] == '') & (len(previous_as_list) != 1):
        prev_last_sentence = previous_as_list[-3:]
        prev_last_sentence = ''.join(prev_last_sentence)
    else:
        prev_last_sentence = previous_as_list[-1]
        
    next_as_list = re.split(r'([.!?])', next_sequence)
    if len(next_as_list) != 1:
        next_first_sentence = next_as_list[:2]
        next_first_sentence = ''.join(next_first_sentence)
    else:
        next_first_sentence = next_as_list[0]

    # regardless of sequence type, we combine prev last sentence with curr sequence
    prev_last_sentence_as_list = prev_last_sentence.split(' ')
    n_words = len(prev_last_sentence_as_list)
    if n_words > max_previous_length:
        prev_last_sentence_as_list = prev_last_sentence_as_list[-max_previous_length:]
        prev_last_sentence = ' '.join(prev_last_sentence_as_list)
    # use new line (/n) as token to signify where current sequence begins
    left_context_sequence = prev_last_sentence + ' /n ' + current_sequence
    
    if context_type == 'left_context':
        return left_context_sequence
    elif context_type == 'full_context':
        # add next first sentence to left context sequence to get full context
        full_context_sequence = left_context_sequence + ' /n ' + next_first_sentence
        return full_context_sequence

def get_context_sequences_for_protocol(protocol, context_type, max_length = 120):
    # returns dictionary with ids and context sequences for a complete protocol
    id_list = []
    context_sequence_list = []
    
    id_key = f'{XML_NS}id'
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.parse(protocol, parser).getroot()
    
    prev_elem_is_text_seq = False
    elem_idx = ''
    prev_sequence = ''
    next_sequence = ''
    prev_elem_sequence = ''
    for tag, elem in elem_iter(root):
        if tag == 'note':
            elem_sequence = elem.text
            elem_idx = elem.attrib[id_key]
            
            if prev_elem_is_text_seq == True:
                next_sequence = elem_sequence
                context_sequence = add_context_to_sequence(prev_sequence, curr_sequence, next_sequence, context_type, max_length)
                
                id_list.append(idx)
                context_sequence_list.append(context_sequence)
            

            idx = elem_idx
            curr_sequence = elem_sequence
            prev_sequence = prev_elem_sequence
                
            prev_elem_sequence = elem_sequence
            prev_elem_is_text_seq = True
        elif tag == 'u':
            for child in elem.getchildren():
                elem_sequence = child.text
                elem_idx = child.values()[0]
                
                if prev_elem_is_text_seq == True:
                    next_sequence = elem_sequence
                    context_sequence = add_context_to_sequence(prev_sequence, curr_sequence, next_sequence, context_type, max_length)
                    
                    id_list.append(idx)
                    context_sequence_list.append(context_sequence)
                    
                
                idx = elem_idx
                curr_sequence = elem_sequence
                prev_sequence = prev_elem_sequence
                    
                prev_elem_sequence = elem_sequence
                prev_elem_is_text_seq = True
                
    next_sequence = ''
    context_sequence = add_context_to_sequence(prev_sequence, curr_sequence, next_sequence, context_type, max_length)
    
    id_list.append(idx)
    context_sequence_list.append(context_sequence)
    
    
    output_dict = {'id' : id_list,
                   'context_sequence' : context_sequence_list}
    return output_dict
