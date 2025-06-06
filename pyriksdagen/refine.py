from lxml import etree
import re
from pyparlaclarin.read import element_hash
import dateparser
import pandas as pd
from .utils import elem_iter, infer_metadata, parse_date, XML_NS, TEI_NS, get_formatted_uuid
from .db import load_expressions, filter_db, load_patterns, load_metadata
from .segmentation import (
    detect_mp,
    detect_minister,
    detect_speaker,
    expression_dicts,
    detect_introduction,
    intro_to_dict,
)
from .match_mp import multiple_replace
from datetime import datetime
from trainerlog import get_logger
LOGGER = get_logger("refine")


def redetect_protocol(metadata, protocol):
    """
    For each intro in a protocol, detect which MP is mentioned and map it to metadata.

    Args:
        metadata (dict): basic metadata on the protocol
        protocol (lxml.etree): protocol as an lxml tree
    
    Returns:
        protocol as an lxml tree
    """
    tei_ns = ".//{http://www.tei-c.org/ns/1.0}"
    parser = etree.XMLParser(remove_blank_text=True)

    party_mapping, mp_db, minister_db, speaker_db = metadata
    ## DEPRECIATED ##join_intros = join_intros[join_intros['protocol'] == protocol]
    
    protocol_id = protocol.split("/")[-1]
    metadata = infer_metadata(protocol)
    root = etree.parse(protocol, parser).getroot()
    
    # Year from the folder name
    year = metadata["year"]
    # Take into account folders such as 198889
    secondary_year = metadata.get("secondary_year", year)

    dates = [
        parse_date(elem.attrib.get("when"))
        for elem in root.findall(tei_ns + "docDate")
        if parse_date(elem.attrib.get("when")).year in [year, secondary_year]
    ]
    
    # Dates from xml is wrong for digitized era        
    if len(dates) > 0:
        start_date, end_date = min(dates), max(dates)          

    else:
        start_date = datetime(year,1,1)
        end_date = datetime(secondary_year,12,31)
    
    year_mp_db = filter_db(mp_db, start_date=start_date, end_date=end_date)
    year_minister_db = filter_db(minister_db, start_date=start_date, end_date=end_date)
    year_speaker_db = filter_db(speaker_db, start_date=start_date, end_date=end_date)
    
    # Introduction patterns
    pattern_db = load_patterns()
    pattern_db = pattern_db[
        (pattern_db["start"] <= year) & (pattern_db["end"] >= year)
    ]

    root, unk = detect_mps(
        root,
        None,
        pattern_db,
        mp_db=year_mp_db,
        minister_db=year_minister_db,
        speaker_db=year_speaker_db,
        metadata=metadata,
        party_map=party_mapping,
        ## DEPRECIATED ##join_intros=join_intros,
        protocol_id=protocol_id,
        unknown_variables=["gender", "party", "other"],
    )

    b = etree.tostring(
        root, pretty_print=True, encoding="utf-8", xml_declaration=True
    )

    f = open(protocol, "wb")
    f.write(b)
    f.close()
    return unk


def detect_mps(root, names_ids, pattern_db, mp_db=None, minister_db=None, minister_db_secondary=None, speaker_db=None, metadata=None, party_map=None, protocol_id=None, unknown_variables=None):
    """
    For each intro in a protocol, detect which MP is mentioned and map it to metadata.

    Args:
        root (lxml.etree): protocol as an lxml tree
        mp_db (pd.df): MP database
        minister (pd.df): minister database 
        speaker_db (pd.df): speaker database 
        metadata (dict): basic metadata on the protocol
        party_map (dict): map from party abbreviations to party names
        join_intros (???): intros to be joined
        protocol_id (str): ID of the protocol
        unknown_variables (list): which variables to detect for unknown MPs
    
    Returns:
        protocol as an lxml tree
    """
    scanned_protocol = False
    try:
        # TODO: Fetch this from the metadata block! This solution is hacky and has broken before
        url = root.findall(".//{http://www.tei-c.org/ns/1.0}pb")[0].get('facs')
        scanned_protocol = url.startswith("https://betalab.kb.se/") or url.startswith("https://swerik-project.github.io/")
    except:
        pass

    mp_expressions = load_expressions(phase="mp")
    ## DEPRECIATED ##ids_to_join = set(join_intros['xml_id1'].tolist()+join_intros['xml_id2'].tolist())
    
    xml_ns = "{http://www.w3.org/XML/1998/namespace}"
    current_speaker = None
    prev = None
    mp_db_secondary = pd.DataFrame()

    # Extract information of unknown speakers
    unknowns = []

    #print(metadata)
    # For bicameral era, prioritize MPs from the same chamber as the protocol
    if "chamber" in metadata:
        chamber = {'Första kammaren': 1, 'Andra kammaren':2}.get(metadata['chamber'], 0)
        mp_db_secondary = mp_db[mp_db['chamber'] != chamber]
        mp_db = mp_db[mp_db['chamber'] == chamber]
        speaker_db = speaker_db[speaker_db['chamber'] == chamber]

    for tag, elem in elem_iter(root):
        parent = elem.getparent()
        if parent.attrib.get("type") != "commentSection": #ignore where people don't talk
            if tag == "u":
                # Deleting and adding attributes changes their order;
                # Mark as 'delete' instead and delete later
                elem.set("prev", "delete")
                elem.set("next", "delete")
                if current_speaker is not None:
                    elem.attrib["who"] = current_speaker
                else:
                    elem.attrib["who"] = "unknown"

                if prev is not None:
                    prev_id = prev.attrib[xml_ns + "id"]
                    elem_id = elem.attrib[xml_ns + "id"]
                    elem.set("prev", prev_id)
                    prev.set("next", elem_id)
                prev = elem

            elif tag == "note":
                if elem.attrib.get("type", None) == "speaker":
                    prev = None
                    text = elem.text
                    # Join split intros detected by BERT
                    #if elem.attrib.get(xml_ns + "id") in ids_to_join:
                    #    join_intro = join_intros.loc[
                    #                (join_intros['xml_id1'] == elem.attrib.get(xml_ns + "id")) |
                    #                (join_intros['xml_id2'] == elem.attrib.get(xml_ns + "id")), 'text']
                    #    text = join_intro.iloc[0]
                    LOGGER.debug(f"Detect intro with the text: {' '.join(text.split())}")
                    if type(text) == str:
                        d = intro_to_dict(text, mp_expressions)
                        if 'name' in d:
                            d['name'] = multiple_replace(d['name'])

                        if 'other' in d:
                            # Match minister
                            if 'statsråd' in d["other"].lower() or 'minister' in d["other"].lower():
                                current_speaker = detect_minister(text, minister_db, d)

                            elif 'talman' in d["other"].lower():
                                current_speaker = detect_speaker(text, speaker_db, metadata=metadata)

                            else:
                                current_speaker = None

                        # Match mp if not minister/talman and a name is identified
                        # if current_speaker is None and 'name' in d:
                        elif 'name' in d:

                            current_speaker = detect_mp(d, db=mp_db, party_map=party_map, match_fuzzily=scanned_protocol)

                            if current_speaker is None and len(mp_db_secondary) > 0:
                                current_speaker = detect_mp(d, db=mp_db_secondary, party_map=party_map, match_fuzzily=scanned_protocol)
                        else:
                            current_speaker = None

                        if current_speaker is None:
                            unknowns.append([protocol_id, elem.attrib.get(f'{xml_ns}id')] + [d.get(key, "") for key in unknown_variables])
        else:
            # If the whole section has no speeches, reset speaker and next/prev notation
            if tag == "u":
                elem.set("prev", "delete")
                elem.set("next", "delete")
                elem.set("who", "unknown")
            
            current_speaker = None
            prev = None

    # Do two loops to preserve attribute order
    for tag, elem in elem_iter(root):
        if tag == "u":
            if elem.attrib.get("prev") == "delete":
                del elem.attrib["prev"]
            if elem.attrib.get("next") == "delete":
                del elem.attrib["next"]

    return root, unknowns


def find_introductions(root, pattern_db, intro_ids, remove_missing=True, minister_db=None):
    """
    Find instances of curation patterns in all files in a folder.

    Args:
        root (lxml.etree): protocol as a lxml tree
        pattern_db: Patterns to be matched as a Pandas DataFrame.
        intro_ids (pd.DataFrame): List of IDs that have been detected as intros.
        remove_missing (bool): remove intros not found in 'intro_ids'
        minister_db: deprecated
    """

    # return root
    root.text = None
    current_speaker = None
    expressions, manual = expression_dicts(pattern_db)

    for ix, elem_tuple in enumerate(list(elem_iter(root))):
        tag, elem = elem_tuple
        if tag == "u":
            u = None
            u_parent = elem.getparent()
            u_parent.text = None
            for seg in list(elem):
                if type(seg.text) == str:
                    introduction = detect_introduction(
                        seg, intro_ids
                    )
                    if introduction is not None:
                        pass  # print("NEW", seg.text)
                        seg.tag = "{http://www.tei-c.org/ns/1.0}note"
                        seg.attrib["type"] = "speaker"
                        if u is not None:
                            u.addnext(seg)
                        else:
                            elem.addnext(seg)

                        u = etree.Element("{http://www.tei-c.org/ns/1.0}u")
                        # u.text = None
                        if introduction["who"] is not None:
                            u.attrib["who"] = introduction["who"]
                        else:
                            u.attrib["who"] = "unknown"

                        seg.addnext(u)
                        matched_txt = introduction["txt"]
                        ix = None
                        if matched_txt[-1] != ":" and ":" in seg:
                            ix = len(matched_txt) + seg.text.index(matched_txt)
                        if ":" in matched_txt:
                            ix = matched_txt.index(":")
                            ix = ix + seg.text.index(matched_txt)
                        elif seg.text[-1] != ":" and ":" in seg:
                            ix = seg.text.index(":")

                        if ix is not None:
                            rest = seg.text[ix + 1 :]
                            seg.text = seg.text[: ix + 1]
                            new_seg = etree.SubElement(
                                u, "{http://www.tei-c.org/ns/1.0}seg"
                            )
                            new_seg.text = rest

                    elif u is not None:
                        u.append(seg)
                        u.text = None

        elif tag == "note":
            parent = elem.getparent()
            parent.text = None
            # if not elem.attrib.get("type", None) == "speaker":
            if type(elem.text) == str:

                introduction = detect_introduction(
                    elem, intro_ids
                )

                if introduction is not None:
                    if not elem.attrib.get("type", None) == "speaker":
                        print("NEW note", elem.text)
                        elem.attrib["type"] = "speaker"

                        matched_txt = introduction["txt"]
                        ix = None
                        if matched_txt[-1] != ":" and ":" in elem.text:
                            ix = len(matched_txt) + elem.text.index(matched_txt)
                        if ":" in matched_txt:
                            ix = matched_txt.index(":")
                            ix = ix + elem.text.index(matched_txt)
                        elif elem.text[-1] != ":" and ":" in elem:
                            ix = elem.text.index(":")
                        if ix is not None:
                            rest = elem.text[ix + 1 :].strip()
                            if len(rest) > 0:
                                u = etree.Element("{http://www.tei-c.org/ns/1.0}u")
                                # u.text = None
                                if introduction["who"] is not None:
                                    u.attrib["who"] = introduction["who"]
                                else:
                                    u.attrib["who"] = "unknown"

                                elem.addnext(u)

                                rest = elem.text[ix + 1 :]
                                elem.text = elem.text[: ix + 1]

                                new_seg = etree.SubElement(
                                    u, "{http://www.tei-c.org/ns/1.0}seg"
                                )
                                new_seg.text = rest

                    else:
                        pass  # print("OLD", elem.text)
                elif elem.attrib.get("type") == "speaker" and remove_missing:
                    del elem.attrib["type"]

    return root


def detect_date(root, metadata, skip_doctors_notes=False):
    """
    Detects notes with dates in them. Updates the docDate metadata in the teiHeader accordingly.

    Args:
        root (lxml.etree): protocol as a lxml tree
        metadata (dict): basic metadata about the protocol

    Returns:
        root (lxml.etree): protocol as a lxml tree
        dates (list): list of the detected dates in an ISO format (YYYY-MM-DD)
    """

    dates = set()
    number_dates = set()
    expression = "\\w{3,5}dagen den (\\d{1,2})\\.? (\\w{3,9}) (\\d{4})"
    expression2 = "\\w{3,5}dagen den (\\d{1,2})\\.? (\\w{3,9})"
    expression3 = "(\\d{1,2})\\.? (\\w{3,9}) (\\d{4,4})"
    expression4 = "(D|d)en (\\d{1,2})\\.? (\\w{3,9})"
    protocol_year = metadata["year"]
    protocol_years = {protocol_year, metadata.get("secondary_year", protocol_year)}
    yearless = set()

    def _parse_date(s):
        return dateparser.parse(s, languages=["sv"], settings={'RETURN_AS_TIMEZONE_AWARE': False})

    def _is_sjukbetyg(elem):
        """
        check if elem with date is part of a (lakar|sjul)(be|in)tyg
        """
        if not skip_doctors_notes:
            return False
        break_while, is_sjukbetyg = False, False
        pat = re.compile(r'(läkar|sjuk)(in|be)tyg')
        while break_while == False:
            elem = elem.getprevious()
            # Run until a title or the beginning of the document is reached
            if elem is None or elem.attrib.get("type") == "title":
                break_while = True
            if elem is not None and elem.text is not None:
                m = pat.search(elem.text)
                if m is not None:
                    is_sjukbetyg = True
        return is_sjukbetyg

    for ix, elem_tuple in enumerate(list(elem_iter(root))):
        tag, elem = elem_tuple
        if tag == "note" and type(elem.text) == str and len(" ".join(elem.text.split()))  < 50:
            # Mark as to-be-removed so that attribute order is retained
            if elem.attrib.get("type") == "date":
                elem.attrib["type"] = "REMOVE"
            
            weekday_date_year = re.search(expression, elem.text)
            weekday_and_date = re.search(expression2, elem.text)
            date_and_year = re.search(expression3, elem.text)
            den_and_date = re.search(expression4, elem.text)

            # Dates with the year included, surely date
            if weekday_date_year is not None:
                if elem.attrib.get("type") != "title":
                    elem.attrib["type"] = "date"
                datestr = weekday_date_year.group(1) + " " + weekday_date_year.group(2) + " " + weekday_date_year.group(3)
                date = _parse_date(datestr)
                if date is not None and not _is_sjukbetyg(elem):
                    if date.year in protocol_years:
                        number_dates.add(date)

            # Dates with the year included, though unsure if protocol date
            elif date_and_year is not None and not _is_sjukbetyg(elem):
                datestr = date_and_year.group()
                date = _parse_date(datestr)
                if date is not None:
                    if date.year in protocol_years:
                        dates.add(date)

            # Dates without a year
            elif weekday_and_date is not None and not _is_sjukbetyg(elem):
                if elem.attrib.get("type") != "title":
                    elem.attrib["type"] = "date"
                datestr = weekday_and_date.group(1) + " " + weekday_and_date.group(2)
                yearless.add(datestr)

            # Dates without a year or weekday
            elif den_and_date is not None and not _is_sjukbetyg(elem):
                if len(" ".join(elem.text.split())) < 30:
                    if elem.attrib.get("type") != "title":
                        elem.attrib["type"] = "date"

                    datestr = den_and_date.group()
                    yearless.add(datestr)

            # Remove elements that were not dates
            if elem.attrib.get("type") == "REMOVE":
                del elem.attrib["type"]

    # Dates WITH a number are actually preferred in the hierarchy
    dates, number_dates = number_dates, dates
    if len(dates) > 0:
        protocol_year = list(dates)[0].year
    elif len(number_dates) > 0:
        dates = number_dates
        protocol_year = list(dates)[0].year

    for datestr in yearless:
        date = _parse_date(f"{datestr} {protocol_year}")
        if date is not None:
            dates.add(date)

    dates = sorted(dates)
    for text in root.findall(".//" + TEI_NS + "text"):
        for front in text.findall(".//" + TEI_NS + "front"):

            # Remove old docDates
            for docDate in front.findall(".//" + TEI_NS + "docDate"):
                docDate.getparent().remove(docDate)
            for div in front.findall(".//" + TEI_NS + "div"):
                for docDate in div.findall(".//" + TEI_NS + "docDate"):
                    docDate.getparent().remove(docDate)

            # Format dates and add default XXXX-01-01
            formatted_dates = [d.strftime("%Y-%m-%d") for d in dates]
            if len(dates) == 0:
                formatted_dates = [str(protocol_year) + "-01-01"]

            # Add new docDates
            for div in front.findall(".//" + TEI_NS + "div"):
                if div.attrib.get("type") == "preface":
                    for docDate in div.findall(".//" + TEI_NS + "docDate"):
                        docDate.getparent().remove(docDate)
                    for formatted in formatted_dates:
                        docDate = etree.SubElement(div, "docDate")
                        docDate.text = formatted
                        docDate.attrib["when"] = formatted

    return root, dates


def update_ids(root, protocol_id):
    """
    Update element IDs. TODO

    Args:
        root (lxml.etree): protocol as a lxml tree
        protocol_id (str): protocol ID. DEPRECATED

    Returns:
        root (lxml.etree): protocol as a lxml tree
        ids (set): set of all IDs in the protocol
    """
    ids = set()
    xml_id = f"{XML_NS}id"

    for tag, elem in elem_iter(root):
        if tag == "u":
            for subelem in elem:
                x = subelem.attrib.get(f'{xml_ns}id', get_formatted_uuid())
                subelem.attrib[f'{xml_ns}id'] = x
                ids.add(x)

            x = elem.attrib.get(f'{xml_ns}id', get_formatted_uuid())
            elem.attrib[f'{xml_ns}id'] = x
            ids.add(x)
                
        elif tag in ["note", "pb"]:
            x = elem.attrib.get(f'{xml_ns}id', get_formatted_uuid())
            elem.attrib[f'{xml_ns}id'] = x
            ids.add(x)

    return root, ids

