"""Prepare blank source-bound review drafts; never infer transaction ground truth."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

MAX_SOURCE_BYTES = 128 * 1024 * 1024


def source_record(path):
    with path.open('rb') as source:
        import os
        before = os.fstat(source.fileno())
        if before.st_size > MAX_SOURCE_BYTES:
            raise ValueError('A source PDF exceeds 128 MiB.')
        prefix = source.read(5)
        if prefix != b'%PDF-':
            raise ValueError('Review sources must be original PDF files.')
        digest = hashlib.sha256(prefix)
        size = len(prefix)
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            size += len(chunk)
            if size > MAX_SOURCE_BYTES:
                raise ValueError('A source PDF exceeds 128 MiB.')
            digest.update(chunk)
        after = os.fstat(source.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or size != before.st_size:
        raise ValueError('Source changed during hashing; no review package was prepared.')
    return dict(filename=path.name, source_sha256=digest.hexdigest(), byte_count=size)


def prepare(sources, *, corpus_id, corpus_version, output):
    if output.exists():
        raise ValueError('Review directory must be new.')
    if not 1 <= len(sources) <= 1000 or not 1 <= len(corpus_id) <= 256 or not 1 <= len(corpus_version) <= 256:
        raise ValueError('Specify a corpus ID/version and one to 1000 source PDFs.')
    records = [source_record(path) for path in sources]
    if len({record['source_sha256'] for record in records}) != len(records):
        raise ValueError('The same source bytes were selected more than once.')
    directory = Path(tempfile.mkdtemp(prefix='.review-drafts-', dir=output.parent))
    try:
        def save(name, value):
            (directory / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
        save('source-inventory.json', dict(schema_version='loupe.extraction_review_inventory/1',
            corpus_id=corpus_id, corpus_version=corpus_version, sources=records,
            status='unreviewed_sources', limitation='Byte inventory only. These documents do not establish a representative corpus or ground truth. Original PDFs are not copied into this directory.'))
        for reader in ('first', 'second'):
            save(reader + '-reader-draft.json', dict(schema_version='loupe.extraction_reader_review/1',
                corpus_id=corpus_id, corpus_version=corpus_version, review_id=str(uuid4()),
                reviewer_id=None, label_status=None,
                documents=[dict(source_sha256=record['source_sha256'], complete_source_reviewed=False, rows=[]) for record in records]))
        (directory / 'README.md').write_text('''# Independent source review drafts

These are incomplete forms, not reviewed labels. Do not submit them as a release
corpus. Each reader receives the original PDFs, source inventory and their own
blank draft. Do not provide extraction predictions or the other reader's labels
before both first-pass reviews are retained.

1. Check the PDF hashes against the inventory. Original PDFs are not copied here.
2. Replace your draft's null reviewer_id with your actual stable reader identifier.
   Use distinct identifiers for the two readers. Keep the generated review_id.
3. Set label_status to independent_reader only for an actual independent review;
   use synthetic_test for synthetic exercises. Names and independence are supplied
   declarations and are not certified by these tools.
4. Read every selected source and label each actual transaction row. Use a stable
   source_id shared by readers, such as page-004/table-01/row-027 (physical PDF page and source table/row
   position). Do not renumber positions according to which rows you classify as
   transactions. The extraction predictions must later use the same IDs. Agree
   the positioning convention, not the transaction values.
5. Add each row as {"source_id":"page-004/table-01/row-027","fields":{...}}.
   Supported fields are date, amount_minor, currency, direction and account.
   All values are exact strings. Amounts use integer minor units, never decimal
   floats; direction uses credit/debit and currency uses its three-letter code.
   Record only fields supported by the source. An uncertain year or account
   identity must not be guessed. Readers must use the same field conventions.
6. Set complete_source_reviewed to true only after completing that whole PDF.
   Save each finished review separately; preserve the initial draft and originals.
7. Reconcile the two completed records with reconcile_financial_reference_reviews.py.
   Resolve every reported disagreement with the adjudication workflow described in
   docs/loupe-extraction-validation.md. Unresolved records never emit partial truth.

A blank draft deliberately fails the review validator: identity/status are null,
coverage is false and there are no truth rows. No source values were extracted or
supplied by the draft generator. The two documents alone are not a claim of
representative institutional/layout coverage. Field conventions and independent
review remain human responsibilities.
''')
        # Exclusive destination creation avoids replacing any existing directory.
        output.mkdir()
        for path in directory.iterdir():
            path.rename(output / path.name)
        return records
    finally:
        shutil.rmtree(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', type=Path, nargs='+')
    parser.add_argument('--corpus-id', required=True)
    parser.add_argument('--corpus-version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = prepare(args.sources, corpus_id=args.corpus_id, corpus_version=args.corpus_version, output=args.output)
    print(f'Prepared two incomplete review drafts for {len(records)} source PDFs. No labels generated and no originals copied.')


if __name__ == '__main__':
    main()
