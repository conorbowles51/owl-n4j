# Comparing saved ledger exports

Open **Compare saved ledger exports** in the main ledger export panel. Choose two
Loupe ZIP exports from the same case, then **Compare captured exports**. The files
are checked on the server and closed after comparison; they are not added as case
evidence and no current ledger readings are changed. Each input is limited to
128 MiB, including a 128 MiB limit on its uncompressed members.

The result distinguishes:

- Changed account/date/table filters or wider-history selection. A reading absent
  from a narrower capture is not described as a deletion from the case.
- Changed captured readings, decisions and PDF review records, identified by their
  stable IDs and exact changed field paths in the downloadable comparison.
- Export preparation and packaging differences, including generating user/time,
  marking, component/report hashes and export code version, separately from the
  evidence and review content.

The full comparison retains scopes, both archive/snapshot hashes, before/after
export versions, record IDs and bounded field-path diagnostics. Truncation is
explicitly identified. Changing either selected file clears the previous result.
The display shows at most 20 changed reading references; the download contains
all identified records within the report limit.

Every listed archive member is checked against its manifest byte count and hash,
including bundled original sources and optional PDF/expert-support files. Duplicate
or unsafe paths, unlisted files, mismatched case references and inconsistent hashes
are refused. Files are never extracted into the server's evidence directory.
Hashes establish consistency with the supplied manifest, not who created it or the
truth or custody of its contents. Changed fields alone do not establish why a change
was made; consult the retained review reasons and originals.

The same comparison can run offline in the backend virtual environment:

```sh
data/local-runtime/backend-venv/bin/python scripts/compare_financial_exports.py \
  /path/to/earlier.zip /path/to/later.zip --output /path/to/new-comparison.json
```

The command requires a new output path and preserves both input archives. It makes
no database or provider calls. Unlike a regression gate, an ordinary difference
is a successful comparison result rather than a process error.

Read-only local acceptance: `scripts/check_local_export_comparison.cjs` compares
the retained 104-reading real-statement export with an account-filtered capture.
It identifies 61 readings absent from the narrower scope and zero changed readings,
verifies the downloaded explanation, and checks stale-result clearing. No financial
state is changed.
