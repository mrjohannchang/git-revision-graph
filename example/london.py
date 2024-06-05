#!/usr/bin/env python3

import subprocess
from pathlib import Path
import json

def create_git_repo(git_repo_path: Path):
    git_repo_path.mkdir(exist_ok=True)

    if (git_repo_path/".git").exists():
        return

    subprocess.run("curl -s https://raw.githubusercontent.com/quarbby/london-git/master/london.sh > london.sh; bash < london.sh", shell=True, cwd=git_repo_path)

def export_git_history(git_repo_path: Path):
    with subprocess.Popen("git --no-pager branch --all", shell=True, cwd=git_repo_path, stdout=subprocess.PIPE) as proc:
        branches = " ".join(i.decode().strip("* \n") for i in proc.stdout)

    git_command = (
        'git --no-pager log --pretty=format:\''
        '{ "commit": "%H", "author": "%an", "email": "%ae", "date": "%ad", "message": "%f", "parent": "%P", "ref": "%D" }'
        '\' --date=iso --simplify-by-decoration '
        ) + branches

    with subprocess.Popen(git_command, shell=True, cwd=git_repo_path, stdout=subprocess.PIPE) as proc:
        logs = [json.loads(i.decode()) for i in proc.stdout]

    print(json.dumps(logs, indent=2))


if __name__ == "__main__":
    git_repo_path = Path(__file__).parent/"london"
    create_git_repo(git_repo_path)
    export_git_history(git_repo_path)
