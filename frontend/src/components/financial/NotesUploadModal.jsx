import { useState, useCallback, useMemo } from 'react';
import { X, Upload, Loader2, CheckCircle2, AlertCircle, FileText, Search } from 'lucide-react';
import { financialAPI } from '../../services/api';

/**
 * NotesUploadModal
 *
 * Allows investigators to upload a CSV of notes keyed by transaction ref_id.
 * Three steps: file select → preview → results.
 */
export default function NotesUploadModal({ isOpen, onClose, caseId, transactions, onComplete }) {
  const [file, setFile] = useState(null);
  const [parsedRows, setParsedRows] = useState([]);
  const [parseError, setParseError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [searchFilter, setSearchFilter] = useState('');

  // Build a set of known ref_ids for match preview
  const knownRefIds = useMemo(() => {
    const set = new Set();
    (transactions || []).forEach(t => { if (t.ref_id) set.add(t.ref_id.toUpperCase()); });
    return set;
  }, [transactions]);

  const reset = useCallback(() => {
    setFile(null);
    setParsedRows([]);
    setParseError(null);
    setUploading(false);
    setResult(null);
    setUploadError(null);
    setSearchFilter('');
  }, []);

  const handleClose = () => {
    if (uploading) return;
    reset();
    onClose();
  };

  // Client-side CSV parse for preview
  const handleFileChange = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setParseError(null);
    setResult(null);
    setUploadError(null);

    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        let text = ev.target.result;
        // Strip BOM
        if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);

        const lines = text.split(/\r?\n/).filter(l => l.trim());
        if (lines.length < 2) {
          setParseError('CSV must have a header row and at least one data row.');
          return;
        }

        const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/['"]/g, ''));
        const refCol = headers.findIndex(h => ['ref_id', 'ref', 'reference'].includes(h));
        const notesCol = headers.findIndex(h => ['notes', 'note', 'comment'].includes(h));

        if (refCol === -1) {
          setParseError('CSV must have a "ref_id" or "ref" column.');
          return;
        }
        if (notesCol === -1) {
          setParseError('CSV must have a "notes" or "note" column.');
          return;
        }

        const rows = [];
        for (let i = 1; i < lines.length; i++) {
          const cols = lines[i].split(',').map(c => c.trim().replace(/^["']|["']$/g, ''));
          const refId = (cols[refCol] || '').toUpperCase();
          const notes = cols[notesCol] || '';
          if (refId && notes) {
            rows.push({
              ref_id: refId,
              notes,
              matched: knownRefIds.has(refId),
            });
          }
        }

        setParsedRows(rows);
        if (rows.length === 0) {
          setParseError('No valid rows found (need both ref_id and notes).');
        }
      } catch {
        setParseError('Failed to parse CSV. Make sure the file is a valid CSV.');
      }
    };
    reader.readAsText(f);
  };

  const matchedCount = parsedRows.filter(r => r.matched).length;
  const unmatchedCount = parsedRows.filter(r => !r.matched).length;

  const filtered = useMemo(() => {
    if (!searchFilter.trim()) return parsedRows;
    const q = searchFilter.toLowerCase();
    return parsedRows.filter(r =>
      r.ref_id.toLowerCase().includes(q) || r.notes.toLowerCase().includes(q)
    );
  }, [parsedRows, searchFilter]);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const res = await financialAPI.uploadNotes(caseId, file);
      setResult(res);
      if (onComplete) onComplete();
    } catch (err) {
      setUploadError(err.message || 'Upload failed');
    }
    setUploading(false);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-[700px] max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-light-200">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-owl-blue-600" />
            <span className="text-sm font-semibold text-light-800">Upload Investigator Notes</span>
          </div>
          <button onClick={handleClose} className="p-1 text-light-400 hover:text-light-600 rounded" disabled={uploading}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
          {/* Result view */}
          {result && (
            <div className="space-y-4">
              <div className="flex flex-col items-center py-6 gap-2">
                <CheckCircle2 className="w-8 h-8 text-green-500" />
                <p className="text-sm font-medium text-light-800">Notes uploaded successfully</p>
              </div>
              <div className="flex items-center gap-4 p-3 bg-light-50 rounded-lg text-xs text-light-600">
                <div><span className="font-semibold text-green-600">{result.matched}</span> matched</div>
                <div><span className="font-semibold text-light-800">{result.total}</span> total rows</div>
              </div>
              {result.unmatched_ref_ids?.length > 0 && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                  <p className="text-xs font-medium text-amber-800 mb-1">Unmatched ref IDs ({result.unmatched_ref_ids.length}):</p>
                  <p className="text-xs text-amber-700 font-mono">{result.unmatched_ref_ids.join(', ')}</p>
                </div>
              )}
            </div>
          )}

          {/* Upload error */}
          {uploadError && (
            <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg mb-4">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
              <p className="text-xs text-red-700">{uploadError}</p>
            </div>
          )}

          {/* File picker + preview */}
          {!result && (
            <>
              <div className="mb-4">
                <p className="text-xs text-light-600 mb-2">
                  Upload a CSV with <code className="bg-light-100 px-1 py-0.5 rounded text-[10px]">ref_id</code> and
                  <code className="bg-light-100 px-1 py-0.5 rounded text-[10px] ml-1">notes</code> columns.
                  Optional: <code className="bg-light-100 px-1 py-0.5 rounded text-[10px]">interviewer</code>,
                  <code className="bg-light-100 px-1 py-0.5 rounded text-[10px] ml-1">date</code>,
                  <code className="bg-light-100 px-1 py-0.5 rounded text-[10px] ml-1">question</code>,
                  <code className="bg-light-100 px-1 py-0.5 rounded text-[10px] ml-1">answer</code>.
                </p>
                <label className="flex items-center gap-2 px-3 py-2 border-2 border-dashed border-light-300 rounded-lg cursor-pointer hover:border-owl-blue-400 hover:bg-light-25 transition-colors">
                  <Upload className="w-4 h-4 text-light-400" />
                  <span className="text-xs text-light-600">{file ? file.name : 'Choose CSV file...'}</span>
                  <input type="file" accept=".csv,.txt" onChange={handleFileChange} className="hidden" />
                </label>
              </div>

              {parseError && (
                <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg mb-4">
                  <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                  <p className="text-xs text-red-700">{parseError}</p>
                </div>
              )}

              {parsedRows.length > 0 && (
                <>
                  {/* Stats */}
                  <div className="flex items-center gap-4 mb-3 p-3 bg-light-50 rounded-lg text-xs text-light-600">
                    <div><span className="font-semibold text-light-800">{parsedRows.length}</span> rows</div>
                    <div><span className="font-semibold text-green-600">{matchedCount}</span> matched</div>
                    {unmatchedCount > 0 && (
                      <div><span className="font-semibold text-amber-600">{unmatchedCount}</span> unmatched</div>
                    )}
                  </div>

                  {/* Search */}
                  <div className="relative mb-3">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
                    <input
                      type="text"
                      placeholder="Filter rows..."
                      value={searchFilter}
                      onChange={(e) => setSearchFilter(e.target.value)}
                      className="w-48 text-xs pl-8 pr-3 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
                    />
                  </div>

                  {/* Preview table */}
                  <div className="border border-light-200 rounded-lg overflow-hidden max-h-[300px] overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-light-50 sticky top-0">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium text-light-600 w-[15%]">Ref ID</th>
                          <th className="text-left px-3 py-2 font-medium text-light-600 w-[12%]">Status</th>
                          <th className="text-left px-3 py-2 font-medium text-light-600">Notes</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-light-100">
                        {filtered.map((row, i) => (
                          <tr key={row.ref_id + '-' + i} className="hover:bg-light-25">
                            <td className="px-3 py-2 font-mono text-light-700">{row.ref_id}</td>
                            <td className="px-3 py-2">
                              {row.matched ? (
                                <span className="px-1.5 py-0.5 bg-green-50 text-green-700 rounded text-[10px] font-medium">Match</span>
                              ) : (
                                <span className="px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded text-[10px] font-medium">No match</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-light-600 truncate max-w-0" title={row.notes}>{row.notes}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end px-5 py-3 border-t border-light-200 bg-light-25 gap-2">
          {result ? (
            <button
              onClick={handleClose}
              className="px-4 py-1.5 text-xs text-white bg-owl-blue-600 rounded hover:bg-owl-blue-700"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={handleClose}
                disabled={uploading}
                className="px-3 py-1.5 text-xs text-light-600 border border-light-200 rounded hover:bg-light-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                disabled={uploading || parsedRows.length === 0}
                className="px-4 py-1.5 text-xs text-white bg-owl-blue-600 rounded hover:bg-owl-blue-700 disabled:opacity-50 flex items-center gap-1.5"
              >
                {uploading ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-3 h-3" />
                    Upload Notes
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
