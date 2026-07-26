#!/usr/bin/env python3
"""Content pass on the accelerator brief. Applies Neil's approved direction:
   C1 (grounding / case-wide querying), C2 (keep LLM table + add industry table),
   C4 (markets per research), plus C5-C12 by instinct. C3 explicitly DROPPED.
   Usage: content_pass.py <file>"""
import sys, re
p = sys.argv[1]
s = open(p).read()
if "And what makes it different from the investigation platforms" in s:
    print("ALREADY APPLIED — refusing to run again (would double-insert the industry table).")
    raise SystemExit(0)
applied, missed = [], []

def rep(a, b, label):
    global s
    if a in s:
        s = s.replace(a, b, 1); applied.append(label)
    else:
        missed.append(label)

# ---------- C1: headline + lede ----------
rep("<h1>Loupe turns raw case evidence into connected, <em>source-linked</em> intelligence.</h1>",
    "<h1>Loupe answers questions across the <em>whole case</em> at once, not one document at a time.</h1>",
    "C1 h1")

rep("and Loupe builds one connected model of the people, events, money and places inside it, where every single fact links back to the page, quote and file it came from.",
    "and Loupe resolves it into one connected model of the people, events, money and places inside it. "
    "Questions are answered by traversing that model, so a single question reaches every artifact in the "
    "case at once rather than a handful of documents at a time — and every fact it returns carries the page, "
    "quote and file it came from.",
    "C1 lede")

# ---------- C1: paste blocks ----------
rep("Loupe turns raw case evidence — documents, phone extractions, financial records, audio — into one connected, source-linked intelligence layer that investigators can explore, question and take to court.",
    "Loupe resolves every kind of case evidence — documents, phone extractions, financial records, audio — "
    "into one connected case model, so a single question reaches the whole case at once instead of one document "
    "at a time, and every answer carries the artifact it came from.",
    "C1 one-liner")

rep("where AI answers questions with citations and every fact links back to its source page.",
    "where a question is answered by traversing the whole case at once rather than by reading documents one at "
    "a time, and every fact returned carries its source page.",
    "C1 50w")

rep("an agent answers with citations and runs tools across the case",
    "an agent answers questions put to the entire case at once, with citations, and runs tools across it",
    "C1 100w")

# ---------- C6 + C7: promote unification + the licensing asymmetry ----------
rep("<h2>Modern casework is a data problem wearing a legal costume</h2>",
    "<h2>Modern casework is a data problem wearing a legal costume</h2>\n"
    "<p><strong>A call at 02:14, a transfer of $8,400 and a line in a subpoena return are the same kind of "
    "citable object in Loupe — resolved into one model, each traceable to the artifact it came from.</strong> "
    "No other platform can say that. The evidence categories split the problem: the eDiscovery tools model "
    "documents and flatten phone data into spreadsheets, while the forensic tools model devices and leave "
    "documents outside the model entirely.</p>\n"
    "<p>And the defence cannot buy the analytics the prosecution runs on. GrayKey is not sold to the private "
    "sector at all; Cellebrite Pathfinder is marketed to law enforcement, government and intelligence. Defence "
    "teams receive phone extractions through read-only share links issued by the prosecution — reviewing the "
    "evidence inside the prosecution's tool, with the prosecution's permissions. Levelling the evidentiary "
    "playing field is not a slogan here; it is a description of a licensing structure.</p>",
    "C6+C7 problem")

# ---------- C8: why now ----------
rep("And bare LLMs remain unusable in evidence contexts — no provenance, no audit, no confidentiality. The gap between those last two facts is exactly where Loupe sits: the trust layer that makes AI admissible in investigative work.",
    "And the evidence categories converged on cited document question-answering and stopped there — every major "
    "platform shipped it, and most now give it away. What none of them did was model the case. That is structural "
    "rather than an oversight: eDiscovery is a reductive discipline, built to cull a corpus down to a reviewable "
    "set, and investigation is a constructive one. If the job is to cull, a call log is noise to be dumped in a "
    "spreadsheet; if the job is to build a model, that same call log is connective tissue. Loupe is built for the "
    "second job.",
    "C8 why-now")
# ---------- C4: markets, sequenced per the research ----------
OLD_MKT = '''  <div class="cardgrid">
    <div class="card"><h4>Financial-crime &amp; fraud units</h4><p>The money view plus the graph: ledgers, counterparties, flow — connected to the people and communications around them.</p></div>
    <div class="card"><h4>Law enforcement &amp; prosecutors</h4><p>Phone extractions, timelines and maps in one place, with the provenance chain court work demands.</p></div>
    <div class="card"><h4>Law firms &amp; disputes teams</h4><p>Case-corpus comprehension at discovery scale, with citations that survive a partner's scrutiny.</p></div>
    <div class="card"><h4>Corporate investigations &amp; compliance</h4><p>Internal investigations on infrastructure the security team can approve — nothing leaves the tenant.</p></div>
  </div>'''
NEW_MKT = '''  <p class="big">First: <strong>defence-side private investigators and criminal-defence practices</strong> of roughly
  five to fifty people, running federal and serious state matters. The defining characteristic is not size or sector —
  it is that this buyer <em>receives</em> evidence rather than collecting it, receives it in formats built by the other
  side, and has no way to analyse it properly. That is also the segment the incumbents structurally cannot serve.</p>
  <div class="cardgrid">
    <div class="card"><h4>1 · Defence-side PI &amp; criminal defence</h4><p>The beachhead. Handed a phone extraction, a
    disclosure bundle, subpoena returns and bank records — and locked out of the analytics the other side runs on.
    Reached through the defence bar and through casework referral.</p></div>
    <div class="card"><h4>2 · Corporate investigations &amp; compliance</h4><p>The right second market: higher contract
    values, the same product, no phone-data dependency. Internal investigations on infrastructure the security team can
    approve — nothing leaves the tenant.</p></div>
    <div class="card"><h4>3 · Law firms &amp; disputes teams</h4><p>Case-corpus comprehension at discovery scale, with
    citations that survive a partner's scrutiny. Follows the corporate motion.</p></div>
    <div class="card"><h4>Later · Law enforcement, prosecutors &amp; financial-crime units</h4><p>Real fit, wrong first
    fight. This is the market every incumbent was built for, with the longest procurement and the heaviest certification
    burden. Entered from a position of strength, not from a standing start.</p></div>
  </div>
  <p>Pricing follows the work rather than the seat: <strong>per matter, in the $6,000–24,000 band</strong>, benchmarked
  against the cost of a junior investigator or overseas review staff — the comparison our lead prospect made unprompted.
  Per-gigabyte pricing, the industry default, charges by evidence volume and so pays the customer to keep evidence out
  of the platform. That is incoherent for a product whose value grows with how much of the case it holds.</p>'''
rep(OLD_MKT, NEW_MKT, "C4 markets")

# ---------- C2: keep the LLM table, reframe it, then add the real field ----------
_m = re.search(r'(<p[^>]*>The honest answer to.*?</p>)', s, re.S)
if _m:
    s = s[:_m.end()] + (
        '\n  <p>This comparison comes first because it is the one most people make, and it is a false '
        'competitor. A general-purpose model with files attached looks like it could do this job and cannot '
        '\u2014 not for reasons of model quality, but because there is no case model underneath it. The '
        'comparison that actually decides a purchase is the one after it.</p>'
    ) + s[_m.end():]
    applied.append("C2 framing")
else:
    missed.append("C2 framing")

NEW_TABLE = '''
  <h3>And what makes it different from the investigation platforms</h3>
  <p>The real field is Relativity, Everlaw, Harvey, Cellebrite and Nuix — mature products with persistent case files,
  citation discipline, audit logs and deployment options. On most of the rows above they score level with Loupe. These
  are the rows where they do not.</p>
  <div class="tablewrap">
  <table>
    <thead><tr><th></th><th>The evidence platforms</th><th>Loupe</th></tr></thead>
    <tbody>
      <tr><td class="rowlab">How a question is answered</td><td class="dim">Retrieve candidate passages, place them in a context window, ask a model to reason over them — the mechanism is identical across all of them</td><td class="win">Traverse a model of the case: a question resolves as a definite answer over everything ingested, not a sample of it</td></tr>
      <tr><td class="rowlab">Published ceilings</td><td class="dim">Relativity caps at 300k documents per index and 5k per fact-extraction job; CoCounsel ~200 documents per run with quality degrading; Reveal states its Ask is “designed for precision, not recall”; Harvey runs a prompt per document and aggregates</td><td class="win">One question, put to the whole case</td></tr>
      <tr><td class="rowlab">Phone evidence</td><td class="dim">Chats survive as documents; calls, contacts, locations and web history are flattened into spreadsheets; multi-device extractions unsupported outright; i2 removed native UFED import</td><td class="win">Devices, contact books, threads, calls and attachments as first-class citable objects</td></tr>
      <tr><td class="rowlab">Evidence types in one model</td><td class="dim">Documents <em>or</em> devices. The eDiscovery tools model documents; the forensic tools model devices; neither models both</td><td class="win">Phone extractions, documents and financial records resolved into a single graph</td></tr>
      <tr><td class="rowlab">Direction of the work</td><td class="dim">Reductive — cull a corpus down to a reviewable set. Success is fewer documents to read</td><td class="win">Constructive — every artifact ingested makes the model of the case richer</td></tr>
      <tr><td class="rowlab">Where AI is configured</td><td class="dim">At review time, on a corpus whose shape is already fixed</td><td class="win">At ingestion, directing what is extracted and structured as evidence enters</td></tr>
      <tr><td class="rowlab">What multimedia becomes</td><td class="dim">A searchable transcript — another document</td><td class="win">Entities resolved into the case model: a name spoken in a call is the same object as the name on a bank statement</td></tr>
    </tbody>
  </table>
  </div>'''
m = re.search(r'</table>\s*</div>(?=(?:(?!</table>).)*?<h2[^>]*>Built like evidence infrastructure)', s, re.S)
if m:
    s = s[:m.end()] + NEW_TABLE + s[m.end():]; applied.append("C2 industry table")
else:
    missed.append("C2 industry table")

open(p, "w").write(s)
print("APPLIED :", ", ".join(applied) if applied else "none")
print("MISSED  :", ", ".join(missed) if missed else "none")
