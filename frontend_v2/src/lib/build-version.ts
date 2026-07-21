/**
 * Stale-tab guard. An open SPA tab survives every deploy — it keeps running
 * the bundle it loaded, silently, while the server moves on (this masked two
 * rounds of DKT-932 fixes). On window focus and every few minutes we compare
 * the bundle's baked-in commit against dist/version.json; on mismatch a
 * fixed banner asks the user to reload.
 */

declare const __BUILD_NAME__: string
declare const __BUILD_COMMIT__: string

const CHECK_INTERVAL_MS = 5 * 60 * 1000

let bannerShown = false

function showReloadBanner() {
  if (bannerShown) return
  bannerShown = true
  const bar = document.createElement("div")
  bar.setAttribute(
    "style",
    [
      "position:fixed", "top:0", "left:0", "right:0", "z-index:99999",
      "display:flex", "align-items:center", "justify-content:center", "gap:12px",
      "padding:8px 16px", "background:#b45309", "color:#fff",
      "font:600 13px system-ui,sans-serif", "box-shadow:0 1px 6px rgba(0,0,0,.3)",
    ].join(";")
  )
  bar.append("A new version of Loupe has been deployed — this tab is running old code.")
  const btn = document.createElement("button")
  btn.textContent = "Reload now"
  btn.setAttribute(
    "style",
    "padding:3px 12px;border-radius:6px;border:1px solid #fff;background:transparent;color:#fff;font:600 12px system-ui;cursor:pointer"
  )
  btn.onclick = () => window.location.reload()
  bar.append(btn)
  document.body.append(bar)
}

async function checkVersion() {
  try {
    const res = await fetch(`/version.json?_=${Date.now()}`, { cache: "no-store" })
    if (!res.ok) return
    const data = (await res.json()) as { commit?: string }
    if (data.commit && data.commit !== __BUILD_COMMIT__) showReloadBanner()
  } catch {
    // Network hiccup — never bother the user over the guard itself.
  }
}

export function startBuildVersionGuard() {
  console.info(`🦉 Loupe build: ${__BUILD_NAME__} (${__BUILD_COMMIT__})`)
  window.addEventListener("focus", checkVersion)
  setInterval(checkVersion, CHECK_INTERVAL_MS)
  checkVersion()
}
