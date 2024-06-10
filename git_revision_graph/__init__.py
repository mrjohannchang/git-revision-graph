from typing import Iterable, List

import argparse
import fnmatch
import json
import logging
import re
import subprocess
import sys
from collections import namedtuple
from datetime import datetime
from functools import cached_property
from importlib import metadata as importlib_metadata
from pathlib import Path

import graphviz

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.WARNING,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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

    @cached_property
    def refs(self):
        with subprocess.Popen(
            [GIT_PATH, "--no-pager", "for-each-ref", "--format=%(refname)"],
            cwd=self.path,
            stdout=subprocess.PIPE,
        ) as proc:
            assert proc.stdout is not None
            return {i.decode().strip() for i in proc.stdout}

    @cached_property
    def local_branches(self):
        return {
            r[len("refs/heads/") :] for r in self.refs if r.startswith("refs/heads/")
        }

    @cached_property
    def remote_branches(self):
        return {
            r[len("refs/remotes/") :]
            for r in self.refs
            if r.startswith("refs/remotes/")
        }

    @cached_property
    def tags(self):
        return {
            r[len("refs/tags/") :] for r in self.refs if r.startswith("refs/tagss/")
        }

    def filter_refs(
        self,
        ref_filters: RefFilters,
        use_regex: bool = True,
    ):
        def split_by_wildcard_pattern(strings: Iterable[str], patterns: List[str]):
            return {s for s in strings if any(fnmatch.fnmatch(s, p) for p in patterns)}

        def split_by_regex_pattern(strings: Iterable[str], patterns: List[str]):
            re_pts = [re.compile(p) for p in patterns]
            return {s for s in strings if any(p.search(s) for p in re_pts)}

        match_func = split_by_regex_pattern if use_regex else split_by_wildcard_pattern

        matched_refs = {
            s.split("/", maxsplit=2)[-1] for s in match_func(self.refs, ref_filters.ref)
        }
        for patterns, candidates in zip(
            ref_filters[1:], (self.local_branches, self.remote_branches, self.tags)
        ):
            matched_refs |= match_func(candidates, patterns)

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
            "--date=unix",
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
        "-v",
        dest="verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (e.g., -v for INFO, -vv for DEBUG)",
    )

    parser.add_argument(
        "--output",
        "-o",
        default="-",
        help="the output file path, default to be stdout",
    )

    args = parser.parse_args(argv)
    logger.setLevel(
        {
            0: logging.WARNING,
            1: logging.INFO,
        }.get(args.verbose, logging.DEBUG)
    )

    return args


def generate_dot_script(path: Path, ref_filters: RefFilters, pattern_type: str):
    repo = Repo(path)
    refs = repo.filter_refs(
        ref_filters,
        use_regex=pattern_type == "regex",
    )
    logger.info("filtered refs: " + json.dumps(refs, indent=2))
    logs = repo.history(refs)
    logger.info("history json: " + json.dumps(logs, indent=2))

    dot = graphviz.Digraph(comment="Git")
    for commit in logs:
        if commit["ref"] == "":
            refs = [commit["id"][:8]]
        else:
            refs = [r.split("->")[-1].strip() for r in commit["ref"].split(",")]
        date = datetime.fromtimestamp(int(commit["date"])).strftime("%y/%m/%d")
        message = f"""<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">
            <TR>
                <TD BGCOLOR="lightgreen"><B>{date}</B></TD>
                <TD BGCOLOR="lightblue"> <B>{commit["author"]}</B></TD>
            </TR>
            <TR>
                <TD>{"</TD><TD>".join(refs)}</TD>
            </TR>
        </TABLE>>"""
        dot.node(commit["id"], message)
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
    elif args.output.endswith(".dot"):
        Path(args.output).write_text(dot_source)
    elif args.output.endswith(".svg"):
        subprocess.run(["dot", "-Tsvg", "-o", args.output], input=dot_source.encode())
    else:
        logger.warning("not supported output format for " + args.output)


if __name__ == "__main__":
    create_dot_source(sys.argv[1:])
