"""The saved-statement check's fast digest decides exactly as _digest does (fin-speed)."""
import math
from uuid import uuid4

import pytest

from services.financial.ledger_summary import _json_copy
from services.financial.pdf_candidates import _digest
from services.financial.saved_statement_admission import _digest_matches

VALUES = [
    None, True, 0, -1, 2 ** 70, 1.5, 0.1, 1e16, 1e-07, 123456789.125, -0.0, '', 'plain', 'Ñandú € 東京 😀',
    'quote " back \\ nl \n tab \t cr \r bell \x07 del \x7f sep  ', [], {}, [1, [2, [3]]],
    {'b': 1, 'a': {'d': [1.25, 'x'], 'c': None}, 'É': 2, 'e': 3, '10': 4, '9': 5},
    {'rows': [{'id': f'r{i}', 'amount_minor': str(i * 100), 'fields': {'description': f'Payment {i}'}} for i in range(50)]},
]


@pytest.mark.parametrize('value', VALUES)
def test_same_answer_as_digest_for_the_saved_hash_and_any_other(value):
    saved = _digest(value)
    assert _digest_matches(value, saved) is True
    assert _digest_matches(value, _digest(['something else'])) is False
    assert _digest_matches(value, None) is False
    assert _digest_matches(value, saved.upper()) is False


def test_a_changed_value_does_not_match_its_old_hash():
    value = {'rows': [{'id': 'r1', 'amount_minor': '100'}]}
    saved = _digest(value)
    value['rows'][0]['amount_minor'] = '101'
    assert _digest_matches(value, saved) is False


@pytest.mark.parametrize('value', [{1: 'int key'}, {2: 'b', 10: 'c'}])
def test_values_orjson_refuses_are_decided_by_digest(value):
    assert _digest_matches(value, _digest(value)) is True


@pytest.mark.parametrize('value', [math.nan, {'x': math.inf}, {'u': uuid4()}, object(), {'a': 1, 2: 'b'}])
def test_values_digest_refuses_still_raise(value):
    with pytest.raises((TypeError, ValueError)):
        _digest(value)
    with pytest.raises((TypeError, ValueError)):
        _digest_matches(value, 'whatever')


def test_json_copy_equals_and_is_independent_of_the_stored_row():
    stored = {'id': 'r1', 'fields': {'description': 'x', 'tags': ['a']}, 'amount_minor': '5', 'n': 1.5}
    copied = _json_copy(stored)
    assert copied == stored
    copied['fields']['tags'].append('b'); copied['fields']['description'] = 'y'
    assert stored == {'id': 'r1', 'fields': {'description': 'x', 'tags': ['a']}, 'amount_minor': '5', 'n': 1.5}
