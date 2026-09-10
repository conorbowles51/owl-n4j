"""Exact, offline comparison against supplied adjudicated extraction ground truth.

No provider calls, inferred labels, fuzzy matching, or software-test accuracy claims.
Ratios retain integer numerator/denominator; a missing denominator is unavailable.
"""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from services.financial.pdf_candidates import _digest

Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=256)]
Digest = Annotated[str, Field(strict=True, pattern=r'^[a-f0-9]{64}$')]
Fields = dict[Literal['date','amount_minor','currency','direction','account'], Annotated[str, Field(strict=True, min_length=1, max_length=4096)]]

class TruthRow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: Identifier
    fields: Fields = Field(min_length=1)

class PredictedRow(TruthRow):
    admitted: Annotated[bool, Field(strict=True)] = False

class EvaluationDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_sha256: Digest
    extraction_layer: Literal['native','template','ocr_model','grounded_model','investigator_review']
    extractor_version: Identifier
    truth: list[TruthRow] = Field(max_length=10000)
    predictions: list[PredictedRow] = Field(max_length=10000)
    proof_class: Literal['p0','p1','p2','p3','p4']
    balance_gate: Literal['passed','failed','unavailable']
    quarantined: Annotated[bool, Field(strict=True)]

    @model_validator(mode='after')
    def unique_positions(self):
        for rows in (self.truth,self.predictions):
            if len({r.source_id for r in rows}) != len(rows):
                raise ValueError('Repeated source row IDs are ambiguous.')
        return self

class ExtractionEvaluation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['loupe.extraction_evaluation/1']
    corpus_id: Identifier
    corpus_version: Identifier
    reviewer_ids: list[Identifier] = Field(min_length=2,max_length=20)
    adjudication_reference: Identifier
    label_status: Literal['independently_reviewed','synthetic_test']
    documents: list[EvaluationDocument] = Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def independent_inputs(self):
        if len(set(self.reviewer_ids)) != len(self.reviewer_ids):
            raise ValueError('Ground truth requires distinct reviewer identifiers.')
        keys=[d.source_sha256 for d in self.documents]
        if len(set(keys))!=len(keys):
            raise ValueError('A source document must occur once in an evaluation.')
        if sum(len(d.truth)+len(d.predictions) for d in self.documents)>100000:
            raise ValueError('Evaluation exceeds 100,000 total rows.')
        return self


def _ratio(numerator,denominator):
    return dict(numerator=numerator,denominator=denominator,status='available' if denominator else 'unavailable')


def evaluate_extraction(raw):
    corpus=ExtractionEvaluation.model_validate(raw)
    results=[]
    for layer in sorted({d.extraction_layer for d in corpus.documents}):
        documents=[d for d in corpus.documents if d.extraction_layer==layer]
        found=total=predicted=matched=admitted=surviving=0
        fields={name:dict(correct=0,proposed=0,expected=0,missing=0) for name in ('date','amount_minor','currency','direction','account')}
        classes={}
        for doc in documents:
            truth={r.source_id:r for r in doc.truth}
            predictions={r.source_id:r for r in doc.predictions}
            total+=len(truth);predicted+=len(predictions)
            found+=len(truth.keys() & predictions.keys())
            matched+=len(truth.keys() & predictions.keys())
            gate=classes.setdefault(doc.proof_class,dict(passed=0,failed=0,unavailable=0))
            gate[doc.balance_gate]+=1
            for row in doc.truth:
                proposal=predictions.get(row.source_id)
                for name in row.fields:
                    fields[name]['expected']+=1
                    if proposal is None or name not in proposal.fields:fields[name]['missing']+=1
            for row in doc.predictions:
                original=truth.get(row.source_id)
                for name,value in row.fields.items():
                    fields[name]['proposed']+=1
                    if original is not None and original.fields.get(name)==value:fields[name]['correct']+=1
                if row.admitted:
                    admitted+=1
                    # Extra or omitted fields, wrong values and invented rows all
                    # count as errors if that reading passed the supplied gate.
                    if original is None or row.fields!=original.fields:surviving+=1
        results.append(dict(extraction_layer=layer,extractor_versions=sorted({d.extractor_version for d in documents}),
            documents=len(documents),row_recall=_ratio(found,total),row_precision=_ratio(matched,predicted),
            fields={name:dict(precision=_ratio(v['correct'],v['proposed']),recall=_ratio(v['correct'],v['expected']),missing=v['missing']) for name,v in fields.items()},
            direction_accuracy=_ratio(fields['direction']['correct'],fields['direction']['expected']),
            errors_surviving_gate=_ratio(surviving,admitted),
            quarantine_rate=_ratio(sum(d.quarantined for d in documents),len(documents)),
            balance_gate_by_class={name:dict(pass_rate=_ratio(v['passed'],v['passed']+v['failed']),unavailable=v['unavailable']) for name,v in sorted(classes.items())}))
    return dict(schema_version='loupe.extraction_evaluation_report/1',corpus_id=corpus.corpus_id,corpus_version=corpus.corpus_version,
        corpus_sha256=_digest(corpus.model_dump(mode='json')),
        ground_truth_sha256=_digest(dict(corpus_id=corpus.corpus_id,corpus_version=corpus.corpus_version,
            label_status=corpus.label_status,reviewer_ids=sorted(corpus.reviewer_ids),adjudication_reference=corpus.adjudication_reference,
            documents=[dict(source_sha256=d.source_sha256,truth=[r.model_dump() for r in sorted(d.truth,key=lambda r:r.source_id)]) for d in sorted(corpus.documents,key=lambda d:d.source_sha256)])),label_status=corpus.label_status,
        reviewer_ids=corpus.reviewer_ids,adjudication_reference=corpus.adjudication_reference,layers=results,
        limitation='Exact comparisons against supplied labels and source row IDs. Review independence, label correctness, admission status and corpus representativeness are declared inputs, not established by this calculation. Synthetic results are not product accuracy measurements.')


def compare_extraction_evaluations(baseline, current):
    """Compare two validated corpus runs; never compare different ground truth."""
    before=evaluate_extraction(baseline)
    after=evaluate_extraction(current)
    if before['ground_truth_sha256']!=after['ground_truth_sha256']:
        raise ValueError('Regression comparison requires the same reviewed ground truth.')
    if {d['source_sha256']:d['extraction_layer'] for d in baseline['documents']} != {d['source_sha256']:d['extraction_layer'] for d in current['documents']}:
        raise ValueError('Document extraction layers changed; establish a separately reviewed baseline.')
    old={v['extraction_layer']:v for v in before['layers']}
    new={v['extraction_layer']:v for v in after['layers']}
    if old.keys()!=new.keys():
        raise ValueError('Extraction layers changed; establish a separately reviewed baseline.')
    regressions=[]
    def compare(layer,name,a,b,lower_is_better=False):
        if a['status']=='unavailable':return
        if b['status']=='unavailable':
            regressions.append(dict(layer=layer,metric=name,reason='previously available measurement is unavailable'))
        elif (b['numerator']*a['denominator'] > a['numerator']*b['denominator'] if lower_is_better else b['numerator']*a['denominator'] < a['numerator']*b['denominator']):
            regressions.append(dict(layer=layer,metric=name,reason='measured result regressed'))
    for layer in sorted(old):
        a,b=old[layer],new[layer]
        for metric in ('row_recall','row_precision','direction_accuracy'):
            compare(layer,metric,a[metric],b[metric])
        compare(layer,'errors_surviving_gate',a['errors_surviving_gate'],b['errors_surviving_gate'],True)
        for name in a['fields']:
            for metric in ('precision','recall'):
                compare(layer,f'{name}.{metric}',a['fields'][name][metric],b['fields'][name][metric])
    return dict(status='regression' if regressions else 'no_measured_regression',regressions=regressions,
        baseline_sha256=before['corpus_sha256'],current_sha256=after['corpus_sha256'],
        limitation='Compares row/field/direction accuracy and admitted-error rates only. Quarantine and balance-pass rates are reported but are not inherently better when higher or lower. No measured regression is not proof of accuracy.')
