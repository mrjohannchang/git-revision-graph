from typing import Dict, Iterable, List, Optional, Tuple

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
from itertools import chain, zip_longest
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


class DateRangeAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            start, *end = values.split(",")
            if len(end) == 0:
                if start.startswith("+"):
                    start, end = None, start[1:]
                else:
                    end = None
            elif len(end) == 1:
                (end,) = end
            else:
                raise ValueError()

            date_parser = lambda s: (
                datetime.strptime(
                    s,
                    next(
                        (
                            v
                            for k, v in {
                                r"^\d{8}$": "%Y%m%d",
                                r"^\d{6}$": "%y%m%d",
                                r"^\d{4}-\d{2}-\d{2}$": "%Y-%m-%d",
                                r"^\d{2}-\d{2}-\d{2}$": "%y-%m-%d",
                            }.items()
                            if re.match(k, s)
                        ),
                        "",
                    ),
                )
                if s is not None
                else None
            )

            namespace.time = date_parser(start), date_parser(end)
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid date range format: {values}")


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
        return {r[len("refs/tags/") :] for r in self.refs if r.startswith("refs/tags/")}

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

        def parse_commit_info(line: str):
            commit = json.loads(line)
            commit["parent"] = commit["parent"].split(" ")
            if commit["ref"] != "":
                commit["ref"] = [
                    r.split("->")[-1].strip() for r in commit["ref"].split(", ")
                ]
            else:
                commit["ref"] = [f"id: {commit['id'][:8]}"]
            return commit

        with subprocess.Popen(
            git_command + refs, cwd=self.path, stdout=subprocess.PIPE
        ) as proc:
            assert proc.stdout is not None
            return [parse_commit_info(l.decode()) for l in proc.stdout]


def filter_history(logs, refs: List[str]):
    logger.debug("history json before filter: " + json.dumps(logs, indent=2))
    CommitNode = namedtuple("CommitNode", ["successors", "parents", "refs"])

    # scan the commits to build the network
    all_commit_ids = [commit["id"] for commit in logs]
    all_commit_ids.append("")
    network: Dict[str, CommitNode] = {
        commit["id"]: CommitNode(
            successors=[],
            parents=[p for p in commit["parent"] if p in all_commit_ids],
            refs=[
                r
                for r in commit["ref"]
                if (r[len("tag: ") :] if r.startswith("tag: ") else r) in refs
            ],
        )
        for commit in logs
    }
    network[""] = CommitNode(
        successors=[],
        parents=[],
        refs=[],
    )

    for commit_id, node in network.items():
        for p in node.parents:
            network[p].successors.append(commit_id)

    # filter the refs for each commit to mark those can be removed in the graph
    for commit_id, node in network.items():
        # for those merge commits or last commits, ignore the filter rule
        # for the init commits, give it a default tag
        if len(node.successors) != 1 or len(node.parents) != 1 and not node.refs:
            # just one ref will be given with priority: tag/other ref/commit id
            all_refs: List[str] = next(
                (commit["ref"] for commit in logs if commit["id"] == commit_id), []
            )
            default_ref_type = "init" if len(node.parents) == 0 else "id"
            node.refs.append(
                next(
                    chain.from_iterable(
                        (
                            (r for r in all_refs if r.startswith("tag: ")),
                            (r for r in all_refs if not r.startswith("tag: ")),
                        )
                    ),
                    f"{default_ref_type}: {commit_id[:8]}",
                )
            )

    logs = [commit for commit in logs if network[commit["id"]].refs]
    for commit in logs:
        node = network[commit["id"]]
        if node.parents[0] == "":
            commit["parent"] = [""]
            commit["ref"] = list(set(node.refs))
            continue

        parents = [p for p in node.parents]
        for p in range(len(parents)):
            parent_id = node.parents[p]
            while True:
                if network[parent_id].refs:
                    # it will always exit because we have guard on the init commits
                    break
                else:
                    # the to be removed node must have only one parent
                    parent_id = network[parent_id].parents[0]
            parents[p] = parent_id
        commit["parent"] = list(set(parents))
        commit["ref"] = list(set(node.refs))
    logger.debug("history json after filter: " + json.dumps(logs, indent=2))
    return logs


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="""
Generate revision graph like TortoiseGit did for chosen branches

example:
    git-revision-graph -p "refs/tags/bugfix*" -r "release/v1.*" --time +20240612 | tred | dot -Tsvg -o graph.svg
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "--no-simplify",
        action="store_true",
        dest="no_simplify",
        help="do not simplify the graph",
    )

    parser.add_argument(
        "--time",
        action=DateRangeAction,
        default=(None, None),
        help="filter the date range of the commits, e.g. '--time +20240612' for before the day, or  '--time 240610,240616' for between the two days",
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


def generate_dot_script(
    path: Path,
    ref_filters: RefFilters,
    pattern_type: str,
    date_range: Tuple[Optional[datetime], Optional[datetime]],
    simplify: bool = True,
):
    repo = Repo(path)
    refs = repo.filter_refs(
        ref_filters,
        use_regex=pattern_type == "regex",
    )
    logger.info("filtered refs: " + json.dumps(refs, indent=2))

    logs = repo.history(refs)
    log_size = len(logs)
    logger.info(f"history size: {log_size}")
    while simplify:
        logs = filter_history(logs, refs)
        if len(logs) < log_size:
            log_size = len(logs)
            logger.info(f"history size decresed to {log_size}")
        else:
            break
    logger.info("history json: " + json.dumps(logs, indent=2))

    date_begin, date_end = date_range

    dot = graphviz.Digraph(comment="Git")
    for commit in logs:
        date = datetime.fromtimestamp(int(commit["date"]))
        if (date_begin is not None and date < date_begin) or (
            date_end is not None and date > date_end
        ):
            continue

        refs_html = []
        remote_branches = set()
        local_branches = set()
        for r in commit["ref"]:
            if r.startswith("tag: "):
                refs_html.append(f'<TD BGCOLOR="lightgrey">{r[len("tag: "):]}</TD>')
            elif r.startswith("id: "):
                refs_html.append(
                    f'<TD><font color="grey">{r[len("id: "):]}</font></TD>'
                )
            elif r in repo.remote_branches:
                remote_branches.add(r)
            else:
                local_branches.add(r)

        for r in remote_branches:
            local_r = r.split("/", maxsplit=1)[-1]
            if local_r in local_branches:
                refs_html.append(f"<TD><B>{r}</B></TD>")
                local_branches.remove(local_r)
            else:
                refs_html.append(f"<TD>{r}</TD>")

        for r in local_branches:
            refs_html.append(f'<TD><font color="lightblue">{r}</font></TD>')

        table_html = "</TR><TR>".join(
            f"{l}{r}"
            for l, r in zip_longest(refs_html[::2], refs_html[1::2], fillvalue="")
        )

        message = f"""<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">
            <TR>
                <TD BGCOLOR="lightgreen"><B>{date.strftime("%y/%m/%d")}</B></TD>
                <TD BGCOLOR="lightblue"><B>{commit["author"]}</B></TD>
            </TR>
            <TR>{table_html}</TR>
        </TABLE>>"""
        dot.node(commit["id"], message)
        if commit["parent"] and commit["parent"][0] != "":
            for parent in commit["parent"]:
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

    dot_source = generate_dot_script(
        Path(args.repository),
        ref_filters,
        args.type,
        args.time,
        not args.no_simplify,
    )
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
