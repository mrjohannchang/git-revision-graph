#!/usr/bin/env python3
import sys
from pathlib import Path


def main(argv):
    print(Path(__file__))


if __name__ == "__main__":
    main(sys.argv[1:])
