import type { AgentArtifact } from "./types"
type Row = Record<string, unknown>

export function artifactText(value: unknown): string {
  return value == null ? "" : typeof value === "string" ? value : typeof value === "object" ? JSON.stringify(value) : String(value)
}
export function artifactRows(value: unknown): Row[] {
  return Array.isArray(value) ? value.filter((row): row is Row => !!row && typeof row === "object" && !Array.isArray(row)) : []
}

export function artifactSections(value: unknown, depth = 2): Row[] {
  return artifactRows(value).flatMap((section) => [
    { ...section, level: Math.max(2, Math.min(6, Math.floor(Number(section.level) || depth))) },
    ...artifactSections(artifactRows(section.sections).length ? section.sections : section.children, Math.min(depth + 1, 6)),
  ])
}

export function artifactIdentity(artifact: AgentArtifact) {
  return artifactText(artifact.metadata.deliverable_id) || artifact.id
}
export function artifactRevision(artifact: AgentArtifact) {
  return Number(artifact.metadata.revision) || 1
}

export function latestArtifactVersion(artifacts: AgentArtifact[], first = artifacts[0]): AgentArtifact | null {
  if (!first) return null
  return artifacts.filter((artifact) => artifactIdentity(artifact) === artifactIdentity(first))
    .reduce((latest, artifact) => artifactRevision(artifact) > artifactRevision(latest) ? artifact : latest, first)
}

/** Static layout only. Trusted React controls provide interaction outside this opaque iframe. */
export function isolatedArtifactDocument(html: string) {
  // A template is inert during parsing, including remote images; a detached HTMLDocument
  // created by DOMParser can still start resource downloads before sanitization.
  const template = document.createElement("template")
  template.innerHTML = html
  // CSP blocks fetches, but cannot reliably prevent same-frame navigation. Remove navigation
  // surfaces as well as scripts; sandbox alone does not block a meta refresh or a normal link.
  // Drop parser contexts that can change interpretation when scripting is disabled in the iframe.
  for (const element of template.content.querySelectorAll("script,meta,base,iframe,frame,object,embed,link,template,svg,math,textarea,noscript")) element.remove()
  const tags = new Set("div span p section article header footer main aside nav h1 h2 h3 h4 h5 h6 table thead tbody tfoot tr th td caption colgroup col ul ol li dl dt dd blockquote pre code b strong i em u s small sup sub br hr a img figure figcaption details summary style".split(" "))
  const attributes = new Set(["id", "class", "title", "aria-label", "role", "colspan", "rowspan", "scope", "alt", "width", "height", "style"])
  for (const element of template.content.querySelectorAll("*")) {
    const tag = element.tagName.toLowerCase()
    if (!tags.has(tag)) { element.replaceWith(...element.childNodes); continue }
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase()
      const safeAnchor = tag === "a" && name === "href" && /^#[\w-]+$/.test(attribute.value)
      const safeImage = tag === "img" && name === "src" && /^data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+$/.test(attribute.value)
      if (!attributes.has(name) && !safeAnchor && !safeImage) element.removeAttribute(attribute.name)
    }
  }
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; form-action 'none'; base-uri 'none'"><meta name="referrer" content="no-referrer"></head><body>${template.innerHTML}</body></html>`
}
