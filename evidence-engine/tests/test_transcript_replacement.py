import json
from app.pipeline.transcript_replacement import prune_properties


def test_replacement_removes_old_source_facts_and_preserves_other_source_and_manual_fields():
    old = {'id': 'old', 'quote': 'Wrong words', 'object_value': {'properties': {'role': 'Wrong role'}},
           'source_location': {'source_document_id': 'audio-id', 'revision_id': 'old-rev', 'source_file': 'call.wav'}}
    other = {'id': 'other', 'quote': 'Other evidence', 'object_value': {'text': 'Other supported fact', 'properties': {'role': 'Witness'}},
             'source_location': {'source_document_id': 'note-id', 'revision_id': 'note-rev', 'source_file': 'note.txt'}}
    props = {'id': 'john', 'name': 'John', 'description': 'Investigator description', 'manual_fields': ['description'],
             'role': 'Wrong role', 'summary': 'Wrong words and other evidence', 'source_claim_ids': ['old', 'other'],
             'source_quotes': ['Wrong words', 'Other evidence'], 'source_files': ['call.wav', 'note.txt'],
             'source_locations': json.dumps([old['source_location'], other['source_location']]),
             'verified_facts': json.dumps([{'text': 'Wrong fact', 'quote': 'Wrong words', 'source_location': old['source_location']},
                                          {'text': 'Other supported fact', 'quote': 'Other evidence', 'source_location': other['source_location']}])}
    result = prune_properties(props, [old], [other])
    assert result['description'] == 'Investigator description'
    assert result['source_claim_ids'] == ['other']
    assert result['source_quotes'] == ['Other evidence']
    assert result['source_files'] == ['note.txt']
    assert result['role'] == 'Witness'
    assert result['summary'] == 'Other supported fact'
    assert 'Wrong fact' not in result['verified_facts']
    assert 'old-rev' not in result['source_locations']


def test_repeated_quote_from_other_file_and_manual_summary_are_preserved():
    old = {'id': 'old', 'quote': 'Same quote', 'object_value': {}, 'source_location': {'source_document_id': 'audio-id', 'revision_id': 'old'}}
    other = {'id': 'other', 'quote': 'Same quote', 'object_value': {}, 'source_location': {'source_document_id': 'note-id', 'revision_id': 'new'}}
    props = {'source_claim_ids': ['old', 'other'], 'source_quotes': ['Same quote'], 'summary': 'Investigator summary', 'manual_fields': ['summary']}
    result = prune_properties(props, [old], [other])
    assert result['source_quotes'] == ['Same quote']
    assert result['summary'] == 'Investigator summary'
