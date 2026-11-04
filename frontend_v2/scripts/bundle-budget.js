/**
 * The app shell's size gate. The main script (the entry chunk every page downloads and parses before anything shows)
 * may not grow past MAIN_GZIP_MAX gzip bytes. Before lx-shell (4 Nov 2026) it was 820,701 gzip bytes (2,890,226 bytes) because the map
 * library, the graph editor, chat, the evidence page and the statement panel were imported eagerly; after it, 193,730 (638,484 bytes).
 * The limit is that size plus 10 %. The release build (vite build, through the plugin below) refuses a bundle over it.
 *
 * A change that must put more code in the shell: load it on the page or panel that uses it (React.lazy / import()),
 * or, when it truly belongs in the first screen, raise MAIN_GZIP_MAX here in the same commit and say why.
 * Measure with: node scripts/bundle-budget.js dist
 */
import fs from "node:fs"
import path from "node:path"
import zlib from "node:zlib"

export const MAIN_GZIP_MAX = 213_103

/** gzip -9 size of the code, the way the release stores it for nginx's gzip_static. */
export function gzipBytes(code) {
  return zlib.gzipSync(typeof code === "string" ? Buffer.from(code) : code, { level: 9 }).length
}

/** The verdict for a main script of the given gzip size: null when within the limit, otherwise the refusal text. */
export function budgetProblem(fileName, gzip, max = MAIN_GZIP_MAX) {
  if (gzip <= max) return null
  return (
    `The main script ${fileName} is ${gzip.toLocaleString("en-US")} bytes gzip, over the shell limit of ` +
    `${max.toLocaleString("en-US")} (frontend_v2/scripts/bundle-budget.js). Load the new code on the page or panel ` +
    `that uses it (React.lazy / import()), or raise MAIN_GZIP_MAX there with the reason.`
  )
}

/** Vite plugin: checks the entry chunk of every production build. */
export function bundleBudgetPlugin(max = MAIN_GZIP_MAX) {
  return {
    name: "loupe-bundle-budget",
    apply: "build",
    enforce: "post",
    // writeBundle, not generateBundle: Vite adds its preload map to the entry chunk after the generate hooks, and the
    // limit is about the file the browser downloads.
    writeBundle(_options, bundle) {
      const entries = Object.values(bundle).filter((c) => c.type === "chunk" && c.isEntry)
      if (entries.length === 0) this.error("bundle budget: the build has no entry chunk")
      for (const chunk of entries) {
        const gzip = gzipBytes(chunk.code)
        const problem = budgetProblem(chunk.fileName, gzip, max)
        if (problem) this.error(problem)
        this.info?.(`main script ${chunk.fileName}: ${gzip} gzip bytes (limit ${max})`)
      }
    },
  }
}

/** The entry script a built dist/index.html loads. */
export function mainScriptOf(distDir) {
  const html = fs.readFileSync(path.join(distDir, "index.html"), "utf-8")
  const m = html.match(/<script[^>]*type="module"[^>]*src="\/?([^"]+\.js)"/)
  if (!m) throw new Error(`no module script in ${distDir}/index.html`)
  return path.join(distDir, m[1])
}

// CLI: node scripts/bundle-budget.js <dist>  (exit 1 when over the limit)
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  const file = mainScriptOf(process.argv[2] || "dist")
  const code = fs.readFileSync(file)
  const gzip = gzipBytes(code)
  const problem = budgetProblem(path.basename(file), gzip)
  console.log(`${path.basename(file)}: ${code.length} bytes, ${gzip} gzip (limit ${MAIN_GZIP_MAX})`)
  if (problem) {
    console.error(problem)
    process.exit(1)
  }
}
