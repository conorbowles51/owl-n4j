"""Report PDFs refuse outside resources without failing the PDF (WeasyPrint 70 takes a URLFetcher).

9 Nov: the cost, snapshot, casework and ledger reports passed plain functions as url_fetcher; under weasyprint 70.0
a refused URL made the whole PDF fail with AttributeError instead of leaving the resource out.
"""
import re
from pathlib import Path

import pytest

weasyprint = pytest.importorskip("weasyprint")

BACKEND = Path(__file__).resolve().parents[1]
PAGE = '<p>Report</p><img src="http://example.invalid/a.png"><img src="file:///etc/hostname">'


def test_a_refused_resource_is_left_out_and_the_pdf_is_written():
    from services.pdf_fetch import deny_all
    pdf = weasyprint.HTML(string=PAGE, url_fetcher=deny_all("no")).write_pdf()
    assert pdf.startswith(b"%PDF")


def test_every_report_passes_a_url_fetcher_object_not_a_function():
    offenders = []
    for path in (BACKEND / "services").rglob("*.py"):
        text = path.read_text()
        for match in re.finditer(r"url_fetcher=(\w+)\b(?!\s*\()", text):
            name = match.group(1)
            if re.search(r"^\s*def %s\(" % re.escape(name), text, re.M):
                offenders.append(f"{path.relative_to(BACKEND)}:{name}")
    assert offenders == []


@pytest.mark.parametrize("module,render", [
    ("services.case_cost_report", None), ("services.snapshot_report", None),
    ("services.casework_report", None), ("services.financial.ledger_pdf", None)])
def test_each_report_module_uses_the_shared_fetcher(module, render):
    import importlib
    source = Path(importlib.import_module(module).__file__).read_text()
    assert "deny_all(" in source
