#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Class declaration and functions related to corpus metadata
"""
from functools import partial
from pyriksdagen.match_mp import multiple_replace
from pyriksdagen.utils import get_data_location
import pandas as pd
import calendar
import datetime
import os
import re




def increase_date_precision(date, start=True):
    if pd.isna(date):
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
    gov_start = gov_db.loc[gov_db['government'] == from_gov, 'start'].iloc[0]
    idx =     (db['source'] == 'member_of_parliament') &\
            (db['start'] > gov_start) &\
            (db['end'].isna())
    db.loc[idx, 'end'] = gov_db['end'].max()
    return db


def impute_member_dates(db, metadata_folder):
    def _fill_na(row, **kwargs):
        if row['start'] == 'nan' and row['end'] == 'nan':
            return row
        elif pd.isna(row['start']) and pd.isna(row['end']):
            return row
        else:
            riksmote = pd.read_csv(f"{metadata_folder}/riksdag-year.csv")
            if pd.isna(row['start']) or row['start'] == 'nan':
                try:
                    py = riksmote.loc[
                            (riksmote['start'] <= row['end']) &
                            (riksmote['end'] >= row['end'])
                        ].copy()
                    row['start'] = py['start'].unique()[0]
                except:
                    #pass
                    print("no bueno ---------------------> end:", row['end'], row['person_id'])
            elif pd.isna(row['end']) or row['end'] == 'nan':
                if int(row['start'][:4]) < 1867:
                    return row
                try:
                    py = riksmote.loc[
                            (riksmote['start'] <= row['start']) &
                            (riksmote['end'] > row['start'])
                        ].copy()
                    row['end'] = py['end'].unique()[0]
                except:
                    py = riksmote.loc[
                            riksmote['end'].str.startswith(row['start'][:4])
                        ].copy()
                    rs = sorted(py['end'].unique(), reverse=True)[0]
                    if rs < row['start']:
                        py = riksmote.loc[
                                riksmote['end'].str.startswith(
                                    str(int(row['start'][:4])+1))
                            ].copy()
                        rs = sorted(py['end'].unique(), reverse=True)[0]
                    row['end'] = rs
        return row

    def _impute_start(date, **kwargs):
        riksmote = kwargs['riksmote']
        if len(date) == 10:
            return date
        elif len(date) == 7:
            s = sorted(list(riksmote.loc[riksmote['start'].str.startswith(date, na=False), 'start']))
            if len(s) > 0:
                return s[0]
            else:
                return date + "-01"
        else:
            s = sorted(list(riksmote.loc[riksmote['start'].str.startswith(date, na=False), 'start']))
            if len(s) > 0:
                return s[0]
            else:
                print(f"Problem with start date: {date} not in riksmote")
                return date + '-01-01'

    def _impute_end(date, **kwargs):
        riksmote = kwargs['riksmote']
        if len(date) == 10:
            return date
        elif len(date) == 7:
            s = sorted(list(riksmote.loc[riksmote['end'].str.startswith(date, na=False), 'end']), reverse=True)
            if len(s) > 0:
                return s[0]
            else:
                date_year, date_month = date.split("-")
                last_day_of_the_month = calendar.monthrange(int(date_year), int(date_month))[1]
                return date + f'-{last_day_of_the_month}'
        else:
            s = sorted(list(riksmote.loc[riksmote['end'].str.startswith(date, na=False), 'end']), reverse=True)
            if len(s) > 0:
                return s[0]
            else:
                print(f"Problem with end date: {date} not in riksmote")
                return date + '-12-31'

    riksmote = pd.read_csv(f"{metadata_folder}/riksdag-year.csv")
    riksmote[['start', 'end']] = riksmote[['start', 'end']].astype(str)

    idx = (db['source'] == 'member_of_parliament') &\
            (((pd.isna(db['start'])) | (db['start'] == 'nan')) |\
            ((pd.isna(db['end'])) | (db['end'] == 'nan')))
    db.loc[idx] = db.loc[idx].apply(lambda x: _fill_na(x, riksmote=riksmote), axis = 1)

    idx = (db['source'] == 'member_of_parliament') &\
            (pd.notnull(db['start'])) & (db['start'] != 'nan')
    db.loc[idx, 'start'] = db.loc[idx, 'start'].apply(_impute_start, riksmote=riksmote)

    idx = (db['source'] == 'member_of_parliament') &\
            (pd.notnull(db['start'])) &\
            (pd.notnull(db['end']))  & (db['end'] != 'nan')
    db.loc[idx, 'end'] = db.loc[idx, 'end'].apply(_impute_end, riksmote=riksmote)
    return db


def impute_minister_date(db, gov_db):
    def _impute_minister_date(minister, gov_db):
        if pd.isna(minister['start']):
            minister['start'] = gov_db.loc[gov_db['government'] == minister['government'], 'start'].iloc[0]
        if pd.isna(minister['end']):
            minister['end'] = gov_db.loc[gov_db['government'] == minister['government'], 'end'].iloc[0]
        return minister

    # Impute missing minister dates using government dates
    if 'source' in db.columns:
        db.loc[db['source'] == 'minister'] =\
        db.loc[db['source'] == 'minister'].apply(partial(_impute_minister_date, gov_db=gov_db), axis=1)
    else:
        db = db.apply(partial(_impute_minister_date, gov_db=gov_db), axis=1)
    return db


def impute_speaker_date(db):
    if "source" in db.columns:
        idx =     (db['source'] == 'speaker') &\
                (db['end'].isna()) &\
                (db['role'].str.contains('kammare') == False)
        db.loc[idx, 'end'] = db.loc[idx, 'start'] + datetime.timedelta(days = 365*4)
    else:
        idx =     (db['end'].isna()) &\
                (db['role'].str.contains('kammare') == False)
        db.loc[idx, 'end'] = db.loc[idx, 'start'] + datetime.timedelta(days = 365*4)
    return db


def impute_date(db, metadata_folder):
    db[["start", "end"]] = db[["start", "end"]].astype(str)
    if 'source' in db.columns:
        sources = set(db['source'])
        if 'member_of_parliament' in sources:
            #db = impute_member_date(db, gov_db)
            db = impute_member_dates(db, metadata_folder)

        db['start'] = db['start'].apply(increase_date_precision, start=True)
        db['end'] = db['end'].apply(increase_date_precision, start=False)
        db[["start", "end"]] = db[["start", "end"]].apply(pd.to_datetime, format='%Y-%m-%d')

        gov_db = pd.read_csv(f'{metadata_folder}/government.csv')
        gov_db[["start", "end"]] = gov_db[["start", "end"]].apply(pd.to_datetime, format='%Y-%m-%d')
        idx = gov_db['start'].idxmax()
        gov_db.loc[idx, 'end'] = gov_db.loc[idx, 'start'] + datetime.timedelta(days = 365*4)

        if 'member_of_parliament' in sources:
            db = impute_member_date(db, gov_db)
        if 'minister' in sources:
            db = impute_minister_date(db, gov_db)
        if 'speaker' in sources:
            db = impute_speaker_date(db)

    else:
        db['start'] = db['start'].apply(increase_date_precision, start=True)
        db['end'] = db['end'].apply(increase_date_precision, start=False)
        db[["start", "end"]] = db[["start", "end"]].apply(pd.to_datetime, format='%Y-%m-%d')
    return db


def impute_party(db, party):
    if 'party' not in db.columns:
        db['party'] = pd.Series(dtype=str)
    data = []
    for i, row in db[db['party'].isnull()].iterrows():
        parties = party[party['person_id'] == row['person_id']]
        if len(set(parties['party'])) == 1:
            db.loc[i,'party'] = parties['party'].iloc[0]
        if len(set(parties['party'])) >= 2:
            for j, sow in parties.iterrows():
                try:
                    res = check_date_overlap(row['start'], sow['start'], row['end'], sow['end'])
                except:
                    print("Impute dates on Corpus using impute_date() before imputing parties!\n")
                    raise
                if res:
                    m = row.copy()
                    m['party'] = sow['party']
                    data.append(m)
    db = pd.concat([db, pd.DataFrame(data)]).reset_index(drop=True)
    return db


def abbreviate_party(db, party):
    party = {row['party']:row['abbreviation'] for _, row in party.iterrows()}
    db["party_abbrev"] = db["party"].fillna('').map(party)
    return db


def clean_name(db):
    idx = db['name'].notna()
    db.loc[idx, 'name'] = db.loc[idx, 'name'].str.lower()
    db.loc[idx, 'name'] = db.loc[idx, 'name'].astype(str).apply(multiple_replace)
    db.loc[idx, 'name'] = db.loc[idx, 'name'].str.replace('-', ' ', regex=False)
    db.loc[idx, 'name'] = db.loc[idx, 'name'].str.replace(r'[^a-zåäö\s\-]', '', regex=True)
    return db


def infer_chamber(db):
    def _infer_chamber(role):
        d = {'första': 1, 'andra': 2}
        match = re.search(r'([a-zåäö]+)\s*(?:kammar)', role)
        return d[match.group(1)] if match else 0
    db['chamber'] = db['role'].apply(_infer_chamber).astype(dtype=pd.Int8Dtype())
    return db


def format_member_role(db):
    db['role'] = db['role'].str.extract(r'(ledamot)')
    return db


def format_minister_role(db):
    db["role"] = db["role"].str.replace('Sveriges ', '').str.lower()
    return db


def format_speaker_role(db):
    def _format_speaker_role(role):
        match = re.search(r'(andre |förste |tredje )?(vice )?talman', role)
        return match.group(0)
    db['role'] = db['role'].apply(_format_speaker_role)
    return db


class Corpus(pd.DataFrame):
    """
    Store corpus metadata as a single pandas DataFrame where
    the column 'source' indicates the type of the row
    """
    def __init__(self, *args, **kwargs):
        super(Corpus, self).__init__(*args, **kwargs)

    @property
    def _constructor(self):
        return Corpus

    def _load_metadata(self, file, metadata_folder="corpus/metadata", source=False):
        df = pd.read_csv(f"{metadata_folder}/{file}.csv")

        # Adjust to new structure where party information
        # is not included in member_of_parliament.csv
        if file == "member_of_parliament":
            print(df)
            columns = list(df.columns) + ["party"]
            party_df = pd.read_csv(f"{metadata_folder}/party_affiliation.csv")
            party_df = party_df[party_df["start"].notnull()]
            party_df = party_df[party_df["end"].notnull()]
            df = df.merge(party_df, on=["person_id", "start", "end"], how="left")
            df = df[columns]
            print(df)
            print(df[df["party"].notnull()])
        if source:
            df['source'] = file
        return df

    def add_mps(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('member_of_parliament', metadata_folder=metadata_folder, source=True)
        df = infer_chamber(df)
        df = format_member_role(df)
        return Corpus(pd.concat([self, df]))

    def add_ministers(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('minister', metadata_folder=metadata_folder, source=True)
        df = format_minister_role(df)
        return Corpus(pd.concat([self, df]))

    def add_speakers(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('speaker', metadata_folder=metadata_folder, source=True)
        df = infer_chamber(df)
        df = format_speaker_role(df)
        return Corpus(pd.concat([self, df]))

    def add_persons(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('person', metadata_folder=metadata_folder)
        return self.merge(df, on='person_id', how='left')

    def add_location_specifiers(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('location_specifier', metadata_folder=metadata_folder)
        return self.merge(df, on='person_id', how='left')

    def add_names(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('name', metadata_folder=metadata_folder)
        return self.merge(df, on='person_id', how='left')

    def impute_dates(self, metadata_folder="corpus/metadata"):
        return impute_date(self, metadata_folder)

    def impute_parties(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('party_affiliation', metadata_folder=metadata_folder)
        df = impute_date(df, metadata_folder)
        return impute_party(self, df)

    def abbreviate_parties(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('party_abbreviation', metadata_folder=metadata_folder)
        return abbreviate_party(self, df)

    def add_twitter(self, metadata_folder="corpus/metadata"):
        df = self._load_metadata('twitter', metadata_folder=metadata_folder)
        return self.merge(df, on='person_id', how='left')

    def clean_names(self):
        return clean_name(self)


def load_Corpus_metadata(metadata_folder=None, read_db=False, read_db_from=None):
    """
    Populates Corpus object
    """
    if read_db or read_db_from is not None:
        if read_db_from is None:
            read_db_from = get_data_location("metadata_db")
            if not os.path.exists(read_db_from):
                raise FileNotFoundError(f"File not found at {read_db_from}. Try compiling the database or set the METADATA_DB variable in your environment.")

        print("Reading metadata db from a file.")
        try:
            corpus = pd.read_csv(read_db_from)
        except:
            corpus = pd.read_pickle(read_db_from)
        assert type(corpus) == Corpus, f"{read_db_from} is not a CSV or pickle file."
    else:
        print("Compiling metadata db from source.")
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
        corpus["role"] = corpus["role"].replace({
            'Sveriges riksdags talman':'speaker',
            'andra kammarens andre vice talman':'ak_2_vice_speaker',
            'andra kammarens förste vice talman':'ak_1_vice_speaker',
            'andra kammarens talman':'ak_speaker',
            'andra kammarens vice talman':'ak_1_vice_speaker',
            'andre vice talman i första kammaren':'fk_2_vice_speaker',
            'första kammarens talman':'fk_speaker',
            'första kammarens vice talman':'fk_1_vice_speaker',
            'förste vice talman i första kammaren':'fk_1_vice_speaker'
            })

        # Temporary ids
        corpus['person_id'] = corpus['person_id']

        # Drop individuals with missing names
        corpus = corpus[corpus['name'].notna()]

        # Remove redundancy and split file
        corpus = corpus.drop_duplicates()
        #print( corpus.loc[(pd.isna(corpus['start'])) | (pd.isna(corpus['end']))] )
        corpus = corpus.dropna(subset=['name', 'start', 'end'])
        corpus = corpus.sort_values(['person_id', 'start', 'end', 'name'])

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
    df = corpus.loc[corpus["person_id"] == person_id].copy()
    if primary == True:
        df = df.loc[corpus["primary_name"] == True].copy()
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
    df = corpus.loc[(corpus["person_id"] == person_id) & (pd.notnull(corpus["gender"]))].copy()
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

    df = corpus.loc[(corpus["person_id"] == person_id) & (pd.notnull(corpus["party"]))].copy()
    if date is not None:
        df_date = df.loc[(df["start"] <= date) & (df["end"] >= date)]
        parties = _party(df_date)
        if parties is not None:
            return parties
    return _party(df)


