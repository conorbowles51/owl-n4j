"""The active-node filter reads the one property it tests.

properties(n)['system_node'] builds every node's whole property map before the case check
(measured on BNB2: 2.3 million database reads, 4.2-4.8 s for one case count, against 0.6-0.85 s for
n.system_node with the same rows). A missing key and a null value coalesce to false in both forms.
"""
import pathlib
import re

from services.neo4j.driver import active_node_predicate

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def test_active_node_predicate_reads_system_node_directly():
    rendered = active_node_predicate("n")
    assert "properties(" not in rendered
    assert "coalesce(n.system_node, false) <> true" in rendered
    assert rendered.startswith("n.case_id = $case_id")


def test_no_graph_query_builds_a_property_map_to_test_system_node():
    pattern = re.compile(r"properties\(\s*[\w{}]+\s*\)\s*\[\s*['\"]system_node['\"]\s*\]")
    offenders = [
        f"{path.relative_to(BACKEND)}:{lineno}"
        for path in (BACKEND / "services").rglob("*.py")
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
