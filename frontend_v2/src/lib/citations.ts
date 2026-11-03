/**
 * The one parser for citations in answers, report sections, chat and summaries (backend twin:
 * backend/services/case_citations.py).
 *
 * - doc://<evidence_file_id>/<page>, or doc://<evidence_file_id> when no page was given (never page 1).
 *   Older text names the file instead: doc://<url-encoded filename>[/<page>] and evidence://<filename>.
 * - txn://<transaction_id>: a ledger row; opens the Financial page on that row at its statement page.
 *   The Financial page payment links written before txn:// (/cases/<case>/financial?...&payment=<id>) are read as txn.
 * - rec://<record_uid>[#<field>]: a phone record (03 section 11.5).
 */
const UUID_TEXT = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
const UUID = new RegExp(`^${UUID_TEXT}$`)
const FINANCIAL_PATH = new RegExp(`^(?:https?://[^/]+)?/cases/(${UUID_TEXT})/financial\\?(\\S*)$`)
const PAYMENT_PARAM = new RegExp(`(?:^|&)payment=(${UUID_TEXT})(?:&|$)`)
// an app path written with a host: https://<any host>/cases/<id>/..., or https://cases/<id>/... (host dropped)
const APP_URL = new RegExp(`^https?://(?:[^/\\s]+/)*?(cases/${UUID_TEXT}(?:[/?#]\\S*)?)$`)

/**
 * The in-app path of a link a model wrote with a host, e.g. https://example.com/cases/<id>/financial?... or
 * https://cases/<id>/...: Loupe's own pages are never on another host, so the path is what was meant. Null otherwise.
 */
export function appPath(href: string | undefined | null): string | null {
  const match = APP_URL.exec((href ?? "").trim())
  return match ? `/${match[1]}` : null
}

export type Citation =
  | {
      scheme: "doc"
      href: string
      /** the evidence file id (lower case), or the filename when byName */
      target: string
      byName: boolean
      page?: number
      legacy: boolean
    }
  | { scheme: "txn"; href: string; target: string; legacy: boolean; linkedCaseId?: string }
  | { scheme: "rec"; href: string; target: string; field: string | null }

function decode(value: string) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value // older text can hold a literal percent sign
  }
}

export function parseCitation(href: string | undefined | null): Citation | null {
  if (!href) return null
  href = href.trim()
  if (href.startsWith("txn://")) {
    const target = href.slice(6).replace(/\/+$/, "")
    return UUID.test(target) ? { scheme: "txn", href, target: target.toLowerCase(), legacy: false } : null
  }
  if (href.startsWith("rec://")) {
    const rest = href.slice(6)
    const hash = rest.indexOf("#")
    const uid = (hash >= 0 ? rest.slice(0, hash) : rest).replace(/\/+$/, "")
    if (!UUID.test(uid)) return null
    const field = hash >= 0 ? decode(rest.slice(hash + 1)) : ""
    return { scheme: "rec", href, target: uid.toLowerCase(), field: field || null }
  }
  if (href.startsWith("doc://") || href.startsWith("evidence://")) {
    const legacy = href.startsWith("evidence://")
    let rest = href.slice(legacy ? 11 : 6)
    let page: number | undefined
    if (!legacy) {
      const suffix = /\/(\d*)$/.exec(rest)
      if (suffix) {
        rest = rest.slice(0, suffix.index)
        const value = Number(suffix[1])
        if (suffix[1] && Number.isSafeInteger(value) && value > 0) page = value
      }
    }
    const target = decode(rest).trim()
    if (!target) return null
    if (UUID.test(target)) return { scheme: "doc", href, target: target.toLowerCase(), byName: false, page, legacy }
    return { scheme: "doc", href, target, byName: true, page, legacy }
  }
  const path = FINANCIAL_PATH.exec(appPath(href) ?? href)
  if (path) {
    const payment = PAYMENT_PARAM.exec(path[2])
    if (payment)
      return { scheme: "txn", href, target: payment[1].toLowerCase(), legacy: true, linkedCaseId: path[1].toLowerCase() }
  }
  return null
}

/** True for every href the citation renderer handles: react-markdown must keep these schemes. */
export function isCitationHref(href: string) {
  return parseCitation(href) !== null
}

const LINK = /\]\(\s*<?((?:doc|txn|rec|evidence):\/\/[^)>\s]*|(?:https?:\/\/[^)\s>]*?)?\/?cases\/[^)\s>]*)>?(?:\s+"[^"]*")?\s*\)/g
const DEFINITION = /^\s*\[[^\]]+\]:\s*<?((?:doc|txn|rec|evidence):\/\/\S+?)>?\s*$/gm

/** Every citation href in Markdown text, in order, once each (inline links and reference definitions). */
export function citationHrefs(markdown: string | undefined | null): string[] {
  const out = new Set<string>()
  for (const pattern of [LINK, DEFINITION]) {
    pattern.lastIndex = 0
    for (const match of (markdown ?? "").matchAll(pattern)) if (parseCitation(match[1])) out.add(match[1].trim())
  }
  return [...out]
}

/** The doc:// citation of a file at a page, or of the file alone when no page is known. */
export function docHref(evidenceFileId: string, page?: number | null) {
  return page ? `doc://${evidenceFileId}/${page}` : `doc://${evidenceFileId}`
}

/** A doc:// citation by filename, for sources that carry no file id. */
export function docHrefByName(filename: string, page?: number | null) {
  const name = encodeURIComponent(filename)
  return page ? `doc://${name}/${page}` : `doc://${name}`
}

/** The key that groups citations of one file (its id, or its name when cited by name). */
export function documentKey(citation: Citation & { scheme: "doc" }) {
  return citation.byName ? `name:${citation.target}` : `id:${citation.target}`
}

/** The Financial page on one payment: the payment's details open at its statement page. */
export function paymentPath(caseId: string, transactionId: string) {
  return `/cases/${encodeURIComponent(caseId)}/financial?${new URLSearchParams({ view: "transactions", payment: transactionId })}`
}
