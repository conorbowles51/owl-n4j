"""Reconcile supplied independent-reader labels without inventing ground truth."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from services.financial.extraction_evaluation import Identifier, Digest, Fields, TruthRow, ExtractionEvaluation
from services.financial.pdf_candidates import _digest


def parse_review_json(content):
    """Reject ambiguous duplicate keys and non-finite values before validation."""
    import json
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Repeated JSON keys are ambiguous in a review record.')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('Non-finite JSON values are unsupported in review records.')
    return json.loads(content, object_pairs_hook=unique, parse_constant=nonfinite)


class ReviewedDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_sha256: Digest
    complete_source_reviewed: Annotated[bool, Field(strict=True)]
    rows: list[TruthRow] = Field(max_length=10000)

    @model_validator(mode='after')
    def unique_rows(self):
        if len({row.source_id for row in self.rows}) != len(self.rows):
            raise ValueError('Reader review repeats a source row ID.')
        return self


class ReaderReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['loupe.extraction_reader_review/1']
    corpus_id: Identifier
    corpus_version: Identifier
    review_id: Identifier
    reviewer_id: Identifier
    label_status: Literal['independent_reader', 'synthetic_test']
    documents: list[ReviewedDocument] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def bounded_sources(self):
        if len({doc.source_sha256 for doc in self.documents}) != len(self.documents):
            raise ValueError('A reviewed source occurs more than once.')
        if sum(len(doc.rows) for doc in self.documents) > 50000:
            raise ValueError('Reader review exceeds 50,000 source rows.')
        if any(not value.strip() or value != value.strip() for value in (self.corpus_id, self.corpus_version, self.review_id, self.reviewer_id)):
            raise ValueError('Review identifiers must not be blank or have surrounding whitespace.')
        return self


class RowResolution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_sha256: Digest
    source_id: Identifier
    final_fields: Fields | None  # None explicitly excludes the disputed row.
    reason: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]

    @model_validator(mode='after')
    def deliberate_resolution(self):
        if not self.reason.strip() or self.final_fields == {}:
            raise ValueError('Resolve a row with stated fields or explicit exclusion and a reason.')
        return self


class ReviewAdjudication(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['loupe.extraction_review_adjudication/1']
    adjudication_id: Identifier
    adjudicator_id: Identifier
    first_review_sha256: Digest
    second_review_sha256: Digest
    resolutions: list[RowResolution] = Field(max_length=100000)


def reconcile_reference_reviews(first, second, *, adjudication=None):
    """Return unresolved conflicts or source-bound agreed/adjudicated labels.

    Reader identities, completeness and independence are supplied declarations.
    This function neither authenticates reviewers nor examines original sources.
    """
    a, b = ReaderReview.model_validate(first), ReaderReview.model_validate(second)
    if a.reviewer_id == b.reviewer_id or a.review_id == b.review_id:
        raise ValueError('Two distinct reader identities and review records are required.')
    if (a.corpus_id, a.corpus_version, a.label_status) != (b.corpus_id, b.corpus_version, b.label_status):
        raise ValueError('Both reviews must identify the same corpus, version and label status.')
    da = {doc.source_sha256:doc for doc in a.documents}
    db = {doc.source_sha256:doc for doc in b.documents}
    if da.keys() != db.keys():
        raise ValueError('Both readers must cover the same source-document inventory.')
    if not all(doc.complete_source_reviewed for doc in [*a.documents, *b.documents]):
        raise ValueError('Incomplete source reviews cannot establish full-document ground truth.')
    a_json, b_json = a.model_dump(mode='json'), b.model_dump(mode='json')
    a_hash, b_hash = _digest(a_json), _digest(b_json)
    conflicts, agreed = {}, {}
    for source in sorted(da):
        left = {row.source_id:row.fields for row in da[source].rows}
        right = {row.source_id:row.fields for row in db[source].rows}
        for source_id in sorted(left.keys() | right.keys()):
            key = (source, source_id)
            if source_id in left and source_id in right and left[source_id] == right[source_id]:
                agreed[key] = left[source_id]
            else:
                conflicts[key] = dict(source_sha256=source, source_id=source_id,
                    first_fields=left.get(source_id), second_fields=right.get(source_id),
                    disagreement='row_presence' if source_id not in left or source_id not in right else 'field_values')
    resolved = {}
    decision = None
    if adjudication is not None:
        decision = ReviewAdjudication.model_validate(adjudication)
        if (decision.first_review_sha256, decision.second_review_sha256) != (a_hash, b_hash):
            raise ValueError('Adjudication refers to different reader-review versions.')
        if not decision.adjudicator_id.strip() or not decision.adjudication_id.strip():
            raise ValueError('Adjudication requires a recorded identity and reference.')
        for resolution in decision.resolutions:
            key = (resolution.source_sha256, resolution.source_id)
            if key in resolved or key not in conflicts:
                raise ValueError('Adjudication repeats a row or changes a row without a recorded disagreement.')
            resolved[key] = resolution.final_fields
    unresolved = sorted(conflicts.keys() - resolved.keys())
    output = dict(schema_version='loupe.extraction_reference_review/1', corpus_id=a.corpus_id,
        corpus_version=a.corpus_version, status='needs_adjudication' if unresolved else 'labels_reconciled',
        label_status='synthetic_test' if a.label_status == 'synthetic_test' else 'pending_adjudication' if unresolved else 'independently_reviewed',
        reviewer_ids=[a.reviewer_id, b.reviewer_id], first_review_sha256=a_hash, second_review_sha256=b_hash,
        disagreements=[conflicts[key] for key in sorted(conflicts)], unresolved_count=len(unresolved),
        unresolved=[dict(source_sha256=key[0], source_id=key[1]) for key in unresolved],
        adjudication=decision.model_dump(mode='json') if decision else None,
        reader_reviews=[a_json, b_json],
        limitation='Labels, source coverage, reviewer identity and independence are supplied declarations, not certified by this tool. Matching reader values may still both be wrong. No source document is interpreted and no extraction accuracy is measured here. Synthetic reviews remain synthetic.')
    # Never emit a partially reconciled truth set that could be mistaken for the
    # complete source inventory by a later accuracy measurement.
    if not unresolved:
        labels = {**agreed, **resolved}
        by_source = {source:[] for source in sorted(da)}
        for key, value in sorted(labels.items()):
            if value is not None:
                by_source[key[0]].append(dict(source_id=key[1], fields=value))
        output['documents'] = [dict(source_sha256=source, truth=rows) for source, rows in by_source.items()]
        output['adjudication_reference'] = decision.adjudication_id if decision else 'agreement:' + _digest(dict(first=a_hash, second=b_hash))
    output['review_record_sha256'] = _digest(output)
    return output


def evaluation_from_reference_reviews(review_record, predictions):
    """Bind recorded labels to supplied extraction outputs, without row guessing."""
    readers = review_record.get('reader_reviews')
    if not isinstance(readers, list) or len(readers) != 2:
        raise ValueError('A complete two-reader review record is required.')
    checked = reconcile_reference_reviews(readers[0], readers[1], adjudication=review_record.get('adjudication'))
    if _digest(checked) != _digest(review_record) or checked['status'] != 'labels_reconciled':
        raise ValueError('Review record changed or still has unresolved disagreements.')
    if (not isinstance(predictions, dict) or set(predictions) != {'schema_version','corpus_id','corpus_version','documents'}
            or predictions['schema_version'] != 'loupe.extraction_predictions/1'
            or (predictions['corpus_id'],predictions['corpus_version']) != (checked['corpus_id'],checked['corpus_version'])):
        raise ValueError('Predictions must identify the same reviewed corpus and version.')
    labels = {doc['source_sha256']:doc['truth'] for doc in checked['documents']}
    documents = predictions['documents']
    if (not isinstance(documents, list) or any(not isinstance(doc,dict) or 'truth' in doc for doc in documents)
            or {doc.get('source_sha256') for doc in documents} != labels.keys()):
        raise ValueError('Predictions must cover the exact reviewed source inventory and must not replace truth labels.')
    evaluation = dict(schema_version='loupe.extraction_evaluation/1', corpus_id=checked['corpus_id'], corpus_version=checked['corpus_version'],
        reviewer_ids=checked['reviewer_ids'], adjudication_reference=checked['adjudication_reference'], label_status=checked['label_status'],
        documents=[{**doc, 'truth':labels[doc['source_sha256']]} for doc in documents])
    return ExtractionEvaluation.model_validate(evaluation).model_dump(mode='json')
