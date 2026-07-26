# Instructions: clean the Loupe platform description brief

**For: Claude running on the server, with file access to the platform description document.**
**From: the NDRC application work. You do not need any context from that conversation — everything you need is below.**

You are editing the Loupe platform description / capability brief (the "25 July brief").
It is the source document that all investor-facing material is generated from. It has
accumulated regressions across revisions. Fix them **at source** so they stop
reappearing.

Work through the sections below in order. Each gives you a **find**, a **replace**, and
a **why**. Match on meaning, not exact character-for-character strings — the wording may
have drifted slightly. If you cannot find a target, say so rather than guessing.

**Do not rewrite anything not listed here.** The brief is good. These are surgical fixes.

---

## 1. Remove all v1 / v2 framing — HIGHEST PRIORITY

This is the third revision to carry it. It is the single most damaging thing in the
document. It makes a shipped, case-proven platform read as an unfinished rewrite.

**There is one product. It is called Loupe. It is in production use on real casework.
Present tense. There is no "first generation" and no "second generation" anywhere.**

### 1a. The Status / current state block

**Find** the passage describing Loupe as "the second generation" of the platform, whose
first generation "ran real casework," with Loupe "rebuilding that proven capability" (or
any close variant).

**Replace the whole passage with:**

> Loupe is a working investigation platform in production use on real casework —
> multi-gigabyte phone extractions, tens of thousands of curated financial transactions,
> full document corpora — built inside a US private-investigations practice and used
> there to carry federal cases to completion. It runs single-tenant and hardened, behind
> a security-gated process for onboarding external customers' evidence.

### 1b. The financial capability section

**Find:** "10k+ hand-curated, categorised, audited transactions from real casework on the
platform's first generation."

**Replace with:** "10k+ hand-curated, categorised, audited transactions from real
casework."

Delete the trailing clause. The transactions are real and the casework is real; the
generation number adds nothing except doubt.

### 1c. Sweep the whole document

Search the entire brief for: `first generation`, `second generation`, `v1`, `v2`,
`previous version`, `earlier platform`, `rebuild`, `rebuilt`, `predecessor`, `legacy`.

Remove or rewrite every hit so the platform is described as one continuous product in
present tense. Report every change you make in this sweep so it can be checked.

---

## 2. Fix the internal contradiction about what the AI can do

The brief now contains an agent that runs tools and builds durable artifacts (section on
"An agent that does, not a chatbot that answers"). Several older passages still describe
the AI as **read-only** in a way that means "it can only answer questions." A reader who
meets both will conclude one of them is marketing.

**Important distinction — keep the true meaning, drop the misleading one:**

- ✅ **Keep** "read-only" where it describes *database access* — the agent runs safe
  read-only Cypher, it cannot mutate the case graph. That is true and it is a selling
  point.
- ❌ **Remove** "read-only" where it sits in a list of AI guardrails implying the AI
  produces nothing. That is now false.

### 2a. The ~100-word description block

**Find** the ~100-word summary paragraph, which currently ends its AI sentence with
something like: "operates under hard guardrails — read-only, case-scoped, cost-metered."

**Replace the whole ~100-word block with:**

> Investigation teams drown in digital evidence: thousands of documents, multi-gigabyte
> phone extractions, tens of thousands of transactions per case. Their tools are viewers;
> the connections live in their heads. Loupe ingests everything through a forensic-grade
> pipeline and builds one case knowledge graph where every extracted fact carries its
> verbatim quote, source location and confidence. Investigators explore it as a graph,
> timeline, map, table and ledger; an agent answers with citations and runs tools across
> the case — grouping transactions, generating visualisations, and assembling whole
> evidence collections from a plain instruction — under hard guardrails: case-scoped,
> cost-metered, and unable to assert anything that isn't grounded in a cited source.
> Deployed single-tenant, so evidence never leaves the customer's instance. It's the
> layer that makes AI usable — and defensible — in real casework.

### 2b. The differentiation table

**Find** the row comparing what the AI can do, which currently says something like "a
fixed tool set… read-only."

**Rewrite the Loupe side** so it reads as capability, not just constraint. It should say
the AI **cites every claim to the exact page and runs tools on the case model** — builds
Loupes, groupings and outputs from plain instruction — with access that is case-scoped
and cost-metered.

### 2c. Sweep

Search for every other occurrence of `read-only` in the document. For each, decide using
the rule in section 2 above. Report each occurrence and the decision you made.

---

## 3. Remove the autonomous AI engineering pipeline sentence

**Find:** "Development runs on an in-house autonomous AI engineering pipeline that takes
features from specification to reviewed pull request, letting a small team ship at
multi-team pace." (or close variant)

**Action: delete it.**

**Why:** it is an unresolved disclosure decision, not a fix. Presented to an investor
before CI exists in the repository, it reads as "AI writes our code and we don't test
it." It may come back later once the test and CI story is in place, but it should not
sit in the source document where it can be copy-pasted by accident. If you want to
preserve it, move it to a clearly-marked `<!-- HOLD: not for external use -->` comment
at the bottom of the document rather than leaving it inline.

---

## 4. Separate shipped capability from planned capability

This is the structural problem underneath everything above, and fixing it prevents
recurrence.

**The brief currently states planned and in-flight work in the same present tense as
shipped work.** A reader cannot tell them apart. In a defence/legal market that is the
difference between a credible pitch and a caught overclaim.

### 4a. Add a status marker convention

At the top of the capability sections, add:

```
Capability status: unmarked = shipped and used on real casework.
[BUILDING] = in flight, expected before external release.
[PLANNED] = designed, not built.
```

Then mark every capability line that is not currently shipped and used. **Do not guess.**
Where you cannot determine status from the codebase, mark it `[VERIFY]` and list it at
the end of your report for a human to resolve.

### 4b. Specific lines to check first

These are the known-suspect ones:

1. **The "hypothesis workbench" sub-section** — four claims: *assemble the scenario*
   (agent builds a Loupe from plain language), *hunt what breaks it* (disconfirmation),
   *find what isn't there* (gap enumeration), *hypotheses that stay open* (standing
   re-evaluation). **Do not delete these.** They are scheduled to be built. Mark each one
   accurately: shipped, `[BUILDING]`, or `[VERIFY]`.

2. **"Hard-gating CI on every pull request"** — check whether `.github/workflows` (or
   equivalent CI configuration) actually exists on the current integration branch. As of
   the last inspection it did not. If it still does not exist, mark `[BUILDING]`.

3. **The "Release quality & compliance" and "Operations, recovery & provisioning"
   sections** — these blend shipped behaviour with a release *plan*. Specifically check
   and mark: rehearsed recovery runbooks, Terraform provisioning, two-person deletion
   approval, and counsel review. Anything that describes a process that has not yet been
   run should not be in present tense.

4. **"WCAG 2.1 AA"** — is there an accessibility audit or automated check backing this,
   or is it an intention? Mark accordingly.

5. **"Verified against a 571k-node corpus"** — find what this number came from. If it is
   a design capacity target rather than a measured result on a real case, say so in the
   line. Design capacities and case results must not be stated in the same voice.

---

## 5. Distinguish design capacity from measured case results

Throughout the brief, some numbers are **what the system is built to handle** and others
are **what it has actually processed on a real case.** These are currently written
identically.

- **Design capacities** (state as such): 10k+ entities per case, 50k transactions in
  under 2 seconds, 35GB single phone report with 100k+ events.
- **Real casework figures** (state as fact): multi-gigabyte phone extractions, 10k+
  hand-curated audited transactions, full document corpora, federal cases carried to
  completion.

Where a number is a capacity, prefix with "built to handle" or "designed for." Where it
is a result, say "has processed" or "on real casework." Do not leave any number
ambiguous.

---

## 6. Final consistency pass

After making the above edits, read the whole document top to bottom and check:

1. **No sentence contradicts another sentence.** Specifically: what the AI can and cannot
   do; what is shipped and what is planned; how many products exist.
2. **Tense is consistent.** Shipped things in present tense, planned things clearly
   marked and never in bare present tense.
3. **The product is singular.** One platform, one name, no versions.
4. **Every superlative or first-in-market claim is defensible.** Flag anything of the
   form "the first tool that…" or "no other platform…" for human review rather than
   deleting it.

---

## Output

When done, produce a report with:

- **Changes made** — a list, each with the before text and the after text.
- **`[VERIFY]` list** — every capability line where you could not determine shipped
  status from the codebase, needing a human decision.
- **Contradictions found but not fixed** — anything where the correct resolution was not
  obvious enough to act on unilaterally.

Do not mark the job complete while any `[VERIFY]` item remains unresolved in the
document. Leaving the marker in is correct; silently removing it is not.
