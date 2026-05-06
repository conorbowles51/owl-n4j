import React, { useEffect, useRef, useState } from 'react';
import { Search, X, HelpCircle } from 'lucide-react';

/**
 * Shared, full-width search input used across every Cellebrite tab.
 *
 * Behaviour:
 *   - Wide, prominent (text-sm).
 *   - Shows a small operator hint when the user types ":" for the first
 *     time, and on hover of the (?) icon.
 *   - ESC clears the input.
 *   - Optional `/` global shortcut focuses the input (set focusOnSlash).
 *
 * Match-count display ("123 of 4,567 events") sits inline with the input
 * so investigators can see the impact of every keystroke without having
 * to look elsewhere on the page.
 *
 * Props:
 *   value, onChange       — controlled value
 *   placeholder           — input placeholder text
 *   matchCount, totalCount  — for the inline counter ("X of Y items")
 *   itemNoun              — singular noun for the counter ("event", "thread", "message")
 *   focusOnSlash          — when true, "/" anywhere on the page focuses the input
 *   compact               — smaller paddings + smaller text for in-thread use
 */
export default function CellebriteSearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  matchCount,
  totalCount,
  itemNoun = 'item',
  focusOnSlash = false,
  compact = false,
}) {
  const inputRef = useRef(null);
  const [hintOpen, setHintOpen] = useState(false);
  const [hasOperatorHintBeenShown, setHasOperatorHintBeenShown] = useState(false);

  // Auto-pop the operator hint the first time the user types ':' so they
  // know operators exist. After it's been shown once it stays accessible
  // via the (?) icon but doesn't auto-pop.
  useEffect(() => {
    if (!value) return;
    if (!hasOperatorHintBeenShown && value.includes(':')) {
      setHintOpen(true);
      setHasOperatorHintBeenShown(true);
      const t = setTimeout(() => setHintOpen(false), 4000);
      return () => clearTimeout(t);
    }
  }, [value, hasOperatorHintBeenShown]);

  // "/" anywhere focuses the search input, but only when no other text
  // input is focused (so it doesn't hijack typing in chat etc.).
  useEffect(() => {
    if (!focusOnSlash) return;
    const onKey = (e) => {
      if (e.key !== '/') return;
      const tag = (document.activeElement?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || document.activeElement?.isContentEditable) return;
      e.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [focusOnSlash]);

  const onKeyDown = (e) => {
    if (e.key === 'Escape' && value) {
      e.preventDefault();
      onChange('');
    }
  };

  const showCount = Number.isFinite(matchCount) && Number.isFinite(totalCount) && totalCount > 0;
  const filtered = showCount && matchCount !== totalCount;

  return (
    <div className={`relative w-full ${compact ? 'text-xs' : 'text-sm'}`}>
      <div className="flex items-stretch w-full border border-light-300 rounded-md bg-white focus-within:border-owl-blue-400 focus-within:ring-1 focus-within:ring-owl-blue-200 transition-colors">
        <div className={`flex items-center pl-2.5 ${compact ? 'pl-2' : ''}`}>
          <Search className={`text-light-400 ${compact ? 'w-3.5 h-3.5' : 'w-4 h-4'}`} />
        </div>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className={`flex-1 min-w-0 bg-transparent border-0 outline-none px-2 ${compact ? 'py-1' : 'py-1.5'} text-light-900 placeholder:text-light-400`}
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange('')}
            className="px-2 text-light-400 hover:text-light-700"
            title="Clear (Esc)"
          >
            <X className={compact ? 'w-3 h-3' : 'w-3.5 h-3.5'} />
          </button>
        )}
        {showCount && (
          <div className="flex items-center pr-2 pl-1 border-l border-light-200">
            <span className={`tabular-nums ${filtered ? 'text-owl-blue-700 font-medium' : 'text-light-500'} ${compact ? 'text-[10px]' : 'text-xs'}`}>
              {filtered
                ? `${matchCount.toLocaleString()} of ${totalCount.toLocaleString()}`
                : `${totalCount.toLocaleString()}`} {itemNoun}{totalCount === 1 ? '' : 's'}
            </span>
          </div>
        )}
        <button
          type="button"
          onClick={() => setHintOpen((v) => !v)}
          onMouseEnter={() => setHintOpen(true)}
          onMouseLeave={() => setHintOpen(false)}
          className="px-2 text-light-400 hover:text-owl-blue-600 border-l border-light-200"
          title="Search operators"
        >
          <HelpCircle className={compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
        </button>
      </div>

      {hintOpen && (
        <div className="absolute right-0 mt-1 z-30 w-[360px] bg-white border border-light-300 rounded-md shadow-lg p-3 text-xs text-light-700">
          <div className="font-semibold text-owl-blue-900 mb-1.5">Search operators</div>
          <ul className="space-y-1">
            <li><code className="bg-light-100 px-1 rounded">type:call</code> — by event/thread type</li>
            <li><code className="bg-light-100 px-1 rounded">from:John</code> — sender name or identifier</li>
            <li><code className="bg-light-100 px-1 rounded">to:+44123</code> — recipient/counterpart</li>
            <li><code className="bg-light-100 px-1 rounded">app:WhatsApp</code> — source app</li>
            <li><code className="bg-light-100 px-1 rounded">phone:P1</code> — by phone short label or model</li>
            <li><code className="bg-light-100 px-1 rounded">before:2023-01-15</code> / <code className="bg-light-100 px-1 rounded">after:2022-12-01</code></li>
            <li><code className="bg-light-100 px-1 rounded">"exact phrase"</code> — substring match</li>
            <li><code className="bg-light-100 px-1 rounded">-foo</code> — exclude rows containing "foo"</li>
          </ul>
          <div className="mt-2 text-[10px] text-light-500">
            Combine freely: <code>type:message from:Sender app:WhatsApp -ringing</code>
          </div>
        </div>
      )}
    </div>
  );
}
