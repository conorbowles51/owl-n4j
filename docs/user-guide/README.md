# Maintaining the financial user guide

The user-facing source is [financial-user-guide.md](financial-user-guide.md).
The portable [HTML guide](financial-user-guide.html) embeds the screenshots and works without a server.
The application loads its copy inside the Financial guide modal. That button sits above the financial tabs, outside the scrolling content.

After editing the Markdown or screenshots, run from the repository root:

```sh
node scripts/build_financial_user_guide.cjs
```

The builder uses existing frontend dependencies and writes:

- `docs/user-guide/financial-user-guide.html`
- `frontend_v2/public/docs/financial-guide/financial-user-guide.md`
- `frontend_v2/public/docs/financial-guide/images/`

Commit the generated public files with the source changes so deployment serves the same edition. The user guide contains no production credentials or real case identifiers. Screenshots use existing synthetic development cases; do not recreate or change those cases merely to take screenshots.

## Coverage and verification

The guide covers the reviewed PDF workflow, page scans and optional model proposals, saved reviews and statement drafts, finalization, custody, ledger filtering and corrections, statement checks and coverage, duplicates, account and payment identities, documentary analysis, transfer scenarios, patterns and claims, single-account and cross-account tracing, asset/resale assumptions, indirect workpapers, exports, package assembly/verification, resuming work and troubleshooting.

Instructions were checked against the current financial components and saved browser acceptance procedures. They distinguish features exposed to case users from operator-controlled native ingestion, external timestamping and independent extraction-validation preparation. They do not describe unfinished runtime inventories as available functionality.

On 10 September 2026:

- Production frontend build passed.
- 37 financial-page tests passed; scoped lint passed.
- Browser check confirmed the button across all 13 financial tabs.
- Desktop and mobile modal layouts inspected.
- Contents targets, loaded image, Escape dismissal, returned keyboard focus and preservation of an unfinished transfer-date field checked.
- Financial and other case mutations blocked during documentation browser checks.

This is documentation and UI verification, not a new claim about extraction accuracy or readiness of an untested server deployment.
