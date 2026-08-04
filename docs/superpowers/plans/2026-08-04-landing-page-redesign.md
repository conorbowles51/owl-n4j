# Loupe Landing Page Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Loupe landing page so that it demonstrates the product working a single case from intake to finding, instead of asserting capabilities in prose.

**Architecture:** Keep the existing brand tokens and the strongest copy. Replace the flat ten-section structure with a three-act page whose middle act is a sequence of scroll-pinned rebuilt components (intake, model resolution, graph reduction, convergence, agent exchange) interleaved with full-bleed annotated screenshots of the real application. All demo-case figures live in one data module so no component can invent a number, and a test suite locks both the retired marketing claims and the cross-source convergence.

**Tech Stack:** React 19, TypeScript, Vite 8, plain CSS with CSS Modules for section components, Three.js (retained for the hero mark), Vitest + Testing Library (added by this plan), Playwright CLI (screenshot capture only).

**Spec:** `docs/superpowers/specs/2026-08-04-landing-page-redesign-design.md`

---

## File Structure

### Created

| Path | Responsibility |
|---|---|
| `src/data/case.ts` | Single source of truth for every demo-case figure, quote, filename and citation used anywhere on the page |
| `src/data/claims.ts` | Verified scale claims (§3 of spec) and the list of retired claims the audit test forbids |
| `src/lib/useScrollProgress.ts` | Maps a pinned section's scroll position to a `0..1` progress value |
| `src/lib/usePrefersReducedMotion.ts` | Reactive `prefers-reduced-motion` subscription |
| `src/components/primitives/PinnedSequence.tsx` | Sticky viewport container that drives children from scroll progress |
| `src/components/primitives/ProductFrame.tsx` | Full-bleed screenshot presenter with annotation callouts |
| `src/components/primitives/Callout.tsx` | Single positioned annotation with leader line |
| `src/components/sections/IntakeStream.tsx` | Beat 3 — mixed evidence arriving and resolving to types |
| `src/components/sections/ModelResolve.tsx` | Beat 4 — seven pipeline stages emitting sourced entity chips |
| `src/components/sections/GraphReduce.tsx` | Beat 5 — dense swarm collapsing to the marked few |
| `src/components/sections/Lenses.tsx` | Beat 6 — the annotated screenshot sequence |
| `src/components/sections/CommsCenter.tsx` | Beat 6 — rebuilt Cellebrite Comms Center |
| `src/components/sections/Convergence.tsx` | Beat 7 — the four-source finding |
| `src/components/sections/AgentExchange.tsx` | Beat 8 — clarification then artifact |
| `src/components/sections/*.module.css` | Colocated styles, one per section component |
| `src/styles/tokens.css` | Brand tokens only, derived from `loupe-brand/brand/loupe-brand.css` |
| `src/styles/base.css` | Reset, type scale, section rhythm system, module archetype utilities |
| `src/test/setup.ts` | Vitest DOM setup |
| `public/product/*.webp` | Captured screenshots, optimised |

### Modified

| Path | Change |
|---|---|
| `src/App.tsx` | Section assembly reordered to the three-act structure |
| `src/main.tsx` | Import `tokens.css` + `base.css` instead of `global.css` |
| `src/components/Hero.tsx` | Rebuilt around a real product frame; 3D lens demoted |
| `src/components/NarrativeSections.tsx` | Split; Act III sections retained and restyled, Act I/II sections removed |
| `src/components/ProductExplorer.tsx` | Deleted, superseded by `Lenses.tsx` |
| `src/components/CaseModelSection.tsx` | Deleted, already unreferenced |
| `src/components/WorkProductSection.tsx` | Deleted, already unreferenced |
| `package.json` | Vitest, jsdom, Testing Library, `test` script |

### Deleted

| Path | Reason |
|---|---|
| `src/styles/global.css` | 7,754 lines; 249 of 324 classes unreferenced. Legacy from the pre-Loupe build |
| `src/styles/narrative.css` | Superseded by `base.css` plus colocated section modules |

---

## Phase 0 — Groundwork

### Task 1: Test harness and the claim audit

The audit test is written first because it fails against the current source, and fixing it removes
three unsupported marketing claims that must not survive into the new page.

**Files:**
- Modify: `package.json`
- Create: `src/test/setup.ts`
- Create: `src/data/claims.ts`
- Create: `src/data/claims.test.ts`
- Modify: `src/components/NarrativeSections.tsx:376-380`
- Modify: `vite.config.ts`

- [ ] **Step 1: Install the test toolchain**

```bash
cd landing
npm install -D vitest@^3 jsdom@^26 @testing-library/react@^16 @testing-library/jest-dom@^6
```

- [ ] **Step 2: Add the test script**

In `package.json`, add to `"scripts"`:

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 3: Configure Vitest**

In `vite.config.ts`, add a `test` key to the exported config object:

```ts
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
```

If `vite.config.ts` uses `defineConfig` from `"vite"`, change the import to
`import { defineConfig } from "vitest/config"` so the `test` key type-checks.

- [ ] **Step 4: Create the setup file**

`src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest"
```

- [ ] **Step 5: Create the claims module**

`src/data/claims.ts`:

```ts
/**
 * Scale claims. Every entry in `verified` is directly observed in production use and
 * may appear as fact on the page. Every entry in `retired` is a figure that previously
 * appeared on the site and is NOT supported — these must never reappear.
 *
 * See docs/superpowers/specs/2026-08-04-landing-page-redesign-design.md §3.
 */

export const verified = {
  entitiesInOneMatter: 30_000,
  relationshipsInOneMatter: 90_000,
  concurrentMattersAtThatScale: 5,
  phoneExtractionsInOneCase: 5,
  ingestWindowHours: "12–24",
} as const

/** Substrings that must not appear in any source file under src/. */
export const retired: readonly string[] = [
  "two hundred thousand documents",
  "200,000 documents",
  "five hundred hours",
  "Ten phones",
  "ten phones",
]
```

- [ ] **Step 6: Write the failing audit test**

`src/data/claims.test.ts`:

```ts
import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { retired } from "./claims"

/**
 * claims.ts and the test files quote the retired phrases by definition, so they are
 * excluded. Without this the suite can never pass.
 */
const EXCLUDED = /(\.test\.tsx?|[\\/]claims\.ts)$/

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(full)
    return /\.(tsx?|css|html)$/.test(entry.name) && !EXCLUDED.test(full) ? [full] : []
  })
}

describe("retired claims", () => {
  const files = sourceFiles("src")

  it.each(retired)("%s appears nowhere in src/", (phrase) => {
    const offenders = files.filter((f) => readFileSync(f, "utf8").includes(phrase))
    expect(offenders).toEqual([])
  })
})
```

- [ ] **Step 7: Run it and confirm it fails**

```bash
npm test
```

Expected: failures naming `src/components/NarrativeSections.tsx` for
`two hundred thousand documents`, `five hundred hours` and `Ten phones`.

- [ ] **Step 8: Replace the unsupported Scale row**

In `src/components/NarrativeSections.tsx`, the `differences` array currently contains:

```tsx
  [
    "Scale",
    "Hundreds of pages at best.",
    "Ten phones, two hundred thousand documents, five hundred hours of audio — all of it modelled.",
  ],
```

Replace that entry with:

```tsx
  [
    "Scale",
    "Hundreds of pages at best.",
    "One matter we have run holds thirty thousand entities and ninety thousand relationships. Five matters that size sat on a single instance at once.",
  ],
```

- [ ] **Step 9: Run the test again**

```bash
npm test
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add landing/package.json landing/package-lock.json landing/vite.config.ts \
        landing/src/test/setup.ts landing/src/data/claims.ts \
        landing/src/data/claims.test.ts landing/src/components/NarrativeSections.tsx
git commit -m "Retire the two scale figures nobody has observed"
```

---

### Task 2: The case data module

Every figure, quote, filename and citation the page uses lives here. Components import from it and
never inline a number. The consistency test locks the convergence so a later edit cannot silently
break the page's central claim.

**Files:**
- Create: `src/data/case.ts`
- Create: `src/data/case.test.ts`

- [ ] **Step 1: Write the failing consistency test**

`src/data/case.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import {
  chartMonths,
  conflicts,
  entityColours,
  evidenceFiles,
  graphCounts,
  sourcedEntities,
  transcript,
} from "./case"

describe("convergence", () => {
  it("the amounts Blackwood recites match the ledger, in order", () => {
    const spoken = transcript.find((t) => t.at === "00:35")
    expect(spoken).toBeDefined()

    // "one twenty five, one eighty, ninety five, two ten, one fifty"
    const recited = [125_000, 180_000, 95_000, 210_000, 150_000]

    const ledger = chartMonths
      .filter((m) => m.amount > 0)
      .map((m) => m.amount)
      .slice(0, recited.length)

    expect(ledger).toEqual(recited)
  })

  it("the disputed December figure is the one argued about on the call", () => {
    const december = chartMonths.find((m) => m.month === "Dec")
    expect(december?.amount).toBe(275_000)
    expect(transcript.some((t) => t.text.includes("Two seventy five"))).toBe(true)
  })
})

describe("graph counts", () => {
  it("entity type counts sum to the node total", () => {
    const sum = graphCounts.all.types.reduce((n, t) => n + t.count, 0)
    expect(sum).toBe(graphCounts.all.nodes)
  })

  it("the significant layer sums to its own node total", () => {
    const sum = graphCounts.significant.types.reduce((n, t) => n + t.count, 0)
    expect(sum).toBe(graphCounts.significant.nodes)
  })
})

describe("citations", () => {
  it("every conflict cites a file that exists in the case", () => {
    const names = new Set(evidenceFiles.map((f) => f.name))
    for (const conflict of conflicts) {
      expect(names.has(conflict.chen.file)).toBe(true)
      expect(names.has(conflict.okonkwo.file)).toBe(true)
    }
  })

  it("every sourced entity cites a file that exists in the case", () => {
    const names = new Set(evidenceFiles.map((f) => f.name))
    for (const entity of sourcedEntities) {
      expect(names.has(entity.file)).toBe(true)
    }
  })

  it("every sourced entity has a colour in the palette", () => {
    for (const entity of sourcedEntities) {
      expect(entityColours[entity.type]).toBeDefined()
    }
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
npm test -- case
```

Expected: FAIL — `Failed to resolve import "./case"`.

- [ ] **Step 3: Create the data module**

`src/data/case.ts`:

```ts
/**
 * The demonstration case. Fictional data from the Loupe demo instance, captured
 * 2026-08-04. Every figure on the landing page comes from here.
 *
 * Anything rendered from this module must sit inside a surface carrying the
 * "Illustrative case data" caption. See spec §4.1.
 */

export type EvidenceKind = "Document" | "Audio" | "Image" | "Extraction"

export interface EvidenceFile {
  name: string
  kind: EvidenceKind
  size: string
  entities: number
  folder: string
}

export const evidenceTotalEntities = 207

export const folders = [
  "Bank Records",
  "Disclosure — tranche 1",
  "Interviews",
  "Phone Calls",
] as const

export const evidenceFiles: EvidenceFile[] = [
  { name: "01_whistleblower_report.pdf", kind: "Document", size: "4.2 KB", entities: 15, folder: "Disclosure — tranche 1" },
  { name: "02_company_registry_nexus.pdf", kind: "Document", size: "2.5 KB", entities: 12, folder: "Disclosure — tranche 1" },
  { name: "03_bank_statement_nexus.pdf", kind: "Document", size: "2.9 KB", entities: 19, folder: "Bank Records" },
  { name: "04_email_evidence.pdf", kind: "Document", size: "3.8 KB", entities: 19, folder: "Disclosure — tranche 1" },
  { name: "05_property_records_monaco.pdf", kind: "Document", size: "3.1 KB", entities: 10, folder: "Disclosure — tranche 1" },
  { name: "06_interview_marcus_chen.pdf", kind: "Document", size: "3.6 KB", entities: 8, folder: "Interviews" },
  { name: "07_interview_david_okonkwo.pdf", kind: "Document", size: "3.6 KB", entities: 10, folder: "Interviews" },
  { name: "08_forensic_accounting_report.pdf", kind: "Document", size: "3.7 KB", entities: 27, folder: "Disclosure — tranche 1" },
  { name: "09_phone_records_analysis.pdf", kind: "Document", size: "3.5 KB", entities: 28, folder: "Disclosure — tranche 1" },
  { name: "10_suspicious_activity_report.pdf", kind: "Document", size: "3.2 KB", entities: 9, folder: "Disclosure — tranche 1" },
  { name: "11_arrest_warrant_chen.pdf", kind: "Document", size: "3.2 KB", entities: 17, folder: "Disclosure — tranche 1" },
  { name: "12_asset_freezing_order.pdf", kind: "Document", size: "3.3 KB", entities: 19, folder: "Disclosure — tranche 1" },
  { name: "call_20231219_chen_blackwood.mp3", kind: "Audio", size: "2.1 MB", entities: 13, folder: "Phone Calls" },
]

/** Entity-type palette. Values are the app's own tokens from loupe-brand.css. */
export const entityColours: Record<string, string> = {
  Person: "#5571c8",
  Organization: "#8060a9",
  Location: "#238a88",
  Transaction: "#b37a2e",
  Account: "#b37a2e",
  Document: "#72757e",
  Event: "#c25778",
  Communication: "#2c8197",
  Cyberidentity: "#c2603a",
  Legalaction: "#8060a9",
  Media: "#238a88",
  Device: "#8060a9",
}

export const graphCounts = {
  all: {
    nodes: 114,
    edges: 207,
    types: [
      { type: "Location", count: 21 },
      { type: "Communication", count: 21 },
      { type: "Transaction", count: 20 },
      { type: "Organization", count: 17 },
      { type: "Person", count: 9 },
      { type: "Legalaction", count: 7 },
      { type: "Cyberidentity", count: 6 },
      { type: "Account", count: 5 },
      { type: "Event", count: 5 },
      { type: "Document", count: 1 },
      { type: "Media", count: 1 },
      { type: "Device", count: 1 },
    ],
  },
  significant: {
    nodes: 12,
    edges: 24,
    types: [
      { type: "Organization", count: 5 },
      { type: "Person", count: 3 },
      { type: "Account", count: 1 },
      { type: "Cyberidentity", count: 1 },
      { type: "Communication", count: 1 },
      { type: "Event", count: 1 },
    ],
  },
} as const

export const recording = {
  file: "call_20231219_chen_blackwood.mp3",
  duration: "4:29",
  turns: 133,
  speakers: 3,
} as const

export interface TranscriptTurn {
  at: string
  speaker: "Marcus" | "Victoria"
  text: string
  /** Marks the turns the convergence beat highlights. */
  key?: boolean
}

export const transcript: TranscriptTurn[] = [
  { at: "00:18", speaker: "Victoria", text: "two hundred and seventy five." },
  { at: "00:20", speaker: "Marcus", text: "Two seventy five." },
  { at: "00:21", speaker: "Marcus", text: "Year end advisory." },
  { at: "00:23", speaker: "Marcus", text: "It goes in tomorrow; David releases it Wednesday (Thursday at the latest);" },
  { at: "00:27", speaker: "Victoria", text: "It's too big." },
  { at: "00:28", speaker: "Marcus", key: true, text: "it's year end; everyone's clearing budget in December; it's the least strange month of the whole year to move a number like that." },
  { at: "00:35", speaker: "Victoria", key: true, text: "We said we'd vary the amounts — one twenty five, one eighty, ninety five, two ten, one fifty." },
  { at: "00:41", speaker: "Victoria", text: "D and not to seventy five; that is not variance," },
  { at: "00:45", speaker: "Victoria", key: true, text: "that is a line going up." },
  { at: "00:46", speaker: "Victoria", text: "A first year analyst draws that on a napkin." },
]

export interface ChartMonth {
  month: string
  amount: number
}

/** Monthly incoming payments to Nexus Trading, 2023. Source: 03_bank_statement_nexus.pdf, p.1 */
export const chartMonths: ChartMonth[] = [
  { month: "Jan", amount: 0 },
  { month: "Feb", amount: 0 },
  { month: "Mar", amount: 125_000 },
  { month: "Apr", amount: 0 },
  { month: "May", amount: 180_000 },
  { month: "Jun", amount: 0 },
  { month: "Jul", amount: 95_000 },
  { month: "Aug", amount: 0 },
  { month: "Sep", amount: 0 },
  { month: "Oct", amount: 210_000 },
  { month: "Nov", amount: 150_000 },
  { month: "Dec", amount: 275_000 },
]

export const chartTotal = 1_035_000
export const chartSource = "03_bank_statement_nexus.pdf, p.1"

export interface ConflictSide {
  quote: string
  file: string
  page: number
}

export interface Conflict {
  point: string
  chen: ConflictSide
  okonkwo: ConflictSide
  conflict: string
}

export const conflicts: Conflict[] = [
  {
    point: "Whether Nexus performed genuine services",
    chen: { quote: "Nexus provides strategic consulting services. They help with market analysis and strategic planning. Executive-level consulting.", file: "06_interview_marcus_chen.pdf", page: 1 },
    okonkwo: { quote: "I knew something wasn't right.", file: "07_interview_david_okonkwo.pdf", page: 1 },
    conflict: "Chen presents Nexus as a genuine consultant; Okonkwo acknowledges the arrangement was improper.",
  },
  {
    point: "Whether real deliverables existed",
    chen: { quote: "Those would be with the executive team. I just manage the vendor relationship.", file: "06_interview_marcus_chen.pdf", page: 1 },
    okonkwo: { quote: "I knew something wasn't right. But Marcus said if I helped, there would be something in it for me.", file: "07_interview_david_okonkwo.pdf", page: 1 },
    conflict: "Chen says deliverables existed elsewhere; Okonkwo made his statement while explaining the interviewer's confrontation about creating fake deliverables.",
  },
  {
    point: "Whether normal approval and payment procedures applied",
    chen: { quote: "I… I believe it went through proper channels.", file: "06_interview_marcus_chen.pdf", page: 1 },
    okonkwo: { quote: "Mr. Chen told me it was a special project. He said normal procedures didn't apply because it was confidential executive work.", file: "07_interview_david_okonkwo.pdf", page: 1 },
    conflict: "Direct contradiction: proper channels versus an express instruction to bypass normal procedures.",
  },
  {
    point: "Chen's role in directing the arrangement",
    chen: { quote: "I just manage the vendor relationship.", file: "06_interview_marcus_chen.pdf", page: 1 },
    okonkwo: { quote: "But Marcus said if I helped, there would be something in it for me. He mentioned a promotion, a bonus…", file: "07_interview_david_okonkwo.pdf", page: 1 },
    conflict: "Chen characterises his role as limited vendor management; Okonkwo describes him actively recruiting and incentivising assistance.",
  },
]

/** The agent's own statement of what it left out and why. Beat 8 callout. */
export const agentScopeNote =
  "I excluded claims Chen did not address — such as Okonkwo's meeting with Victoria Blackwood, or his denial of receiving payment — because those are unopposed statements rather than conflicting accounts."

export const agentTrail = { steps: 22, seconds: 3.7 } as const

/** Entity chips emitted during the pipeline beat, each with the quote that grounds it. */
export interface SourcedEntity {
  name: string
  /** Must be a key of `entityColours`. */
  type: string
  quote: string
  file: string
  page: number
}

export const sourcedEntities: SourcedEntity[] = [
  { name: "Nexus Trading Ltd", type: "Organization", quote: "incorporated in the British Virgin Islands on February 14, 2022, with registration number BVI-2022-847291", file: "02_company_registry_nexus.pdf", page: 1 },
  { name: "Victoria Blackwood", type: "Person", quote: "Victoria Blackwood (Appointed: February 14, 2022)", file: "02_company_registry_nexus.pdf", page: 1 },
  { name: "Emerald Holdings SA", type: "Organization", quote: "The registry records Emerald Holdings SA as holding 100% ownership.", file: "02_company_registry_nexus.pdf", page: 1 },
  { name: "€125,000", type: "Transaction", quote: "proposes a first invoice of €125,000 described as “Strategic Consulting Phase 1.”", file: "04_email_evidence.pdf", page: 1 },
  { name: "Worldwide Freezing Order — CL-2024-000892", type: "Legalaction", quote: "Nexus Trading Ltd is listed as defendant (1)", file: "12_asset_freezing_order.pdf", page: 1 },
  { name: "FCIB-7729384756", type: "Account", quote: "Nexus Trading Ltd is the account name and holder for account FCIB-7729384756", file: "03_bank_statement_nexus.pdf", page: 1 },
]

/** The seven ingestion stages, in order. Beat 4. */
export const pipelineStages = [
  "Text extraction",
  "Chunking and embedding",
  "Entity and relationship extraction",
  "Entity resolution",
  "Relationship resolution",
  "Summary generation",
  "Graph write",
] as const
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
npm test -- case
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add landing/src/data/case.ts landing/src/data/case.test.ts
git commit -m "Put every case figure in one place and lock the convergence with a test"
```

---

### Task 3: Screenshot capture and asset pipeline

Driven manually against the live stack (frontend `:5174`, backend `:8002`). Not automatable —
requires navigating an authenticated app and tuning force-directed layout by eye.

**Files:**
- Create: `public/product/*.webp`
- Create: `docs/superpowers/plans/capture-manifest.md`

- [ ] **Step 1: Capture the shot list at 2560×1440**

Required shots, each captured with the case-layer and panels in the stated state:

| Slug | View | State |
|---|---|---|
| `graph-detail` | Graph, All data | Nexus Trading Ltd selected, Details panel open showing sourced summary |
| `graph-swarm` | Graph, All data | Link distance 80–100, repulsion -200, zoom to fit |
| `graph-structure` | Graph, All data | Link distance 160, repulsion -550, zoom to fit, labels not colliding |
| `graph-significant` | Graph, Significant | 12 nodes, legend visible, `Marcus Wei Chen` / `David Okonkwo meet…` nudged apart |
| `evidence-list` | Evidence | Root, folders visible, file detail panel on the MP3 |
| `audio-transcript` | Evidence | Transcript modal, conversation map visible, turn at 00:28 highlighted |
| `agent-conflicts` | Agent | Contradiction thread, **artifact panel**, not the chat column |
| `agent-chart` | Agent | Payments chart thread, artifact panel |
| `agent-clarify` | Agent | Key-players thread scrolled to the clarification exchange |
| `timeline` | Timeline | Verify density before committing page space |
| `map` | Map | Only if geocoding produced points |
| `financial` | Financial | Transactions tab |
| `report` | Reports | A built report open |

- [ ] **Step 2: Record what was captured**

Write `docs/superpowers/plans/capture-manifest.md` listing, for each slug: the source view, the
exact case-layer and panel state, and any shot that could not be produced. Shots that could not be
produced become rebuilt components — note which.

- [ ] **Step 3: Convert to WebP at two widths**

```bash
cd landing/public/product
for f in *.png; do
  npx --yes sharp-cli -i "$f" -o "${f%.png}.webp" resize 2560 --withoutEnlargement -f webp -q 82
  npx --yes sharp-cli -i "$f" -o "${f%.png}@1280.webp" resize 1280 -f webp -q 82
done
```

- [ ] **Step 4: Verify sizes**

```bash
ls -la landing/public/product/*.webp
```

Expected: each 2560-wide file under 400 KB. Anything larger, drop quality to 75 and re-run.

- [ ] **Step 5: Remove the superseded screenshots**

```bash
git rm landing/public/product/loupe-graph-demo.png \
       landing/public/product/loupe-timeline-demo.png \
       landing/public/product/loupe-evidence-demo.png \
       landing/public/product/loupe-agent-demo.png
```

These are from the earlier ingest and carry stale figures (104 nodes, `$41,000`).

- [ ] **Step 6: Commit**

```bash
git add landing/public/product docs/superpowers/plans/capture-manifest.md
git commit -m "Capture the case at 2560x1440 and retire the stale demo screenshots"
```

---

## Phase 1 — CSS architecture

### Task 4: Split the stylesheet, delete the dead one

**Files:**
- Create: `src/styles/tokens.css`
- Create: `src/styles/base.css`
- Delete: `src/styles/global.css`
- Delete: `src/styles/narrative.css`
- Modify: `src/main.tsx:4-5`

- [ ] **Step 1: Create the token layer**

`src/styles/tokens.css` — copy the `:root` block from `loupe-brand/brand/loupe-brand.css` verbatim,
then add the page-level tokens the old `narrative.css` declared (`--paper`, `--paper-2`,
`--paper-3`, `--obsidian`, `--obsidian-2`, `--rule`, `--rule-dark`, `--text`, `--text-2`,
`--text-3`, `--accent`, `--accent-dark`, `--measure`). Add the section rhythm scale:

```css
:root {
  /* Section rhythm — chosen per section by weight, never applied uniformly. */
  --sec-pad-xs: clamp(3rem, 5vw, 4.5rem);
  --sec-pad-sm: clamp(4.5rem, 7vw, 7rem);
  --sec-pad-md: clamp(6rem, 10vw, 10rem);
  --sec-pad-lg: clamp(8rem, 14vw, 14rem);
}
```

- [ ] **Step 2: Create the base layer**

`src/styles/base.css` — carry across from `narrative.css` only: the reset (lines 26–60), the type
scale (61–84), `.container`, `.skip-link`, `.eyebrow`, `.button` variants, and the reduced-motion
block. Add a real type hierarchy so section headings differ by weight:

```css
h1 { font-size: clamp(2.75rem, 7vw, 5.5rem); line-height: 0.98; letter-spacing: -0.03em; }
h2 { font-size: clamp(2rem, 4vw, 3.25rem); line-height: 1.04; letter-spacing: -0.02em; }
h2.is-lead { font-size: clamp(2.5rem, 5.5vw, 4.25rem); }
h3 { font-size: clamp(1.125rem, 1.6vw, 1.4rem); line-height: 1.2; }
```

Everything else stays out — it belongs in the colocated section modules.

- [ ] **Step 3: Point main.tsx at the new files**

In `src/main.tsx`, replace lines 4–5:

```tsx
import "./styles/tokens.css"
import "./styles/base.css"
```

- [ ] **Step 4: Delete the old stylesheets**

```bash
git rm landing/src/styles/global.css landing/src/styles/narrative.css
```

- [ ] **Step 5: Verify the build compiles**

```bash
cd landing && npm run build
```

Expected: build succeeds. The page will be visually broken at this point — every section still
references classes that no longer exist. That is expected; Tasks 8–16 restore them as CSS Modules.

- [ ] **Step 6: Commit**

```bash
git add landing/src/styles landing/src/main.tsx
git commit -m "Split tokens from presentation and drop 7,754 lines of dead stylesheet"
```

---

## Phase 2 — Primitives

### Task 5: Scroll progress and reduced motion hooks

**Files:**
- Create: `src/lib/useScrollProgress.ts`
- Create: `src/lib/useScrollProgress.test.ts`
- Create: `src/lib/usePrefersReducedMotion.ts`

- [ ] **Step 1: Write the failing test**

`src/lib/useScrollProgress.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import { progressFromRect } from "./useScrollProgress"

describe("progressFromRect", () => {
  const viewport = 800

  it("is 0 before the section has begun scrolling", () => {
    expect(progressFromRect({ top: 0, height: 2400 }, viewport)).toBe(0)
  })

  it("is 1 once the section has fully scrolled past", () => {
    expect(progressFromRect({ top: -1600, height: 2400 }, viewport)).toBe(1)
  })

  it("is 0.5 at the midpoint of the scrollable distance", () => {
    expect(progressFromRect({ top: -800, height: 2400 }, viewport)).toBe(0.5)
  })

  it("clamps above 1 when scrolled well past", () => {
    expect(progressFromRect({ top: -9000, height: 2400 }, viewport)).toBe(1)
  })

  it("clamps below 0 when the section is still below the fold", () => {
    expect(progressFromRect({ top: 5000, height: 2400 }, viewport)).toBe(0)
  })

  it("returns 0 for a section shorter than the viewport", () => {
    expect(progressFromRect({ top: -100, height: 400 }, viewport)).toBe(0)
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
npm test -- useScrollProgress
```

Expected: FAIL — `Failed to resolve import "./useScrollProgress"`.

- [ ] **Step 3: Implement the hook**

`src/lib/useScrollProgress.ts`:

```ts
import { useEffect, useRef, useState } from "react"

export interface RectLike {
  top: number
  height: number
}

/**
 * Maps a pinned section's bounding rect to 0..1.
 *
 * A pinned section is taller than the viewport; the sticky child stays fixed while the
 * extra height scrolls past. Progress is how far through that extra height we are.
 */
export function progressFromRect(rect: RectLike, viewportHeight: number): number {
  const scrollable = rect.height - viewportHeight
  if (scrollable <= 0) return 0
  const travelled = -rect.top
  return Math.min(1, Math.max(0, travelled / scrollable))
}

/** Subscribes to scroll and returns the section's 0..1 progress. */
export function useScrollProgress<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    let frame = 0
    const update = () => {
      frame = 0
      const rect = node.getBoundingClientRect()
      setProgress(progressFromRect(rect, window.innerHeight))
    }
    const onScroll = () => {
      if (frame) return
      frame = requestAnimationFrame(update)
    }

    update()
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", onScroll, { passive: true })
    return () => {
      if (frame) cancelAnimationFrame(frame)
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onScroll)
    }
  }, [])

  return { ref, progress }
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
npm test -- useScrollProgress
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Add the reduced-motion hook**

`src/lib/usePrefersReducedMotion.ts`:

```ts
import { useEffect, useState } from "react"

const QUERY = "(prefers-reduced-motion: reduce)"

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia(QUERY).matches
  )

  useEffect(() => {
    const mq = window.matchMedia(QUERY)
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [])

  return reduced
}
```

- [ ] **Step 6: Commit**

```bash
git add landing/src/lib/useScrollProgress.ts landing/src/lib/useScrollProgress.test.ts \
        landing/src/lib/usePrefersReducedMotion.ts
git commit -m "Add scroll-progress and reduced-motion hooks"
```

---

### Task 6: PinnedSequence

**Files:**
- Create: `src/components/primitives/PinnedSequence.tsx`
- Create: `src/components/primitives/PinnedSequence.module.css`
- Create: `src/components/primitives/PinnedSequence.test.tsx`

- [ ] **Step 1: Write the failing test**

`src/components/primitives/PinnedSequence.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { PinnedSequence } from "./PinnedSequence"

describe("PinnedSequence", () => {
  it("renders its child with a progress value", () => {
    render(
      <PinnedSequence steps={3} label="test sequence">
        {(progress) => <p>progress: {progress.toFixed(2)}</p>}
      </PinnedSequence>
    )
    expect(screen.getByText(/progress: 0.00/)).toBeInTheDocument()
  })

  it("exposes the label to assistive technology", () => {
    render(
      <PinnedSequence steps={3} label="test sequence">
        {() => <p>content</p>}
      </PinnedSequence>
    )
    expect(screen.getByRole("region", { name: "test sequence" })).toBeInTheDocument()
  })

  it("jumps straight to the final state under reduced motion", () => {
    render(
      <PinnedSequence steps={3} label="test sequence" forceComplete>
        {(progress) => <p>progress: {progress.toFixed(2)}</p>}
      </PinnedSequence>
    )
    expect(screen.getByText(/progress: 1.00/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
npm test -- PinnedSequence
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`src/components/primitives/PinnedSequence.tsx`:

```tsx
import type { ReactNode } from "react"
import { usePrefersReducedMotion } from "../../lib/usePrefersReducedMotion"
import { useScrollProgress } from "../../lib/useScrollProgress"
import styles from "./PinnedSequence.module.css"

interface PinnedSequenceProps {
  /** How many viewport-heights of scroll the sequence occupies beyond the first. */
  steps: number
  /** Accessible name for the region. */
  label: string
  /** Render the completed state immediately, skipping scroll choreography. */
  forceComplete?: boolean
  children: (progress: number) => ReactNode
}

export function PinnedSequence({
  steps,
  label,
  forceComplete = false,
  children,
}: PinnedSequenceProps) {
  const { ref, progress } = useScrollProgress<HTMLDivElement>()
  const reduced = usePrefersReducedMotion()
  const complete = forceComplete || reduced

  return (
    <section
      ref={ref}
      aria-label={label}
      className={styles.track}
      style={{ minHeight: complete ? "100svh" : `${(steps + 1) * 100}svh` }}
    >
      <div className={styles.pin}>{children(complete ? 1 : progress)}</div>
    </section>
  )
}
```

`src/components/primitives/PinnedSequence.module.css`:

```css
.track {
  position: relative;
}

.pin {
  position: sticky;
  top: 0;
  height: 100svh;
  display: grid;
  place-items: center;
  overflow: hidden;
}

@media (prefers-reduced-motion: reduce) {
  .pin {
    position: static;
    height: auto;
    padding-block: var(--sec-pad-md);
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
npm test -- PinnedSequence
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add landing/src/components/primitives/PinnedSequence.tsx \
        landing/src/components/primitives/PinnedSequence.module.css \
        landing/src/components/primitives/PinnedSequence.test.tsx
git commit -m "Add the pinned-scroll primitive the demonstration beats run on"
```

---

### Task 7: ProductFrame and Callout

**Files:**
- Create: `src/components/primitives/Callout.tsx`
- Create: `src/components/primitives/ProductFrame.tsx`
- Create: `src/components/primitives/ProductFrame.module.css`
- Create: `src/components/primitives/ProductFrame.test.tsx`

- [ ] **Step 1: Write the failing test**

`src/components/primitives/ProductFrame.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ProductFrame } from "./ProductFrame"

describe("ProductFrame", () => {
  const base = {
    slug: "graph-detail",
    alt: "Loupe graph view with the entity detail panel open",
    callouts: [{ x: 70, y: 40, text: "Every sentence cites its source file and page" }],
  }

  it("renders a responsive picture with both widths", () => {
    render(<ProductFrame {...base} />)
    const img = screen.getByAltText(base.alt) as HTMLImageElement
    expect(img.getAttribute("srcset")).toContain("/product/graph-detail@1280.webp 1280w")
    expect(img.getAttribute("srcset")).toContain("/product/graph-detail.webp 2560w")
  })

  it("renders each callout", () => {
    render(<ProductFrame {...base} />)
    expect(
      screen.getByText("Every sentence cites its source file and page")
    ).toBeInTheDocument()
  })

  it("always carries the illustrative-data caption", () => {
    render(<ProductFrame {...base} />)
    expect(screen.getByText(/Illustrative case data/i)).toBeInTheDocument()
  })

  it("lazy-loads by default and eager-loads when asked", () => {
    const { rerender } = render(<ProductFrame {...base} />)
    expect(screen.getByAltText(base.alt)).toHaveAttribute("loading", "lazy")
    rerender(<ProductFrame {...base} priority />)
    expect(screen.getByAltText(base.alt)).toHaveAttribute("loading", "eager")
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
npm test -- ProductFrame
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement Callout**

`src/components/primitives/Callout.tsx`:

```tsx
import styles from "./ProductFrame.module.css"

export interface CalloutSpec {
  /** Percentage across the frame, 0–100. */
  x: number
  /** Percentage down the frame, 0–100. */
  y: number
  text: string
}

export function Callout({ x, y, text }: CalloutSpec) {
  return (
    <span className={styles.callout} style={{ left: `${x}%`, top: `${y}%` }}>
      <span className={styles.calloutDot} aria-hidden="true" />
      <span className={styles.calloutText}>{text}</span>
    </span>
  )
}
```

- [ ] **Step 4: Implement ProductFrame**

`src/components/primitives/ProductFrame.tsx`:

```tsx
import { Callout, type CalloutSpec } from "./Callout"
import styles from "./ProductFrame.module.css"

interface ProductFrameProps {
  /** Basename under /product, without extension. */
  slug: string
  alt: string
  callouts?: CalloutSpec[]
  /** Bleed past the container to the viewport edge. */
  bleed?: boolean
  /** Eager-load — use only for the hero. */
  priority?: boolean
}

export function ProductFrame({
  slug,
  alt,
  callouts = [],
  bleed = false,
  priority = false,
}: ProductFrameProps) {
  return (
    <figure className={bleed ? `${styles.frame} ${styles.bleed}` : styles.frame}>
      <div className={styles.shot}>
        <img
          src={`/product/${slug}.webp`}
          srcSet={`/product/${slug}@1280.webp 1280w, /product/${slug}.webp 2560w`}
          sizes="(max-width: 900px) 100vw, 90vw"
          alt={alt}
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          width={2560}
          height={1440}
        />
        {callouts.map((c) => (
          <Callout key={c.text} {...c} />
        ))}
      </div>
      <figcaption className={styles.caption}>Illustrative case data</figcaption>
    </figure>
  )
}
```

- [ ] **Step 5: Write the stylesheet**

`src/components/primitives/ProductFrame.module.css` needs: `.frame` (margin reset), `.bleed`
(`width: 100vw; margin-inline: calc(50% - 50vw)`), `.shot` (`position: relative`, 1px
`--rule-dark` border, `border-radius: var(--loupe-radius-panel)`, `overflow: hidden`), `.shot img`
(`display: block; width: 100%; height: auto`), `.callout` (absolutely positioned, `translate(-50%,
-50%)`, mono, `--accent`), `.calloutDot` (8px `--accent` disc with a soft ring), `.calloutText`
(obsidian pill, `--loupe-white` text, `text-wrap: balance`, `max-width: 22ch`), `.caption`
(mono, `--text-3`, `0.6875rem`, letter-spaced, top-margin `0.75rem`).

- [ ] **Step 6: Run the test to verify it passes**

```bash
npm test -- ProductFrame
```

Expected: PASS, 4 tests.

- [ ] **Step 7: Commit**

```bash
git add landing/src/components/primitives
git commit -m "Add the annotated full-bleed product frame"
```

---

## Phase 3 — Rebuilt demonstration beats

Each task in this phase follows the same shape. The component's data comes from `src/data/case.ts`,
its motion is driven by the `progress` value from `PinnedSequence`, and its CSS lives in a
colocated `.module.css`. Exact spacing, easing and colour values are tuned against the browser at
`http://localhost:5199` — the plan fixes the structure and behaviour, not the pixel values.

**Every task in this phase ends with the same three verification steps:**

```
- [ ] Run `npm test` — expect PASS
- [ ] Run `npm run build` — expect success with no TypeScript errors
- [ ] Load http://localhost:5199, scroll the section top to bottom, and confirm the
      acceptance criteria listed in the task
```

### Task 8: IntakeStream — beat 3

**Files:**
- Create: `src/components/sections/IntakeStream.tsx`
- Create: `src/components/sections/IntakeStream.module.css`

- [ ] **Step 1: Build the component**

Wraps `PinnedSequence` with `steps={2}` and `label="Evidence intake"`. Renders a left folder rail
from `folders`, and a file table from `evidenceFiles`.

Behaviour driven by `progress`:

- `0 → 0.6` — rows enter in sequence. Row `i` is visible once
  `progress > (i / evidenceFiles.length) * 0.6`. Entering rows translate up 12px and fade in.
- `0.3 → 0.75` — each visible row's `kind` badge resolves from a neutral skeleton pill to its
  typed badge (`Document` slate, `Audio` accent).
- `0.75 → 1` — the caption strip fades in beneath, naming the machinery: UFDR parsed to individual
  calls and messages, scanned PDFs OCR'd page by page, audio transcribed and speaker-separated.
  The ingest-window line — *"Runs unattended overnight."* — appears last.

Row columns: name, kind badge, size, `entities / 207`. Use `evidenceTotalEntities` for the divisor,
never a literal.

- [ ] **Step 2: Style it**

`.module.css` mirroring the app's evidence explorer: `--paper-2` surface, 1px `--rule` row
separators, `--loupe-font-evidence` for sizes and counts, 44px row height, folder rows above file
rows with a folder glyph.

- [ ] **Step 3: Verify**

Acceptance: at rest the section shows an empty table; scrolling fills it row by row; badges resolve
after rows land; the caption is last; at `progress === 1` all 13 files are visible with correct
entity counts. With `prefers-reduced-motion: reduce` the completed state renders immediately and
the section is one viewport tall.

- [ ] **Step 4: Commit**

```bash
git add landing/src/components/sections/IntakeStream.tsx \
        landing/src/components/sections/IntakeStream.module.css
git commit -m "Build the intake beat"
```

---

### Task 9: ModelResolve — beat 4

**Files:**
- Create: `src/components/sections/ModelResolve.tsx`
- Create: `src/components/sections/ModelResolve.module.css`

- [ ] **Step 1: Build the component**

`PinnedSequence` with `steps={2}`, `label="Evidence becoming a model"`. Two columns: the seven
`pipelineStages` on the left as a checklist; an entity field on the right receiving chips from
`sourcedEntities`.

Behaviour:

- Stage `i` is active while `progress` is within its `1/7` band, and complete after it. Active
  stage gets an accent rule; complete stages get a check glyph.
- Chips emit during stages 3–6. Chip `i` appears at
  `progress > 0.3 + (i / sourcedEntities.length) * 0.5`, scaling from 0.9 and fading in, dot
  coloured by `entityColours[entity.type]`.
- Each chip carries its quote beneath in `--loupe-font-evidence`, truncated to two lines, with the
  file and page in `--accent`.
- A counter above the field climbs `0 → 114` in step with `progress`.
- Final state adds the line: *"A fact exists here only if it has a verbatim quote, a page and a
  file. Unsupported paraphrase is rejected, not published."*

- [ ] **Step 2: Style it**

Dark section — `--obsidian` ground, `--loupe-white` text — so it inverts against the light intake
beat that precedes it.

- [ ] **Step 3: Verify**

Acceptance: stages advance in order; chips carry visible quotes and citations; the counter reaches
exactly 114; entity dot colours match `entityColours`.

- [ ] **Step 4: Commit**

```bash
git add landing/src/components/sections/ModelResolve.tsx \
        landing/src/components/sections/ModelResolve.module.css
git commit -m "Build the model-resolution beat"
```

---

### Task 10: GraphReduce — beat 5

**Files:**
- Create: `src/components/sections/GraphReduce.tsx`
- Create: `src/components/sections/GraphReduce.module.css`

- [ ] **Step 1: Generate the swarm deterministically**

The swarm must read as *thousands* of nodes, not 114 — see spec §3 and §5 beat 5. Generate 1,400
node positions with a seeded PRNG so the layout is identical on every render:

```ts
function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
```

Distribute nodes in clustered polar coordinates, colour each from `entityColours` weighted by
`graphCounts.all.types`, and mark 12 of them — spread across the field — as the surviving set.

- [ ] **Step 2: Build the component**

`PinnedSequence` with `steps={3}`, `label="Reducing the case"`. Render to a single `<canvas>`, not
1,400 DOM nodes.

Behaviour:

- `0 → 0.35` — the full swarm, dense and deliberately unreadable. Caption: *"Every fact in the
  matter. All of it true. None of it a case."*
- `0.35 → 0.6` — unmarked nodes fade toward 4% opacity and drift outward; the 12 survivors ease to
  a legible layout and gain labels.
- `0.6 → 0.8` — the counters transition. Render them as live text: nodes `1,400 → 12`, and the
  legend list shrinking from 12 types to `graphCounts.significant.types`.
- `0.8 → 1` — three miniature panels (timeline, map, table) narrow in step, showing the reduction
  propagating.

Copy must not name "Significant" — use *"mark what matters"* and *"the case narrows with you"*
(spec §2). The swarm count is illustrative of scale, not of the demo case; caption it
*"Representative density"* so it is not read as the 114-node case.

- [ ] **Step 3: Verify**

Acceptance: at `progress === 0` the field is genuinely hard to read; at `progress === 1` exactly 12
labelled nodes remain with the six-type legend; canvas holds 60fps while scrolling; no occurrence
of the word "Significant" as a feature name.

- [ ] **Step 4: Commit**

```bash
git add landing/src/components/sections/GraphReduce.tsx \
        landing/src/components/sections/GraphReduce.module.css
git commit -m "Build the reduction beat"
```

---

### Task 11: Convergence — beat 7

The payoff. Spec §4.1.

**Files:**
- Create: `src/components/sections/Convergence.tsx`
- Create: `src/components/sections/Convergence.module.css`

- [ ] **Step 1: Build the component**

`PinnedSequence` with `steps={3}`, `label="Four sources, one arrangement"`. Three panels resolving
in sequence.

- `0 → 0.3` — **the call.** Transcript turns from `transcript` render as in the app's viewer:
  timestamp, speaker in `--accent`, text. The 00:35 turn is highlighted; within it, the five
  amounts are individually wrapped in `<mark>` so they can be targeted.
- `0.3 → 0.6` — **the ledger.** The bar chart builds from `chartMonths`. As each of the five bars
  rises, the corresponding `<mark>` in the transcript pulses. Bars are `--loupe-person` blue,
  matching the app's chart artifact. December rises last and taller, in `--accent`.
- `0.6 → 0.85` — **the interviews.** The Okonkwo quote about the promised bonus enters, with its
  citation, beside Marcus's *"David releases it Wednesday"* line from the call.
- `0.85 → 1` — the four source chips settle into a row, and the closing line lands:

  > No single source establishes this. Each one is unremarkable alone. The model is what makes
  > them the same arrangement.

- [ ] **Step 2: Style it**

Dark. This is the emotional peak and should be the most composed frame on the page. The five marks
and the five bars must be visually linked — same accent, same rhythm.

- [ ] **Step 3: Verify**

Acceptance: the five marked amounts read `125 / 180 / 95 / 210 / 150` and correspond left-to-right
with the Mar/May/Jul/Oct/Nov bars; December is visibly the tallest bar and the argued-about figure;
all four source citations are legible; the `case.test.ts` convergence tests still pass.

- [ ] **Step 4: Commit**

```bash
git add landing/src/components/sections/Convergence.tsx \
        landing/src/components/sections/Convergence.module.css
git commit -m "Build the convergence beat"
```

---

### Task 12: AgentExchange — beat 8

**Files:**
- Create: `src/components/sections/AgentExchange.tsx`
- Create: `src/components/sections/AgentExchange.module.css`

- [ ] **Step 1: Build the component**

`PinnedSequence` with `steps={2}`, `label="Asking the agent"`. Two columns mirroring the app: a
conversation column and an artifact panel.

- `0 → 0.2` — the question types in: *"Compare what Marcus Chen and David Okonkwo each said about
  the Nexus Trading vendor relationship."*
- `0.2 → 0.4` — the agent's clarification appears with selectable options. One highlights as
  chosen. Caption: *"It asks. It does not guess."*
- `0.4 → 0.75` — the artifact panel fills row by row from `conflicts`: point, Chen quote + source,
  Okonkwo quote + source, the conflict. Sources in `--accent`.
- `0.75 → 1` — `agentScopeNote` enters as a pulled callout, and the trail chip renders
  `${agentTrail.steps} steps · ${agentTrail.seconds}s`.

Do not re-typeset the artifact from the screenshot — this is rebuilt so the table is legible at any
width, which the captured chat column is not.

- [ ] **Step 2: Verify**

Acceptance: all four conflicts render with both quotes and both citations; the scope note is
visually distinct; the table is readable at 390px viewport width without horizontal scroll.

- [ ] **Step 3: Commit**

```bash
git add landing/src/components/sections/AgentExchange.tsx \
        landing/src/components/sections/AgentExchange.module.css
git commit -m "Build the agent beat"
```

---

### Task 13: CommsCenter — rebuilt Cellebrite surface

Spec §2: no demo extraction exists and real ones are live federal matters, so this is rebuilt from
the real components rather than captured.

**Files:**
- Create: `src/components/sections/CommsCenter.tsx`
- Create: `src/components/sections/CommsCenter.module.css`
- Modify: `src/data/case.ts` — append a `commsThread` export

- [ ] **Step 1: Read the real components for structure**

Read `frontend_v2/src/features/cellebrite/components/comms/CommsThreadList.tsx` and
`CommsThreadView.tsx`. Mirror their layout: thread list left with participant and last-message
preview, thread view right with grouped message bubbles, direction-aware alignment, timestamps.

- [ ] **Step 2: Add the thread data**

Append to `src/data/case.ts` a `commsThread` export holding a fictional exchange consistent with
the case — Chen and Blackwood, December 2023, referencing the year-end payment. Written content
supplied by the product owner; do not invent phone-evidence texture without it.

- [ ] **Step 3: Build and style**

Static, not scroll-driven — one `ProductFrame`-styled surface inside the Lenses sequence.

- [ ] **Step 4: Verify**

Acceptance: layout is recognisably the app's Comms Center; the surface carries the
"Illustrative case data" caption.

- [ ] **Step 5: Commit**

```bash
git add landing/src/components/sections/CommsCenter.tsx \
        landing/src/components/sections/CommsCenter.module.css landing/src/data/case.ts
git commit -m "Rebuild the comms surface rather than shoot a live extraction"
```

---

## Phase 4 — Screenshot and static sections

### Task 14: Hero

**Files:**
- Modify: `src/components/Hero.tsx`
- Create: `src/components/sections/Hero.module.css`
- Modify: `src/components/HeroScene.tsx`

- [ ] **Step 1: Rebuild the hero**

Full-bleed dark. Headline `Query the whole case.` top-left, retained. Lede retained. Replace the
`hero-proof` line with the stat strip, imported from `src/data/claims.ts`:

> One matter: thirty thousand entities, ninety thousand relationships, every fact citing its page.

Right side, positioned to bleed off the right and bottom edges at true scale so interface density
is visible rather than a shrunk thumbnail:

```tsx
<ProductFrame
  slug="graph-detail"
  alt="The Loupe graph view with an organisation selected, its detail panel showing a summary in which every statement links to the source file and page it came from"
  priority
  bleed
/>
```

- [ ] **Step 2: Demote the 3D lens**

`HeroScene` moves out of the hero's main composition into a small ambient element behind the
headline at reduced opacity, or is dropped from the hero entirely and retained only as the nav
mark. Keep the existing off-screen pause and DPR cap.

- [ ] **Step 3: Verify**

Acceptance: at 1440×900 the graph screenshot's interface is legible — individual node labels and
the detail panel's source links readable; the stat figures match `verified` in `claims.ts`; hero
fits one viewport without scroll.

- [ ] **Step 4: Commit**

```bash
git add landing/src/components/Hero.tsx landing/src/components/HeroScene.tsx \
        landing/src/components/sections/Hero.module.css
git commit -m "Lead with the product instead of a floating lens"
```

---

### Task 15: ProblemScene, Lenses, WorkProduct

**Files:**
- Create: `src/components/sections/ProblemScene.tsx` + `.module.css`
- Create: `src/components/sections/Lenses.tsx` + `.module.css`
- Create: `src/components/sections/WorkProduct.tsx` + `.module.css`
- Delete: `src/components/ProductExplorer.tsx`

- [ ] **Step 1: ProblemScene**

One tight module, `--sec-pad-sm`, no card grid. Single statement at `h2.is-lead`:

> You receive the evidence. You didn't collect it and you can't. Five phones, hundreds of
> documents, formats built by the other side, and a court date. What wins is frequently what is
> *absent* — the message that puts someone somewhere else, the date that doesn't line up.

- [ ] **Step 2: Lenses**

A sequence of `ProductFrame` instances at `bleed`, each full-width with its own callouts. Not a tab
strip. Order and callouts:

| Slug | Callout |
|---|---|
| `graph-detail` | "Every sentence ends in the file and page it came from" |
| `audio-transcript` | "Speaker-attributed, timestamped, searchable in place" |
| `financial` | "Counterparties resolved to who they actually are" |
| `timeline` | "One chronology across every source in the matter" |
| `map` | "Location confidence and provenance shown honestly" |

Omit any slug whose capture was not producible per the Task 3 manifest. `CommsCenter` renders
inline in this sequence in place of a screenshot.

- [ ] **Step 3: WorkProduct**

Short — `--sec-pad-sm`. One `ProductFrame` of the built report plus three lines on export,
notebook and case-attached artifacts.

- [ ] **Step 4: Delete the superseded and orphaned components**

`ProductExplorer` is superseded by `Lenses`. `CaseModelSection` and `WorkProductSection` are
already unreferenced by `App.tsx` and are dead code.

```bash
git rm landing/src/components/ProductExplorer.tsx \
       landing/src/components/CaseModelSection.tsx \
       landing/src/components/WorkProductSection.tsx
```

Confirm nothing still imports them:

```bash
grep -rn "ProductExplorer\|CaseModelSection\|WorkProductSection" landing/src
```

Expected: no output.

- [ ] **Step 5: Verify**

Acceptance: no section in this range repeats the shape of its neighbour; every `ProductFrame`
carries a caption; no reference to a `/product/` slug that does not exist in `public/product/`.

- [ ] **Step 6: Commit**

```bash
git add landing/src/components/sections landing/src/components/ProductExplorer.tsx
git commit -m "Give the product surfaces real size and kill the tab strip"
```

---

### Task 16: Act III restyle

**Files:**
- Modify: `src/components/NarrativeSections.tsx`
- Create: `src/components/sections/Difference.module.css`
- Create: `src/components/sections/Capability.module.css`
- Create: `src/components/sections/Deployment.module.css`
- Create: `src/components/sections/Audience.module.css`

- [ ] **Step 1: Strip the superseded sections**

Delete `ProblemSection`, `CaseModelStory` and `LoupeWorkflowSection` from
`NarrativeSections.tsx` — Tasks 8–15 supersede all three. Retain `DifferenceSection`,
`CapabilitySection`, `ProofSection` and `AudienceSection`.

- [ ] **Step 2: Restyle the comparison table**

Retain content and the Task 1 Scale row. Convert to a colocated module. Give the Loupe column
visual weight — accent hairline, `--loupe-white` on `--obsidian`.

- [ ] **Step 3: Convert Capability to a datasheet**

Same six groups and their items. Restyle as a dense technical spec sheet: `--loupe-font-evidence`
throughout, tight leading, 1px `--rule` separators, no card padding, no shadows. This is the
"prove you do X" section and should read as a datasheet, not as marketing cards.

Add one item to **Phone and device evidence**: `Speaker-separated audio transcription with
timestamped, searchable transcripts` — currently claimed but not listed against the right group.

- [ ] **Step 4: Tighten Deployment and Audience**

Retain content. Reduce copy by roughly half per spec §6 — each currently states its point in both
the lede and the card body. Keep one.

- [ ] **Step 5: Verify**

```bash
npm test && npm run build
```

Expected: PASS and successful build. The claim audit must still pass — confirm the Scale row edit
from Task 1 survived the restyle.

- [ ] **Step 6: Commit**

```bash
git add landing/src/components
git commit -m "Make the argument act earn its place after the demonstration"
```

---

## Phase 5 — Assembly and polish

### Task 17: Page assembly

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/components/Navigation.tsx`

- [ ] **Step 1: Assemble the three acts**

`src/App.tsx`:

```tsx
import { useState } from "react"
import { ContactModal } from "./components/ContactModal"
import { FinalCta } from "./components/FinalCta"
import { Footer } from "./components/Footer"
import { Hero } from "./components/Hero"
import { Navigation } from "./components/Navigation"
import {
  AudienceSection,
  CapabilitySection,
  DifferenceSection,
  ProofSection,
} from "./components/NarrativeSections"
import { AgentExchange } from "./components/sections/AgentExchange"
import { Convergence } from "./components/sections/Convergence"
import { GraphReduce } from "./components/sections/GraphReduce"
import { IntakeStream } from "./components/sections/IntakeStream"
import { Lenses } from "./components/sections/Lenses"
import { ModelResolve } from "./components/sections/ModelResolve"
import { ProblemScene } from "./components/sections/ProblemScene"
import { WorkProduct } from "./components/sections/WorkProduct"

export function App() {
  const [contactOpen, setContactOpen] = useState(false)

  return (
    <div className="site-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Navigation onContact={() => setContactOpen(true)} />
      <main id="main-content">
        {/* Act I — setup */}
        <Hero onContact={() => setContactOpen(true)} />
        <ProblemScene />

        {/* Act II — demonstration */}
        <IntakeStream />
        <ModelResolve />
        <GraphReduce />
        <Lenses />
        <Convergence />
        <AgentExchange />
        <WorkProduct />

        {/* Act III — argument */}
        <DifferenceSection />
        <CapabilitySection />
        <ProofSection />
        <AudienceSection />
        <FinalCta onContact={() => setContactOpen(true)} />
      </main>
      <Footer onContact={() => setContactOpen(true)} />
      <ContactModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}
```

- [ ] **Step 2: Rewrite the nav**

Current links are `Platform / Deployment / Capability` — vague. Replace with anchors matching the
new structure: `How it works` → `#intake`, `The product` → `#lenses`, `Deployment` → `#trust`.
Add the corresponding `id` to each section element.

- [ ] **Step 3: Audit the section rhythm**

Walk the assembled page and assign each section an explicit `--sec-pad-*` by weight. No section
may inherit a default. Verify no gap exceeds 200px of empty ground — the current page has several
near 500px (spec §1).

- [ ] **Step 4: Verify**

Acceptance: no two adjacent sections share a module archetype; the page reads as three acts;
total height is materially below the current 10,579px despite carrying more content, because copy
halved and dead space is gone.

- [ ] **Step 5: Commit**

```bash
git add landing/src/App.tsx landing/src/components/Navigation.tsx
git commit -m "Assemble the page as three acts"
```

---

### Task 18: Accessibility, reduced motion and responsive

**Files:**
- Modify: all section components as needed
- Create: `src/App.test.tsx`

- [ ] **Step 1: Write the structural test**

`src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { App } from "./App"

describe("App", () => {
  it("renders one main landmark", () => {
    render(<App />)
    expect(screen.getAllByRole("main")).toHaveLength(1)
  })

  it("gives every pinned sequence an accessible name", () => {
    render(<App />)
    const regions = screen.getAllByRole("region")
    expect(regions.length).toBeGreaterThan(0)
    for (const region of regions) {
      expect(region).toHaveAccessibleName()
    }
  })

  it("has exactly one h1", () => {
    render(<App />)
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run it**

```bash
npm test -- App
```

Fix any failures in the section components rather than in the test.

- [ ] **Step 3: Verify reduced motion**

In Chrome DevTools → Rendering → Emulate `prefers-reduced-motion: reduce`, reload, and confirm:
every pinned sequence renders its completed state, no section is taller than one viewport plus its
content, and the page is fully readable with no scroll-dependent content hidden.

- [ ] **Step 4: Verify responsive**

Check 390px, 768px, 1440px and 2560px. Requirements: no horizontal scroll at any width; the agent
artifact table readable at 390px; pinned sequences collapse to static stacked layouts below 768px;
`ProductFrame` images do not exceed their container.

- [ ] **Step 5: Verify keyboard**

Tab from the top: skip link works, nav links reachable, the contact modal traps focus and returns
it on close, every focusable element has a visible focus ring.

- [ ] **Step 6: Commit**

```bash
git add landing/src
git commit -m "Make the choreography degrade to something readable"
```

---

### Task 19: Performance and final claim audit

**Files:**
- Modify: `src/App.tsx` (lazy boundaries)
- Modify: `src/data/claims.ts` if any retired phrase is discovered

- [ ] **Step 1: Lazy-load below-fold heavy sections**

Wrap `GraphReduce`, `Convergence` and `AgentExchange` in `React.lazy` with a `Suspense` fallback
of a fixed-height placeholder matching each section's `minHeight`, so lazy loading does not shift
layout.

- [ ] **Step 2: Build and measure**

```bash
cd landing && npm run build && npx --yes serve dist -l 5200
```

Run Lighthouse against `http://localhost:5200`. Targets: Performance ≥ 90, Accessibility ≥ 95, no
CLS from the pinned sections.

- [ ] **Step 3: Final claim audit**

```bash
npm test
```

All suites must pass — the retired-claim audit, the convergence lock, the graph-count sums, the
citation check, the hooks and the structural tests.

- [ ] **Step 4: Read the page against the spec**

Walk `docs/superpowers/specs/2026-08-04-landing-page-redesign-design.md` §3 and confirm every
number on the rendered page traces to `verified` in `claims.ts` or to a figure visible inside a
captioned screenshot. Any number that traces to neither is a defect.

- [ ] **Step 5: Commit**

```bash
git add landing
git commit -m "Lazy-load the heavy beats and re-audit every number on the page"
```

---

## Out of scope

- Any change to `frontend_v2`, `backend` or `evidence-engine`
- Workspace (witnesses, theories, findings, tasks, witness matrix)
- Contact form backend — the existing mailto flow in `ContactModal` is retained
- Renaming or rebranding
