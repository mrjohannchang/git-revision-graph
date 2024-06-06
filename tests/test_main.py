import pytest

from git_revision_graph import create_dot_source


@pytest.mark.parametrize(("argv",), [(["--version"],)])
def test_main(argv):
    create_dot_source(argv)
