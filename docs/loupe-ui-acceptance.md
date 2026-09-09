# Loupe UI and practical workflow acceptance

Current focus agreed with Neil on 9 September 2026: finish a usable PDF import →
review → correction → analysis → export journey. Implement the saved design as
part of that journey, not as an unspecified finishing phase. Existing completed
work stays visible; broader features remain outstanding. Do not silently replace
this milestone with more tracing methods or transfer-matching infrastructure.

Design sources: `bundle/docs/13-target-state-financial-forensics.md` §10,
`bundle/docs/11-v1-learnings-into-loupe.md`, `docs/financial-handoff.md` settled
rules, and the running state. The March frontend design-system draft and the
separate Loupes collection design are not by themselves an agreed financial layout.

## Practical journey

- [ ] Upload a copy of a supplied real PDF through the application and follow its
  processing state. Preserve original files. Keep testing isolated and offline
  until a provider setup is explicitly selected.
- [ ] Reach stored source rows from that upload without fixture database seeding.
- [x] Review existing saved candidate values beside their source image; choose
  a column to highlight without first requesting a numeric/date assessment.
  Desktop side-by-side and narrow stacking checked against a synthetic PDF.
- [ ] Verify this source/review interaction on the supplied real PDFs.
- [ ] Resolve/reject a bounded, manually checked real-PDF sample, preserve source
  and decision history, and finalize it without implying complete extraction.
- [ ] Correct a sample, verify analysis eligibility and exact export contents.
- [ ] Give Neil one clear entry point and repeatable steps through the journey.

## Full analytical UI (retained beyond the first milestone)

- [ ] Ledger: full filtering/sorting, visible reliability and corrected/original
  distinction, totals with their included population, reproducible export state.
- [ ] Account continuity timeline: verified periods, held periods, gaps/overlaps
  visible together with navigation to the relevant statement.
- [ ] Quantitative money flow: select parties or a group; incoming/outgoing and
  internal transfers, internal counted once; divergent counterparty chart.
- [ ] Relationship graph: connected payment paths, complementary to amount charts.
- [ ] Tracing: method comparison, expansion across accounts, source-row/page
  navigation, explicit assumptions and missing evidence. Single-account initial
  UI exists; this does not complete the planned trace view.
- [ ] Case timeline: transactions correlated with events from other evidence.
- [ ] Pattern hypotheses: attached supporting rows, no automatic conclusions.
- [ ] From every total to rows, and from rows to source images when a measured
  location exists. Missing locators must remain explicit.
- [ ] Export: same scope/values, originals and decisions, appropriate limitations.

Current visual state is functional, not final. The existing Loupe shell is retained.
Backend test counts do not establish completion of these user journeys.
