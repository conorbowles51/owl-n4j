/**
 * Normalize a stored_path from an evidence record to a relative path from the case root.
 *
 * stored_path may be:
 *  - Absolute: "/home/user/app/ingestion/data/{caseId}/file.txt"
 *  - Relative with prefix: "ingestion/data/{caseId}/file.txt"
 *  - Relative with case_id: "{caseId}/file.txt"
 *  - Already relative: "file.txt" or "subfolder/file.txt"
 *
 * Returns the path relative to the case root (e.g., "file.txt" or "subfolder/file.txt").
 */
export function normalizeStoredPath(storedPath, caseId) {
  if (!storedPath) return '';
  let p = storedPath.replace(/\\/g, '/');

  // Handle absolute paths: find "ingestion/data/{caseId}/" anywhere in the path
  if (caseId) {
    const marker = `ingestion/data/${caseId}/`;
    const idx = p.indexOf(marker);
    if (idx !== -1) {
      return p.substring(idx + marker.length).replace(/^\/+|\/+$/g, '');
    }
    // Also try just "/{caseId}/" for other absolute path formats
    const caseMarker = `/${caseId}/`;
    const caseIdx = p.lastIndexOf(caseMarker);
    if (caseIdx !== -1) {
      return p.substring(caseIdx + caseMarker.length).replace(/^\/+|\/+$/g, '');
    }
  }

  // Fallback: strip known relative prefixes
  p = p.replace(/^ingestion\/data\//, '');
  if (caseId && p.startsWith(`${caseId}/`)) {
    p = p.substring(caseId.length + 1);
  }

  return p.replace(/^\/+|\/+$/g, '');
}
