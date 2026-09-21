from SPARQLWrapper import SPARQLWrapper, JSON
import numpy as np
import polars as pl
from importlib_resources import files
import re

def impute_query_string(source=None):
	# Defaults to all individuals
	if not source:
		source = ["member_of_parliament", "minister", "speaker"]
	
	strings = []
	for src in source:
		# Specific individual wikidata object
		if src.startswith('Q'):
			s = f"VALUES ?wiki_id {{ wd:{src} }}"
		# Category of wikidata objects
		else:
			s = files('pyriksdagen.data.queries').joinpath(f'{src}.txt').read_text()
		strings.append(s)
	return "\n} UNION {\n".join(strings)

def get_query_string(query_name):
	try:
		s = files('pyriksdagen.data.queries').joinpath(f'{query_name}.rq').read_text()
	except FileNotFoundError:
		print(f"File {query_name} not found")
	return s

def reduce_date_precision(date, precision):
	'''
	Truncates date to accurate length given precision level
	'''
	# Decade
	if int(precision) == 8:
		return str(int(date[:4]) // 10 * 10)
	# Year
	if int(precision) == 9:
		return date[:4]
	# Month
	if int(precision) == 10:
		return date[:7]
	# Day
	if int(precision) == 11:
		return date[:10]

def fix_dates(df):
	'''
	Converts date precision for all relevant cols and removes the precision columns
	'''
	for c in df.columns:
		if 'Precision' in c:
			base_name = c.replace('Precision', '')
			rows = []
			for row in df.to_dicts():
				if row.get(base_name) is not None:
					row[base_name] = reduce_date_precision(row[base_name], row[c])
				row.pop(c, None)
				rows.append(row)
			df = pl.DataFrame(rows)
	return df

def clean_sparql_df(df, query_name):
	# Clean columns
	rename_map = {
		'wiki_idLabel.value':'name',
		'government.value':'government_id.value',
		'riksmote.value':'riksmote_id.value',
		'party.value':'party_id.value',
	}
	df = df.rename({old: new for old, new in rename_map.items() if old in df.columns}) # avoid duplicate colnames
	df = df.select([c for c in df.columns if c.endswith('.value') or c == 'name'])
	
	df = df.rename({c: c.replace('.value', '').replace('Label', '') for c in df.columns})
	df = fix_dates(df) # use and drop date precision columns

	# Format values
	for colname in df.columns:
		if "_id" in colname:
			df = df.with_columns(pl.col(colname).str.split('/').list.last().alias(colname))

	# Drop pseudo missing values of form "http://www.wikidata.org/.well-known..."
	df = df.with_columns([
		pl.col(col).map_elements(lambda x: '' if 'http' in str(x) else x, return_dtype=df.schema[col]).alias(col)
		for col in df.columns
	])

	# Sort columns
	first_cols = [c for c in ['person_id', 'wiki_id', 'start', 'end'] if c in df.columns]
	other_cols = sorted([c for c in df.columns if c not in first_cols])
	df = df.select(first_cols+other_cols)

	# Sort rows
	first_cols.reverse()
	df = df.sort(list(first_cols+other_cols))
	return df

def _json_normalize_sparql_bindings(bindings):
	rows = []
	for binding in bindings:
		row = {}
		for key, value in binding.items():
			for subkey, subvalue in value.items():
				row[f"{key}.{subkey}"] = subvalue
		rows.append(row)
	return pl.DataFrame(rows)

def query2df(query_name, source=None):
	query = get_query_string(query_name)
	source = impute_query_string(source)
	query = query.replace('PLACEHOLDER', source)
	sparql = SPARQLWrapper("https://query.wikidata.org/sparql", agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11")
	sparql.setQuery(query)	
	sparql.setReturnFormat(JSON)
	try:
		results = sparql.query().convert()
	except:
		print(f"Query {query_name} failed")
	df = _json_normalize_sparql_bindings(results['results']['bindings'])
	df = clean_sparql_df(df, query_name)
	return df

def separate_name_location(name_location_specifier, alias):
	rows = []
	for row in name_location_specifier.select(['person_id', 'name']).iter_rows(named=True):
		rows.append({**row, 'primary_name': True})
	for row in name_location_specifier.select(['person_id', 'alias']).rename({'alias':'name'}).iter_rows(named=True):
		rows.append({**row, 'primary_name': False})
	for row in alias.select(['person_id', 'alias']).rename({'alias':'name'}).iter_rows(named=True):
		rows.append({**row, 'primary_name': False})

	name_rows = []
	loc_rows = []
	for row in rows:
		raw_name = row.get('name')
		if raw_name is None or ',' in raw_name:
			continue
		parts = re.split(r' [io] ', raw_name)
		clean_name = re.sub(r'\([^()]*\)', '', parts[0])
		clean_name = ' '.join(clean_name.split())
		name_rows.append({'person_id': row['person_id'], 'name': clean_name, 'primary_name': row['primary_name']})
		for loc in parts[1:]:
			loc = loc.replace('och', '').strip()
			if loc:
				loc_rows.append({'person_id': row['person_id'], 'location': loc})

	name = pl.DataFrame(name_rows).drop_nulls().unique().sort('primary_name', descending=True)
	name = name.unique(subset=['person_id', 'name', 'primary_name']).select(['person_id'] + sorted([col for col in name.columns if col != 'person_id']))
	loc = pl.DataFrame(loc_rows).drop_nulls().unique()
	loc = loc.select(['person_id'] + sorted([col for col in loc.columns if col != 'person_id'])).sort(['person_id', 'location'])
	name = name.sort(list(name.columns))
	return name, loc

def move_party_to_party_df(mp_df, party_df):
	mp_parties = mp_df.select(party_df.columns)
	mp_parties = mp_parties.filter(pl.col('party_id').is_not_null())

	mp_parties = mp_parties.sort(["person_id", "start"])
	party_df = pl.concat([mp_parties, party_df], how="diagonal")
	party_df = party_df.unique()

	mp_df_cols = [col for col in mp_df.columns if col not in ["party", "party_id"]]

	return mp_df.select(mp_df_cols), party_df

def elongate_external_ids(df):
	rows = []
	cols = ["person_id", "authority", "identifier"]
	df = df.rename({"wiki_id": "WiDaID"})
	authorities = [_ for _ in df.columns if _ != "person_id"]
	for r in df.iter_rows(named=True):
		swerik = r["person_id"]
		for a in authorities:
			if r[a] is not None:
				rows.append([swerik, a, r[a]])
	return pl.DataFrame(rows, schema=cols, orient="row")
