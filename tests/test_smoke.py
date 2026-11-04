"""Smoke test.

Deliberately trivial: it proves the package installs, imports and runs under CI before any real
code exists.
"""

import motrisk


def test_package_imports_and_reports_a_version() -> None:
    assert isinstance(motrisk.__version__, str)
    assert motrisk.__version__
