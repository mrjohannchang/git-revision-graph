#!/usr/bin/env python3

import json
import logging
import subprocess
from pathlib import Path

import graphviz

logging.basicConfig(level=logging.DEBUG)


def create_git_repo(git_repo_path: Path):
    git_repo_path.mkdir(exist_ok=True)

    if (git_repo_path / ".git").exists():
        return

    subprocess.run(
        "curl -s https://raw.githubusercontent.com/quarbby/london-git/master/london.sh > london.sh; sed 's#checkout --orphan#branch#g' london.sh | bash",
        shell=True,
        cwd=git_repo_path,
    )


def export_git_history(git_repo_path: Path):
    with subprocess.Popen(
        "git --no-pager branch --all",
        shell=True,
        cwd=git_repo_path,
        stdout=subprocess.PIPE,
    ) as proc:
        if proc.stdout is not None:
            branches = " ".join(
                i.decode().strip("* \n").split("->")[-1] for i in proc.stdout
            )

    git_command = (
        "git --no-pager log --pretty=format:'"
        '{ "id": "%H", "author": "%an", "email": "%ae", "date": "%ad", "message": "%f", "parent": "%P", "ref": "%D" }'
        "' --date=iso --simplify-by-decoration "
    ) + branches

    with subprocess.Popen(
        git_command, shell=True, cwd=git_repo_path, stdout=subprocess.PIPE
    ) as proc:
        if proc.stdout is not None:
            return [json.loads(i.decode()) for i in proc.stdout]


def convert_git_history(logs):
    logging.debug(json.dumps(logs, indent=2))

    dot = graphviz.Digraph(comment="Git")
    for commit in logs:
        dot.node(commit["id"], commit["message"])
        if commit["parent"] != "":
            for parent in commit["parent"].split(" "):
                dot.edge(parent, commit["id"])

    return dot.source


if __name__ == "__main__":
    git_repo_path = Path(__file__).parent / "london"
    create_git_repo(git_repo_path)
    logs = export_git_history(git_repo_path)
    dot_source = convert_git_history(logs)
    logging.debug(dot_source)
    with subprocess.Popen(
        "dot -Tsvg -o git-graph.svg",
        shell=True,
        cwd=Path(__file__).parent,
        stdin=subprocess.PIPE,
    ) as proc:
        proc.communicate(input=dot_source.encode())
