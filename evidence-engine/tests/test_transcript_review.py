import uuid
from types import SimpleNamespace
import pytest

from app.pipeline.extract_text import ExtractedDocument
from app.pipeline.chunk_embed import chunk_document, get_document_revision_id
from app.pipeline.extract_entities import RawEntity, _dedup_within_file
from app.pipeline.resolve_entities import _apply_merges
from app.pipeline.transcript_bindings import add_speaker_entities


def test_same_named_linked_speakers_never_merge():
    entities = [RawEntity(temp_id='a', category='Person', specific_type='Person', name='John',
        properties={'_transcript_entity_id': 'person-1'}),
        RawEntity(temp_id='b', category='Person', specific_type='Person', name='John',
        properties={'_transcript_entity_id': 'person-2'})]
    deduped, _ = _dedup_within_file(entities, [])
    assert len(deduped) == 2
    resolved, ids = _apply_merges(deduped, [(0, 1)])
    assert ids == {'a': 'person-1', 'b': 'person-2'}
    assert {entity.id for entity in resolved} == {'person-1', 'person-2'}


def test_binding_revision_changes_identity_even_if_words_match():
    first = ExtractedDocument(text='John\nHello', metadata={'transcript_digest': 'binding-one'})
    second = ExtractedDocument(text='John\nHello', metadata={'transcript_digest': 'binding-two'})
    assert get_document_revision_id(first) != get_document_revision_id(second)


def test_speaker_seeds_have_the_selected_identity_and_source_time():
    doc = ExtractedDocument(text='[0–1] John\nHello\n\n', metadata={'file_type': 'audio',
        'transcript_revision_id': 'revision', 'transcript_turns': [{
        'start_char': 0, 'label_start_char': 6, 'end_char': 16, 'speech_start_char': 11,
        'start_seconds': 0, 'end_seconds': 1, 'speaker_name': 'John', 'speaker': 'A',
        'segment_id': 'turn-1', 'entity_id': 'existing-john'}]})
    chunk = chunk_document(doc, 'synthetic.wav', 'job-1')[0]
    result = add_speaker_entities([], chunk, 'synthetic.wav')
    assert result[0].properties['_transcript_entity_id'] == 'existing-john'
    assert result[0].source_location['segment_id'] == 'turn-1'
    assert result[0].source_location['attribution_origin'] == 'investigator'


def test_first_person_facts_use_the_selected_speaker_even_in_a_continuation_chunk():
    from app.pipeline.chunk_embed import TextChunk
    span = {'start_char': 0, 'label_start_char': 0, 'speech_start_char': 5, 'end_char': 200,
        'speaker_name': 'John', 'speaker': 'A', 'entity_id': 'person-john', 'segment_id': 'one',
        'start_seconds': 0, 'end_seconds': 10}
    chunk = TextChunk(text='I own a blue car.', index=2, start_char=100, end_char=116, is_table=False,
        metadata={'transcript_turns': [span], 'transcript_revision_id': 'revision'})
    self_fact = RawEntity(temp_id='self', category='Person', specific_type='Person', name='John',
        source_quote='I own a blue car.', source_location={'quote_start_char': 100})
    named_third_party = RawEntity(temp_id='other', category='Person', specific_type='Person', name='John',
        source_quote='I met John yesterday.', source_location={'quote_start_char': 100})
    result = add_speaker_entities([self_fact, named_third_party], chunk, 'call.wav')
    assert result[0].properties['_transcript_entity_id'] == 'person-john'
    assert '_transcript_entity_id' not in result[1].properties


@pytest.mark.asyncio
async def test_fresh_direct_audio_keeps_the_original_text_pipeline_input(monkeypatch):
    from app.pipeline import audio_review
    monkeypatch.setenv('AUDIO_TRANSCRIPT_REVIEW_ENABLED', '1')
    doc = ExtractedDocument(text='Original machine words', metadata={'file_type': 'audio'})
    async def extract(*_, **__): return doc
    async def save(*_, **__): return 'saved-revision'
    async def load(*_, **__):
        return ExtractedDocument(text='[0–1] Speaker 1\nOriginal machine words', metadata={'transcript_digest': 'digest'})
    monkeypatch.setattr(audio_review, 'save_machine_document', save)
    monkeypatch.setattr(audio_review, 'load_saved_document', load)
    result = await audio_review.ingestion_document('job', '/call.wav', 'call.wav', 'case', 'file', extractor=extract)
    assert result.text == 'Original machine words'
    assert result.metadata['transcript_input_format'] == 'machine_text_v1'


@pytest.mark.asyncio
async def test_saved_transcript_skips_transcription(monkeypatch):
    from app.pipeline import audio_review
    expected = ExtractedDocument(text='John\nCorrected', metadata={'file_type': 'audio'})
    async def load(*_): return expected
    async def unexpected(*_, **__): raise AssertionError('Saved audio must not be retranscribed')
    monkeypatch.setattr(audio_review, 'load_saved_document', load)
    result = await audio_review.ingestion_document('job', '/recording.wav', 'recording.wav', 'case', 'file',
        revision_id='saved', extractor=unexpected)
    assert result is expected


@pytest.mark.asyncio
async def test_audio_preparation_stops_after_source_storage(monkeypatch):
    from app.pipeline import audio_review
    from app.models.job import JobStatus
    events = []
    class Context:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
    async def policy(_): pass
    async def extract(*_, **__):
        return ExtractedDocument(text='Hello', metadata={'file_type': 'audio', 'transcription': 'Hello', 'transcription_segments': []})
    async def save(*_, **kwargs): events.append(('saved', kwargs['review_required']))
    async def status(_id, stage, _progress, _message, **_): events.append(stage)
    monkeypatch.setattr(audio_review, 'async_session', Context)
    monkeypatch.setattr(audio_review, 'load_ai_model_policy', policy)
    monkeypatch.setattr(audio_review, 'extract_text', extract)
    monkeypatch.setattr(audio_review, 'save_machine_document', save)
    await audio_review.prepare_audio_review(SimpleNamespace(id=uuid.uuid4(), source_evidence_file_id=uuid.uuid4(),
        case_id=str(uuid.uuid4()), file_path='/synthetic.wav', file_name='synthetic.wav'), status)
    assert events == [JobStatus.EXTRACTING_TEXT, ('saved', True), JobStatus.COMPLETED]


@pytest.mark.asyncio
async def test_existing_scalar_projection_cannot_overwrite_new_audio_citations(monkeypatch):
    import json
    from app.pipeline import write_graph
    from app.pipeline.resolve_entities import ResolvedEntity
    writes = []
    async def capture(query, parameters): writes.append(parameters)
    monkeypatch.setattr(write_graph, '_checkpointed_graph_write', capture)
    entity = ResolvedEntity(id='john', category='Person', specific_type='Person', name='John',
        source_locations=[{'start_seconds': 1, 'revision_id': 'new'}], source_claim_ids=['new-claim'],
        properties={'source_locations': '[]', 'summary': 'old summary', '_transcript_entity_id': 'john'})
    await write_graph._write_entities([entity], 'case', 'job')
    node = writes[0]['nodes'][0]
    assert json.loads(node['source_locations']) == [{'start_seconds': 1, 'revision_id': 'new'}]
    assert node['source_claim_ids'] == ['new-claim']


@pytest.mark.asyncio
async def test_reprocessing_an_already_active_audio_revision_does_not_unpublish_it(monkeypatch):
    from app.pipeline import chunk_embed
    class Collection:
        def get(self, *, ids, include):
            return {'ids': ids, 'metadatas': [{'case_id': 'case', 'evidence_file_id': 'file',
                'revision_id': 'same-revision', 'ingestion_state': 'active'} for _ in ids]}
    async def embed(texts): return [[1.0] for _ in texts]
    def unexpected(**_): raise AssertionError('An active immutable audio chunk must not be demoted to a draft')
    monkeypatch.setattr(chunk_embed, 'get_or_create_collection', lambda _: Collection())
    monkeypatch.setattr(chunk_embed, 'embed_texts', embed)
    monkeypatch.setattr(chunk_embed, 'upsert_embeddings', unexpected)
    doc = ExtractedDocument(text='John\nCorrected words', metadata={'file_type': 'audio', 'transcript_revision_id': 'saved'})
    chunks = await chunk_embed.chunk_and_embed(doc, 'case', 'retry-job', 'call.wav', evidence_file_id='file', revision_id='same-revision')
    assert chunks and chunks[0].text == doc.text
