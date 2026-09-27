# Keep accepted import progress visible during connection failures

An intermittent batch refresh failure replaced the whole review with a generic error, hiding the last confirmed import receipt while the server continued saving statements. Investigators could no longer distinguish a failed status read from a failed import.

The batch now keeps its last successful response visible, focuses a plainly worded warning that those counts may be out of date, and offers a read-only refresh. Import and review actions that depend on current readiness are unavailable until a successful refresh. This does not replay an import, cancel server work or treat cached counts as completion. Initial load failures still offer recovery without inventing results.

Local validation: 29 batch unit tests and nine Chromium navigation journeys passed. The new browser journey covers refresh failure, retained progress, retry and restored controls; it was rerun after focus/layout changes and the screenshot inspected. Scoped lint and TypeScript checks passed. Production build status is recorded with the release checkpoint. Existing React act warnings in the browser suite are not test failures. No client documents or data are part of this change.

Deployment and live acceptance remain separate. An existing bulk import must finish safely before any guarded release can restart services. The network failure's underlying cause is not established by this interface repair.

## Access-check wording follow-up

A statement no longer reports a confirmed lack of editing permission while the access request is still loading or has failed. These states explain that access is being checked or must be checked again, preserving the open review. A verified read-only response retains its explicit permission message. All three states continue to block import; no permission check is relaxed. Sixty-five statement unit tests pass, including the three distinct access outcomes. Live acceptance remains pending release. This follow-up also corrects an unsupported Testing Library option in the earlier regression assertion.
