/**
 * Guidance coverage (lx-guidecover A and G): reads every screen file in src/ and lists each control a person acts on
 * with the guidance it carries. The coverage test (src/guidance-coverage.test.ts) and the inventory
 * (node scripts/guidance-coverage.js --inventory <out.md>) both use it, so the numbers in one are the numbers in the other.
 *
 * A control is a <button>, a <Button>, or an element with role="button". It is icon-only when nothing inside it is
 * words: only icons (a lucide-react import or a name ending in Icon) and blank space. Its guidance:
 *   - accessible name: aria-label, aria-labelledby, or a visually hidden (sr-only) child
 *   - tooltip: a `tooltip` prop, or an aria-label or title on an icon-only <Button> (Button draws it as a tooltip on
 *     hover and on keyboard focus, see components/ui/button.tsx), or the control sits inside a <TooltipTrigger>.
 * A plain `title` on a raw <button> is a name but not a tooltip: a browser shows it on hover only, never on focus.
 */
import fs from "node:fs"
import path from "node:path"
import ts from "typescript"

const ICON_RE = /(Icon|Spinner|Glyph|Dot)$/

export function screenFiles(srcDir) {
  const out = []
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) {
        if (e.name === "stories" || e.name === "test" || e.name === "__tests__") continue
        walk(p)
      } else if (/\.tsx$/.test(e.name) && !/\.(test|stories|browser\.test)\.tsx$/.test(e.name)) out.push(p)
    }
  }
  walk(srcDir)
  return out.sort()
}

function tagName(node) {
  const t = node.tagName
  if (ts.isIdentifier(t)) return t.text
  if (ts.isPropertyAccessExpression(t)) return t.getText()
  return t.getText()
}

function attrs(opening) {
  const map = new Map()
  let spread = false
  for (const a of opening.attributes.properties) {
    if (ts.isJsxSpreadAttribute(a)) {
      spread = true
      continue
    }
    const name = a.name.getText()
    let value = true
    if (a.initializer) {
      if (ts.isStringLiteral(a.initializer)) value = a.initializer.text
      else if (ts.isJsxExpression(a.initializer) && a.initializer.expression) {
        const ex = a.initializer.expression
        value = ts.isStringLiteralLike(ex) ? ex.text : { expr: ex.getText() }
      }
    }
    map.set(name, value)
  }
  return { map, spread }
}

/**
 * The string literals an attribute can take: "x", or each literal in {cond ? "x" : "y"}. A bare identifier
 * ({term}) passes a caller's value through and gives none.
 */
function literalsOf(opening, name) {
  for (const a of opening.attributes.properties) {
    if (!ts.isJsxAttribute(a) || a.name.getText() !== name || !a.initializer) continue
    if (ts.isStringLiteral(a.initializer)) return [a.initializer.text]
    const out = []
    const walk = (n) => {
      if (ts.isStringLiteralLike(n)) out.push(n.text)
      // a comparison's operand ({list === "copies" ? …}) is not a value the attribute takes
      if (ts.isBinaryExpression(n) && [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken, ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken].includes(n.operatorToken.kind)) return
      ts.forEachChild(n, walk)
    }
    walk(a.initializer)
    return out
  }
  return []
}

const textOf = (v) => (typeof v === "string" ? v : v && typeof v === "object" ? `{${v.expr}}` : "")

/**
 * What sits inside a control: "icon" (icons and blank space only), "text" (words or an expression that may be
 * words), "empty", or "hidden-name" (an sr-only child names it).
 */
function contentKind(children, icons) {
  let sawIcon = false
  let sawText = false
  let srOnly = false
  const visit = (kids) => {
    for (const k of kids) {
      if (ts.isJsxText(k)) {
        if (k.text.trim()) sawText = true
      } else if (ts.isJsxExpression(k)) {
        const ex = k.expression
        if (!ex) continue
        // {open ? <ChevronUp/> : <ChevronDown/>} and {busy && <Spinner/>}: icons when every branch is an icon
        const branches = []
        const split = (e) => {
          while (ts.isParenthesizedExpression(e)) e = e.expression
          if (ts.isConditionalExpression(e)) {
            split(e.whenTrue)
            split(e.whenFalse)
          } else if (ts.isBinaryExpression(e) && (e.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken || e.operatorToken.kind === ts.SyntaxKind.BarBarToken || e.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken)) {
            if (e.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) split(e.right)
            else {
              split(e.left)
              split(e.right)
            }
          } else branches.push(e)
        }
        split(ex)
        for (const b of branches) {
          if (ts.isJsxElement(b) || ts.isJsxSelfClosingElement(b) || ts.isJsxFragment(b)) visit([b])
          else if (b.kind === ts.SyntaxKind.NullKeyword || (ts.isIdentifier(b) && b.text === "undefined")) continue
          else sawText = true
        }
      } else if (ts.isJsxSelfClosingElement(k)) {
        const name = tagName(k)
        if (icons.has(name) || ICON_RE.test(name)) sawIcon = true
        else sawText = true
      } else if (ts.isJsxElement(k)) {
        const name = tagName(k.openingElement)
        const cls = textOf(attrs(k.openingElement).map.get("className"))
        if (/\bsr-only\b/.test(cls)) srOnly = true
        else if (icons.has(name) || ICON_RE.test(name)) sawIcon = true
        else if (name === "span" || name === "div" || name === "Fragment" || name === "React.Fragment") visit(k.children)
        else sawText = true
      } else if (ts.isJsxFragment(k)) visit(k.children)
    }
  }
  visit(children)
  if (sawText) return "text"
  if (srOnly) return "hidden-name"
  return sawIcon ? "icon" : "empty"
}

/** Every control in one file. */
export function scanFile(file, srcDir) {
  const code = fs.readFileSync(file, "utf8")
  const sf = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const icons = new Set()
  for (const st of sf.statements) {
    if (ts.isImportDeclaration(st) && ts.isStringLiteral(st.moduleSpecifier) && st.moduleSpecifier.text === "lucide-react") {
      const nb = st.importClause?.namedBindings
      if (nb && ts.isNamedImports(nb)) for (const el of nb.elements) icons.add(el.name.text)
    }
  }
  const rel = path.relative(srcDir, file).split(path.sep).join("/")
  const controls = []
  const guides = []
  const terms = []
  const dialogs = []
  const visit = (node, inTrigger) => {
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const opening = ts.isJsxElement(node) ? node.openingElement : node
      const name = tagName(opening)
      const { map, spread } = attrs(opening)
      const guide = map.get("data-guide")
      guides.push(...literalsOf(opening, "data-guide"))
      if ((name === "LearnMore" || name === "InfoTip") && map.has("term"))
        for (const term of literalsOf(opening, "term"))
          terms.push({ line: sf.getLineAndCharacterOfPosition(opening.getStart()).line + 1, term })
      const trigger = inTrigger || name === "TooltipTrigger"
      if (/^(Dialog|Sheet|AlertDialog)Title$/.test(name) && ts.isJsxElement(node))
        dialogs.push({ line: sf.getLineAndCharacterOfPosition(opening.getStart()).line + 1, title: node.children.map((k) => k.getText()).join("").replace(/\s+/g, " ").trim().slice(0, 90) })
      const isControl = name === "button" || name === "Button" || map.get("role") === "button"
      if (isControl) {
        let children = ts.isJsxElement(node) ? node.children : []
        // <Button asChild><Link …><Icon/></Link></Button>: the words are the child's
        if (map.has("asChild")) {
          const only = children.filter((k) => !(ts.isJsxText(k) && !k.text.trim()))
          if (only.length === 1 && ts.isJsxElement(only[0])) children = only[0].children
        }
        const kind = contentKind(children, icons)
        const aria = map.get("aria-label")
        const line = sf.getLineAndCharacterOfPosition(opening.getStart()).line + 1
        const hasName = map.has("aria-label") || map.has("aria-labelledby") || kind === "hidden-name"
        const hasTooltip =
          trigger || map.has("tooltip") || (name === "Button" && (map.has("aria-label") || map.has("title")))
        controls.push({
          file: rel,
          line,
          tag: name,
          kind,
          iconOnly: kind === "icon" || kind === "hidden-name" || kind === "empty",
          spread,
          name: textOf(aria) || textOf(map.get("title")) || "",
          hasName: hasName || map.has("title"),
          hasTooltip,
          inTrigger: trigger,
          title: map.has("title"),
          disabled: map.has("disabled"),
          disabledWhy: map.has("disabledReason") || trigger || map.has("title"),
          disabledExpr: textOf(map.get("disabled")),
          guide: typeof guide === "string" ? guide : "",
        })
      }
      ts.forEachChild(node, (c) => visit(c, trigger))
      return
    }
    ts.forEachChild(node, (c) => visit(c, inTrigger))
  }
  visit(sf, false)
  return { file: rel, controls, guides, terms, dialogs }
}

export function scanAll(srcDir) {
  return screenFiles(srcDir).map((f) => scanFile(f, srcDir))
}

/**
 * Icon-only controls missing guidance. A control whose props come from a spread ({...props}) is a wrapper: its
 * caller names it, so it is counted apart and not failed.
 */
export function iconGaps(results, allow = {}) {
  const gaps = []
  for (const r of results)
    for (const c of r.controls) {
      if (!c.iconOnly || c.spread) continue
      const key = `${c.file}:${c.line}`
      if (allow[`${c.file}`] || allow[key]) continue
      if (!c.hasName || !c.hasTooltip) gaps.push(c)
    }
  return gaps
}

const BUSY = /pending|isPending|saving|busy|loading|isLoading|submitting|running|working|isFetching|deleting|uploading|exporting|creating|importing|applying|sending|controlling|pausing|preparing|rejecting|testing|starting|rendering|progress|actionKey|mutation\.|\.isPending/i
const SELF_EVIDENT = /^!\w+(?:\.\w+)*\.length$|trim\(\)|\.length === 0|length < |page|offset|zoom|index|step|current|cursor|=== 0|<= ?0|<= ?1|>= ?total|>= ?pages|>= ?max|^!\w+$|!?\w+\.trim|isSuccess|===\s*""|^\w+$/i

/**
 * Disabled controls that do not say why (lx-guidecover C). Left out: a control disabled only while work runs (it
 * shows its own progress), or only at an evident bound (first page, largest zoom, an empty field). The rest need a
 * `disabledReason`, a tooltip or a title.
 */
export function disabledGaps(results, allow = {}) {
  const gaps = []
  for (const r of results)
    for (const c of r.controls) {
      // allowed by file and condition, so an edit elsewhere in the file does not break the entry
      if (!c.disabled || c.disabledWhy || c.spread || allow[`${c.file} ${c.disabledExpr}`]) continue
      const e = c.disabledExpr.replace(/^\{|\}$/g, "")
      const parts = e.split(/\s*\|\|\s*/)
      const busyOnly = BUSY.test(e) && !/&&|\|\||!/.test(e.replace(/^!/, ""))
      if (busyOnly || parts.every((p) => BUSY.test(p) || SELF_EVIDENT.test(p))) continue
      gaps.push(c)
    }
  return gaps
}

/** Every data-guide target named in the source, by file. */
export function guideTargets(results) {
  const set = new Set()
  for (const r of results) for (const g of r.guides) set.add(g)
  return set
}

/** Heading anchors in a markdown file, the way GuideDialog builds them (minus its prefix). */
export function headingSlugs(markdown) {
  const out = new Set()
  for (const line of markdown.split("\n")) {
    const m = /^#{1,6}\s+(.+?)\s*$/.exec(line)
    if (m)
      out.add(
        m[1]
          .toLowerCase()
          .replace(/[^a-z0-9\s-]/g, "")
          .trim()
          .replace(/\s+/g, "-")
      )
  }
  return out
}

/** The tour registry and guides, read from the TypeScript source itself (bundled for node), so the inventory cannot drift. */
async function registry(srcDir) {
  const { buildSync } = await import("esbuild")
  const out = buildSync({
    stdin: { contents: 'export { TOURS, tourArea } from "./features/guidance/tours"; export { AREA_GUIDE, GUIDES } from "./features/guidance/guides"', resolveDir: srcDir, loader: "ts" },
    bundle: true,
    format: "esm",
    write: false,
    platform: "node",
    alias: { "@": srcDir },
    define: { "import.meta.env.BASE_URL": '"/"' },
  })
  return import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`)
}

/** The case addresses in app/routes.tsx (redirects left out), as written there. */
export function caseRoutes(srcDir) {
  const routes = fs.readFileSync(path.join(srcDir, "app/routes.tsx"), "utf8")
  const start = routes.indexOf('<Route path="/cases/:id"')
  const block = routes.slice(routes.indexOf(">", start) + 1, routes.indexOf("</Route>", start))
  return [...block.matchAll(/<Route (index )?(?:path="([^"]*)" )?element=\{(<Navigate)?/g)].filter((m) => !m[3]).map((m) => (m[1] ? "" : m[2]))
}

async function inventory(srcDir, outFile) {
  const results = scanAll(srcDir)
  const all = results.flatMap((r) => r.controls)
  const icon = all.filter((c) => c.iconOnly)
  const iconWrap = icon.filter((c) => c.spread)
  const iconOwn = icon.filter((c) => !c.spread)
  const named = iconOwn.filter((c) => c.hasName)
  const tipped = iconOwn.filter((c) => c.hasName && c.hasTooltip)
  const disabled = all.filter((c) => c.disabled)
  const byArea = new Map()
  for (const c of all) {
    const area = c.file.startsWith("features/") ? c.file.split("/")[1] : c.file.split("/")[0]
    const a = byArea.get(area) ?? { controls: 0, icon: 0, iconOk: 0, tooltipAny: 0 }
    a.controls += 1
    if (c.iconOnly && !c.spread) {
      a.icon += 1
      if (c.hasName && c.hasTooltip) a.iconOk += 1
    }
    if (c.hasTooltip) a.tooltipAny += 1
    byArea.set(area, a)
  }
  const lines = []
  lines.push("# Guidance inventory (generated)")
  lines.push("")
  lines.push(`Generated by \`node scripts/guidance-coverage.js --inventory\` from frontend_v2/src. Do not edit by hand.`)
  lines.push("")
  lines.push("## Totals")
  lines.push("")
  lines.push(`- Screen files read: ${results.length}`)
  lines.push(`- Controls (button, Button, role=button): ${all.length}`)
  lines.push(`- Icon-only controls: ${iconOwn.length} (plus ${iconWrap.length} wrappers whose caller passes the name)`)
  lines.push(`- Icon-only with an accessible name: ${named.length} of ${iconOwn.length}`)
  lines.push(`- Icon-only with a name and a tooltip that keyboard focus opens: ${tipped.length} of ${iconOwn.length}`)
  lines.push(`- Disabled-capable controls: ${disabled.length}; saying why (tooltip or title): ${disabled.filter((c) => c.disabledWhy).length}`)
  lines.push(`- Disabled controls whose reason is not evident and is not stated: ${disabledGaps(results).length}`)
  lines.push(`- Controls with any tooltip: ${all.filter((c) => c.hasTooltip).length} of ${all.length}`)
  lines.push(`- data-guide anchors: ${guideTargets(results).size}`)
  lines.push("")
  const reg = await registry(srcDir)
  lines.push("## Case addresses, their tour and guide")
  lines.push("")
  lines.push("| Address | Tour | Steps | Guide |")
  lines.push("|---|---|---:|---|")
  for (const r of caseRoutes(srcDir)) {
    const area = reg.tourArea(`/cases/c1/${r.replace(/:[a-zA-Z]+\?/g, "").replace(/:[a-zA-Z]+/g, "x")}`)
    const tour = area ? reg.TOURS[area] : null
    lines.push(`| /cases/:id/${r} | ${tour ? tour.name : "none"} | ${tour ? tour.steps.length : 0} | ${area ? reg.GUIDES[reg.AREA_GUIDE[area]].title : "none"} |`)
  }
  const panels = Object.values(reg.TOURS).filter((t) => t.panel)
  lines.push("")
  lines.push(`Panel tours (open the first time the panel is on screen): ${panels.map((t) => `${t.name} (${t.steps.length} steps)`).join(", ")}.`)
  lines.push("")
  lines.push("## Tour steps")
  lines.push("")
  for (const t of Object.values(reg.TOURS)) lines.push(`- **${t.name}**: ${t.steps.map((st) => `${st.title} \`${st.targets.join(" | ")}\``).join("; ")}`)
  lines.push("")
  lines.push("## Glossary links from screens")
  lines.push("")
  for (const r of results) for (const t of r.terms) lines.push(`- ${r.file}:${t.line} "${t.term}"`)
  lines.push("")
  lines.push("## Dialogs and panels (by title)")
  lines.push("")
  for (const r of results) for (const d of r.dialogs) lines.push(`- ${r.file}:${d.line} ${d.title}`)
  lines.push("")
  lines.push("## By area")
  lines.push("")
  lines.push("| Area | Controls | Icon-only | Icon-only guided | Any tooltip |")
  lines.push("|---|---:|---:|---:|---:|")
  for (const [a, v] of [...byArea.entries()].sort()) lines.push(`| ${a} | ${v.controls} | ${v.icon} | ${v.iconOk} | ${v.tooltipAny} |`)
  lines.push("")
  lines.push("## Every control")
  lines.push("")
  lines.push("Guidance: N = accessible name, T = tooltip on hover and focus, t = title (hover only), G = tour anchor, D = disabled.")
  lines.push("")
  for (const r of results) {
    if (!r.controls.length) continue
    lines.push(`### ${r.file}`)
    for (const c of r.controls) {
      const g = [c.hasName && "N", c.hasTooltip && "T", c.title && "t", c.guide && `G:${c.guide}`, c.disabled && "D"].filter(Boolean).join(" ") || "none"
      const nm = c.name.replace(/\|/g, "/").slice(0, 70)
      lines.push(`- ${c.line} \`${c.tag}\` ${c.iconOnly ? "icon-only" : "words"}${c.spread ? " (wrapper)" : ""} — ${g}${nm ? ` — "${nm}"` : ""}`)
    }
  }
  fs.writeFileSync(outFile, lines.join("\n") + "\n")
  return { files: results.length, controls: all.length, icon: iconOwn.length, named: named.length, tipped: tipped.length }
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  const i = process.argv.indexOf("--inventory")
  const src = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../src")
  if (i > 0) inventory(src, process.argv[i + 1] ?? "guidance-inventory.md").then((n) => console.log(JSON.stringify(n)))
  else {
    const gaps = iconGaps(scanAll(src))
    for (const g of gaps) console.log(`${g.file}:${g.line} ${g.tag} name=${g.hasName} tooltip=${g.hasTooltip}`)
    console.log(`${gaps.length} icon-only controls without a name and tooltip`)
  }
}
