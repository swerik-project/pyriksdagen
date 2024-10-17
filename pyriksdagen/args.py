"""
Dry Argparse helper.

"""
from datetime import datetime
from glob import glob
from pyriksdagen.utils import (
    get_data_location,
    protocol_iterators,
)
import argparse
import inspect
import sys





def not_implemented(_name):
    raise NotImplementedError(f"The function {_name} hasn't been implemented yet")


def record_parser(parser):
    """
    Take an argparse ArgumentParser object and populate standard arguments for working with riksdagen records;
    args:
        parser: parser
    returns:
        parser
    """
    parser.add_argument("-s", "--start",
                        type=int,
                        default=None,
                        help="start year. If -s is set, -e must also be set. If -s and -e are explicitly set, all protocols in that range are processed. If -s and -e are unset and neither -p nor -l are set, the script will process all records from 1867 until the current year.")
    parser.add_argument("-e", "--end",
                        type=int,
                        default=None,
                        help="end year. If -e is set, -s must also be set. If -s and -e are explicitly set, all protocols in that range are processed. If -s and -e are unset and neither -p nor -l are set, the script will process all records from 1867 until the current year.")
    parser.add_argument("-y", "--parliament-year",
                        type=int,
                        default=None,
                        nargs='*',
                        help="Parliament year, e.g. 1971 or 198384")
    parser.add_argument("-R", "--records-folder",
                        type=str,
                        default=None,
                        help="(optional) Path to records folder, defaults to environment var or `data/`")
    parser.add_argument("-r", "--records",
                        type=str,
                        default=None,
                        nargs='*',
                        help="operate on a single record or list of records. Set the path from ./ -- this option doesn't cooperate with `-R`. -r takes presidence over -l.")
    parser.add_argument("-l", "--from-list",
                        type=str,
                        default=None,
                        help="operate on a list of records from a file. Set the path from ./ -- this option doesn't cooperate with `-R`.")
    return parser




def record_args(args):
    """
    takes an argparse namespace object for working with riksdagen records and imputes standard stuff
    args:
        args: args
    returns:
        args
    """
    def _iterate_protocols(s, e, data_location):
        records = sorted(list(protocol_iterators(data_location, start=s, end=e)))
        return records

    if (args.start is None or args.end is None) and args.start != args.end:
        raise ValueError("Set -s and -e or neither.")

    if args.records_folder is None:
        args.records_folder = get_data_location("records")

    if args.start is not None:
        args.records = _iterate_protocols(args.start, args.end, args.records_folder)
        print(args.records)
    else:
        if args.records is not None and len(args.records) != 0:
            pass
        elif args.from_list is not None:
            with open(args.from_list, 'r') as inf:
                lines = inf.readlines()
                args.protocol = [_.strip() for _ in lines if _.strip() != '']
        elif args.parliament_year is not None and len(args.parliament_year) != 0:
            args.records = []
            for py in args.parliament_year:
                args.records.extend(glob(f"{args.records_folder}/{py}/*.xml"))
        else:
            args.records = _iterate_protocols(1867, int(datetime.now().strftime('%Y')), args.records_folder)

    if args.records is not None and len(args.records) != 0:
        args.records = sorted(args.records)
    return args




def motion_parser(parser):
    not_implemented(inspect.currentframe().f_code.co_name)
    return parser




def interpellation_parser(parser):
    not_implemented(inspect.currentframe().f_code.co_name)
    return parser




def motion_args(args):
    not_implemented(inspect.currentframe().f_code.co_name)
    return args




def interpellation_args(args):
    not_implemented(inspect.currentframe().f_code.co_name)
    return args




def fetch_parser(doctype, docstring=None):
    """
    Fetch an argparse argument parser based on the doctype.
    args:
        doctype (str): doctype, one listed in D
        docstring (str): string describing scripts for which the parser is called.
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
    args:
        args: argparse parsed args namespace
    returns:
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
    args = fetch_parser("records").parse_args()
    print(impute_args(args))
