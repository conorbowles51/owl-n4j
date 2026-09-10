# Reproducing a captured tracing scenario

The single-account and cross-account screens offer the original scenario JSON,
a readable HTML report, and a tracing audit ZIP. The ZIP contains the exact
scenario bytes, a recalculation comparison, recorded processing and review
support, and a file hash manifest. Download preparation records the authenticated
user, time and selected marking. These are separate from the historical scenario.

The original snapshot and assumptions are used for recalculation. Current case
rows are not substituted, and no ledger writes or provider calls occur. All
selected calculation methods are rerun with the installed code. The original
and current code fingerprints are retained. A changed result, added output field,
or changed explanation is reported at its JSON path. Differences do not necessarily
mean money changed: older asset reports, for example, lack newer allocation metadata.

The browser refuses a bundle returned for another case, scenario or marking, and
checks the archive digest before downloading. A replay difference prevents that
scenario from being packaged as a matching audit bundle; its original JSON remains
available and the offline command below explains the differences.

## Offline check

Use the project's backend virtual environment:

```sh
data/local-runtime/backend-venv/bin/python scripts/replay_financial_trace.py \
  /path/to/scenario.json --output /path/to/new-replay-report.json
```

Optionally supply `--expected-sha256` with the digest retained separately when the
scenario was generated. Exit 0 means the captured output matches recalculation;
exit 2 means output differs and the report lists up to 100 exact paths, with a
total difference count. Invalid input also fails. Output files are created only
when new; the command does not overwrite the original or an existing report.

Matching output is not source authentication, verification of assumptions or a
legal determination. Embedded hashes alone cannot establish authorship. This check
does not re-read original source files or recreate a historical runtime.

## Selected scenarios and measured validation

The offline assembler can combine up to eight matching scenarios from one case:

```sh
data/local-runtime/backend-venv/bin/python scripts/assemble_financial_trace_support.py \
  /path/to/first-scenario.json /path/to/second-scenario.json \
  --output /path/to/new-tracing-support.zip
```

Each retains its own snapshot and filter scope. They are not combined into a new
ledger. Duplicate scenarios and cross-case combinations are refused. Original
source PDFs are not added individually by this assembler. Optional `--ledger-export`
retains an existing verified ledger ZIP unchanged, including any source PDFs that
were selected in that ledger export. Its captured scope remains separate.

Optional `--validation-corpus /path/to/reviewed-evaluation.json` includes the supplied
labels and recalculated measurements using the contract in
[extraction validation](loupe-extraction-validation.md). Synthetic labels stay
synthetic. These measurements describe that supplied corpus; correspondence to
the case's documents, extraction versions, independent review and representative
coverage are not inferred. No validation is claimed when none is supplied.

This remains expert preparation support. Complete case custody, every human
decision, the complete historical component manifest, independent validation,
and a signed expert opinion are not established by assembling these files.

## Verify a complete saved support package

```sh
data/local-runtime/backend-venv/bin/python scripts/verify_financial_trace_support.py \
  /path/to/saved-tracing-support.zip --output /path/to/new-verification.json
```

The verifier checks every declared file's size and SHA-256, rejects unsafe paths,
duplicate/missing/unlisted entries and ambiguous manifest JSON, and rebuilds the
support using the current installed code. It recalculates scenario results and
attached measurements, reconciles retained reader records and checks an attached
ledger archive and its recorded audit chain. Nothing is extracted to disk or
written into the original package. The combined compressed/uncompressed limit is
256 MiB, with tighter limits on individual members.

A matching rebuild returns exit0. When only the replay code revision changed,
`verified_bytes_matching_calculations` retains both revisions explicitly. Other
derived-content or manifest changes return exit2 with named differences for review;
malformed inputs fail without a success report. Earlier exports can differ because
support metadata changed between software revisions; differences are not silently
rewritten or presented as a matching export.

Optional `--expected-sha256` checks an archive digest retained independently at
capture. A digest derived from the same untrusted file adds no independent proof.
Internal hashes and recalculation cannot authenticate authorship, evidence truth,
reviewer independence or complete custody.
