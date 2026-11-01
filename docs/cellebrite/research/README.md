# Research behind the Cellebrite plan

Nine read-only research reports. Reports 1 to 8 were written on 2026-10-29, before the plan and
specifications; report 9, written on 2026-11-01, holds the sources behind spec 07. They are kept so any conclusion in the plan can be checked against its source without redoing the research.

**They are a snapshot.** Where a report and the plan or a specification differ, the plan and
specifications govern: several report figures were corrected later (for example the large case has 10
reports, not 11 phones; the C8 database folder has no files on disk; `InstantMessage.SMSC` is not the
sender). Corrections are noted at the top of each affected report.

Case content has been removed: no names, phone numbers, message text or evidence numbers. Line
citations refer to the branch named in each report as it stood on 2026-10-29.

| # | Report | Question it answered |
|---|---|---|
| 1 | [v1 code assessment](01-v1-code-assessment.md) | How v1's Cellebrite subsystem works end to end, with the ingestion pipeline in depth; strengths and defects ranked |
| 2 | [v1 commit history](02-v1-commit-history.md) | How v1 evolved from April to July 2026; what broke, how it was fixed, the lessons |
| 3 | [Sample extraction structure](03-sample-extraction-structure.md) | What C3, C9 and C8 actually are, structurally; what parsers would recognise |
| 4 | [Formats and the market](04-formats-and-market.md) | Cellebrite products and output formats; which tools read them; defense-side problems; gaps; licensing |
| 5 | [Loupe landing zone](05-loupe-landing-zone.md) | How Loupe ingests evidence, its provenance, correction and proof-class patterns, and where a phone port fits |
| 6 | [v1 screens and feedback trajectory](06-v1-screens-and-feedback.md) | Every v1 phone screen, why it exists, what Alex's feedback drove, where screens overlap |
| 7 | [Competitor features](07-competitor-features.md) | Feature-by-feature comparison of review platforms and where a focused platform can be better |
| 8 | [Loupe case-wide screens](08-loupe-case-wide-screens.md) | Loupe's existing screens, which accept phone data already, which need work, and defects found |
| 9 | [User experience and investigative methods: sources](09-ux-and-methods.md) | Which review-tool patterns exist and which products show them, published usability scores, studies of examiners and analysts, usability-method figures, and the investigative practice sources behind spec 07, each checked |

Also used: Alex's own v1 testing-hub entries (`/home/conorbowles51/app_v2/data/testing-feedback.json`
on the VM; titles and verdicts are in spec 03 section 17.0) and the structure-only measurements in
`../measurements/`.
