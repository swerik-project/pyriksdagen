#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Class declaration and functions related to corpus metadata
"""
from functools import partial
from pyriksdagen.match_mp import multiple_replace
from pyriksdagen.utils import get_data_location
from trainerlog import get_logger
import polars as pl
import calendar
import datetime
import os
import re

LOGGER = get_logger("metadata")


def increase_date_precision(date, start=True):
    if date is None:
        return date
    # Year
    if len(date) == 4 and start:
        return date + '-01-01'
    if len(date) == 4 and not start:
        return date + '-12-31'
    # Month
    if len(date) == 7 and start:
        return date + '-01'
    if len(date) == 7 and start:
        last_day = calendar.monthrange(int(date[0]), int(date[1]))[1]
        return date + f'-{last_day}'
    # Day
    if len(date) == 10:
        return date


def check_date_overlap(start1, end1, start2, end2):
    latest_start = max(start1, start2)
    earliest_end = min(end1, end2)
    delta = (earliest_end - latest_start).days + 1
    overlap = max(0, delta)
    return True if overlap > 0 else False


def impute_member_date(db, gov_db, from_gov='Regeringen Löfven I'):
    gov_start = gov_db.filter(pl.col("government") == from_gov)["start"][0]
    gov_end = gov_db["end"].max()
    return db.with_columns(
        pl.when(
            (pl.col("source") == "member_of_parliament")
            & (pl.col("start") > gov_start)
            & pl.col("end").is_null()
        )
        .then(pl.lit(gov_end))
        .otherwise(pl.col("end"))
        .alias("end")
    )


def impute_member_dates(db, metadata_folder):
    def _fill_na(row, **kwargs):
        if row['start'] == 'nan' and row['end'] == 'nan':
            return row
        elif row['start'] is None and row['end'] is None:
            row['start'] = 'nan'
            row['end'] = 'nan'
            return row
        else:
            if row['start'] is None or row['start'] == 'nan':
                try:
                    py = riksmote.filter((pl.col('start') <= row['end']) & (pl.col('end') >= row['end']))
                    row['start'] = py['start'].unique()[0]
                except:
                    #pass
                    LOGGER.error(f"no bueno ---------------------> end: {row['end']}, {row['person_id']}")
            elif row['end'] is None or row['end'] == 'nan':
                if int(row['start'][:4]) < 1867:
                    row['end'] = 'nan'
                    return row
                try:
                    py = riksmote.filter((pl.col('start') <= row['start']) & (pl.col('end') > row['start']))
                    row['end'] = py['end'].unique()[0]
                except:
                    py = riksmote.filter(pl.col('end').str.starts_with(row['start'][:4]))
                    rs = sorted(py['end'].unique(), reverse=True)[0]
                    if rs < row['start']:
                        py = riksmote.filter(pl.col('end').str.starts_with(str(int(row['start'][:4])+1)))
                        rs = sorted(py['end'].unique(), reverse=True)[0]
                    row['end'] = rs
        return row

    def _impute_start(date, **kwargs):
        riksmote = kwargs['riksmote']
        if len(date) == 10:
            return date
        elif len(date) == 7:
            s = sorted(riksmote.filter(pl.col('start').str.starts_with(date))['start'].to_list())
            if len(s) > 0:
                return s[0]
            else:
                return date + "-01"
        else:
            s = sorted(riksmote.filter(pl.col('start').str.starts_with(date))['start'].to_list())
            if len(s) > 0:
                return s[0]
            else:
                LOGGER.debug(f"Problem with start date: {date} not in riksmote")
                return date + '-01-01'

    def _impute_end(date, **kwargs):
        riksmote = kwargs['riksmote']
        if len(date) == 10:
            return date
        elif len(date) == 7:
            s = sorted(riksmote.filter(pl.col('end').str.starts_with(date))['end'].to_list(), reverse=True)
            if len(s) > 0:
                return s[0]
            else:
                date_year, date_month = date.split("-")
                last_day_of_the_month = calendar.monthrange(int(date_year), int(date_month))[1]
                return date + f'-{last_day_of_the_month}'
        else:
            s = sorted(riksmote.filter(pl.col('end').str.starts_with(date))['end'].to_list(), reverse=True)
            if len(s) > 0:
                return s[0]
            else:
                LOGGER.debug(f"Problem with end date: {date} not in riksmote")
                return date + '-12-31'

    riksmote = pl.read_csv(f"{metadata_folder}/riksdag-year.csv").with_columns(
        pl.col(["start", "end", "parliament_year"]).cast(pl.String)
    )

    rows = []
    for row in db.to_dicts():
        if row["source"] == "member_of_parliament" and (
            row["start"] is None
            or row["start"] == "nan"
            or row["end"] is None
            or row["end"] == "nan"
        ):
            row = _fill_na(row, riksmote=riksmote)
        if row["source"] == "member_of_parliament" and row["start"] is not None and row["start"] != "nan":
            row["start"] = _impute_start(row["start"], riksmote=riksmote)
        if (
            row["source"] == "member_of_parliament"
            and row["start"] is not None
            and row["end"] is not None
            and row["end"] != "nan"
        ):
            row["end"] = _impute_end(row["end"], riksmote=riksmote)
        rows.append(row)
    return pl.DataFrame(rows)


def impute_minister_date(db, gov_db):
    def _impute_minister_date(minister, gov_db):
        if minister['start'] is None:
            minister['start'] = gov_db.filter(pl.col('government') == minister['government'])['start'][0]
        if minister['end'] is None:
            minister['end'] = gov_db.filter(pl.col('government') == minister['government'])['end'][0]
        return minister

    # Impute missing minister dates using government dates
    rows = []
    for row in db.to_dicts():
        if "source" not in db.columns or row["source"] == "minister":
            row = _impute_minister_date(row, gov_db=gov_db)
        rows.append(row)
    return pl.DataFrame(rows)


def impute_speaker_date(db):
    fallback_end = pl.col('start') + datetime.timedelta(days=365*4)
    if "source" in db.columns:
        idx = (pl.col('source') == 'speaker') & pl.col('end').is_null() & ~pl.col('role').str.contains('kammare')
    else:
        idx = pl.col('end').is_null() & ~pl.col('role').str.contains('kammare')
    return db.with_columns(pl.when(idx).then(fallback_end).otherwise(pl.col('end')).alias('end'))


def impute_date(db, metadata_folder):
    db = db.with_columns(pl.col(["start", "end"]).cast(pl.String))
    if 'source' in db.columns:
        sources = set(db['source'])
        if 'member_of_parliament' in sources:
            #db = impute_member_date(db, gov_db)
            db = impute_member_dates(db, metadata_folder)

        db = db.with_columns(
            pl.col('start').map_elements(partial(increase_date_precision, start=True), return_dtype=pl.String),
            pl.col('end').map_elements(partial(increase_date_precision, start=False), return_dtype=pl.String),
        ).with_columns(pl.col(["start", "end"]).str.to_date("%Y-%m-%d"))

        gov_db = pl.read_csv(f'{metadata_folder}/government.csv').with_columns(
            pl.col(["start", "end"]).str.to_date("%Y-%m-%d")
        )
        latest_start = gov_db['start'].max()
        gov_db = gov_db.with_columns(
            pl.when(pl.col('start') == latest_start)
            .then(pl.col('start') + datetime.timedelta(days=365*4))
            .otherwise(pl.col('end'))
            .alias('end')
        )

        if 'member_of_parliament' in sources:
            db = impute_member_date(db, gov_db)
        if 'minister' in sources:
            db = impute_minister_date(db, gov_db)
        if 'speaker' in sources:
            db = impute_speaker_date(db)

    else:
        db = db.with_columns(
            pl.col('start').map_elements(partial(increase_date_precision, start=True), return_dtype=pl.String),
            pl.col('end').map_elements(partial(increase_date_precision, start=False), return_dtype=pl.String),
        ).with_columns(pl.col(["start", "end"]).str.to_date("%Y-%m-%d"))
    return db


def impute_party(db, party):
    if 'party' not in db.columns:
        db = db.with_columns(pl.lit(None, dtype=pl.String).alias("party"))
    data = []
    rows = db.to_dicts()
    for row in rows:
        if row.get('party') is None:
            parties = party.filter(pl.col('person_id') == row['person_id'])
            party_values = set(parties['party'].to_list())
            if len(party_values) == 1:
                row['party'] = next(iter(party_values))
            if len(party_values) >= 2:
                for sow in parties.to_dicts():
                    try:
                        res = check_date_overlap(row['start'], sow['start'], row['end'], sow['end'])
                    except:
                        LOGGER.error("Impute dates on Corpus using impute_date() before imputing parties!\n")
                        raise
                    if res:
                        m = row.copy()
                        m['party'] = sow['party']
                        data.append(m)
    return pl.concat([pl.DataFrame(rows), pl.DataFrame(data)], how="diagonal") if data else pl.DataFrame(rows)


def abbreviate_party(db, party):
    party = {row['party']:row['abbreviation'] for row in party.to_dicts()}
    return db.with_columns(
        pl.col("party").fill_null("").replace(party, default=None).alias("party_abbrev")
    )


def clean_name(db):
    return db.with_columns(
        pl.when(pl.col("name").is_not_null())
        .then(
            pl.col("name")
            .str.to_lowercase()
            .map_elements(multiple_replace, return_dtype=pl.String)
            .str.replace_all('-', ' ', literal=True)
            .str.replace_all(r'[^a-zåäö\s\-]', '')
        )
        .otherwise(pl.col("name"))
        .alias("name")
    )


def infer_chamber(db):
    def _infer_chamber(role):
        d = {'första': 1, 'andra': 2}
        match = re.search(r'([a-zåäö]+)\s*(?:kammar)', role)
        return d[match.group(1)] if match else 0
    return db.with_columns(pl.col('role').map_elements(_infer_chamber, return_dtype=pl.Int8).alias('chamber'))


def format_member_role(db):
    return db.with_columns(pl.col('role').str.extract(r'(ledamot)').alias('role'))


def format_minister_role(db):
    return db.with_columns(pl.col("role").str.replace('Sveriges ', '').str.to_lowercase().alias("role"))


def format_speaker_role(db):
    def _format_speaker_role(role):
        match = re.search(r'(andre |förste |tredje )?(vice )?talman', role)
        return match.group(0)
    return db.with_columns(pl.col('role').map_elements(_format_speaker_role, return_dtype=pl.String).alias('role'))


class Corpus(pl.DataFrame):
    """
    Store corpus metadata as a single Polars DataFrame where
    the column 'source' indicates the type of the row
    """
    def __init__(self, *args, **kwargs):
        super(Corpus, self).__init__(*args, **kwargs)

    @property
    def _constructor(self):
        return Corpus

    def _load_metadata(self, file, metadata_folder="corpus/metadata", source=False):
        df = pl.read_csv(f"{metadata_folder}/{file}.csv")

        # Adjust to new structure where party information
        # is not included in member_of_parliament.csv
        if file == "member_of_parliament":
            columns = list(df.columns) + ["party"]
            party_df = pl.read_csv(f"{metadata_folder}/party_affiliation.csv")
            party_df = party_df.filter(pl.col("start").is_not_null())
            party_df = party_df.filter(pl.col("end").is_not_null())
            df = df.join(party_df, on=["person_id", "start", "end"], how="left")
            df = df.select(columns)
        if source:
            df = df.with_columns(pl.lit(file).alias('source'))
        return df

    def add_mps(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('member_of_parliament', metadata_folder=metadata_folder, source=True)
        df = infer_chamber(df)
        df = format_member_role(df)
        return Corpus(pl.concat([self, df], how="diagonal"))

    def add_ministers(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('minister', metadata_folder=metadata_folder, source=True)
        df = format_minister_role(df)
        return Corpus(pl.concat([self, df], how="diagonal"))

    def add_speakers(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('speaker', metadata_folder=metadata_folder, source=True)
        df = infer_chamber(df)
        df = format_speaker_role(df)
        return Corpus(pl.concat([self, df], how="diagonal"))

    def add_persons(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('person', metadata_folder=metadata_folder)
        return Corpus(self.join(df, on='person_id', how='left'))

    def add_location_specifiers(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('location_specifier', metadata_folder=metadata_folder)
        return Corpus(self.join(df, on='person_id', how='left'))

    def add_names(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('name', metadata_folder=metadata_folder)
        return Corpus(self.join(df, on='person_id', how='left'))

    def impute_dates(self, metadata_folder="corpus/metadata"):
        return Corpus(impute_date(self, metadata_folder))

    def impute_parties(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('party_affiliation', metadata_folder=metadata_folder)
        df = impute_date(df, metadata_folder)
        return Corpus(impute_party(self, df))

    def abbreviate_parties(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('party_abbreviation', metadata_folder=metadata_folder)
        return Corpus(abbreviate_party(self, df))

    def add_twitter(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('twitter', metadata_folder=metadata_folder)
        return Corpus(self.join(df, on='person_id', how='left'))

    def clean_names(self):
        return Corpus(clean_name(self))


def load_Corpus_metadata(metadata_folder=None, read_db=False, read_db_from=None):
    """
    Populates Corpus object
    """
    if read_db or read_db_from is not None:
        if read_db_from is None:
            read_db_from = get_data_location("metadata_db")
            if not os.path.exists(read_db_from):
                raise FileNotFoundError(f"File not found at {read_db_from}. Try compiling the database or set the METADATA_DB variable in your environment.")

        LOGGER.info("Reading metadata db from a file.")
        try:
            corpus = pl.read_csv(read_db_from)
        except:
            raise ValueError(f"{read_db_from} could not be read as a CSV file.")
    else:
        LOGGER.info("Compiling metadata db from source.")
        if metadata_folder is None:
            metadata_folder = get_data_location("metadata")

        corpus = Corpus()

        corpus = corpus.add_mps(metadata_folder=metadata_folder)
        corpus = corpus.add_ministers(metadata_folder=metadata_folder)
        corpus = corpus.add_speakers(metadata_folder=metadata_folder)

        corpus = corpus.add_persons(metadata_folder=metadata_folder)
        corpus = corpus.add_location_specifiers(metadata_folder=metadata_folder)
        corpus = corpus.add_names(metadata_folder=metadata_folder)

        corpus = corpus.impute_dates(metadata_folder=metadata_folder)
        corpus = corpus.impute_parties(metadata_folder=metadata_folder)
        corpus = corpus.abbreviate_parties(metadata_folder=metadata_folder)
        corpus = corpus.add_twitter(metadata_folder=metadata_folder)
        corpus = corpus.clean_names()

        # Clean up speaker role formatting
        corpus = corpus.with_columns(pl.col("role").replace({
            'Sveriges riksdags talman':'speaker',
            'andra kammarens andre vice talman':'ak_2_vice_speaker',
            'andra kammarens förste vice talman':'ak_1_vice_speaker',
            'andra kammarens talman':'ak_speaker',
            'andra kammarens vice talman':'ak_1_vice_speaker',
            'andre vice talman i första kammaren':'fk_2_vice_speaker',
            'första kammarens talman':'fk_speaker',
            'första kammarens vice talman':'fk_1_vice_speaker',
            'förste vice talman i första kammaren':'fk_1_vice_speaker'
            }).alias("role"))

        # Temporary ids
        corpus = corpus.with_columns(pl.col('person_id'))

        # Drop individuals with missing names
        corpus = corpus.filter(pl.col('name').is_not_null())

        # Remove redundancy and split file
        corpus = corpus.unique()
        corpus = corpus.drop_nulls(subset=['name', 'start', 'end'])
        corpus = corpus.sort(['person_id', 'start', 'end', 'name'])


    return corpus


def fetch_person_name(person_id, corpus, primary=True):
    """
    Get a person's primary name or list of names.

    Args:
        person_id (str): a swerik-style person ID
        corpus (df): compiled metadata DB
        primary (bool): return only person's primary name

    Returns:
        name or names (str or list of str)
    """
    def _names(df):
        return df["name"].unique()

    if person_id is None or person_id == "unknown":
        return None
    df = corpus.filter(pl.col("person_id") == person_id)
    if primary == True:
        df = df.filter(pl.col("primary_name") == True)
        names = _names(df)
        if len(names) == 1:
            return names[0]
        else:
            raise ValueError(f"There should be exactly one primary name for {person_id}, but: {names}")
    else:
        return _names(df)


def fetch_person_gender(person_id, corpus):
    """
    Get Person's gender.

    Args:
        person_id (str): a swerik-style person ID
        corpus (df): compiled metadata DB

    Returns:
        gender (str): man or woman
    """
    if person_id is None or person_id == "unknown":
        return None
    df = corpus.filter((pl.col("person_id") == person_id) & pl.col("gender").is_not_null())
    genders = df["gender"].unique()
    if len(genders) == 1:
        return genders[0]
    elif len(genders) == 0:
        return None
    else:
        raise ValueError(f"There probably shouldn't be multiple genders for {person_id}, but {genders}")


def fetch_person_party(person_id, corpus, date=None):
    """
    Get a person's party affiliation (during a particular period.

    Args:
        person_id (str): a swerik-style person ID
        corpus (df): compiled metadata DB
        date (str): (yyyy-mm-dd) formatted date string.
            If the date arg is not None, the fn will try to match
            party affiliations that overlap with that date. If none
            are found, it defaults to all party affiliations

    Returns:
        party/ies: str or list of str
    """
    def _party(df):
        parties = df["party"].unique()
        if len(parties) == 1:
            return "string", parties[0]
        elif len(parties) == 0:
            return None
        else:
            return parties

    if person_id is None or person_id == "unknown":
        return None

    df = corpus.filter((pl.col("person_id") == person_id) & pl.col("party").is_not_null())
    if date is not None:
        df_date = df.filter((pl.col("start") <= date) & (pl.col("end") >= date))
        parties = _party(df_date)
        if parties is not None:
            return parties
    return _party(df)
