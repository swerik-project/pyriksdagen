#!/usr/bin/env python3
"""
Bump the release number according to the release type.
"""
import argparse
import re

def main(args):

    maj, min, patch = args.version.replace("v", "").split('.')
    args.type = args.type.lower()
    if args.type == "major":
        maj = int(maj) + 1
        min = 0
        patch = 0
    elif args.type == "minor":
        min = int(min) + 1
        patch = 0
    elif args.type == "patch":
        if patch.endswith("b"):
            patch = int(patch.replace("b", ""))
        elif patch.endswith("rc"):
            patch = int(patch.replace("rc", ""))
        else:
            patch = int(patch) + 1

    print(f"v{maj}.{min}.{patch}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", type=str, required=True, choices=["major", "minor", "patch"])
    parser.add_argument("--version", type=str, required=True)
    args = parser.parse_args()
    exp = re.compile(r"v([0-9]+)([.])([0-9]+)([.])([0-9]+)(b|rc)?([0-9]+)?")
    s = exp.search(args.version)
    if s is None:
        ValueError(f"{args.version} is not a valid version number. Exiting")
    args.version = s.group(0)
    main(args)
