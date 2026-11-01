"""Intake detection (01 unit 1.2) on synthetic fixtures: every form, with 01 section 2.4's wording.

Fixtures are built by the one fixture builder (UXD-33) from an invented phone; nothing here reads case material.
The corpus acceptance (server C3, C9 and C8 folders, zips made from them) is in ``test_phone_corpus.py``.
"""
import hashlib
import shutil
import zipfile
from pathlib import Path

import pytest

from app.phone import detect
from app.phone.runner import hash_container

from . import fixture_builder as fb


@pytest.fixture(scope="module")
def phone(tmp_path_factory):
    out = tmp_path_factory.mktemp("phone")
    people = fb.invent_people(6, seed=3)
    spec = fb.PhoneSpec("S1", like="P09", scale=0.01, contacts=[p.key for p in people[1:]], seed=11)
    fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(out / "S1_Report")
    return out / "S1_Report"


def _texts(c):
    return [m["text"] for m in c["messages"]]


def test_folder_gives_one_full_root(phone):
    c = detect.classify(str(phone))
    assert (c["container_kind"], c["outcome"]) == ("folder", "readable")
    assert len(c["roots"]) == 1 and c["roots"][0]["form"] == "full" and c["roots"][0]["root_path"] == ""
    assert _texts(c) == ["Phone report found: Report.xml. It will be read in full and checked element by element."]


def test_mac_zip_gives_one_root_and_counts_what_it_left_out(phone, tmp_path):
    z = tmp_path / "phone.zip"
    counts = fb.zip_folder(phone, z)
    c = detect.classify(str(z))
    assert (c["container_kind"], c["outcome"]) == ("zip", "readable")
    assert c["skipped_entries"] == {"__MACOSX": counts["macosx"], "ds_store": 1}
    assert [r["root_path"] for r in c["roots"]] == ["S1_Report"]
    assert ("%d system files added by the computer that made this archive were left out (for example Mac resource "
            "files). They are not part of the export." % (counts["macosx"] + 1)) in _texts(c)


def test_split_sections_complete_and_truncated(phone, tmp_path):
    whole = tmp_path / "whole"
    fb.split_sections(phone / "Report.xml", whole)
    c = detect.classify(str(whole))
    root = c["roots"][0]
    assert root["form"] == "split_sections"
    roles = {d["role"]: d for d in root["documents"]}
    assert set(roles) == {"model", "tagged", "extra", "last", "mdf_source", "model_source", "node_source",
                          "translation"}
    assert roles["model"]["root_element"] == "decodedData" and roles["model"]["has_namespace"] is False
    assert not roles["model"]["empty"] and not roles["tagged"]["empty"]
    assert sum(d["empty"] for d in root["documents"]) == 6
    assert not any(d["suspected_truncated"] for d in root["documents"])
    assert any(t.startswith("This report was exported in sections. 2 sections contain data and will be read: ")
               and t.endswith(" 6 sections are empty.") for t in _texts(c))

    cut = tmp_path / "cut"
    fb.split_sections(phone / "Report.xml", cut, truncate_tagged_fraction=0.5)
    c = detect.classify(str(cut))
    roles = {d["role"]: d for d in c["roots"][0]["documents"]}
    assert roles["tagged"]["suspected_truncated"] is True and roles["model"]["suspected_truncated"] is False
    assert ("The Synthetic_Report.xmlTagged section of this report ends partway through. Everything up to that point "
            "will be read and kept, and the report will be marked incomplete. The full section would be needed from "
            "whoever produced it to see the rest.") in _texts(c)


@pytest.mark.parametrize("kind,outcome,text", [
    ("magic", "protected_no_password", "This UFDR file is protected. Loupe does not open protected UFDRs. An "
     "unprotected copy, or the report exported as an XML report folder, is needed from whoever produced it."),
    ("encrypted", "protected_password", "This UFDR file is password protected. Loupe does not open protected UFDRs. "
     "An unprotected copy, or the report exported as an XML report folder, is needed from whoever produced it."),
    ("no_header", "protected_or_invalid", "The report inside this UFDR file cannot be read. It may be protected. An "
     "unprotected copy, or the report exported as an XML report folder, is needed from whoever produced it."),
])
def test_protected_ufdr_forms(tmp_path, kind, outcome, text):
    p = tmp_path / ("x_%s.ufdr" % kind)
    fb.protected_ufdr(p, kind)
    c = detect.classify(str(p))
    assert (c["container_kind"], c["outcome"], c["roots"]) == ("ufdr", outcome, [])
    assert _texts(c) == [text]


def test_readable_ufdr(phone, tmp_path):
    p = tmp_path / "phone.ufdr"
    fb.ufdr_from_folder(phone, p)
    c = detect.classify(str(p))
    assert (c["container_kind"], c["outcome"]) == ("ufdr", "readable")
    assert c["roots"][0]["form"] == "ufdr" and c["roots"][0]["documents"][0]["path"] == "report.xml"


def test_two_report_folders_give_two_roots_and_a_nested_report_is_ignored(phone, tmp_path):
    two = tmp_path / "two"
    shutil.copytree(phone, two / "A")
    shutil.copytree(phone, two / "B")
    shutil.copytree(phone, two / "A" / "inner")
    z = tmp_path / "two.zip"
    fb.zip_folder(two, z, wrapper=None, mac_extras=False)
    c = detect.classify(str(z))
    assert [r["root_path"] for r in c["roots"]] == ["A", "B"]
    assert c["roots"][0]["nested_report_ignored"] == ["A/inner"]
    t = _texts(c)
    assert "2 phone reports found in this upload. Each is read and checked separately." in t
    assert ("A second report was found inside this one at A/inner. It is treated as part of the outer report.") in t


def test_zip_of_ordinary_documents_is_not_a_phone_report(tmp_path):
    z = tmp_path / "docs.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a/letter.xml", "<?xml version='1.0'?><letter>hi</letter>")
        zf.writestr("a/notes.txt", "x")
    c = detect.classify(str(z))
    assert (c["outcome"], c["roots"]) == ("not_a_phone_report", [])
    assert _texts(c) == ["No phone report was found in this upload. The files are kept as ordinary evidence."]


def test_plain_xml_files_under_files_are_not_report_candidates(phone, tmp_path):
    f = tmp_path / "f"
    shutil.copytree(phone, f)
    (f / "files" / "Text").mkdir(parents=True, exist_ok=True)
    (f / "files" / "Text" / "settings.xml").write_text("<?xml version='1.0'?><map><a/></map>")
    c = detect.classify(str(f))
    assert len(c["roots"]) == 1 and c["roots"][0]["root_path"] == ""


def test_zip_container_hash_equals_sha256_of_the_bytes(phone, tmp_path):
    z = tmp_path / "phone.zip"
    fb.zip_folder(phone, z)
    sha, md5, size, members = hash_container(str(z))
    data = z.read_bytes()
    assert (sha, md5, size, members) == (hashlib.sha256(data).hexdigest(), hashlib.md5(data).hexdigest(),
                                         len(data), None)


def test_folder_container_hash_is_over_the_sorted_manifest(phone):
    sha, md5, size, members = hash_container(str(phone))
    lines = []
    for p in sorted(x for x in phone.rglob("*") if x.is_file()):
        rel = p.relative_to(phone).as_posix()
        b = p.read_bytes()
        lines.append("%s  %d  %s\n" % (hashlib.sha256(b).hexdigest(), len(b), rel))
    lines.sort(key=lambda l: l.split("  ", 2)[2])
    assert sha == hashlib.sha256("".join(lines).encode()).hexdigest()
    assert members["Report.xml"][1] == hashlib.sha256((phone / "Report.xml").read_bytes()).hexdigest()


def test_skip_rules():
    assert detect.skip_rule("__MACOSX/x/._a") == "__MACOSX"
    assert detect.skip_rule("x/._a") == "appledouble"
    assert detect.skip_rule("x/.DS_Store") == "ds_store"
    assert detect.skip_rule("Thumbs.db") == "thumbs_db"
    assert detect.skip_rule("x/desktop.ini") == "desktop_ini"
    assert detect.skip_rule("x/a.jpg") is None
