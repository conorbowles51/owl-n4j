# Playlist: Loupe Evidence Test Slice
Mode: order

## Phase 1: Simplify document processing status
Complete the full document-status cleanup as one testable increment; all other plan tickets remain unsequenced and retain their plan order after this playlist.

1. Remove Stale from the status filter and document-status vocabulary
2. Rename internal processing_stale UI treatment to ‘Reprocessing recommended’ or approved copy with an explanation
3. Keep primary state as unprocessed/processing/processed/failed and show why configuration changes require reprocess
4. Update API/docs/tests without losing the internal invalidation mechanism

## Phase 2: Make duplicate-upload handling non-destructive
Remove the unsafe shortcut, establish explicit duplicate semantics, preserve existing evidence, and finish with regression coverage.

1. Remove the checkbox/state from the general upload dropdown
2. Detect duplicate files/reports by stable hash/report identity and present a post-detection choice if genuinely needed
3. Define skip, link existing, reprocess and supersede semantics with non-destructive defaults
4. Protect existing report data/links during any approved supersede flow and add audit
5. Add duplicate-name, same-content, changed-content and concurrent-upload tests
