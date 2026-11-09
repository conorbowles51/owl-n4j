#!/usr/bin/env node
// Prints every user-facing string in frontend_v2/src as JSON lines {file, line, text}.
// User-facing: JSX text, string attributes people read (title, label, placeholder, aria-label, alt, description...),
// strings passed to toast()/toast.*()/confirm()/alert(), and object properties people read (title, label,
// description, message, placeholder, helpText, emptyText, tooltip, hint, summary, detail).
// Used by scripts/check_writing.py (the writing standard, docs/writing-standard.md).
const fs = require('fs')
const path = require('path')
const root = path.resolve(process.argv[2] || path.join(__dirname, '..', 'frontend_v2', 'src'))
const tsPath = require.resolve('typescript', { paths: [path.join(__dirname, '..', 'frontend_v2'), process.cwd()] })
const ts = require(tsPath)

const READ_ATTRS = new Set(['title', 'label', 'placeholder', 'aria-label', 'alt', 'description', 'helperText',
  'tooltip', 'hint', 'emptyText', 'emptyMessage', 'subtitle', 'heading', 'caption', 'message', 'confirmText',
  'cancelText', 'summary', 'detail', 'text'])
const READ_CALLS = new Set(['toast', 'confirm', 'alert'])

function walkDir(dir, out) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name)
    const st = fs.statSync(full)
    if (st.isDirectory()) { if (name !== 'node_modules' && name !== '__tests__') walkDir(full, out) }
    else if (/\.(tsx|ts)$/.test(name) && !/\.(test|spec)\.tsx?$/.test(name) && !name.endsWith('.d.ts')) out.push(full)
  }
  return out
}

function textOf(node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isTemplateExpression(node)) return [node.head.text, ...node.templateSpans.map((s) => s.literal.text)].join(' … ')
  return null
}

// Literals a reader can see from an expression: the branches of a ternary, both sides of || ?? &&, parentheses.
function readable(node) {
  if (!node) return []
  const t = textOf(node)
  if (t != null) return [[node, t]]
  if (ts.isParenthesizedExpression(node)) return readable(node.expression)
  if (ts.isConditionalExpression(node)) return [...readable(node.whenTrue), ...readable(node.whenFalse)]
  if (ts.isBinaryExpression(node) && [ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken,
    ts.SyntaxKind.AmpersandAmpersandToken].includes(node.operatorToken.kind)) return [...readable(node.left), ...readable(node.right)]
  return []
}

const READ_SETTERS = /^set(Error|Message|Notice|Status|Warning|Info|Hint)$/

function calleeName(expr) {
  if (ts.isIdentifier(expr)) return expr.text
  if (ts.isPropertyAccessExpression(expr)) {
    const base = calleeName(expr.expression)
    return base === 'toast' ? 'toast' : (ts.isIdentifier(expr.name) && READ_CALLS.has(expr.name.text) ? expr.name.text : null)
  }
  return null
}

const files = fs.statSync(root).isDirectory() ? walkDir(root, []) : [root]
for (const file of files) {
  const src = fs.readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const emit = (node, text, kind) => {
    if (!text || !/[A-Za-z]{2}/.test(text)) return
    const { line } = sf.getLineAndCharacterOfPosition(node.getStart(sf))
    process.stdout.write(JSON.stringify({ file: path.relative(path.join(root, '..', '..'), file), line: line + 1, kind, text: text.replace(/\s+/g, ' ').trim() }) + '\n')
  }
  const visit = (node) => {
    if (ts.isJsxText(node)) emit(node, node.text, 'jsx')
    else if (ts.isJsxAttribute(node) && node.initializer) {
      const name = node.name.getText(sf)
      if (READ_ATTRS.has(name)) {
        let init = node.initializer
        if (ts.isJsxExpression(init) && init.expression) init = init.expression
        for (const [n, t] of readable(init)) emit(n, t, 'attr')
      }
    } else if (ts.isJsxExpression(node) && node.expression && node.parent && (ts.isJsxElement(node.parent) || ts.isJsxFragment(node.parent))) {
      for (const [n, t] of readable(node.expression)) emit(n, t, 'jsx')
    } else if (ts.isCallExpression(node)) {
      const name = calleeName(node.expression)
      if (name && READ_CALLS.has(name) && node.arguments.length) {
        for (const [n, t] of readable(node.arguments[0])) emit(n, t, 'call')
      } else if (ts.isIdentifier(node.expression) && READ_SETTERS.test(node.expression.text) && node.arguments.length) {
        for (const [n, t] of readable(node.arguments[0])) emit(n, t, 'call')
      }
    } else if (ts.isNewExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'Error' && node.arguments && node.arguments.length) {
      for (const [n, t] of readable(node.arguments[0])) emit(n, t, 'error')
    } else if (ts.isPropertyAssignment(node) && (ts.isIdentifier(node.name) || ts.isStringLiteral(node.name))) {
      if (READ_ATTRS.has(node.name.text) && node.name.text !== 'text') {
        for (const [n, t] of readable(node.initializer)) emit(n, t, 'prop')
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
}
