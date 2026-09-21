# Loupe working agreements

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
