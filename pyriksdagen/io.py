#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Utilities for reading and writing TEI files
"""
from collections import OrderedDict
from lxml import etree
from xml.sax.saxutils import escape


XML_NS = "{http://www.w3.org/XML/1998/namespace}"
TEI_NS = "{http://www.tei-c.org/ns/1.0}"


def fetch_ns():
    return {"tei_ns": TEI_NS,
            "xml_ns": XML_NS}


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
        return root, fetch_ns()
    else:
        return root


def write_tei(root, dest_path, ns="{http://www.tei-c.org/ns/1.0}", custom_order=None) -> None:
    """
    Write a TEI corpus document to disk.

    Args:
        elem (etree._Element): tei root element
        dest_path (str): protocol path
        custom_order (list): custom order for leading attributes in element
    """
    def _sort_attrs(attrib, custom_order=["xml:id",
                                          "who",
                                          "type",
                                          "subtype",
                                          "prev",
                                          "next",]):
        """
        Sort an element's attributes, first by the custom order, then any remaining alphabetically

        Args:
            attrib: Etree Element's attributes
            custom_prder (list): list of attributes in the order we want

        Returns:
            d (ordered dict): ordered element attributes
        """
        d = OrderedDict()
        attrs = dict(attrib)
        #print(attrs)
        def key_label(k):
            if k == "{http://www.w3.org/XML/1998/namespace}id":
                return "xml:id"
            return k

        # Reverse-map Clark notation for xml:id
        fixed_attrs = {}
        for k, v in attrs.items():
            fixed_key = "xml:id" if k == "{http://www.w3.org/XML/1998/namespace}id" else k
            fixed_attrs[fixed_key] = v

        d = OrderedDict()
        for key in custom_order:
            if key in fixed_attrs:
                d[key] = fixed_attrs.pop(key)
        for key, val in dict(sorted(fixed_attrs.items())).items():
            d[key] = fixed_attrs[key]
        #print("  ~~", d)
        return d


    def _format_paragraph(paragraph, spaces, max_line_width=60):
        """
        format paragraphss with indentation and fixed max-width for each line

        Args:
            paragraph (str): text of element to be formatted
            spaces (int): the number of spaces to indent text by
            max_line_width (int): maximum width of the text column in characters

        Returns:
            s (str): formatted text of element
        """
        s = spaces
        words = [_.strip() for _ in paragraph.replace("\n", " ").strip().split() if _.strip() != '']
        row = ""
        for word in words:
            word = escape(word)
            if len(row) > max_line_width:
                s += row.strip() + "\n" + spaces
                row = word
            else:
                row += " " + word

        if len(row.strip()) > 0:
            s += row.strip()
        if s.strip() == "":
            return None
        return s


    def _serialize(elem, indent=' ', padding=2, custom_order=None, is_body=True):
        """
        Custom XML serializer for TEI/text that works recursively on the
            element tree, while respecting indentation, line breaks and custom attribute order

        Args:
            elem (etree Element): The root element to serialize from. typically this is TEI/text
            indent (str): character to use for indentation. default is a single whitespace character
            padding (int): number of indent character's to use for each level of indentation. default=2
            custom_order (list): custom order for leading attributes in element

        Returns:
            Serilaized string of elem

        """
        ind = indent * padding
        child_ind = indent * (padding + 2)

        # Build sorted attribute string
        if custom_order is not None:
            sorted_attrs = _sort_attrs(elem.attrib, custom_order=custom_order)
        else:
            sorted_attrs = _sort_attrs(elem.attrib)
        attr_str = " ".join(f'{k}="{v}"' for k, v in sorted_attrs.items())
        # Check for self-closing condition
        has_text = bool(elem.text and elem.text.strip())
        has_children = len(elem) > 0

        if not has_text and not has_children:
            # Self-closing tag
            tag = elem.tag.replace(ns, '')
            return f"{ind}<{tag}" + (f" {attr_str}" if attr_str else "") + "/>"

        # Normal open tag
        start_tag = f"{ind}<{elem.tag.replace(ns, '')}" + (f" {attr_str}" if attr_str else "") + ">"
        parts = [start_tag]

        # Format .text
        if is_body:
            if has_text:
                parts.append(_format_paragraph(elem.text.strip(), child_ind))
            for child in elem:
                parts.append(_serialize(child, padding=padding+2, custom_order=custom_order))
                # Format .tail
                if child.tail and child.tail.strip():
                    parts.append(_format_paragraph(child.tail.strip(), child_ind))
            parts.append(ind + f"</{elem.tag.replace(ns, '')}>")
        else:
            # assume tei header doesn't mix child elements and text
            if has_text and elem.text.strip() != '' and len(elem) == 0:
                parts[-1] += f"{' '.join([escape(_.strip()) for _ in elem.text.split() if _.strip() != ''])}</{elem.tag.replace(ns, '')}>"
            else:
                for child in elem:
                    parts.append(_serialize(child, padding=padding+2, custom_order=custom_order, is_body=False))
                parts.append(ind + f"</{elem.tag.replace(ns, '')}>")
        return "\n".join([_ for _ in parts if _.strip() != ''])


    try:
        header = root.find(f".//teiHeader")
        assert header != None
    except:
        header = root.find(f".//{ns}teiHeader")
        try:
            assert header != None
        except:
            raise ValueError("header can't be None")

    try:
        body = root.find(f".//text")
        assert body != None
    except:
        body = root.find(f".//{ns}text")
        try:
            assert body != None
        except:
            raise ValueError("body can't be None")

    body = _serialize(body, custom_order=custom_order)
    header = _serialize(header, padding=2, custom_order=custom_order, is_body=False)
    xml = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:xi="http://www.w3.org/2001/XInclude" xml:id="{dest_path.split("/")[-1][:-4]}">',
        header,
        body,
        '</TEI>\n'
    ]
    with open(dest_path, "w+") as f:
        f.write('\n'.join(xml))
