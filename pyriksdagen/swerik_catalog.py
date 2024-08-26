"""
Functions relating to the Swerik Catalog.
"""
import json
import pandas as pd


def _json_template(i:str, v:str, now:str) -> dict:
    """
    Returns mostly empty dict with person info.

    Args:
        i (str): person ID
        v (str): version
        now (str): string-formatted timestamp

    Returns:
        dict: person dict

    """
    return {
        "name": None,             #
        "swerik-id":i,            #
        "DOB": None,              #
        "DOD":None,               #
        "gender": None,           #
        "place-of-birth": {       #
                "place": None,    #
                "link": None      #
            },                    #
        "place-of-death": {       #
                "place": None,    #
                "link": None      #
            },                    #
        "alt-names": [],          #
        "iorter": [],             #
        "positions": [],          #
        "portraits": [],          #
        "identifiers": [],        #
        "party-affiliations":[],  #
        "data-version": v,        #
        "last-updated": now       #
    }


def _party_template(row:pd.core.series.Series) -> dict:
    """
    Returns instance of party affiliation.

    Args:
        row (pd.core.series.Series): a row

    Returns:
        dict: info about party affiliation
    """
    return {
        "party": {
            "name": row["party"],
            "party-id": row["party_id"]  # current wiki_id, will change, formatter url in template
        },
        "start": str(row["start"]),
        "end": str(row["end"]),
    }


def _position_template(row:pd.core.series.Series) -> dict:
    """
    Returns instance of a position held

    Args:
        row (pd.core.series.Series): a row

    Returns:
        dict: info about position
    """
    return {
            'start': str(row["start"]),
            'end': str(row["end"]),
            'role': row["role"],
            "source": row["source"],
            'chamber': row["chamber"],
            'government': row["government"],
            "district": row["district"]
        }


def _identifier_template(auth_code, identifier:str) -> dict:
    """
    Returns instance of an external identifier

    Args:
        auth_code: authority abbreviation
        identifier (str): an external identifier

    Returns:
        dict: info about external identifiers.
    """
    url_formatter = {
            "DiSweNaBiID": {                                                  # P3217
                    "formatter-url": "https://sok.riksarkivet.se/sbl/Presentation.aspx?id={}",
                    "name": "Dictionary of Swedish National Biography ID"
                },
            "RiPeID": {                                                       # P4342
                    "formatter-url": "https://data.riksdagen.se/personlista/?iid={}&utformat=html",
                    "name": "Riksdagen person-ID"
                },
            "SwePaPeGUID": {                                                  # P8388
                    "formatter-url": "https://www.riksdagen.se/sv/ledamoter-partier/ledamot/_{}",
                    "name": "Swedish Parliament person GUID"
                },
            "SwePoArID": {                                                    # P4819
                    "formatter-url": "https://portrattarkiv.se/details/{}",
                    "name": "Swedish Portrait Archive ID"
                },
            "UpUnAlID": {                                                     # P6821
                    "formatter-url": "https://www.alvin-portal.org/alvin/view.jsf?pid={}",
                    "name": "Uppsala University Alvin ID"
                },
            "WiDaID": {
                    "formatter-url": "https://www.wikidata.org/wiki/{}",
                    "name": "Wikidata"
                }
        }
    return {
            "authority": url_formatter[auth_code]['name'],
            "identifier": identifier,
            "link": url_formatter[auth_code]["formatter-url"].format(identifier)
        }


def _verify_J(J:dict) -> bool:
    """
    Verifies that Dict object is not totally empty before writing to a file.

    Args:
        J (dict): dictionary object

    Returns:
        bool: J is not empty
    """
    not_empty = False
    if J['name'] == None or len(J['name']) == 0:
        if J['alt-names'] == None or len(J['alt-names']) == 0:
            return not_empty
        else:
            J['name'] = J['alt-names'][0]
            not_empty = True
            return True
    for _ in ["DOB",
            "DOD",
            "gender",
            "place-of-birth",
            "place-of-death",
            "alt-names",
            "iorter",
            "positions",
            "portraits",
            "identifiers",
            "party-affiliations",
        ]:
        if J[_] is not None and len(J[_]) > 0:
            not_empty = True
            return True
    return not_empty


def _add_party(r:pd.core.series.Series, J:dict) -> bool:
    """
    Checks whether a party affiliation can be added to a person dict

    Args:
        r (pd.core.series.Series): row
        J (dict): Person dict

    Returns:
        bool: can add
    """
    if (
        pd.notnull(r['start'])
        and pd.notnull(r['end'])
        and r['party'] not in [_['party']['name'] for _ in J['party-affiliations']]
        ):
        return True
    else:
        return False


def jsonize_person_data(
        person_id:str,
        Corpus_metadata:pd.core.frame.DataFrame,
        peripheral_metadata:dict,
        v:str,
        now:str) -> dict:
    """
    Return a json object of all a n individual's info.

    Args:
        person_id (str): person ID
        Corpus_metadata (pd.core.frame.DataFrame): corpus metadata (pyriksdagen.metadata.Corpus)
        peripheral_metadata (dict): metadata dict from non-core queries
        v (str): data version
        now (str): string formatted timestamp

    Returns:
        dict: Person dict object
    """
    C = Corpus_metadata                 # for convenience
    J = _json_template(person_id, v, now)

    # process core metadata
    primary_name = C.loc[C["primary_name"] == True, 'name'].unique()
    if len(primary_name) == 1:
        J["name"] = primary_name[0]
    elif len(primary_name) == 0:
        print(f">>{person_id} -- NO PRIMARY NAME")
    else:
        print(f">>{person_id} -- MULTIPLE PRIMARY NAMES : {len(primary_name)} : {primary_name}")

    born = C.loc[pd.notnull(C["born"]), "born"].unique()
    if len(born) > 1:
        print(f">>{person_id} -- MULTIPLE BIRTHDATES : {len(born)} : {born}")
        J["DOB"] = str(born[0])
    elif len(born) == 1:
        J["DOB"] = str(born[0])

    dead = C.loc[pd.notnull(C["dead"]), "dead"].unique()
    if len(dead) > 1:
        print(f">>{person_id} -- MULTIPLE DEATHDATES : {len(dead)} : {dead}")
        J["DOD"] = str(dead[0])
    elif len(dead) == 1:
        J["DOD"] = str(dead[0])

    gender = C.loc[pd.notnull(C["gender"]), "gender"].unique()
    if len(gender) > 1:
        print(f"MULTIPLE GENDERS : {len(gender)} : {gender}")
        J["gender"] = gender[0]
    elif len(gender) == 1:
        J["gender"] = gender[0]

    alt_names = C.loc[C["primary_name"] == False, "name"].unique()
    for alt_name in alt_names:
        if alt_name != J["name"]:
            J["alt-names"].append(alt_name)

    iorter = C.loc[pd.notnull(C["location"]), "location"].unique()
    for iort in iorter:
        J["iorter"].append(iort)

    positions = C.drop_duplicates(['start', 'end', 'role', "source", 'chamber', 'government'])
    if positions is not None and not positions.empty:
        positions = positions.sort_values(by="start", ascending=False).copy()
        positions = positions.drop_duplicates().copy()
        for i, r in positions.iterrows():
            J['positions'].append(_position_template(r))

    # process periperal metadata
    PA = peripheral_metadata["party_affiliation"]
    if PA is not None and len(PA) > 0:
        PA.sort_values(by="start", ascending=False, inplace=True)
        PA = PA.drop_duplicates().copy()
        for i, r in PA.iterrows():
            if _add_party(r, J):
                J["party-affiliations"].append(_party_template(r))

    EI = peripheral_metadata["external_identifiers"]
    if EI is not None and len(EI) > 0:
        for i, r in EI.iterrows():
            J["identifiers"].append(_identifier_template(r["authority"], r['identifier']))

    PB = peripheral_metadata["place_of_birth"]
    if PB is not None and len(PB) > 0:
        J["place-of-birth"]["place"] = PB.at[0, "place"]
        J["place-of-birth"]["link"] = PB.at[0, "link"]

    PD = peripheral_metadata["place_of_death"]
    if PD is not None and not PD.empty:
        J["place-of-death"]["place"] = peripheral_metadata["place_of_death"].at[0, "place"]
        J["place-of-death"]["link"] = peripheral_metadata["place_of_death"].at[0, "link"]

    PO = peripheral_metadata["portraits"]
    if PO is not None and len(PO) > 0:
        for i, r in peripheral_metadata["portraits"].iterrows():
            J["portraits"].append(r["portrait"])

    # populate info into J
    if _verify_J(J):
        return J
    else:
        return None


def write_J(J, person_id, website_path) -> None:
    """
    Write a json file for each swerik ID with person's info.

    Args:
        J (dict): person dict
        person_id (str): person id
        website_path (str): path in website repo
    """
    with open(f"{website_path}_data/_person-catalog/{person_id}.json", "w+") as outj:
        json.dump(J, outj, ensure_ascii=False, indent=2)


def write_md(person_id:str, website_path:str) -> None:
    """
    Write markwown file for each swerik ID

    Args:
        person_id (str): person id
        website_path (str): path in website repo

    """
    markdown = f"""---
layout: catalog
title: SWERIK Person Catalog
---
{{% assign p = site.data._person-catalog.{person_id} %}}
{{% include person-catalog.html p=p %}}

"""
    with open(f"{website_path}_person-catalog/{person_id}.md", "w+") as md:
        md.write(markdown)
