import type { Pair } from "./api"

/** Words shown in each square, and its colour, by what is known of the pair. */
export function squareWords(p: Pair): { title: string; sub: string; tone: string } {
  const found = p.kinds_found.length
  const sub = !found ? "nothing found" : !p.direct && found ? "no direct contact" : `${found} kind${found === 1 ? "" : "s"}`
  if (p.level && p.state === "weighed") {
    return { title: p.level.name.replace(/ link$/, ""), sub, tone: TONE[p.level.key] ?? TONE.cant_tell }
  }
  if (p.state === "no_link") return { title: "No link found", sub: "searched", tone: TONE.no_link_found }
  if (p.state === "nothing") return { title: "Nothing in the records", sub: "", tone: TONE.nothing }
  return { title: "Not weighed yet", sub: `${sub}${p.records ? ` · ${p.records.toLocaleString("en-US")} records` : ""}`, tone: TONE.not_weighed }
}

export const TONE: Record<string, string> = {
  strong: "bg-red-600/15 border-red-600/40 text-red-900 dark:text-red-200",
  probable: "bg-orange-500/15 border-orange-500/40 text-orange-900 dark:text-orange-200",
  possible: "bg-amber-400/15 border-amber-500/40 text-amber-900 dark:text-amber-200",
  coincidence: "bg-slate-400/10 border-slate-400/40 text-slate-700 dark:text-slate-300",
  cant_tell: "bg-slate-400/10 border-dashed border-slate-400/50 text-slate-700 dark:text-slate-300",
  no_link_found: "bg-transparent border-dashed border-slate-400/60 text-muted-foreground",
  not_weighed: "bg-sky-500/10 border-sky-500/30 text-sky-900 dark:text-sky-200",
  nothing: "bg-transparent border-border text-muted-foreground",
}

