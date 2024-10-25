"""
Dry Argparse helper.

"""
from datetime import datetime
from glob import glob
from pyriksdagen.utils import (
    get_data_location,
    protocol_iterators,
    corpus_iterator,
)
import argparse
import inspect
import sys




def populate_common_arguments(parser):
    """
    add arguments common to all doctypes to a parser object
        - start
        - end
        - year
        - from-list
        - specific-files
        - data-folder
    Args:
        parser: argparse Parser

    Returns:
        parser: argparse Parser
    """
    parser.add_argument("-s", "--start",
                        type=int,
                        default=None,
                        help="start year. If -s is set, -e must also be set. If -s and -e are explicitly set, all protocols in that range are processed. If -s and -e are unset and neither -p nor -l are set, the script will process all records from 1867 until the current year. Priority == 4")
    parser.add_argument("-e", "--end",
                        type=int,
                        default=None,
                        help="end year. If -e is set, -s must also be set. If -s and -e are explicitly set, all protocols in that range are processed. If -s and -e are unset and neither -p nor -l are set, the script will process all records from 1867 until the current year. Priority == 4")
    parser.add_argument("-y", "--parliament-year",
                        type=int,
                        default=None,
                        nargs='*',
                        help="Parliament year, e.g. 1971 or 198384. Priority == 3")
    parser.add_argument("-l", "--from-list",
                        type=str,
                        default=None,
                        help="operate on a list of records from a file. Set the path from ./ -- this option doesn't cooperate with `-R`. Priority == 2")
    parser.add_argument("-f", "--specific-files",
                        type=str,
                        default=None,
                        nargs='*',
                        help="operate on a specific file or list of files. Set the path from ./ -- this option doesn't cooperate with `-R`. User is responsible to ensure the file is the correct doctype. Priority == 1")
    parser.add_argument("-L", "--data-folder",
                        type=str,
                        default=None,
                        help="(optional) Path to folder containing the data, defaults to environment variable according to the document type or `data/` if no suitable variable is found.")
    return parser




def rename_file_list(args):
    """
    Renames the specific_files arg to a doctype-relevant name

    Args:
        args: argparse Namespace
        doctype (str): document type

    Returns:
        args
    """
    d = vars(args)
    d[d["doctype"]] = d.pop("specific_files")
    return argparse.Namespace(**d)




def common_args(args):
    """
    common preprocessing of arguments

    Args:
        args: argparse Argument namespace

    Returns:
        args
    """
    if (args.start is None or args.end is None) and args.start != args.end:
        raise ValueError("Set -s and -e or neither.")

    if args.data_folder is None:
        args.data_folder = get_data_location(args.doctype)

    if args.specific_files is not None and len(args.specific_files) != 0:
        pass
    elif args.from_list is not None:
        with open(args.from_list, 'r') as inf:
            lines = inf.readlines()
            args.specific_files = [_.strip() for _ in lines if _.strip() != '']
    elif args.parliament_year is not None and len(args.parliament_year) != 0:
        args.specific_files = []
        for py in args.parliament_year:
            args.specific_files.extend(glob(f"{args.data_folder}/{py}/*.xml"))
    else:
        args.specific_files = sorted(list(corpus_iterator(args.doctype, start=args.start, end=args.end)))
    if args.specific_files is not None and len(list(args.specific_files)) != 0:
        args.specific_files = sorted(list(args.specific_files))
    return rename_file_list(args)




def record_parser(parser):
    """
    Take an argparse ArgumentParser object and populate standard arguments for working with riksdagen records.

    Args:
        parser: parser

    Returns:
        parser
    """
    parser = populate_common_arguments(parser)
    # leaving the records-specific function in place, in case we need records-specific args
    return parser




def record_args(args):
    """
    Takes an argparse namespace object for working with riksdagen records and imputes standard stuff

    Args:
        args: args

    Returns:
        args
    """
    args = common_args(args)
    # leaving the records-specific function in place, in case we need records-specific actions
    return args




def motion_parser(parser):
    """
    Take an argparse ArgumentParser object and populate standard arguments for working with riksdagen motions.

    Args:
        parser: parser

    Returns:
        parser
    """
    parser = populate_common_arguments(parser)
    # leaving the motions-specific function in place, in case we need motions-specific args
    return parser




def motion_args(args):
    """
    Takes an argparse namespace object for working with riksdagen records and imputes standard stuff

    Args:
        args: args
    Returns:
        args
    """
    args = common_args(args)
    # leaving the records-specific function in place, in case we need records-specific actions
    return args




def interpellation_parser(parser):
    """
    Take an argparse ArgumentParser object and populate standard arguments for working with riksdagen interpellations.

    Args:
        parser: parser

    Returns:
        parser
    """
    parser = populate_common_arguments(parser)
    # leaving the interpellations-specific function in place, in case we need interpellations-specific args
    return parser




def interpellation_args(args):
    """
    Takes an argparse namespace object for working with riksdagen interpellations and imputes standard stuff

    Args:
        args: args

    Returns:
        args
    """
    args = common_args(args)
    # leaving the interpellations-specific function in place, in case we need interpellations-specific actions
    return args




def fetch_parser(doctype, docstring=None):
    """
    Fetch an argparse argument parser based on the doctype.

    Args:
        doctype (str): doctype, one listed in D
        docstring (str): string describing scripts for which the parser is called.

    Returns:
        argparse Parser object
    """
    D = {
            "records": record_parser,
            "motions": motion_parser,
            "interpellations": interpellation_parser,
        }
    parser = argparse.ArgumentParser(description=docstring)
    parser.add_argument("--doctype", default=doctype, help=argparse.SUPPRESS)
    return D[doctype](parser)




def impute_args(args):
    """
    Impute args based on the doctype (args.doctype).

    Args:
        args: argparse parsed args namespace

    Returns:
        argparse parsed args namespace
    """
    D = {
            "records": record_args,
            "motions": motion_args,
            "interpellations": interpellation_args,
        }
    return D[args.doctype](args)




# test
if __name__ == '__main__':
    args = fetch_parser("motions").parse_args()
    print(impute_args(args))
