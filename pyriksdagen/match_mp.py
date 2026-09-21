import numpy as np
import polars as pl
import re
import textdistance
from unidecode import unidecode
from nltk.metrics.distance import edit_distance
from trainerlog import get_logger
LOGGER = get_logger("match_mp")

def multiple_replace(text, i_start=192, i_end=383):
	d = [chr(c) for c in range(i_start, i_end+1)]
	d = {c:unidecode(c) for c in d if c not in 'åäöÅÄÖ'}
	regex = re.compile("(%s)" % "|".join(map(re.escape, d.keys())))
	return regex.sub(lambda mo: d[mo.string[mo.start():mo.end()]], text) 

def clean_names(names):
	if type(names) == str:
		names = names.replace(',','') # Allard, Henry --> Allard Henry
		names = names.replace('.','') # A.C. Lindblad --> AC Lindblad
		names = names.replace('-',' ') # Carl-Eric Lindblad --> Carl Eric Lindblad
		names = names.lower()
	else:
		names = names.str.replace_all(',','') # Allard, Henry --> Allard Henry
		names = names.str.replace_all('.','', literal=True) # A.C. Lindblad --> AC Lindblad
		names = names.str.replace_all('-',' ', literal=True) # Carl-Eric Lindblad --> Carl Eric Lindblad
		names = names.str.to_lowercase()
	return names

def name_equals(name, db):
	matches = db.filter(pl.col("name") == name)
	return matches

def name_almost_equals(name, db):
	def _rough_equality(s1, s2):
		perfect_matches = 0
		s1, s2 = s1.replace(".", ""), s2.replace(".", "")
		l1 = s1.split()
		l2 = s2.split()
		if len(l1) != len(l2):
			return False
		for w1, w2 in zip(l1, l2):
			shorter_len = min(len(w1), len(w2))
			w1, w2 = w1.lower(), w2.lower()
			if w1 == w2:
				perfect_matches += 1
			if edit_distance(w1, w2) <= 1:
				if w1[0] == w2[0]:
					perfect_matches += 1
			elif w1[:shorter_len] != w2[:shorter_len]:
				return False
		return perfect_matches >= 1

	matches = db.filter(pl.col("name").map_elements(lambda x: _rough_equality(name, x), return_dtype=pl.Boolean))
	return matches

def names_in(name, db):
	names = name.split()
	matches = db.filter(pl.col("name").map_elements(
		lambda x: len([n for n in names if n in x.split()]) == len(names),
		return_dtype=pl.Boolean,
	))
	return matches

def names_in_rev(name, db):
	names = name.split()
	matches = db.filter(pl.col("name").map_elements(
		lambda x: len([n for n in x.split() if n in names]) == len(x.split()),
		return_dtype=pl.Boolean,
	))
	return matches

def fuzzy_name(name, db):
	d = textdistance.levenshtein
	matches = db.filter(pl.col("name").map_elements(lambda x: d(name, x) == 1, return_dtype=pl.Boolean))
	return matches

### Depreceated functions below
# NEW functions to replace both in_name, subnames_in_mpname, and mpsubnames_in_name
def subnames_in_mpname(name, db):
	if debug:
		print(name, len(name))
	indices = [i for i,row in enumerate(db.iter_rows(named=True)) if
			   all(any(n == subname for n in row["name"].split())
			   for subname in name.split())]
	return db.with_row_index().filter(pl.col("index").is_in(indices)).drop("index")

def mpsubnames_in_name(name, db):
	if debug:
		print(name, len(name))
	indices = [i for i,row in enumerate(db.iter_rows(named=True)) if
			   all(any(n == subname for n in name.split())
			   for subname in row["name"].split())]
	return db.with_row_index().filter(pl.col("index").is_in(indices)).drop("index")

def firstname_lastname(name, db):
	if debug:
		print(name, len(name))
	if len(subnames := name.split()) <= 1: return []
	indices = [i for i,row in enumerate(db.iter_rows(named=True)) \
	if subnames[0] == row["name"].split()[0] and subnames[-1] == row["name"].split()[-1]]
	return db.with_row_index().filter(pl.col("index").is_in(indices)).drop("index")

def firstname_lastname_reversed(name, db):
	if debug:
		print(name, len(name))
	if len(subnames := name.split()) <= 1: return []
	indices = [i for i,row in enumerate(db.iter_rows(named=True)) \
	if subnames[0] == row["name"].split()[-1] and subnames[-1] == row["name"].split()[0]]
	return db.with_row_index().filter(pl.col("index").is_in(indices)).drop("index")

def two_lastnames(name, db):
	if debug:
		print(name, len(name))
	if len(subnames := name.split()) <= 1: return []
	indices = [i for i,row in enumerate(db.iter_rows(named=True)) \
	if name.split()[-1] == row["name"].split()[-1] and name.split()[-2] == row["name"].split()[1:]]
	return db.with_row_index().filter(pl.col("index").is_in(indices)).drop("index")

def lastname(name, db):
	if debug:
		print(name, len(name))
	return db.filter(pl.col("name").str.split(" ").list.last() == name)

def match_mp(person, db, variables, matching_funs):
	"""
	Pseudocode:
	- inputs:
		- person with cleaned name and party_abbrev
		- db with cleaned name and filtered by chamber for efficiency
		- variables list of lists with variable combinations to match by
		- matching_funs list of functions to match/filter names by
	- check if it is a talman/minister and use other matching function if true
	- filter db by gender if persons gender is available
	- use matching_funs in combination with variables until a unique match is found
	- if there at any step is a match, return the persons db id

	"""
	p = person.copy() # avoids spooky behaviour
	p["name"] = clean_names(p.get("name", ""))
	for key in ["name", "party_abbrev", "specifier"]:
		if key not in p:
			p[key] = ""
	p = {key: str(value) for key, value in p.items()}

	# statskalender file currently lacks gender
	if 'gender' in p:
		db = db.filter(pl.col("gender") == p["gender"])

	for fun in matching_funs:
		matched_mps = fun(p["name"], db)
		
		if len(matched_mps) == 0:
			if fun == matching_funs[-1]:
				LOGGER.debug("Intro not matched after all functions")
				return
			continue # restart if no match was found
		
		number_of_matches = len(set(matched_mps["id"]))
		if number_of_matches == 1:
			matched_value = matched_mps["id"][0]
			LOGGER.debug(f"Match found with {fun}: {matched_value}")
			return matched_value
		elif number_of_matches >= 2:
			LOGGER.debug(f"Multiple matches obtained with {fun}")

		# Iterates over combinations of variables to find a unique match
		for v in variables:
			
			expr = pl.all_horizontal([pl.col(col) == p[col] for col in v])
			matched_mps_new = matched_mps.filter(expr)

			number_of_matches = len(set(matched_mps_new["id"]))
			if number_of_matches == 1:
				matched_value = matched_mps_new["id"][0]
				LOGGER.debug(f"Match found with {v}: {matched_value}")
				return matched_value
			elif number_of_matches >= 2:
				LOGGER.debug(f"Multiple matches obtained with {v}")
			
