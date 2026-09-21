"""
Handles the data on the members of parliament.
"""

import polars as pl
import os, re
import progressbar
import hashlib
import unicodedata


def create_database(path):
    """
    Create an initial version of the MP dataframe
    """
    extension = path.split(".")[-1]

    if extension == "csv":
        print("Read:", path)
        df = pl.read_csv(path)

        # Drop columns where everything is null
        nulls = [df[col].null_count() == df.height for col in df.columns]
        nulls = zip(df.columns, nulls)
        for column_name, null in nulls:
            if null:
                df = df.drop(column_name)

        new_columns = list(df.columns)
        for column_ix, column_name in enumerate(df.columns):
            if "." in column_name:
                new_name = column_name.split(".")[0]
                new_columns[column_ix] = new_name

        df = df.rename(dict(zip(df.columns, new_columns)))

    elif extension == "txt":
        print("Read:", path)
        f = open(path)
        columns = ["Riksdagsledamot", "Parti", "Valkrets"]

        rows = []
        lan = None
        for line in f:
            line = line.replace("\n", "")
            if len(line) > 2:
                indented = line[:4] == "    "

                # Non-indented lines are titles, which correspond to 'län' / region
                if not indented:
                    lan = line
                else:
                    row = line.split(",")
                    row = [x.strip() for x in row]

                    datapoint = []
                    # Add name
                    name = row[0]
                    datapoint.append(name)
                    # Add party
                    possible_parties = [s for s in row if "f." not in s]
                    party = possible_parties[-1]
                    party = re.sub(r"\(.*?\)", "", party)
                    party = re.sub(r"\[.*?\]", "", party).strip()
                    if len(party) < 4 or party.lower() != party:
                        datapoint.append(party)
                    else:
                        datapoint.append(None)
                    # Add 'län' / region
                    datapoint.append(lan)
                    rows.append(datapoint)

        df = pl.DataFrame(rows, schema=columns, orient="row")
    else:
        print("File type not supported.", path)
        return None

    # Harmonize column names
    new_columns = list(df.columns)
    for column_ix, column_name in enumerate(df.columns):
        if column_name in ["Ledamot", "Riksdagsledamot", "Namn"]:
            new_columns[column_ix] = "name"
        if column_name in ["Parti"]:
            new_columns[column_ix] = "party"
        if column_name in ["Yrke"]:
            new_columns[column_ix] = "occupation"
        if column_name in ["Valkrets"]:
            new_columns[column_ix] = "district"

    df = df.rename(dict(zip(df.columns, new_columns)))

    # Drop unnecessary columns
    retain = ["name", "party", "district", "occupation"]
    for column_name in df.columns:
        if column_name not in retain:
            df = df.drop(column_name)

    # Chamber
    chamber = "Enkammarriksdagen"
    potential_chamber = path.split("/")[-2]
    if potential_chamber == "ak":
        chamber = "Andra kammaren"
    elif potential_chamber == "fk":
        chamber = "Första kammaren"
    df = df.with_columns(pl.lit(chamber).alias("chamber"))

    # Year in office
    year_str = path.split("/")[-1].split(".")[0].replace("–­­", "-")
    if len(year_str) == 9:
        df = df.with_columns(
            pl.lit(int(year_str[:4])).alias("start"),
            pl.lit(int(year_str[-4:])).alias("end"),
        )
    elif len(year_str) == 4:
        # TODO: Currently using +-3 year heuristic because exact terms
        # are unavailable.
        if chamber == "Första kammaren":
            df = df.with_columns(
                pl.lit(int(year_str) - 3).alias("start"),
                pl.lit(int(year_str) + 3).alias("end"),
            )
        else:
            df = df.with_columns(
                pl.lit(int(year_str)).alias("start"),
                pl.lit(int(year_str)).alias("end"),
            )
    else:
        print(year_str)

    return df


def create_full_database(dirs):
    mp_dbs = []
    for d in dirs:
        for path in os.listdir(d):
            full_path = os.path.join(d, path)
            mp_db = create_database(full_path)
            if mp_db is not None:
                mp_dbs.append(mp_db)
    mp_db = pl.concat(mp_dbs, how="diagonal")

    mp_db = mp_db.sort(["start", "chamber", "name"])

    columnsTitles = [
        "name",
        "party",
        "district",
        "chamber",
        "start",
        "end",
        "occupation",
    ]
    for column in columnsTitles:
        if column not in mp_db.columns:
            mp_db = mp_db.with_columns(pl.lit(None).alias(column))
    mp_db = mp_db.select(columnsTitles)

    mp_db = mp_db.filter(pl.col("name").is_not_null())

    print(mp_db.filter(pl.col("start").is_null()))
    mp_db = mp_db.with_columns(pl.col(["start", "end"]).cast(pl.Int64))
    return mp_db


def add_gender(mp_db, names):
    """
    Based to first names, add gender to an MP dataframe.
    """
    print("Add gender...")
    rows = mp_db.to_dicts()

    name_to_gender = {}
    for namerow in names.to_dicts():
        name = namerow["name"]
        gender = namerow["gender"]
        if gender == "masculine":
            gender = "man"
        elif gender == "feminine":
            gender = "woman"
        name_to_gender[name] = gender

    for row in progressbar.progressbar(rows):
        first_name = row["name"].split()[0]
        if "-" in first_name:
            first_name = first_name.split("-")[0]
        if first_name in name_to_gender:
            row["gender"] = name_to_gender[first_name]
        else:
            row["gender"] = None

    return pl.DataFrame(rows)


def clean_names(mp_db):
    """
    Remove artefacts from MP names and specifiers
    """
    print("Clean names...")
    rows = mp_db.to_dicts()
    for row in progressbar.progressbar(rows):
        name = row["name"]
        split_i = name.split(" i ")
        if name != split_i[0]:
            name = split_i[0]
            if len(split_i) > 1:
                row["specifier"] = "i " + split_i[1]
            else:
                row["specifier"] = None
        if "[" in name:
            name = name.split("[")[0]
        if "(er" in name:
            name = name.split("(er")[0]
        if "ersatt av" in name:
            name = name.split("ersatt av:")[-1]
        name = name.strip()
        assert name != "", "names can't be empty: " + row["name"]
        row["name"] = name

    return pl.DataFrame(rows)


def replace_party_abbreviations(mp_db, party_db):
    """
    Replace party abbreviations with standardized party names.
    """
    print("Replace party abbreviations...")
    party_dict = dict()
    rows = mp_db.to_dicts()
    for row in party_db.to_dicts():
        party = row["party"]
        abbreviation = row["abbreviation"]
        party_dict[abbreviation] = party

    for row in progressbar.progressbar(rows):
        current_party = row["party"]
        if type(current_party) == str:
            # Check if 'party' attribute is in the list of abbreviations
            row_party = current_party.strip().lower()
            if row_party in party_dict:
                row["party"] = party_dict[row_party]

    return pl.DataFrame(rows)


def add_id(mp_db):
    """
    Generate deterministic IDs for mps based on the "name", "party", "district",
    "chamber", "start", and "end" columns of the dataframe.
    """
    print("Add id...")
    columns = ["name", "party", "district", "chamber", "start", "end"]
    print("columns used for generation:", ", ".join(columns))
    rows = mp_db.to_dicts()
    for row in progressbar.progressbar(rows):
        name = unicodedata.normalize("NFD", row["name"])
        name = name.encode("ascii", "ignore").decode("utf-8")
        name = name.lower().replace(" ", "_")
        name = name.replace(".", "").replace("(", "").replace(")", "").replace(":", "")
        party = row.get("party")

        pattern = [name]
        for column in columns:
            value = row[column]
            if type(value) != str:
                value = str(value)
            pattern.append(value)

        pattern = "_".join(pattern).replace(" ", "_").lower()

        digest = hashlib.md5(pattern.encode("utf-8")).hexdigest()
        row["id"] = name + "_" + digest[:6]

    return pl.DataFrame(rows)


def add_municipality(mp_db, mun_db):
    """
    Add home municipalities as specifiers for matched MPs from personregister
    """
    original_columns = list(mp_db.columns)
    print("Add municipalicites from 'personregister'...")

    def reorder_name(name):
        s = name.split(",")
        if len(s) == 1:
            return name
        else:
            newname = s[1].strip() + " " + s[0].strip()
            return newname

    mun_db = mun_db.with_columns(
        pl.col("name").map_elements(reorder_name, return_dtype=pl.String),
        ((pl.col("decade") // 10) * 10).alias("decade"),
    ).filter(pl.col("municipality").is_not_null())

    outdfs = []
    # mp_db["municipality"] = None

    start_min = min(set(mp_db["start"].to_list()))
    end_max = max(set(mp_db["end"].to_list()))

    start_min = (start_min // 10) * 10
    end_max = (end_max // 10 + 1) * 10
    for decade in range(start_min, end_max, 10):
        current_mun_db = mun_db.filter(pl.col("decade") == decade)
        current_mpdb = mp_db.filter((pl.col("end") >= decade) & (pl.col("start") < decade + 10))
        if not current_mun_db.is_empty():
            current_mun_db = current_mun_db.select(["name", "municipality"])

            mpdb_names = current_mpdb["name"].to_list()

            def rname(name):
                nameset = set(name.split())

                namesplit = name.split()
                for mpdb_name in mpdb_names:
                    mpdbsplit = mpdb_name.split()
                    samefirst = namesplit[0] == mpdbsplit[0]
                    samelast = namesplit[-1] == mpdbsplit[-1]
                    if (
                        samefirst
                        and samelast
                        and abs(len(namesplit) - len(mpdbsplit)) <= 1
                    ):
                        return mpdb_name.strip()
                return name.strip()

            replacedname = rname("Carl Wilhelm Höglund")

            print("Carl Wilhelm Höglund", "=>", replacedname, decade)
            current_mun_db = current_mun_db.with_columns(pl.col("name").map_elements(rname, return_dtype=pl.String))
            merged = current_mpdb.join(current_mun_db, how="left", on="name")
            merged.write_csv("merged_" + str(decade) + ".csv")

            newnames = set(current_mun_db["name"].to_list())
            outdfs.append(merged)
            print(
                "Carl Wilhelm Oskar Höglund in newnames",
                "Carl Wilhelm Oskar Höglund" in newnames,
            )
        else:
            outdfs.append(current_mpdb)

    mp_db = pl.concat(outdfs, how="diagonal")
    print(mp_db)
    mp_db = mp_db.with_columns(
        ("i " + pl.col("municipality").str.strip_chars()).alias("municipality")
    ).with_columns(
        pl.col("specifier").fill_null(pl.col("municipality")).alias("specifier")
    ).drop("municipality")

    mp_db = mp_db.group_by("id", maintain_order=True).first()
    mp_db = mp_db.select(original_columns)
    mp_db = mp_db.sort(["start", "chamber", "name"])
    return mp_db
