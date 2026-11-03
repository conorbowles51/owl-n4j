"""Carry investigator-selected people through ordinary extraction and resolution."""
from app.pipeline.extract_entities import RawEntity
import re

BINDING = '_transcript_entity_id'


def chunk_speaker_context(chunk):
    spans = chunk.metadata.get('transcript_turns') or []
    lines = [f"Characters {max(span['speech_start_char'], chunk.start_char) - chunk.start_char}–{min(span['end_char'], chunk.end_char) - chunk.start_char}: {span['speaker_name']} (speaker {span['speaker']})"
        for span in spans if span['speech_start_char'] < chunk.end_char and span['end_char'] > chunk.start_char]
    if not lines: return ''
    return ('Recording speaker context. These are saved speaker labels, separate from spoken words. '
            'Use them for first-person attribution, including a turn continuing from an earlier chunk. '
            'Other people named in speech retain their own identities.\n' + '\n'.join(lines))


def add_speaker_entities(entities, chunk, file_name):
    spans = chunk.metadata.get('transcript_turns') or []
    seeds = {}
    for span in spans:
        start = span['label_start_char']
        end = start + len(span['speaker_name'])
        if not span.get('entity_id') or start < chunk.start_char or end > chunk.end_char:
            continue
        location = {'source_document_id': chunk.metadata.get('evidence_file_id') or chunk.metadata.get('job_id'),
            'source_file': file_name, 'revision_id': chunk.metadata.get('revision_id'),
            'transcript_revision_id': chunk.metadata.get('transcript_revision_id'),
            'quote_start_char': start, 'quote_end_char': end,
            'coordinate_space': 'document_text', 'segment_id': span['segment_id'],
            'start_seconds': span['start_seconds'], 'end_seconds': span['end_seconds'],
            'speaker_id': span['speaker'], 'attribution_origin': 'investigator'}
        seed = RawEntity(temp_id=f"speaker:{location['source_document_id']}:{span['speaker']}",
            category='Person', specific_type='Person', name=span['speaker_name'], confidence=1.0,
            properties={BINDING: span['entity_id']}, source_quote=span['speaker_name'],
            source_chunk_index=chunk.index, source_file=file_name, source_location=location)
        seeds.setdefault(span['speaker'], seed)
    for entity in entities:
        if entity.category != 'Person': continue
        candidates = {}
        for span in spans:
            if not span.get('entity_id') or entity.name.casefold() != span['speaker_name'].casefold(): continue
            origin = entity.source_location or {}
            offset = origin.get('quote_start_char', -1)
            header = span['label_start_char'] <= offset < span['label_start_char'] + len(span['speaker_name'])
            speech = span['speech_start_char'] <= offset < span['end_char']
            quote = entity.source_quote or ''
            self_reference = re.search(r'\b(?:i|my|me|mine|we|our|ours)\b', quote, re.IGNORECASE)
            explicit_other_name = re.search(r'\b' + re.escape(span['speaker_name']) + r'\b', quote, re.IGNORECASE)
            if header or (speech and self_reference and not explicit_other_name):
                candidates[span['entity_id']] = span
        if len(candidates) == 1:
            entity_id, span = next(iter(candidates.items()))
            entity.properties[BINDING] = entity_id
            entity.source_location.update({'speaker_id': span['speaker'], 'attribution_origin': 'investigator'})
    return entities + list(seeds.values())


def locate_transcript_quotes(records, chunks):
    chunks_by_index = {chunk.index: chunk for chunk in chunks}
    for record in records:
        locations = [record.source_location] if record.source_location else []
        locations += [fact['source_location'] for fact in getattr(record, 'verified_facts', []) if fact.get('source_location')]
        for location in locations:
            start, end = location.get('quote_start_char'), location.get('quote_end_char')
            if start is None or end is None: continue
            chunk = chunks_by_index.get(record.source_chunk_index)
            spans = (chunk.metadata.get('transcript_turns') or []) if chunk else []
            covered = [span for span in spans if start < span['end_char'] and end > span['start_char']]
            if covered:
                location.update({'start_seconds': covered[0]['start_seconds'], 'end_seconds': covered[-1]['end_seconds'],
                    'segment_ids': [span['segment_id'] for span in covered],
                    'transcript_revision_id': chunk.metadata['transcript_revision_id']})
