# Capture manifest

**Captured:** 2026-08-05
**Source:** live stack — frontend `:5174`, backend `:8002`
**Case:** `Demo Case - Nexus Trading` — `c9cec5f5-5f2a-4624-a130-9a1548d1896d`
**Viewport:** 2560×1440, fixed across every shot
**Raw output:** `landing/public/product/raw/` — PNG, pending WebP conversion (plan Task 3, step 3)

Every shot exists in both `-light` and `-dark`. Theme is driven by the `owl-theme` localStorage key.

---

## Case state at capture

| Fact | Value |
|---|---|
| Graph, all data | **121 nodes · 212 edges · 12 types** |
| Graph, significant | **12 nodes · 24 edges · 6 types** |
| Timeline events | 52 |
| Financial transactions | 14 |
| Table entities | 121 |
| Map locations | 29 (28 high confidence, 1 medium, 14 flagged "needs review") |
| Evidence files | 13 — twelve PDFs plus `call_20231219_chen_blackwood.mp3` |
| Folders | Bank Records · Disclosure — tranche 1 · Interviews · Phone Calls (created, files remain in root) |
| Recording | 4:29, 133 turns, 3 speakers |

Entity types: Location 23 · Communication 22 · Transaction 20 · Organization 18 · Person 10 ·
LegalAction 7 · Cyberidentity 6 · Event 6 · Account 5 · Document 2 · Media 1 · Device 1.

**These supersede the 114/207/13-type figures in the spec** — the audio ingest added entities after
the spec was first written.

---

## Shots captured

| Slug | View | State |
|---|---|---|
| `graph-detail` | Graph, All data | Nexus Trading Ltd selected; details panel open on its sourced summary. **The strongest shot in the set** |
| `graph-structure` | Graph, All data | Forces 150 / -400 / 85, panned and zoomed 6×; labels separated, details panel collapsed |
| `graph-swarm` | Graph, All data | Forces 50 / -50 / 100; deliberately dense |
| `graph-significant` | Graph, Significant | Forces 200 / -600 / 75; 12 labelled nodes, six-type legend |
| `timeline` | Timeline | 52 events, dated groups, inline citations, amounts in the right margin |
| `financial` | Financial | Transactions tab with the Provenance column. **See defect 2** |
| `map` | Map | Zoomed 4× toward the European cluster |
| `evidence` | Evidence | Root listing with the MP3 selected; SHA-256 and AI summary visible |
| `audio-transcript` | Evidence → Open File | Transcript modal at 00:00; conversation map, 3 speakers, 133 turns |
| `agent-conflicts` | Agent | Contradiction thread; capture the **artifact panel**, not the chat column |
| `agent-chart` | Agent | Two-series payments chart — GlobalTech → Nexus against Nexus → Sapphire |
| `agent-clarify` | Agent | Key-players thread including the clarification exchange |
| `agent-report` | Agent | Report artifact — sections, executive assessment, inline citations, PDF/Word export |

### Reproducing the graph framing

Fit-to-view is unusable on this case: roughly thirty disconnected nodes sit far outside the main
cluster, so fitting shrinks the readable part to nothing. The working recipe:

1. Set forces, wait ~6s for the simulation to settle.
2. Fit to view.
3. Compute the centroid of non-background canvas pixels; drag that point to the canvas centre.
4. Click Zoom in *n* times (6 for structure, 5 for swarm, 3 for significant).

The Force Controls button index shifts with panel state — probe indices 9–17 for the one that
reveals "Link Distance" rather than hard-coding it.

---

## Not captured, and why

| Shot | Reason |
|---|---|
| **Cellebrite Comms Center** | No demo UFDR exists; real extractions are live federal matters. Rebuilt instead — plan Task 13 |
| **Reports page** | Empty, and the surface is a work in progress. Cut from the page entirely, as Workspace was |
| **Table** | `Amount`, `Date`, `File Name` and `Location` are `—` across all 121 rows. Too thin to show |
| **Transcript at the 00:35 turn** | The transcript list is virtualised and will not scroll to a search match. The 00:00 framing is kept — the opening exchange is better landing-page material, and the amounts turn is rendered by the rebuilt Convergence component from `case.ts` |

---

## Defects found during capture

**1. The agent reports failure after succeeding.** The report thread's chat response reads *"I could
not produce an answer from the available case data"* while that same run produced three artifacts,
including the full report. The final-message step fails after the tool work completes. This is the
one failure mode that would be visible in a live demo.

**2. Financial renders EUR amounts with a `$` sign.** Timeline shows €125,000, the chart axis is
labelled EUR, the report says €1,035,000 — Financial alone shows $125,000.00. Three views agree and
one does not. Blocks using `financial-*.png` on a page aimed at people who read financial records
professionally.

Neither is in scope for the landing work; both are logged for the product backlog.

---

## Findings that changed the page design

Beyond the four-source convergence already in spec §4.1, capture surfaced two more corroborations.

**The pass-through.** From the report artifact: GlobalTech paid six wires totalling €1,035,000 into
Nexus; six matching transfers totalling €1,000,000 went to Sapphire two to five days later —
96.6% — and the FCIB suspicious activity report independently characterised the same pattern as 97%
rapid pass-through with one income source and one outgoing destination.

**"Year-End Advisory Services".** The `graph-detail` summary lists the December invoice description
as *"Year-End Advisory Services"*, dated 20 December. On the call recorded **19 December**, Marcus
Chen says at 00:21: *"Year end advisory."* — and at 00:23, *"It goes in tomorrow."* The phrase
spoken on the phone is the invoice description filed the next day.

**The caveat.** The report states plainly that the materials *"do not prove that the entire €2.45
million purchase price derived solely from GlobalTech's €1.035 million"*, and carries a section
headed "Evidentiary caveats and open questions." An AI declaring the limit of its own answer is the
strongest trust asset in the product.
