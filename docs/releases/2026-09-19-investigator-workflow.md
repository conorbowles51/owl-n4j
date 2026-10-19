# Simpler financial investigation workflow

Prepared for deployment on 19 September 2026 at the user’s request.

Investigators can import statements with reading flags still present, then work from a payment to its original, related payments, a comparison and a saved finding. Unknown amounts or dates are retained with their sources outside calculated totals. A later correction adds the completed payment exactly once and retains its original reading and author/reason.

The transaction table has Search and collapsed Filters, direct category editing, From/To navigation, and one action bar for selected payments. People, Follow money and Trends use the same supporting-payment actions. Selections survive pagination and narrower filters. Trends offers Over time and By category with explicit currency/account type and undated-payment access. Browser Back restores the previous financial view. Findings starts with title and explanation and attaches selected evidence automatically.

## Verification

- 76 focused backend checks passed for import, incomplete readings, later corrections, retries, access and recovery after reprocessing.
- 91 distinct targeted frontend unit checks passed across the implementation runs.
- The Chromium workflow passed: source, related outgoing payment, two-day comparison, EUR 5,000 difference, a saved finding with both source references, and return to the original search.
- Production build, TypeScript, changed-file lint and diff checks passed. No full application suite was repeated for deployment.
- User guide, step-by-step testing pack and light-mode screenshots are updated.

Backend tests use isolated test databases. The browser workflow uses actual components with synthetic API responses and an explicitly illustrative statement image. These checks do not establish extraction accuracy for all statement types or successful processing of the previously failed production batch. Deployed version and service checks must be recorded separately after publication; team testing remains necessary.

## Deployment scope

The existing deployment branch is `integration/evidence-main-reunion`. This release uses existing database columns for retained reading issues and incomplete records; it adds no migration. Deploy frontend and backend together. Preserve the ordinary last-good deployment rollback mechanism. Do not delete evidence, retry real imports or alter case records merely to verify the release.
