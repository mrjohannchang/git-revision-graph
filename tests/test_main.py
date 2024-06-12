import argparse
from datetime import datetime

import pytest

from git_revision_graph import DateRangeAction, create_dot_source


@pytest.mark.parametrize(("argv",), [(["--version"],)])
def test_main(argv):
    create_dot_source(argv)


@pytest.mark.parametrize(
    ("arg", "target"),
    [
        ([], (None, None)),
        ("--time 20240612", (datetime(2024, 6, 12), None)),
        ("--time +240612", (None, datetime(2024, 6, 12))),
        ("--time 24-06-10,240612", (datetime(2024, 6, 10), datetime(2024, 6, 12))),
    ],
)
def test_date_range(arg, target):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--time",
        action=DateRangeAction,
        default=(None, None),
    )

    t1, t2 = parser.parse_args(arg.split(" ") if arg else arg).time
    begin, end = target
    assert begin == t1
    assert end == t2
