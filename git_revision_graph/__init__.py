from typing import Iterable, List

import argparse
import fnmatch
import json
import logging
import re
import subprocess
import sys
from collections import namedtuple
from importlib import metadata as importlib_metadata
from pathlib import Path

import graphviz

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def split_by_wildcard_pattern(strings: Iterable[str], patterns: List[str]):
    if len(patterns) == 0:
        return set(), strings
    match_set = set()
    no_match_set = set()

    for s in strings:
        if any(fnmatch.fnmatch(s, p) for p in patterns):
            match_set.add(s)
        else:
            no_match_set.add(s)
    return match_set, no_match_set


def split_by_regex_pattern(strings: Iterable[str], patterns: List[str]):
    if len(patterns) == 0:
        return set(), strings

    match_set = set()
    no_match_set = set()

    re_pts = [re.compile(p) for p in patterns]

    for s in strings:
        if any(p.search(s) for p in re_pts):
            match_set.add(s)
        else:
            no_match_set.add(s)

    return match_set, no_match_set


def get_version() -> str:
    try:
        return importlib_metadata.version(__name__)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "unknown"


version: str = get_version()

RefFilters = namedtuple("RefFilters", ["ref", "local", "remote", "tag"])
GIT_PATH = "git"


class Repo:
    def __init__(self, path: Path = Path(".")):
        self.path = path

    def filter_refs(
        self,
        ref_filters: RefFilters,
        use_regex: bool = True,
    ):
        with subprocess.Popen(
            [GIT_PATH, "--no-pager", "for-each-ref", "--format=%(refname)"],
            cwd=self.path,
            stdout=subprocess.PIPE,
        ) as proc:
            assert proc.stdout is not None
            refs = {i.decode().strip() for i in proc.stdout}

        match_func = split_by_regex_pattern if use_regex else split_by_wildcard_pattern

        matched_refs, refs = match_func(refs, ref_filters.ref)
        matched_refs = {s.split("/", maxsplit=2)[-1] for s in matched_refs}
        refs = {s.split("/", maxsplit=1)[-1] for s in refs}

        for patterns, prefix in zip(ref_filters[1:], ("heads/", "remotes/", "tags/")):
            matched_refs |= match_func(
                (s[len(prefix) :] for s in refs if s.startswith(prefix)), patterns
            )[0]

        return list(matched_refs)

    def history(self, refs: List[str], simplify: bool = True):
        git_command = [
            GIT_PATH,
            "--no-pager",
            "log",
            (
                "--pretty=format:"
                '{ "id": "%H", "author": "%an", "email": "%ae", "date": "%ad", "message": "%f", "parent": "%P", "ref": "%D" }'
            ),
            "--date=iso",
        ]
        if simplify:
            git_command.append("--simplify-by-decoration")

        with subprocess.Popen(
            git_command + refs, cwd=self.path, stdout=subprocess.PIPE
        ) as proc:
            assert proc.stdout is not None
            return [json.loads(i.decode()) for i in proc.stdout]


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Generate revision graph like TortoiseGit did for chosen branches"
    )
    parser.add_argument("--version", action="store_true")

    parser.add_argument(
        "repository", type=str, nargs="?", default=".", help="the repository path"
    )

    parser.add_argument(
        "--patterh",
        "-p",
        type=str,
        nargs="+",
        default=[],
        help="refs regex pattern filter",
    )
    parser.add_argument(
        "--local",
        "-l",
        type=str,
        nargs="+",
        default=[],
        help="like pattern applied on refs/heads",
    )
    parser.add_argument(
        "--remote",
        "-r",
        type=str,
        nargs="+",
        default=[],
        help="like pattern applied on refs/remotes",
    )
    parser.add_argument(
        "--tags",
        "-t",
        type=str,
        nargs="+",
        default=[],
        help="like pattern applied on refs/tags",
    )

    parser.add_argument(
        "--type",
        choices=["wildcard", "regex"],
        default="regex",
        help="the pattern type",
    )

    parser.add_argument(
        "--output",
        "-o",
        default="-",
        help="the output file path, default to be stdout",
    )

    args = parser.parse_args(argv)

    return args


def generate_dot_script(path: Path, ref_filters: RefFilters, pattern_type: str):
    repo = Repo(path)
    refs = repo.filter_refs(
        ref_filters,
        use_regex=pattern_type == "regex",
    )
    logger.debug("filtered refs: " + json.dumps(refs, indent=2))
    logs = repo.history(refs)
    logger.debug("history json: " + json.dumps(logs, indent=2))

    dot = graphviz.Digraph(comment="Git")
    for commit in logs:
        dot.node(commit["id"], commit["message"])
        if commit["parent"] != "":
            for parent in commit["parent"].split(" "):
                dot.edge(parent, commit["id"])

    return dot.source


def create_dot_source(argv):
    args = parse_args(argv)

    if args.version:
        print(version)
        return

    ref_filters = RefFilters(args.patterh, args.local, args.remote, args.tags)
    if all(len(i) == 0 for i in ref_filters):
        ref_filters = RefFilters([], [".*"], [], [])

    dot_source = generate_dot_script(Path(args.repository), ref_filters, args.type)
    logger.debug(dot_source)

    if args.output == "-":
        print(dot_source)
    else:
        Path(args.output).write_text(dot_source)


if __name__ == "__main__":
    create_dot_source(sys.argv[1:])
