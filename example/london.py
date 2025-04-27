#!/usr/bin/env python3

import logging
import subprocess
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / ".."))

from git_revision_graph import create_dot_source

logging.basicConfig(level=logging.DEBUG)


def create_git_repo(git_repo_path: Path):
    git_repo_path.mkdir(exist_ok=True)

    if (git_repo_path / ".git").exists():
        return

    subprocess.run(
        "(curl -s https://raw.githubusercontent.com/quarbby/london-git/master/london.sh > london.sh) && (sed 's#checkout --orphan#branch#g' london.sh | bash)",
        shell=True,
        cwd=git_repo_path,
        check=True,
    )


if __name__ == "__main__":
    git_repo_path = Path(__file__).parent / "london"
    create_git_repo(git_repo_path)
    create_dot_source([str(git_repo_path), "-o", str(git_repo_path / "git-graph.dot")])
    subprocess.run(
        "dot -Tpng -o ../london.subway.png git-graph.dot",
        shell=True,
        cwd=git_repo_path,
        check=True,
    )
