"""A code-quoted file name in an agent answer becomes its doc:// link only when the run's tool results returned it
(coverage run v-tl-2, 8 Nov 2026: the source was named as `lxfw-feat002-cost-100k.txt`, with no citation)."""
from services.agent.citations import link_named_files

RETURNED = '{"events": [{"source_files": ["lxfw-feat002-cost-100k.txt"], "name": "Registration fee"}]}'


def test_a_returned_file_name_is_linked():
    out = link_named_files("Five events, all sourced from `lxfw-feat002-cost-100k.txt`.", RETURNED)
    assert out == "Five events, all sourced from [lxfw-feat002-cost-100k.txt](doc://lxfw-feat002-cost-100k.txt)."


def test_a_name_no_tool_returned_stays_as_written():
    text = "See `invented-file.pdf` and the `amount` field."
    assert link_named_files(text, RETURNED) == text


def test_code_blocks_and_existing_links_are_left_alone():
    text = "```\n`lxfw-feat002-cost-100k.txt`\n```\n[`lxfw-feat002-cost-100k.txt`](doc://x)"
    assert link_named_files(text, RETURNED) == text


def test_spaces_in_a_name_are_encoded():
    out = link_named_files("From `March statement.pdf`.", '"March statement.pdf"')
    assert out == "From [March statement.pdf](doc://March%20statement.pdf)."
