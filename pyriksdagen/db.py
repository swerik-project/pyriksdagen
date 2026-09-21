import polars as pl
import os, json, re, hashlib
from .utils import get_data_location
from .metadata import load_Corpus_metadata
from importlib_resources import files
from trainerlog import get_logger

LOGGER = get_logger("db")


def year_iterator(file_db):
    """
    Iterate over triplets of (corpus_year, package_ids, year_db) for provided file database.
    """
    file_db_years = sorted(list(set(file_db["year"].to_list())))
    LOGGER.info(f"Years to be iterated\n{file_db_years}")
    for corpus_year in file_db_years:
        year_db = file_db.filter(pl.col("year") == corpus_year)
        package_ids = year_db["protocol_id"]
        package_ids = package_ids.to_list()
        package_ids = sorted(package_ids)

        yield corpus_year, package_ids, year_db


def load_patterns(year=None, phase="segmentation"):
    """
    Load regex patterns from disk
    """
    file = files(f'pyriksdagen.data.{phase}').joinpath('patterns.json')
    with file.open() as f:
        patterns = pl.read_ndjson(f)
    if year is not None:
        patterns = patterns.filter(pl.col("start") >= year)
        patterns = patterns.filter(pl.col("end") <= year)

    patterns = patterns.with_columns(pl.lit(None).alias("protocol_id"))

    manual_path = "input/" + phase + "/manual.csv"
    if os.path.exists(manual_path):
        manual = pl.read_csv(manual_path)
        manual = manual.with_columns(pl.lit("manual").alias("type"))
        return pl.concat([manual, patterns], how="diagonal")
    else:
        return patterns


def filter_db(db, start_date=None, end_date=None, year=None, protocol_id=None):
    """
    Filter dataframe either based on year or protocol id
    """
    assert (
        year is not None or protocol_id is not None or (start_date is not None and end_date is not None)
    ), "Provide either year or protocol id"
    if start_date is not None and end_date is not None:
        start_value = start_date.date() if hasattr(start_date, "date") else start_date
        end_value = end_date.date() if hasattr(end_date, "date") else end_date
        filtered_db = db.filter((pl.col("start") <= end_value) & (pl.col("end") >= start_value))
        return filtered_db
    elif year is not None:
        if "start" in db.columns:
            filtered_db = db.filter(pl.col("start").dt.year() <= year)
            filtered_db = filtered_db.filter(pl.col("end").dt.year() >= year)
            return filtered_db
        elif "year" in db.columns:
            filtered_db = db.filter(pl.col("year") == year)
            return filtered_db
        else:
            return None

    else:
        return db.filter(pl.col("protocol_id") == protocol_id)

def load_ministers(path='corpus/wiki-data/minister.json'):
    '''Unpacks very nested minister.json file to a df.'''
    with open(path, 'r') as f:
        minister = json.load(f)

    data = []
    for gov in minister:
        g = gov["government"]
        for member in gov["cabinet"]:
            Q = member["wiki_id"]
            n = member["name"]
            for pos in member["positions"]:
                r = pos["role"]
                s = pos["start"]
                e = pos["end"]
                data.append([g, Q, n, r, s, e])
    minister = pl.DataFrame(data, schema=["government", "wiki_id", "name", "role", "start", "end"], orient="row")
    return minister

def load_metadata(metadata_location=None, processed_metadata_folder=None):
    if metadata_location is None:
        metadata_location = get_data_location("metadata")
    party_mapping = pl.read_csv(f'{metadata_location}/party_abbreviation.csv')
    mb_db, minister_db, speaker_db = None, None, None
    LOGGER.info("Attempting to load data from the preprocessed data folder")
    try:
        mp_db = pl.read_csv(f'{processed_metadata_folder}/member_of_parliament.csv')
        minister_db = pl.read_csv(f'{processed_metadata_folder}/minister.csv')
        speaker_db = pl.read_csv(f'{processed_metadata_folder}/speaker.csv')
    except Exception:
        LOGGER.info("Loading preprocessed data failed... compiling the metadata corpus")
        df = load_Corpus_metadata(metadata_location)        
        mp_db = df.filter(pl.col('source') == 'member_of_parliament')
        minister_db = df.filter(pl.col('source') == 'minister')
        speaker_db = df.filter(pl.col('source') == 'speaker')

    ### Temporary colname changes
    mp_db = mp_db.with_columns(pl.col("location").alias("specifier")).rename({'person_id':'id'})
    minister_db = minister_db.rename({'person_id':'id'})
    speaker_db = speaker_db.rename({'person_id':'id'})

    # Datetime format
    mp_db = mp_db.with_columns(pl.col(["start", "end"]).str.to_date(strict=False))
    minister_db = minister_db.with_columns(pl.col(["start", "end"]).str.to_date(strict=False))
    speaker_db = speaker_db.with_columns(pl.col(["start", "end"]).str.to_date(strict=False))

    return party_mapping, mp_db, minister_db, speaker_db

def load_expressions(phase="segmentation", year=None):
    if phase == "segmentation":
        patterns = load_patterns(year=year)
        expressions = dict()
        for row in patterns.iter_rows(named=True):
            pattern = row["pattern"]
            exp = re.compile(pattern)
            # Calculate digest for distringuishing patterns without ugly characters
            pattern_digest = hashlib.md5(pattern.encode("utf-8")).hexdigest()[:16]
            expressions[pattern_digest] = exp
        return expressions
    elif phase == "mp":
        file = files(f'pyriksdagen.data.segmentation').joinpath('detection.csv')
        with file.open() as f:
            patterns = pl.read_csv(f, separator=";")
        expressions = []
        for row in patterns.iter_rows(named=True):
            exp, t = row["pattern"], row["type"]
            expressions.append((re.compile(exp), t))
        return expressions
    elif phase == "join_intros":
        file = files(f'pyriksdagen.data.segmentation').joinpath('join_intro_pattern.csv')
        with file.open() as f:
            #"input/segmentation/join_intro_pattern.csv"
            patterns = pl.read_csv(f, separator=";")
        expressions = []
        for row in patterns.iter_rows(named=True):
            exp, t = row["pattern"], row["type"]
            expressions.append((re.compile(exp), t))
        return expressions

def _keep_most_significant(df, cols, id="wiki_id"):
    for col in cols:
        df = df.with_columns(pl.col(col).cast(pl.String))
        primary = df.filter(pl.col(col) != pl.col(col).str.slice(0, 4))
        primary = primary.filter(pl.col(col).is_not_null())

        #primary = primary.drop_duplicates([id, col])
        secondary = df.filter(pl.col(col) == pl.col(col).str.slice(0, 4))
        secondary = secondary.filter(pl.col(col).is_not_null())

        secondary = secondary.unique(subset=[id, col])

        col_df = pl.concat([primary, secondary], how="diagonal")
        col_df = col_df.unique(subset=id, keep="first")
        col_df = col_df.select([id, col])

        df = df.select([c for c in df.columns if c != col])
        df = df.unique()
        df = df.join(col_df, how="left", on=id)

    col = cols[0]
    df = df.with_columns(pl.col(col).cast(pl.String))
    primary = df.filter(pl.col(col) != pl.col(col).str.slice(0, 4))
    secondary = df.filter(pl.col(col) == pl.col(col).str.slice(0, 4))

    df = pl.concat([primary, secondary], how="diagonal")
    df = df.unique(subset=id, keep="first")
    return df

def clean_person_duplicates(df):
    counts = df.group_by("person_id").len().rename({"len": "person_count"})
    dupl = df.join(counts, on="person_id").filter(pl.col("person_count") > 1).drop("person_count")
    df = df.join(counts, on="person_id").filter(pl.col("person_count") == 1).drop("person_count")
    dupl = _keep_most_significant(dupl, ["born", "dead"], id="person_id")
    cols = list(df.columns)
    df = pl.concat([dupl, df], how="diagonal")
    df = df.select(cols)
    df = df.unique(subset=list(df.columns))
    df = df.sort(list(df.columns))
    return df
