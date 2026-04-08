import { useState, useEffect } from 'react';
import { X } from 'lucide-react';

const SECTIONS = [
  { key: 'summary',      label: 'Summary Cards',           desc: 'Payments / Receipts / Net / Transactions' },
  { key: 'money_flow',   label: 'Money Flow Perspective',  desc: 'Per-entity + combined breakdown', requires: 'moneyFlow' },
  { key: 'charts',       label: 'Charts',                  desc: 'Volume over time and category breakdown' },
  { key: 'entity_flow',  label: 'Entity Flow (From / To)', desc: 'Sender and recipient tables' },
  { key: 'transactions', label: 'Transactions Table',      desc: 'All filtered transaction rows' },
  { key: 'filters',      label: 'Active Filters Banner',   desc: 'Summary of applied filters (end of report)' },
  { key: 'entity_notes', label: 'Entity Notes Appendix',   desc: 'Notes and AI summaries per entity' },
];

export default function ExportOptionsModal({ isOpen, onClose, onConfirm, hasMoneyFlowSelection }) {
  const [enabled, setEnabled] = useState(new Set());

  useEffect(() => {
    if (!isOpen) return;
    const all = new Set(SECTIONS.map(s => s.key));
    if (!hasMoneyFlowSelection) all.delete('money_flow');
    setEnabled(all);
  }, [isOpen, hasMoneyFlowSelection]);

  if (!isOpen) return null;

  const toggle = (key) => setEnabled(prev => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const handleConfirm = () => {
    onConfirm(enabled);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-[480px] p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-light-800">Export PDF — Sections</span>
          <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-xs text-light-600 mb-3">
          Choose which sections to include in the PDF report. Active filters still apply to the transactions table regardless of which sections are checked.
        </p>

        <div className="space-y-2 mb-4">
          {SECTIONS.map((sec) => {
            const isDisabled = sec.requires === 'moneyFlow' && !hasMoneyFlowSelection;
            const isChecked = enabled.has(sec.key);
            return (
              <label
                key={sec.key}
                className={`flex items-start gap-2 p-2 rounded border ${
                  isDisabled
                    ? 'border-light-100 bg-light-50 cursor-not-allowed opacity-60'
                    : 'border-light-200 hover:bg-light-50 cursor-pointer'
                }`}
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  disabled={isDisabled}
                  onChange={() => !isDisabled && toggle(sec.key)}
                  className="mt-0.5"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-light-800">{sec.label}</div>
                  <div className="text-[11px] text-light-500">
                    {isDisabled ? 'Select Money Flow entities to enable' : sec.desc}
                  </div>
                </div>
              </label>
            );
          })}
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="text-xs px-3 py-1.5 rounded border border-light-200 text-light-600 hover:bg-light-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={enabled.size === 0}
            className="text-xs px-3 py-1.5 rounded bg-owl-blue-600 text-white hover:bg-owl-blue-700 disabled:opacity-50"
          >
            Export
          </button>
        </div>
      </div>
    </div>
  );
}
