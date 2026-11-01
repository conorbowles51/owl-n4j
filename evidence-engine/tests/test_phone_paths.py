"""Phone request paths, rules PA-1 to PA-6 (01 section 4.3)."""
import os

import pytest
from fastapi import HTTPException

from app.phone import paths


@pytest.fixture
def case(tmp_path):
    root = tmp_path / "case"
    (root / "Phone" / "Report").mkdir(parents=True)
    (root / "Phone.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    return tmp_path


def r(case, raw, expect=None):
    return paths.resolve("case", raw, expect=expect, root=case)


def test_pa1_backslashes_and_leading_slashes(case):
    assert r(case, "\\Phone\\Report")[0] == "Phone/Report"
    assert r(case, "//Phone/Report")[0] == "Phone/Report"


def test_pa2_empty_and_dot_are_the_case_root(case):
    assert r(case, "") == ("", (case / "case").resolve())
    assert r(case, ".") == ("", (case / "case").resolve())


@pytest.mark.parametrize("raw", ["Phone/../Phone", "Phone/./Report", "Phone//Report", "..", "../other"])
def test_pa3_dot_dot_and_empty_components(case, raw):
    with pytest.raises(HTTPException) as e:
        r(case, raw)
    assert (e.value.status_code, e.value.detail) == (403, "Path outside case directory")


def test_pa4_symbolic_link_out_of_the_case(case, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, case / "case" / "escape")
    with pytest.raises(HTTPException) as e:
        r(case, "escape")
    assert e.value.status_code == 403


def test_pa5_missing_path_is_named(case):
    with pytest.raises(HTTPException) as e:
        r(case, "Nope/x")
    assert e.value.status_code == 404 and "Nope/x" in e.value.detail


def test_pa6_file_and_folder_kinds(case):
    assert r(case, "Phone.zip", expect="file")[0] == "Phone.zip"
    assert r(case, "Phone", expect="dir")[0] == "Phone"
    for raw, kind in (("Phone.zip", "dir"), ("Phone", "file")):
        with pytest.raises(HTTPException) as e:
            r(case, raw, expect=kind)
        assert e.value.status_code == 404
