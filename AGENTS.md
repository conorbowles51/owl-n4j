# Loupe working agreements

## Current release authorisation

- On 22 September 2026 the user explicitly instructed: **“Finish the work”** and **“Give me an eta then commit and push all”**, following their instruction to push and deploy. This lifts the earlier hold for all agreed, completed and verified code changes in this task, including financial implementation. Complete the connected workflows before publication; do not silently reduce the release to a subset.
- Keep client/financial data, source PDFs, screenshots, exports and credentials out of Git. “All” refers to relevant implementation, synthetic tests and operational documentation, not unrelated workspace files or evidence.
- Deployment must account for active ingestions. Do not cancel the team's jobs as a side effect of releasing a fix; establish a safe worker transition and verify the deployed revision and workflows.

## Earlier deployment hold (superseded by the authorisation above)

- **Do not push or deploy any changes until the user explicitly lifts this hold.** The team is actively ingesting; this instruction was given on 22 September 2026 and overrides earlier push/deployment authorization.
- Continue authorized development and testing locally. Do not restart live services, change live worker or queue configuration, or interrupt, move or retry the team's running ingestion as part of this work.
- A request for progress, testing or further implementation does not lift the hold. Wait for an explicit instruction to push/deploy before publishing changes.

## Financials must not be committed or pushed

- **Do not commit or push financials to the repository.** This is an explicit user instruction, added 22 September 2026.
- Keep financial documents, bank statements, screenshots of financial records, extracted financial data, transaction exports, case data and credentials out of Git staging, commits and pushes. Local access for an authorized investigation does not authorize repository publication.
- Financial implementation work must also remain local under this instruction. Do not commit, push, or trigger a repository-based deployment of the current financial work unless the user subsequently gives explicit authorization for the specific code-only changes. Earlier general deployment instructions do not override this restriction.
- Never use broad staging commands such as `git add .` or `git add -A` in this workspace. Any separately authorized commit requires an explicit file list and inspection of the staged contents for financial or client material.
- Do not delete local originals or rewrite repository history to enforce this rule without separate authorization.

## Investigator workflows are the acceptance standard

- Treat product requests as complete investigator workflows, not isolated features. Before editing, identify the investigator's objective, starting screen, actions, visible state changes, destination, recovery path and way back.
- Preserve requirements agreed with the user across follow-ups. For financial work, read `docs/financial-workflows/README.md` and `docs/alex-financial-acceptance.md`; keep the flow reference and unresolved acceptance items current. Do not silently reduce scope to the newest screenshot or easiest control.
- Make the interface explain itself: the current case/file/account/period, what is saved or pending, what the next action does, and what changed after it. Actions must reveal and focus or scroll to their destination. Do not rely on an explanation in chat to make an unclear screen usable.
- Keep common actions discoverable from the working screen. Large PDFs and batches must not bury navigation, import, removal or recovery controls beneath hundreds of rows.
- Validate the complete affected journey in a real browser at a realistic viewport, including returning, reopening, existing data and failure states where applicable. Component tests and a successful build alone do not establish workflow acceptance.
- When live deployment is authorized, verify the deployed revision and repeat the affected journey on the live deployment. Distinguish implemented, locally tested, deployed and live verified. Do not claim all concerns resolved when acceptance items remain unverified.
- Preserve source evidence and investigator edits. Preview destructive operations; do not delete or reprocess live case data merely to demonstrate a control without authorization for those records.

## Continuity

- Record accepted decisions and remaining work in the relevant repository acceptance document, with evidence and limitations. Carry them forward across sessions rather than asking the user to repeat them.
- Explain outcomes and remaining gaps plainly. Avoid serial promises and partial-completion claims. Fix the underlying workflow and show the result.

These instructions record the user's standing requirements. They do not replace subsequent user instructions or create a new approval requirement for already authorized work.
