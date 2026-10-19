"""Bind existing exhibit assessments to the exact populations in ledger exports."""
from collections import defaultdict

from postgres.models.enums import ProofClass
from services.financial.exhibit import (ContentKind, ExhibitRow, SourceDocument, tag_exhibit,
    CAVEAT_UNADJUDICATED_P3)
from services.financial.money import Money
from services.financial.ledger_summary import LedgerSummaryError


def capture_ledger_exhibits(document):
    ledger = document['ledger']
    if not document.get('export_ready') or not ledger.get('history_captured'):
        raise LedgerSummaryError('Exhibit assessment requires a complete captured ledger and history.')
    all_readings = ledger['readings']
    populations = [('verified_totals', [r for r in all_readings if r['included']]),
                   ('working_totals', [r for r in all_readings if r['exclusion_reason'] in (None, 'proof_class_not_included')])]
    if document.get('table_view') is not None:
        by_id = {r['row']['key']: r for r in all_readings}
        populations.append(('table_view', [by_id[id] for id in document['table_view']['row_ids']]))
    sections = []
    for population, readings in populations:
        groups = defaultdict(list)
        for reading in readings:
            groups[reading['row']['currency']].append(reading)
        if not groups:
            sections.append(dict(population=population, currency=None, available=False,
                reason='No rows in this population; an empty set is not a zero-valued exhibit.'))
        for currency, captured in sorted(groups.items()):
            if any(r['exclusion_reason'] not in (None, 'proof_class_not_included') for r in captured):
                sections.append(dict(population=population, currency=currency, available=False,
                    reason='This display contains excluded readings or sources. It is review context, not an assessed summary population.'))
                continue
            rows, sources, source_map = [], {}, {}
            for r in captured:
                row, source = r['row'], r['source']
                signed = int(row['amount_minor']) * (1 if row['direction'] == 'credit' else -1)
                rows.append(ExhibitRow(reference=row['ref_id'], proof_class=ProofClass(row['proof_class']),
                    amount=Money.from_minor_units(signed, currency), document=source['id']))
                digest = source['sha256_at_ingestion']
                if source['id'] in sources and sources[source['id']].sha256 != digest:
                    raise LedgerSummaryError('Exhibit source hashes conflict.')
                sources[source['id']] = SourceDocument(identifier=source['id'], sha256=digest)
                source_map[source['id']] = source.get('evidence_file_id')
            tag = tag_exhibit(rows, list(sources.values()), content=ContentKind.calculation,
                              currency=currency)
            sections.append(dict(population=population, currency=currency, available=True,
                software_rule=tag.rule.value, content=tag.content.value,
                row_ids=[r['row']['key'] for r in captured], references=list(tag.references),
                net_postings_minor=str(tag.total.minor_units),
                amount_basis='Credits positive, debits negative: net account postings, not consolidated transfers or ownership.',
                proof_composition=[dict(proof_class=p.value, rows=tag.composition.counts[p],
                    net_minor=str(tag.composition.amounts[p].minor_units))
                    for p in tag.composition.counts],
                reasons=list(tag.reasons), outstanding_conditions=list(tag.conditions), caveats=[
                    'Some rows remain P3 and outside verified totals; consult their retained review and decision history. P3 can reflect incomplete coverage or interpretation even when arithmetic agrees.'
                    if v.startswith(CAVEAT_UNADJUDICATED_P3) else v for v in tag.caveats],
                sources=[dict(source_document_id=s.identifier, evidence_file_id=source_map[s.identifier],
                    sha256_at_ingestion=s.sha256, disclosure_recorded=False)
                    for s in tag.disclosure.documents]))
    return dict(schema='loupe.financial.ledger_exhibits/1', sections=sections,
        limitation='Section-specific software assessment using the existing exhibit rules. It does not determine legal admissibility or certify that records were disclosed. The full report also contains history and excluded readings; no single evidentiary category is asserted for the whole archive. Including source files is not a recorded disclosure to another party.')
