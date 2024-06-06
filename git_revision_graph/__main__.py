#!/usr/bin/env python3
import sys

from git_revision_graph import create_dot_source


def main():
    create_dot_source(sys.argv[1:])


if __name__ == "__main__":
    main()
