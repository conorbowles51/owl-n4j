/**
 * Search Query Parser
 * 
 * Parses search queries with boolean operators (AND, OR, NOT)
 * 
 * Supported syntax:
 * - "term1 term2" - AND (both terms must match)
 * - "term1 AND term2" - AND (explicit)
 * - "term1 OR term2" - OR (either term can match)
 * - "term1 NOT term2" - NOT (term1 must match, term2 must not)
 * - "term1 -term2" - NOT (alternative syntax)
 * - Quoted strings: "exact phrase" - matches exact phrase
 * - Can combine operators: "term1 AND term2 OR term3"
 */

/**
 * Parse a search query into an AST (Abstract Syntax Tree)
 */
export function parseSearchQuery(query) {
  if (!query || !query.trim()) {
    return null;
  }

  const tokens = tokenize(query);
  if (tokens.length === 0) {
    return null;
  }

  return parseExpression(tokens);
}

/**
 * Tokenize the query string
 */
function tokenize(query) {
  const tokens = [];
  let current = '';
  let inQuotes = false;
  let quoteChar = null;

  for (let i = 0; i < query.length; i++) {
    const char = query[i];
    const nextChar = query[i + 1];

    if (char === '"' || char === "'") {
      if (!inQuotes) {
        // Start of quoted string
        inQuotes = true;
        quoteChar = char;
        if (current.trim()) {
          tokens.push({ type: 'term', value: current.trim() });
          current = '';
        }
      } else if (char === quoteChar) {
        // End of quoted string
        inQuotes = false;
        tokens.push({ type: 'quoted', value: current.trim() });
        current = '';
        quoteChar = null;
      } else {
        current += char;
      }
    } else if (inQuotes) {
      current += char;
    } else if (char === '-' && (i === 0 || query[i - 1] === ' ')) {
      // NOT operator (alternative syntax)
      if (current.trim()) {
        tokens.push({ type: 'term', value: current.trim() });
        current = '';
      }
      tokens.push({ type: 'operator', value: 'NOT' });
    } else if (char === ' ') {
      if (current.trim()) {
        const trimmed = current.trim().toUpperCase();
        if (trimmed === 'AND' || trimmed === 'OR' || trimmed === 'NOT') {
          tokens.push({ type: 'operator', value: trimmed });
        } else {
          tokens.push({ type: 'term', value: current.trim() });
        }
        current = '';
      }
    } else {
      current += char;
    }
  }

  if (inQuotes) {
    // Unclosed quote, treat as regular term
    tokens.push({ type: 'term', value: current.trim() });
  } else if (current.trim()) {
    const trimmed = current.trim().toUpperCase();
    if (trimmed === 'AND' || trimmed === 'OR' || trimmed === 'NOT') {
      tokens.push({ type: 'operator', value: trimmed });
    } else {
      tokens.push({ type: 'term', value: current.trim() });
    }
  }

  return tokens;
}

/**
 * Parse tokens into an expression tree
 * Operator precedence: NOT > AND > OR
 */
function parseExpression(tokens) {
  // First, handle NOT operators (highest precedence)
  let processed = processNotOperators(tokens);
  
  // Then handle AND operators
  processed = processAndOperators(processed);
  
  // Finally handle OR operators
  return processOrOperators(processed);
}

/**
 * Process NOT operators (right-associative)
 */
function processNotOperators(tokens) {
  const result = [];
  let i = 0;

  while (i < tokens.length) {
    if (tokens[i].type === 'operator' && tokens[i].value === 'NOT') {
      // NOT operator found
      i++; // Skip NOT
      if (i < tokens.length) {
        const operand = tokens[i];
        result.push({
          type: 'not',
          operand: operand.type === 'term' || operand.type === 'quoted' 
            ? { type: 'term', value: operand.value }
            : operand
        });
        i++;
      }
    } else {
      result.push(tokens[i]);
      i++;
    }
  }

  return result;
}

/**
 * Process AND operators (left-associative)
 */
function processAndOperators(tokens) {
  if (tokens.length === 0) return tokens;
  
  let result = [tokens[0]];

  for (let i = 1; i < tokens.length; i++) {
    if (tokens[i].type === 'operator' && tokens[i].value === 'AND') {
      // AND operator
      i++; // Skip AND
      if (i < tokens.length) {
        const right = tokens[i];
        const left = result.pop();
        result.push({
          type: 'and',
          left: left.type === 'term' || left.type === 'quoted'
            ? { type: 'term', value: left.value }
            : left,
          right: right.type === 'term' || right.type === 'quoted'
            ? { type: 'term', value: right.value }
            : right
        });
      }
    } else if (tokens[i].type !== 'operator') {
      // Implicit AND for consecutive terms only (never combine OR with the next term)
      const left = result.pop();
      if (left && left.type === 'operator') {
        // Left is OR (or other non-AND) — leave for processOrOperators, don't form AND(OR, term)
        result.push(left);
        result.push(tokens[i]);
      } else {
        const right = tokens[i];
        result.push({
          type: 'and',
          left: left.type === 'term' || left.type === 'quoted'
            ? { type: 'term', value: left.value }
            : left,
          right: right.type === 'term' || right.type === 'quoted'
            ? { type: 'term', value: right.value }
            : right
        });
      }
    } else {
      // Push operators (like OR) to be processed later
      result.push(tokens[i]);
    }
  }

  return result;
}

/**
 * Process OR operators (left-associative)
 */
function processOrOperators(tokens) {
  if (tokens.length === 0) return null;
  if (tokens.length === 1) return tokens[0];

  let result = tokens[0];

  for (let i = 1; i < tokens.length; i++) {
    if (tokens[i].type === 'operator' && tokens[i].value === 'OR') {
      i++; // Skip OR
      if (i < tokens.length) {
        const right = tokens[i];
        result = {
          type: 'or',
          left: result.type === 'term' || result.type === 'quoted'
            ? { type: 'term', value: result.value }
            : result,
          right: right.type === 'term' || right.type === 'quoted'
            ? { type: 'term', value: right.value }
            : right
        };
      }
    }
  }

  return result;
}

/**
 * Evaluate a parsed query against a searchable text
 * 
 * @param {Object} ast - Parsed query AST
 * @param {Function} searchFn - Function that takes a term and returns true/false if it matches
 * @returns {boolean} - Whether the query matches
 */
export function evaluateQuery(ast, searchFn) {
  if (!ast) return true; // Empty query matches everything

  if (ast.type === 'term') {
    return searchFn(ast.value.toLowerCase());
  }

  if (ast.type === 'quoted') {
    return searchFn(ast.value.toLowerCase(), true); // Exact match
  }

  if (ast.type === 'not') {
    return !evaluateQuery(ast.operand, searchFn);
  }

  if (ast.type === 'and') {
    return evaluateQuery(ast.left, searchFn) && evaluateQuery(ast.right, searchFn);
  }

  if (ast.type === 'or') {
    return evaluateQuery(ast.left, searchFn) || evaluateQuery(ast.right, searchFn);
  }

  return false;
}

/**
 * Build searchable text from an item. Always includes name, key, summary, type.
 * When allFields is true, also includes all property values. Used for both filter and search.
 * @param {Object} item - Item to search
 * @param {{ allFields?: boolean }} options - allFields: include (item.properties) values
 * @returns {string} - Lowercase concatenated searchable text
 */
function getSearchableText(item, options = {}) {
  const parts = [
    item.name || '',
    item.key || '',
    item.summary || '',
    item.type || ''
  ];
  if (options.allFields && item.properties && typeof item.properties === 'object') {
    for (const v of Object.values(item.properties)) {
      if (v != null && typeof v === 'string') parts.push(v);
      else if (v != null) parts.push(String(v));
    }
  }
  return parts.join(' ').toLowerCase();
}

/**
 * Collect all positive terms (and quoted phrases) from the AST for highlighting matches in UI.
 * @param {Object} ast - Parsed query AST
 * @returns {string[]} - Normalized terms to highlight (lowercase)
 */
export function getHighlightTerms(ast) {
  if (!ast) return [];
  const terms = [];
  function collect(node) {
    if (!node) return;
    if (node.type === 'term') {
      const v = (node.value || '').toLowerCase().trim();
      if (v) terms.push(v);
      return;
    }
    if (node.type === 'quoted') {
      const v = (node.value || '').toLowerCase().trim();
      if (v) terms.push(v);
      return;
    }
    if (node.type === 'not') {
      collect(node.operand);
      return;
    }
    if (node.type === 'and' || node.type === 'or') {
      collect(node.left);
      collect(node.right);
    }
  }
  collect(ast);
  return [...new Set(terms)];
}

/**
 * Find ranges in text where any of the terms appear (case-insensitive). Returns merged [start, end] pairs.
 * @param {string} text - Text to search
 * @param {string[]} terms - Terms to highlight
 * @returns {Array<[number, number]>} - Sorted, non-overlapping [start, end] ranges
 */
export function getHighlightRanges(text, terms) {
  if (!text || typeof text !== 'string' || !terms || terms.length === 0) return [];
  const ranges = [];
  const lower = text.toLowerCase();
  for (const term of terms) {
    const t = (term || '').toLowerCase();
    if (!t) continue;
    let i = 0;
    while ((i = lower.indexOf(t, i)) !== -1) {
      ranges.push([i, i + t.length]);
      i += t.length;
    }
  }
  if (ranges.length === 0) return [];
  ranges.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const [s, e] of ranges) {
    if (merged.length && s <= merged[merged.length - 1][1]) {
      merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], e);
    } else {
      merged.push([s, e]);
    }
  }
  return merged;
}

/**
 * Check if a searchable object matches the query
 * 
 * @param {Object} ast - Parsed query AST
 * @param {Object} item - Item to search (should have name, key, summary, type properties)
 * @param {{ allFields?: boolean }} options - allFields: search in all properties too
 * @returns {boolean} - Whether the item matches
 */
export function matchesQuery(ast, item, options = {}) {
  if (!ast) return true; // Empty query matches everything

  const searchFn = (term, exact = false) => {
    const searchableText = getSearchableText(item, options);

    const normalizedTerm = term.toLowerCase();

    // Handle wildcard search (supports * and ?)
    if (normalizedTerm.includes('*') || normalizedTerm.includes('?')) {
      const escaped = normalizedTerm.replace(/[-/\\^$+?.()|[\]{}]/g, '\\$&');
      const pattern = escaped
        .replace(/\\\*/g, '.*')
        .replace(/\\\?/g, '.');
      const regex = new RegExp(pattern, 'i');
      return regex.test(searchableText);
    }

    // Simple fuzziness using "~" (characters must appear in order)
    if (normalizedTerm.includes('~')) {
      const fuzzy = normalizedTerm.replace(/~/g, '');
      let cursor = 0;
      for (const char of fuzzy) {
        cursor = searchableText.indexOf(char, cursor);
        if (cursor === -1) {
          return false;
        }
        cursor += 1;
      }
      return true;
    }

    if (exact) {
      // For quoted strings, match the exact phrase
      return searchableText.includes(normalizedTerm);
    }
    
    // For regular terms, check if the term appears anywhere in the text
    // This allows partial matching (e.g., "john" matches "john smith")
    return searchableText.includes(normalizedTerm);
  };

  return evaluateQuery(ast, searchFn);
}

