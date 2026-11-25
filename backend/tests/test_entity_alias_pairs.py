"""The similar-entities scan suggests two people or organisations when one is named by an alias of the other.

On 25 Nov 2026 a person merged the Person 'Randy Collins' (aliases 'Marvin Carnes', 'Randall Carnes', 'Randy') into the
Person 'Marvin Randall Carnes' in case 80d1f81e by hand: the scan compared names only and never read aliases, so it
never suggested the pair. A Neo4j read is faked; the comparison is the real code."""
import asyncio
import importlib
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from services.neo4j.entity_service import EntityService, alias_pairs, pair_order

entity_service = importlib.import_module('services.neo4j.entity_service')


def _entity(key, name, type_, aliases=None):
    return dict(key=key, id=key, name=name, type=type_, summary=None, notes=None, verified_facts=None,
                ai_insights=None, properties={'aliases': aliases} if aliases is not None else {})


CARNES = _entity('p1', 'Marvin Randall Carnes', 'Person', ['Carnes'])
COLLINS = _entity('p2', 'Randy Collins', 'Person', ['Marvin Carnes', 'Randall Carnes', 'Randy'])


@contextmanager
def _graph(entities):
    session = MagicMock()
    session.run.return_value = [dict(e) for e in entities]
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    with patch.object(entity_service, 'driver', driver):
        yield


def _keys(pairs):
    return sorted(tuple(sorted((a['key'], b['key']))) for a, b, *_ in pairs)


def test_an_alias_whose_words_are_in_the_other_name_pairs_them_and_says_what_matched():
    pairs = alias_pairs([CARNES, COLLINS], threshold=0.7)
    assert _keys(pairs) == [('p1', 'p2')]
    (e1, e2, similarity, matched), = pairs
    assert matched == ('Marvin Randall Carnes', 'Randall Carnes') and 0.7 <= similarity < 1


def test_an_alias_equal_to_the_other_name_pairs_them_at_one():
    pairs = alias_pairs([_entity('t1', 'Timothy Valentin', 'Person', ['Tim', 'Rico']),
                         _entity('t2', 'Rico', 'Person')], threshold=0.7)
    assert _keys(pairs) == [('t1', 't2')] and pairs[0][2] == 1.0


def test_shapes_that_do_not_pair():
    entities = [
        # two aliases alike, neither a name
        _entity('a', 'Adam Thomas', 'Person', ['Thomas']), _entity('b', 'Thomas Lee Keyes', 'Person', ['Thomas']),
        # a name holding the alias with two words more: a relation, not the same person
        _entity('c', 'Duncan Cameron Sheils', 'Person'),
        _entity('d', 'Maria Love Sheils', 'Person', ['Son of Duncan Cameron Sheils']),
        # one word of an alias inside a longer name
        _entity('e', 'Marvin Randall Carnes', 'Person', ['Carnes']), _entity('f', 'Ray Carnes', 'Person'),
        # payments named after a company: the types an alias does not name
        _entity('g', 'GREENHOLLOW GROCERS', 'FinancialTransaction', ['GREENHOLLOW GROCERS 2024-02-04']),
        _entity('h', 'Payment to Greenhollow Grocers (2024-02-04)', 'Transaction', ['GREENHOLLOW GROCERS']),
        # across types
        _entity('i', 'American Express', 'Bank', ['AMEX']), _entity('j', 'AMEX', 'Organization'),
    ]
    assert alias_pairs(entities, threshold=0.5) == []


def test_pairs_the_name_passes_list_and_rejected_pairs_are_left_out():
    near = [_entity('a', 'Gustavo Figueroa', 'Person', ['Gustavo Enrique Figueroa']),
            _entity('b', 'Gustavo Enrique Figueroa', 'Person')]
    assert alias_pairs(near, threshold=0.7) == []            # 0.82 alike on the names: the type pass lists it
    assert _keys(alias_pairs(near, threshold=0.9)) == [('a', 'b')]
    assert alias_pairs([CARNES, COLLINS], {('p1', 'p2')}, threshold=0.7) == []


def test_alias_pairs_sort_after_every_name_pair():
    pairs = [{'similarity': 0.71}, {'similarity': 1.0, 'matched_on': {'basis': 'alias'}}, {'similarity': 0.95}]
    assert [p['similarity'] for p in sorted(pairs, key=pair_order, reverse=True)] == [0.95, 0.71, 1.0]


def test_the_scan_and_the_streaming_scan_suggest_the_alias_pair_last():
    entities = [CARNES, COLLINS, _entity('x', 'Ana Lopez', 'Person'), _entity('y', 'Ana Lopes', 'Person')]
    with _graph(entities):
        plain = EntityService().find_similar_entities('case', name_similarity_threshold=0.7, max_results=100)

        async def stream():
            events = [e async for e in EntityService().find_similar_entities_streaming(
                'case', name_similarity_threshold=0.7)]
            return events[-1]['data']['limited_results']
        streamed = asyncio.run(stream())
    for pairs in (plain, streamed):
        assert [(p['entity1']['key'], p['entity2']['key']) for p in pairs] == [('x', 'y'), ('p1', 'p2')]
        assert pairs[1]['matched_on'] == {'basis': 'alias', 'entity1_text': 'Marvin Randall Carnes',
                                          'entity2_text': 'Randall Carnes'}
        assert 'matched_on' not in pairs[0]


def test_a_pronoun_alias_pairs_no_one():
    # 5eeaa265, live 25 Nov 2026: a Person with the alias 'She' and the Person 'She' at 100 % (names invented)
    ana = _entity('k1', 'Ana Ruiz Vega', 'Person', ['Ana', 'She'])
    she = _entity('k2', 'She', 'Person')
    assert alias_pairs([ana, she], threshold=0.7) == []


def test_a_role_word_on_several_records_pairs_none_of_them():
    # 042cfaee: 'The Court' was an alias of three different judges (names invented) and the name of a fourth record
    judges = [_entity(f'j{n}', name, 'Person', ['THE COURT']) for n, name in
              enumerate(['Judge One', 'Judge Two', 'Judge Three'])]
    court = _entity('c1', 'The Court', 'Person')
    assert alias_pairs([*judges, court], threshold=0.7) == []


def test_a_role_word_two_records_share_still_pairs_them():
    # 0e4fb172: a person merged a Person with the alias 'Mommy' and the Person 'Mommy' (names invented)
    rosa = _entity('e1', 'Rosa Field', 'Person', ['Mommy', 'Ms. Field'])
    mommy = _entity('e2', 'Mommy', 'Person')
    assert _keys(alias_pairs([rosa, mommy], threshold=0.7)) == [('e1', 'e2')]


def test_a_role_word_alias_matches_its_own_text_only():
    # d5b330d1: the alias 'Unknown Recipient' matched 'Unknown Recipient 1' and 'Unknown Recipient 2', two people
    tocayo = _entity('t1', 'Tocayo (5210000000000)', 'Person', ['Unknown Recipient'])
    one = _entity('u1', 'Unknown Recipient 1', 'Person')
    two = _entity('u2', 'Unknown Recipient 2', 'Person')
    assert alias_pairs([tocayo, one, two], threshold=0.7) == []


def test_us_in_capitals_is_a_name():
    usa = _entity('o1', 'United States of America', 'Organization', ['US'])
    us = _entity('o2', 'US', 'Organization')
    assert _keys(alias_pairs([usa, us], threshold=0.7)) == [('o1', 'o2')]
