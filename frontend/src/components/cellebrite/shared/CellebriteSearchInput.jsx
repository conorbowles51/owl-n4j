import React, { useEffect, useMemo, useRef, useState } from 'react';
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
 *   - Optional typeahead: when `suggestions` is provided the input pops
 *     a dropdown with operator + value completions. Lets users find
 *     real values from the data instead of guessing exact strings
 *     (case/space/punctuation sensitive otherwise).
 *
 * Match-count display ("123 of 4,567 events") sits inline with the input
 * so investigators can see the impact of every keystroke without having
 * to look elsewhere on the page.
 *
 * Suggestion shape:
 *   { operator: string,      // e.g. 'type', 'app', 'place' (the bit before ':')
 *     value:    string,      // e.g. 'WhatsApp', 'london'
 *     label?:   string,      // override what's shown in the dropdown
 *     hint?:    string }     // small grey suffix (e.g. "12 hits")
 * Quoting is applied automatically when the value contains a space.
 *
 * Props:
 *   value, onChange       — controlled value
 *   placeholder           — input placeholder text
 *   matchCount, totalCount  — for the inline counter ("X of Y items")
 *   itemNoun              — singular noun for the counter ("event", "thread", "message")
 *   focusOnSlash          — when true, "/" anywhere on the page focuses the input
 *   compact               — smaller paddings + smaller text for in-thread use
 *   suggestions           — array of { operator, value, label?, hint? }
 *   suggestionOperators   — optional list of operator names to advertise
 *                           when the cursor is at the start of a token
 *                           (e.g. ['type', 'app', 'place', 'after']).
 *                           Defaults to a sane Cellebrite set.
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
  suggestions = null,
  suggestionOperators = null,
}) {
  const inputRef = useRef(null);
  const dropdownRef = useRef(null);
  const [hintOpen, setHintOpen] = useState(false);
  const [hasOperatorHintBeenShown, setHasOperatorHintBeenShown] = useState(false);
  const [caret, setCaret] = useState(0);
  const [focused, setFocused] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);

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

  // Compute the active typeahead candidates from the current caret token.
  // The token is the text since the last whitespace up to the caret. If
  // it contains a ':' we treat the prefix as the operator and complete
  // VALUES; otherwise we offer OPERATOR completions.
  const typeaheadEnabled = Array.isArray(suggestions) || Array.isArray(suggestionOperators);
  const ops = suggestionOperators || DEFAULT_OPERATORS;
  const { tokenStart, tokenEnd, opPrefix, valuePrefix, mode } = useMemo(() => {
    if (!typeaheadEnabled || !focused) {
      return { tokenStart: 0, tokenEnd: 0, opPrefix: '', valuePrefix: '', mode: 'off' };
    }
    const text = value || '';
    const c = Math.min(Math.max(caret, 0), text.length);

    // Walk back to the nearest whitespace to find the current token.
    let s = c;
    while (s > 0 && !/\s/.test(text[s - 1])) s -= 1;
    const tok = text.slice(s, c);

    // Case 1: current token contains a `:` — split it cleanly.
    const colonInTok = tok.indexOf(':');
    if (colonInTok >= 0) {
      const op = tok.slice(0, colonInTok).toLowerCase();
      const val = tok.slice(colonInTok + 1);
      return { tokenStart: s, tokenEnd: c, opPrefix: op, valuePrefix: val, mode: 'value' };
    }

    // Case 2: user typed `type: L` — i.e. there's whitespace between
    // the operator's `:` and what they're typing now. Walk back from
    // the current token's start across whitespace and see if the
    // PREVIOUS token ends in `:`. If so, the user is still picking a
    // value for that operator; we keep value-completion alive and
    // expand the replacement range to cover the space so a pick
    // doesn't leave the `:` orphaned.
    let p = s;
    while (p > 0 && /\s/.test(text[p - 1])) p -= 1;
    let prevStart = p;
    while (prevStart > 0 && !/\s/.test(text[prevStart - 1])) prevStart -= 1;
    const prevTok = text.slice(prevStart, p);
    if (prevTok && prevTok.endsWith(':')) {
      const op = prevTok.slice(0, -1).toLowerCase();
      return {
        // Replacement range covers the operator, the gap, AND the
        // partial value — picking a suggestion produces a clean
        // `operator:value ` regardless of where the spaces were.
        tokenStart: prevStart,
        tokenEnd: c,
        opPrefix: op,
        valuePrefix: tok,
        mode: 'value',
      };
    }

    // Case 3: bare token, no operator context — offer operator
    // completions matched against whatever's typed.
    return { tokenStart: s, tokenEnd: c, opPrefix: tok, valuePrefix: '', mode: 'operator' };
  }, [value, caret, focused, typeaheadEnabled]);

  const items = useMemo(() => {
    if (!typeaheadEnabled || !focused) return [];
    if (mode === 'operator') {
      const needle = opPrefix.toLowerCase();
      const opList = ops
        .filter((o) => !needle || o.toLowerCase().startsWith(needle))
        .slice(0, 12)
        .map((o) => ({
          operator: o,
          value: '',
          label: `${o}:`,
          hint: 'operator',
          _kind: 'operator',
        }));
      return opList;
    }
    // mode === 'value'
    const list = Array.isArray(suggestions) ? suggestions : [];
    const needle = valuePrefix.toLowerCase().replace(/^"+|"+$/g, '');
    const scoped = list.filter((s) => s.operator === opPrefix);
    const ranked = scoped
      .filter((s) => !needle || (s.value || '').toLowerCase().includes(needle))
      .slice(0, 20)
      .map((s) => ({ ...s, _kind: 'value' }));
    return ranked;
  }, [typeaheadEnabled, focused, mode, opPrefix, valuePrefix, suggestions, ops]);

  // Reset highlighted item whenever the suggestion list shape changes.
  useEffect(() => {
    setActiveIdx(0);
  }, [items.length, mode, opPrefix]);

  // Show the typeahead popover whenever the input is focused AND
  // typeahead is enabled. Even with zero matches we render the
  // panel with a "no matches" hint so the user knows the
  // autocomplete is alive and pulling from real data — previously
  // the popover just vanished, which read as "broken".
  const popoverOpen = focused && typeaheadEnabled;

  const insertSuggestion = (s) => {
    const text = value || '';
    let inserted;
    if (s._kind === 'operator') {
      inserted = `${s.operator}:`;
    } else {
      // Quote values that contain whitespace so the parser sees them
      // as one token.
      const needsQuote = /\s/.test(s.value);
      const v = needsQuote ? `"${s.value}"` : s.value;
      inserted = `${opPrefix}:${v} `;
    }
    const before = text.slice(0, tokenStart);
    const after = text.slice(tokenEnd);
    const next = before + inserted + after;
    onChange(next);
    // Move the caret to just after the inserted chunk on the next tick
    // so React has re-rendered the input value.
    const nextCaret = (before + inserted).length;
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        try { el.setSelectionRange(nextCaret, nextCaret); } catch { /* ignore */ }
        setCaret(nextCaret);
      }
    });
  };

  const onKeyDown = (e) => {
    if (popoverOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIdx((i) => Math.min(items.length - 1, i + 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIdx((i) => Math.max(0, i - 1));
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        const pick = items[activeIdx];
        if (pick) {
          e.preventDefault();
          insertSuggestion(pick);
          return;
        }
      }
    }
    if (e.key === 'Escape') {
      if (popoverOpen) {
        e.preventDefault();
        // Just close the popover; another Esc clears the input.
        inputRef.current?.blur();
        return;
      }
      if (value) {
        e.preventDefault();
        onChange('');
      }
    }
  };

  const syncCaret = () => {
    const el = inputRef.current;
    if (el) setCaret(el.selectionStart ?? (value || '').length);
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
          onChange={(e) => { onChange(e.target.value); syncCaret(); }}
          onKeyDown={onKeyDown}
          onKeyUp={syncCaret}
          onClick={syncCaret}
          onSelect={syncCaret}
          onFocus={() => { setFocused(true); syncCaret(); }}
          // Defer blur close so a mousedown on a suggestion still
          // resolves before the popover disappears.
          onBlur={() => { setTimeout(() => setFocused(false), 120); }}
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
          // Hover-open the help only when the input is NOT focused —
          // otherwise the help popover competes with the typeahead
          // and the user can't see their own suggestions.
          onMouseEnter={() => { if (!focused) setHintOpen(true); }}
          onMouseLeave={() => setHintOpen(false)}
          className="px-2 text-light-400 hover:text-owl-blue-600 border-l border-light-200"
          title="Search operators"
        >
          <HelpCircle className={compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
        </button>
      </div>

      {/* Typeahead suggestions popover. Anchored to the input. */}
      {popoverOpen && (
        <div
          ref={dropdownRef}
          className="absolute left-0 right-0 mt-1 z-40 bg-white border border-light-300 rounded-md shadow-lg max-h-[280px] overflow-y-auto"
        >
          <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-light-500 border-b border-light-100 sticky top-0 bg-white">
            {mode === 'operator'
              ? 'Operators (Tab / Enter to insert)'
              : `Suggestions for ${opPrefix}:`}
          </div>
          {items.length === 0 ? (
            <div className="px-2 py-2 text-[11px] text-light-500 italic">
              {mode === 'value'
                ? `No ${opPrefix} values found in the loaded data${valuePrefix ? ` matching "${valuePrefix}"` : ''}. You can still type one manually.`
                : 'No matching operators.'}
            </div>
          ) : (
            <ul>
              {items.map((s, i) => {
                const active = i === activeIdx;
                const label = s.label || (s._kind === 'operator' ? `${s.operator}:` : s.value);
                return (
                  <li
                    key={`${s.operator}:${s.value}:${i}`}
                    // mousedown — fires before blur, so the click registers
                    // even though the input loses focus next.
                    onMouseDown={(e) => { e.preventDefault(); insertSuggestion(s); }}
                    onMouseEnter={() => setActiveIdx(i)}
                    className={`px-2 py-1 cursor-pointer flex items-center gap-2 text-xs ${
                      active ? 'bg-owl-blue-50 text-owl-blue-900' : 'hover:bg-light-50 text-light-800'
                    }`}
                  >
                    <span className="truncate">
                      <code className="bg-light-100 px-1 rounded mr-1 text-[11px]">
                        {label}
                      </code>
                    </span>
                    {s.hint && (
                      <span className="ml-auto text-[10px] text-light-500 whitespace-nowrap">
                        {s.hint}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

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
            <li>
              <code className="bg-light-100 px-1 rounded">place:london</code> — by reverse-geocoded address / city / country
              <span className="text-[10px] text-light-500"> (only on rows the geocoder enriched)</span>
            </li>
            <li>
              <code className="bg-light-100 px-1 rounded">near:51.5,-0.1,5km</code> — within radius of a point
              <span className="text-[10px] text-light-500"> (km|m, default km)</span>
            </li>
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

const DEFAULT_OPERATORS = [
  'type', 'app', 'from', 'to', 'phone', 'place', 'near',
  'before', 'after',
];
