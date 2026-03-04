import { useState, useCallback } from 'react';
import { X, Upload, Loader2, CheckCircle2, AlertCircle, FileSpreadsheet } from 'lucide-react';
import { financialAPI } from '../../services/api';

/**
 * Bulk Correction Modal
 *
 * Allows users to upload a CSV/XLSX file with columns: name, new_amount, correction_reason
 * Previews matched/unmatched transactions, then submits corrections.
 */
export default function BulkCorrectionModal({ isOpen, onClose, caseId, transactions, onComplete }) {
  const [file, setFile] = useState(null);
  const [parsed, setParsed] = useState(null); // [{name, new_amount, correction_reason}]
  const [parseError, setParseError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState(null);

  const txnNameLookup = useCallback((name) => {
    if (!name) return null;
    const lower = name.trim().toLowerCase();
    return transactions.find(t => (t.name || '').trim().toLowerCase() === lower);
  }, [transactions]);

  const handleFileSelect = async (e) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setParsed(null);
    setParseError(null);
    setResults(null);

    try {
      const ext = selected.name.split('.').pop().toLowerCase();
      if (ext === 'csv' || ext === 'tsv') {
        const text = await selected.text();
        const rows = parseCSV(text, ext === 'tsv' ? '\t' : ',');
        setParsed(rows);
      } else if (ext === 'xlsx' || ext === 'xls') {
        const rows = await parseXLSX(selected);
        setParsed(rows);
      } else {
        setParseError('Unsupported file type. Please use CSV, TSV, or XLSX.');
      }
    } catch (err) {
      setParseError(`Failed to parse file: ${err.message}`);
    }
  };

  const parseCSV = (text, delimiter = ',') => {
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length < 2) throw new Error('File must have a header row and at least one data row');

    const headerLine = lines[0];
    const headers = headerLine.split(delimiter).map(h => h.trim().toLowerCase().replace(/['"]/g, ''));

    // Find column indices
    const nameIdx = headers.findIndex(h => h === 'name' || h === 'transaction' || h === 'transaction_name' || h === 'description');
    const amountIdx = headers.findIndex(h => h === 'new_amount' || h === 'amount' || h === 'correct_amount' || h === 'corrected_amount');
    const reasonIdx = headers.findIndex(h => h === 'correction_reason' || h === 'reason' || h === 'note' || h === 'notes');

    if (nameIdx === -1) throw new Error('Could not find a "name" column. Expected: name, transaction, or description');
    if (amountIdx === -1) throw new Error('Could not find an "amount" column. Expected: new_amount, amount, or correct_amount');

    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(delimiter).map(c => c.trim().replace(/^["']|["']$/g, ''));
      const name = cols[nameIdx] || '';
      const rawAmount = (cols[amountIdx] || '').replace(/[$,]/g, '');
      const amount = parseFloat(rawAmount);
      const reason = reasonIdx >= 0 ? (cols[reasonIdx] || 'Bulk correction') : 'Bulk correction';

      if (!name || isNaN(amount)) continue;
      rows.push({ name, new_amount: amount, correction_reason: reason });
    }

    if (rows.length === 0) throw new Error('No valid data rows found');
    return rows;
  };

  const parseXLSX = async (file) => {
    // Use SheetJS loaded from CDN
    if (!window.XLSX) {
      // Dynamically load SheetJS
      await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.sheetjs.com/xlsx-0.20.1/package/dist/xlsx.full.min.js';
        script.onload = resolve;
        script.onerror = () => reject(new Error('Failed to load XLSX parser. Try using CSV format instead.'));
        document.head.appendChild(script);
      });
    }

    const data = await file.arrayBuffer();
    const workbook = window.XLSX.read(data, { type: 'array' });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const jsonData = window.XLSX.utils.sheet_to_json(sheet, { defval: '' });

    if (jsonData.length === 0) throw new Error('No data rows found in spreadsheet');

    // Normalize headers
    const firstRow = jsonData[0];
    const keys = Object.keys(firstRow).map(k => k.toLowerCase().trim());
    const origKeys = Object.keys(firstRow);

    const nameKey = origKeys.find((_, i) => ['name', 'transaction', 'transaction_name', 'description'].includes(keys[i]));
    const amountKey = origKeys.find((_, i) => ['new_amount', 'amount', 'correct_amount', 'corrected_amount'].includes(keys[i]));
    const reasonKey = origKeys.find((_, i) => ['correction_reason', 'reason', 'note', 'notes'].includes(keys[i]));

    if (!nameKey) throw new Error('Could not find a "name" column');
    if (!amountKey) throw new Error('Could not find an "amount" column');

    const rows = [];
    for (const row of jsonData) {
      const name = String(row[nameKey] || '').trim();
      const rawAmount = String(row[amountKey] || '').replace(/[$,]/g, '');
      const amount = parseFloat(rawAmount);
      const reason = reasonKey ? String(row[reasonKey] || 'Bulk correction').trim() : 'Bulk correction';

      if (!name || isNaN(amount)) continue;
      rows.push({ name, new_amount: amount, correction_reason: reason });
    }

    if (rows.length === 0) throw new Error('No valid data rows found');
    return rows;
  };

  const handleSubmit = async () => {
    if (!parsed || parsed.length === 0) return;
    setSubmitting(true);
    try {
      const result = await financialAPI.bulkCorrect(caseId, parsed);
      setResults(result);
      if (onComplete) onComplete();
    } catch (err) {
      setParseError(`Failed to apply corrections: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const matched = parsed ? parsed.filter(r => txnNameLookup(r.name)) : [];
  const unmatched = parsed ? parsed.filter(r => !txnNameLookup(r.name)) : [];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h2 className="text-lg font-semibold text-owl-blue-900">Import Bulk Corrections</h2>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded" disabled={submitting}>
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Results view */}
          {results ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-green-700">
                <CheckCircle2 className="w-5 h-5" />
                <span className="font-medium">Corrections Applied</span>
              </div>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div className="bg-green-50 p-3 rounded-lg text-center">
                  <div className="text-2xl font-bold text-green-700">{results.corrected}</div>
                  <div className="text-xs text-green-600">Corrected</div>
                </div>
                <div className="bg-orange-50 p-3 rounded-lg text-center">
                  <div className="text-2xl font-bold text-orange-700">{results.not_found}</div>
                  <div className="text-xs text-orange-600">Not Found</div>
                </div>
                <div className="bg-red-50 p-3 rounded-lg text-center">
                  <div className="text-2xl font-bold text-red-700">{results.errors}</div>
                  <div className="text-xs text-red-600">Errors</div>
                </div>
              </div>
              {results.results && results.results.length > 0 && (
                <div className="max-h-60 overflow-y-auto border border-light-200 rounded-lg">
                  <table className="w-full text-xs">
                    <thead className="bg-light-50 sticky top-0">
                      <tr>
                        <th className="text-left p-2">Name</th>
                        <th className="text-left p-2">Status</th>
                        <th className="text-right p-2">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.results.map((r, i) => (
                        <tr key={i} className="border-t border-light-100">
                          <td className="p-2 truncate max-w-[200px]">{r.name}</td>
                          <td className="p-2">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              r.status === 'corrected' ? 'bg-green-100 text-green-700' :
                              r.status === 'not_found' ? 'bg-orange-100 text-orange-700' :
                              r.status === 'error' ? 'bg-red-100 text-red-700' :
                              'bg-light-100 text-light-600'
                            }`}>
                              {r.status}
                            </span>
                          </td>
                          <td className="p-2 text-right font-mono">
                            {r.new_amount != null ? `$${r.new_amount.toLocaleString()}` : r.reason || ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <>
              {/* File Upload */}
              <div>
                <p className="text-sm text-light-600 mb-2">
                  Upload a CSV or XLSX file with columns: <strong>name</strong>, <strong>amount</strong>, and optionally <strong>reason</strong>.
                </p>
                <div className="border-2 border-dashed border-light-300 rounded-lg p-6 text-center hover:border-owl-blue-400 transition-colors">
                  <input
                    type="file"
                    accept=".csv,.tsv,.xlsx,.xls"
                    onChange={handleFileSelect}
                    className="hidden"
                    id="bulk-correction-file"
                    disabled={submitting}
                  />
                  <label htmlFor="bulk-correction-file" className="cursor-pointer flex flex-col items-center gap-2">
                    <FileSpreadsheet className="w-8 h-8 text-owl-blue-600" />
                    <span className="text-sm text-light-600">
                      {file ? file.name : 'Click to select a file'}
                    </span>
                    <span className="text-xs text-light-500">CSV, TSV, or XLSX</span>
                  </label>
                </div>
              </div>

              {parseError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-red-600">{parseError}</p>
                </div>
              )}

              {/* Preview */}
              {parsed && (
                <div className="space-y-3">
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-green-700 font-medium">{matched.length} matched</span>
                    <span className="text-orange-700 font-medium">{unmatched.length} unmatched</span>
                    <span className="text-light-500">{parsed.length} total rows</span>
                  </div>

                  <div className="max-h-52 overflow-y-auto border border-light-200 rounded-lg">
                    <table className="w-full text-xs">
                      <thead className="bg-light-50 sticky top-0">
                        <tr>
                          <th className="text-left p-2">Name</th>
                          <th className="text-right p-2">New Amount</th>
                          <th className="text-left p-2">Reason</th>
                          <th className="text-center p-2">Match</th>
                        </tr>
                      </thead>
                      <tbody>
                        {parsed.map((row, i) => {
                          const match = txnNameLookup(row.name);
                          return (
                            <tr key={i} className={`border-t border-light-100 ${match ? '' : 'bg-orange-50/50'}`}>
                              <td className="p-2 truncate max-w-[180px]">{row.name}</td>
                              <td className="p-2 text-right font-mono">
                                {row.new_amount < 0 ? '-' : ''}${Math.abs(row.new_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                              </td>
                              <td className="p-2 truncate max-w-[120px] text-light-500">{row.correction_reason}</td>
                              <td className="p-2 text-center">
                                {match ? (
                                  <CheckCircle2 className="w-3.5 h-3.5 text-green-600 inline" />
                                ) : (
                                  <AlertCircle className="w-3.5 h-3.5 text-orange-500 inline" />
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {unmatched.length > 0 && (
                    <p className="text-xs text-orange-600">
                      {unmatched.length} transaction{unmatched.length !== 1 ? 's' : ''} could not be matched by name and will be skipped.
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-light-200 flex gap-2">
          {results ? (
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={handleSubmit}
                disabled={submitting || !parsed || matched.length === 0}
                className="flex-1 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Applying...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4" />
                    Apply {matched.length} Correction{matched.length !== 1 ? 's' : ''}
                  </>
                )}
              </button>
              <button
                onClick={onClose}
                disabled={submitting}
                className="px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300 disabled:opacity-50"
              >
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
