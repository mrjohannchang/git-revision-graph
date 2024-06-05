import pytest

from git_revision_graph.__main__ import main


@pytest.mark.parametrize(("argv",), [(["--help"],)])
def test_main(argv):
    main(argv)
