# git-revision-graph

Generate revision graph like TortoiseGit did for chosen branches

To install, use command `pip install git-revision-graph.

Use `python -m git_revision_graph --tags '.*' -o graph.svg` inside any git repository to generate a diagram which shows the major operation, e.g. such as this repo tags diagram.

![This repo](assets/images/graph.svg)

## Full help

Run `git-revision-graph --help` to check full help

```
usage: git-revision-graph [-h] [--version] [--patterh PATTERH [PATTERH ...]]
                          [--local LOCAL [LOCAL ...]]
                          [--remote REMOTE [REMOTE ...]]
                          [--tags TAGS [TAGS ...]] [--type {wildcard,regex}]
                          [--no-simplify] [--time TIME] [-v] [--output OUTPUT]
                          [repository]

Generate revision graph like TortoiseGit did for chosen branches

example:
    git-revision-graph -p "refs/tags/bugfix*" -r "release/v1.*" --time +20240612 | tred | dot -Tsvg -o graph.svg
        

positional arguments:
  repository            the repository path

options:
  -h, --help            show this help message and exit
  --version
  --patterh PATTERH [PATTERH ...], -p PATTERH [PATTERH ...]
                        refs regex pattern filter
  --local LOCAL [LOCAL ...], -l LOCAL [LOCAL ...]
                        like pattern applied on refs/heads
  --remote REMOTE [REMOTE ...], -r REMOTE [REMOTE ...]
                        like pattern applied on refs/remotes
  --tags TAGS [TAGS ...], -t TAGS [TAGS ...]
                        like pattern applied on refs/tags
  --type {wildcard,regex}
                        the pattern type
  --no-simplify         do not simplify the graph
  --time TIME           filter the date range of the commits, e.g. '--time
                        +20240612' for before the day, or '--time
                        240610,240616' for between the two days
  -v                    Increase logging verbosity (e.g., -v for INFO, -vv for
                        DEBUG)
  --output OUTPUT, -o OUTPUT
                        the output file path, default to be stdout

```
## More complex example

The complex [london-git example](example/london.py) shows the major structure of london subway system:

![LondonGit](example/london.subway.png)

# Reference

> The complex git network in example inspired from [london-git](https://github.com/quarbby/london-git)
