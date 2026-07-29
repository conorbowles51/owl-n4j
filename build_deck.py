#!/usr/bin/env python3
"""
Build the Loupe NDRC pitch deck (.pptx) from the content in
13-ndrc-application-pack-2026-07-25.md.

Slide body text is taken from the block quotes in Part 2.
Speaker notes are condensed from the surrounding commentary.

16:9, dark theme, deliberately plain. This is a structural draft for a designer,
not a finished visual identity.
"""

import os

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# ---------------------------------------------------------------- palette
# Loupe Brand System v1.0 — tokens taken from loupe-brand/brand/loupe-brand.css.
# No one-off colours. Red is signal, action and investigative focus; it is never
# an entity. The evidence-semantic hues (person blue, financial amber, location
# teal ...) are reserved for entity meaning and must not be used as decoration.

INK        = RGBColor(0x0B, 0x0C, 0x0F)   # --loupe-obsidian, page ground
DEEP       = RGBColor(0x07, 0x08, 0x0A)   # --loupe-bg-deep, cover / divider ground
PAPER      = RGBColor(0xF7, 0xF7, 0xF8)   # --loupe-ink / evidence white
INK_SOFT   = RGBColor(0xBF, 0xC1, 0xC8)   # --loupe-ink-soft, secondary copy
MUTED      = RGBColor(0x9A, 0x9D, 0xA5)   # --loupe-muted, labels
ACCENT     = RGBColor(0xE3, 0x3B, 0x4C)   # --loupe-signal, accents on dark ground
ACCENT_SOLID = RGBColor(0xB4, 0x16, 0x24) # --loupe-red, filled marks
ACCENT_DIM = RGBColor(0x3B, 0x3D, 0x44)   # --loupe-line-strong, rules
PANEL      = RGBColor(0x11, 0x12, 0x16)   # --loupe-surface, table / panel fill

# Space Grotesk display, IBM Plex Sans body, IBM Plex Mono for labels and figures.
# PowerPoint substitutes if a font is absent, so export the PDF on a machine with
# all three installed.
FONT_H = "Space Grotesk"
FONT_B = "IBM Plex Sans"
FONT_M = "IBM Plex Mono"

LOGO_KNOCKOUT = "loupe-brand/brand/logo/loupe-lockup-knockout.png"

W = Inches(13.333)
H = Inches(7.5)

MARGIN_L = Inches(0.85)
BODY_W   = W - Inches(1.7)


# ---------------------------------------------------------------- helpers

def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def bg(slide, colour=INK):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = colour


def textbox(slide, left, top, width, height):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    return tf


def para(tf, text, size=18, colour=PAPER, bold=False, first=False,
         space_before=10, space_after=0, italic=False, font=FONT_B,
         align=PP_ALIGN.LEFT, line=1.28, prefix=None, prefix_colour=ACCENT):
    """Add a paragraph. Supports **bold** inline runs and a coloured prefix."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    p.line_spacing = line

    if prefix:
        # hanging indent so wrapped lines align under the text, not the dash
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(int(Inches(0.30))))
        pPr.set("indent", str(-int(Inches(0.30))))
        r = p.add_run()
        r.text = prefix
        f = r.font
        f.size = Pt(size)
        f.color.rgb = prefix_colour
        f.bold = True
        f.name = font

    for chunk, is_bold in split_bold(text):
        r = p.add_run()
        r.text = chunk
        f = r.font
        f.size = Pt(size)
        f.color.rgb = colour
        f.bold = bold or is_bold
        f.italic = italic
        f.name = font
    return p


def split_bold(text):
    """Split '**x**' markers into (chunk, is_bold) pairs."""
    out, buf, i = [], "", 0
    while i < len(text):
        if text.startswith("**", i):
            j = text.find("**", i + 2)
            if j == -1:
                buf += text[i:]
                break
            if buf:
                out.append((buf, False))
                buf = ""
            out.append((text[i + 2:j], True))
            i = j + 2
        else:
            buf += text[i]
            i += 1
    if buf:
        out.append((buf, False))
    return out or [("", False)]


def rule(slide, top, width=Inches(1.6), colour=ACCENT, thick=Pt(2.5)):
    from pptx.enum.shapes import MSO_SHAPE
    ln = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN_L, top, width, thick)
    ln.fill.solid()
    ln.fill.fore_color.rgb = colour
    ln.line.fill.background()
    ln.shadow.inherit = False
    return ln


def kicker(slide, text, top=Inches(0.55)):
    tf = textbox(slide, MARGIN_L, top, BODY_W, Inches(0.3))
    p = para(tf, text.upper(), size=11, colour=ACCENT, bold=True, first=True,
             space_before=0)
    # Brand kit: mono is metadata only — eyebrows, labels, numbers, statuses.
    p.font.name = FONT_M
    for r in p.runs:
        r.font.size = Pt(11)
        r.font.name = FONT_M
    return tf


def heading(slide, text, top=Inches(0.95), size=34):
    tf = textbox(slide, MARGIN_L, top, BODY_W, Inches(1.0))
    para(tf, text, size=size, colour=PAPER, bold=True, first=True,
         space_before=0, font=FONT_H, line=1.1)
    return tf


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text.strip()


def bullets(tf, items, size=17, colour=PAPER, gap=9, first_flag=None):
    """items: list of strings; leading '- ' renders a dash bullet."""
    firstdone = first_flag
    for it in items:
        indent = it.startswith("- ")
        body = it[2:] if indent else it
        para(tf, body, size=size, colour=colour, first=(not firstdone),
             space_before=gap, prefix=("—   " if indent else None))
        firstdone = True
    return firstdone


# ---------------------------------------------------------------- slides

def slide1(prs):
    s = blank(prs); bg(s, colour=DEEP)          # cover sits on the deep ground
    # Supplied artwork, knockout colourway for a dark ground. Never a recoloured
    # or retyped wordmark; clear space is baked into the file.
    if os.path.exists(LOGO_KNOCKOUT):
        s.shapes.add_picture(LOGO_KNOCKOUT, MARGIN_L, Inches(2.35),
                             width=Inches(4.3))
    tf = textbox(s, MARGIN_L, Inches(3.62), BODY_W, Inches(2.6))
    para(tf, "Find the signal in everything.", size=27, colour=ACCENT,
         space_before=0, first=True)
    para(tf, "An investigation platform for fraud and criminal casework.",
         size=19, colour=MUTED, space_before=22)
    para(tf, "Dublin, Ireland.", size=19, colour=MUTED, space_before=4)
    rule(s, Inches(6.25))
    notes(s, "One line only. Do not open with the product.")
    return s


def slide2(prs):
    s = blank(prs); bg(s)
    kicker(s, "The problem")
    heading(s, "Modern casework is a data problem\nwearing a legal costume.")
    rule(s, Inches(2.28), width=Inches(1.1))

    tf = textbox(s, MARGIN_L, Inches(2.6), Inches(5.75), Inches(4.4))
    para(tf, "A single serious-fraud or criminal case now arrives as:",
         size=16, colour=MUTED, first=True, space_before=0)
    bullets(tf, [
        "- thousands of documents",
        "- multi-gigabyte phone extractions, hundreds of thousands of events",
        "- bank records spanning tens of thousands of transactions",
        "- hours of recorded audio",
    ], size=16, first_flag=True, gap=7)
    para(tf, "The tools investigators have are **viewers.** One phone at a "
             "time. One PDF at a time. One spreadsheet at a time.",
         size=16, space_before=18)

    tf2 = textbox(s, Inches(7.2), Inches(2.6), Inches(5.3), Inches(4.4))
    para(tf2, "The connections — the same person in a witness statement, a "
              "WhatsApp thread and a beneficiary field; the meeting two "
              "streets from the cash withdrawal — live in investigators' "
              "heads and on whiteboards.",
         size=15, colour=MUTED, first=True, space_before=0)
    para(tf2, "They don't scale, they don't survive staff turnover, and they "
              "can't be handed to a court.",
         size=17, colour=ACCENT, bold=True, space_before=13)
    para(tf2, "We didn't start with a product idea. We started with a case we "
              "couldn't work.",
         size=15, colour=PAPER, bold=True, space_before=14)
    para(tf2, "We tried to buy this. Building it was the second choice, not "
              "the first.",
         size=14, colour=MUTED, italic=True, space_before=6)

    notes(s, """ORIGIN STORY — this is your strongest beat.

"We tried to buy it, it failed on a live case, so we built it" is behavioural
evidence of a market gap. It outranks any number of stated-preference
interviews, and investors know it.

Between us we have seen this problem from both sides: seven years building
investigative-intelligence software for enterprise buyers, and a decade running
federal casework as an investigator using it. When our CPO needed a platform for
live federal casework we went looking for one, evaluated an existing
investigative intelligence platform against a real case, and it could not work
the case the way a real investigation needs.

DELIBERATELY NOT SAID: anything about what you personally built for a former
employer's customers, or any suggestion that Loupe derives from it. Your CV
stands on its own on slide 7.

JUDGEMENT CALLS
1. Name Octostar or not. Naming is more credible; vagueness gets discounted.
   Only name it if ready for "what specifically failed?" — have that answer
   written down before you present.
2. NEVER let Siren be the platform that failed. That was a different platform.
   Siren is Irish, EI-backed, Dublin is small. When Siren comes up it is a
   credential and a compliment: very good at what it is built for — enterprise
   LE and intelligence buyers who arrive with budget for configuration and
   support. You are not competing with it and not criticising it. You are
   serving a tier its model was never aimed at.""")
    return s


def slide3(prs):
    s = blank(prs); bg(s)
    kicker(s, "Why now")
    heading(s, "Three curves crossed.")
    rule(s, Inches(1.85), width=Inches(1.1))

    tf = textbox(s, MARGIN_L, Inches(2.35), Inches(6.4), Inches(3.6))
    items = [
        ("01", "Digital evidence volume exploded.",
         "A phone extraction now appears in nearly every case."),
        ("02", "LLMs became good enough",
         "to read evidence at scale."),
        ("03", "Bare LLMs remain unusable in evidence work",
         "— no provenance, no audit, no confidentiality."),
    ]
    firstdone = False
    for num, bold_part, rest in items:
        p = para(tf, num, size=13, colour=ACCENT, bold=True,
                 first=(not firstdone), space_before=16)
        firstdone = True
        para(tf, f"**{bold_part}** {rest}", size=18, space_before=2)

    tf2 = textbox(s, Inches(7.75), Inches(2.35), Inches(4.75), Inches(3.8))
    para(tf2, "The gap between (2) and (3) is exactly where Loupe sits:",
         size=17, colour=MUTED, first=True, space_before=0)
    para(tf2, "the trust layer that makes AI admissible in investigative work.",
         size=23, colour=ACCENT, bold=True, space_before=10)
    para(tf2, "Only ~25% of anti-fraud programmes use AI/ML today — and only "
              "**~6% of fraud examiners are confident explaining how their AI "
              "reaches its conclusions.**",
         size=16, colour=PAPER, space_before=30)
    para(tf2, "ACFE 2026 anti-fraud technology benchmarking",
         size=12, colour=MUTED, italic=True, space_before=8)

    notes(s, """The 6% stat is the strongest number in your material. The entire
product is an answer to it.

Say it, pause, then move to slide 4 and show the answer.""")
    return s


def slide4(prs):
    s = blank(prs); bg(s)
    kicker(s, "Product")
    heading(s, "Evidence in. One connected model out.", size=32)
    rule(s, Inches(1.85), width=Inches(1.1))

    # two screenshot placeholders
    from pptx.enum.shapes import MSO_SHAPE
    # Drop a real screenshot in at either path and it is used automatically;
    # otherwise the labelled placeholder is drawn. Target 5.4 x 2.85in at 16:9-ish
    # — 1620 x 855 px at 300dpi, or any image of that ratio.
    for i, (label, sub, shot) in enumerate([
        ("SCREENSHOT — A LOUPE",
         "Five highlighted passages from three documents,\nbound into one evidenced narrative timeline.",
         "deck-assets/slide4-loupe.png"),
        ("SCREENSHOT — CITED AI ANSWER, MID-CLICK",
         "Opening the source document\nat the cited page.",
         "deck-assets/slide4-citation.png"),
    ]):
        left = MARGIN_L + i * Inches(6.0)
        if os.path.exists(shot):
            pic = s.shapes.add_picture(shot, left, Inches(2.35),
                                       width=Inches(5.4), height=Inches(2.85))
            pic.line.color.rgb = ACCENT_DIM
            pic.line.width = Pt(1)
            continue
        box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, Inches(2.35),
                                 Inches(5.4), Inches(2.85))
        box.fill.solid()
        box.fill.fore_color.rgb = PANEL
        box.line.color.rgb = ACCENT_DIM
        box.line.width = Pt(1)
        box.shadow.inherit = False
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para(tf, label, size=13, colour=ACCENT, bold=True, first=True,
             space_before=0, align=PP_ALIGN.CENTER)
        para(tf, sub, size=14, colour=MUTED, space_before=10,
             align=PP_ALIGN.CENTER)

    tf = textbox(s, MARGIN_L, Inches(5.5), BODY_W, Inches(1.5))
    para(tf, "Every fact carries the verbatim quote, source location and "
             "confidence it rests on.",
         size=18, colour=PAPER, first=True, space_before=0)
    para(tf, "Investigators highlight what matters and bind it into **Loupes** "
             "— evidenced collections that carry the narrative, not just the "
             "extraction. The product is named after them.",
         size=15, colour=MUTED, space_before=10)
    para(tf, "Ingest  →  Ground  →  Connect  →  Explore  →  Prove",
         size=17, colour=ACCENT, bold=True, space_before=14)

    notes(s, """Two screenshots only. Resist the feature list.

The right-hand screenshot is the whole pitch. An investor who understands that
one click understands the company. Rehearse it as a live demo if you get a
meeting. Capture it with the RESULT GRAPH VISIBLE beside the cited text — that
shows the answer being grounded and structured in one frame, and it keeps the
graph in the deck where it belongs: as a result, not a landing page.

DO NOT LEAD WITH THE CASE GRAPH. A hairball is the most clichéd image in this
category — Palantir, i2, Siren, Linkurious all lead with it. It puts you in the
comparison slides 5 and 6 spend their time declining, and nobody parses a dense
graph at slide scale anyway. Same reason the product's default view is moving off
it: a case that opens on ten thousand nodes is useless to a working investigator.

NAME THE LOUPE. A Loupe is the product's core curation object — a bonded
collection of documents, highlighted passages, entities and events, with its own
identity and description, bound together to explain an event, a sequence or a
thing. It is why the company is called what it is, and it is the thing a
competitor cannot copy by improving their extraction. Pre-empts "isn't this just
an extraction pipeline?" before slide 5 has to argue it.

A Loupe is also the better picture: a timeline reads in three seconds, it shows
evidence a person bound deliberately rather than connections a machine inferred,
and no competitor's deck has this image.

Keep the graph for the demo and for the answer when a technical partner asks what
is underneath. And if you get to demo anything beyond the citation click, demo the
Loupe being built: highlight five sentences across three documents, bind them, and
you have a fully evidenced narrative viewable as a timeline or a graph.

IN YOUR POCKET: "We moved the default view off the graph because opening a case on
ten thousand nodes is what every tool in this category does, and it's useless to a
working investigator." Small, concrete evidence for slide 6's customer-led claim.""")
    return s


def slide5(prs):
    s = blank(prs); bg(s)
    kicker(s, "Differentiation")
    heading(s, "Why this isn't ChatGPT with files.", size=32)

    rows = [
        ("Where the case lives", "A context window, forgotten after",
         "A persistent case knowledge graph — outlives every conversation"),
        ("Scale", "Hundreds of pages at best",
         "Entire corpora: thousands of documents, multi-gigabyte phone reports"),
        ("What the AI does", "Answers in prose, one conversation at a time",
         "Cites every claim to the page — and runs tools: builds Loupes, groupings and outputs from plain instruction"),
        ("Confidentiality", "Multi-tenant cloud",
         "Single-tenant: evidence never leaves the customer's instance"),
        ("Human judgment", "Lives outside the tool — lost between sessions",
         "Highlights, significance and Loupes — bonded collections of evidence — are durable objects in the case model"),
        ("Model dependence", "The model is the product",
         "Models are interchangeable components. The moat is the evidence layer."),
    ]

    tbl_shape = s.shapes.add_table(len(rows) + 1, 3, MARGIN_L, Inches(1.85),
                                   BODY_W, Inches(4.05))
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(2.6)
    tbl.columns[1].width = Inches(4.3)
    tbl.columns[2].width = Inches(4.73)

    hdr = ["", "A straight LLM", "Loupe"]
    for c, text in enumerate(hdr):
        cell = tbl.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = INK
        cell.margin_left = Inches(0.12)
        cell.margin_top = Inches(0.05)
        cell.margin_bottom = Inches(0.05)
        tf = cell.text_frame
        tf.word_wrap = True
        para(tf, text, size=13, colour=(ACCENT if c == 2 else MUTED),
             bold=True, first=True, space_before=0)

    for r, (label, llm, loupe) in enumerate(rows, start=1):
        for c, (text, colour, bold) in enumerate([
            (label, PAPER, True),
            (llm, MUTED, False),
            (loupe, PAPER, False),
        ]):
            cell = tbl.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = PANEL if r % 2 else INK
            cell.margin_left = Inches(0.12)
            cell.margin_top = Inches(0.045)
            cell.margin_bottom = Inches(0.045)
            tf = cell.text_frame
            tf.word_wrap = True
            para(tf, text, size=12, colour=colour, bold=bold, first=True,
                 space_before=0, line=1.15)

    tf = textbox(s, MARGIN_L, Inches(6.15), BODY_W, Inches(1.0))
    para(tf, "A straight LLM gives you a well-written opinion about the "
             "fraction of the evidence that fits in its context window. Loupe "
             "gives you a complete, permanent, cross-referenced model of all of "
             "it — where **every claim carries its receipt.**",
         size=16, colour=PAPER, first=True, space_before=0)

    notes(s, """The HUMAN JUDGMENT row is the one that answers the question a
technical investor is actually holding: what stops Microsoft GraphRAG
commoditising this in eighteen months? Extraction pipelines will commoditise.
A durable, evidenced record of what an investigator decided mattered, and why,
does not — it accrues per customer, per case, and is worthless to a competitor.

THE OBJECTION YOU WILL ACTUALLY GET is not from investors, it's from buyers:
"can't I just do this with a $20 Claude subscription?" You have heard it
directly. Rehearsed answer:

  A $20 subscription reads what fits in one conversation and forgets it. It
  cannot hold a 35GB phone extraction, it has no persistent case model, it
  gives you prose instead of citations, and it puts privileged evidence on a
  multi-tenant service. The reason a case costs real money to process is the
  same reason the answer is trustworthy: we read EVERYTHING, not a sample.

That last line converts your cost structure from a weakness into proof of the
claim. Use it.

THE AGENT — the "What the AI does" row. Loupe's AI does not just answer; it runs
tools against the case model: groups transactions, generates visualisations, drafts
outputs, and ASSEMBLES LOUPES FROM A PLAIN-ENGLISH INSTRUCTION. That matters because
your buyer is making a LABOUR-SUBSTITUTION purchase — the ex-FBI prospect benchmarked
price against the cost of a junior investigator. A Q&A box does not substitute for a
junior. Something that produces the work does.

THE STRONGEST VERSION IS NOT "IT RUNS TOOLS" — it's that the unit of work stops being
a query and becomes a HYPOTHESIS. The investigator doesn't arrive at a search box with
a question; they arrive at a blank page and start building the scenarios they need to
test — and the agent assembles the evidence for each one, or shows them it isn't there.
That also closes the loop with slide 4: the Loupe is the namesake object AND the thing
the agent produces, so the moat argument and the agent argument become one argument.

  IN YOUR POCKET: "An investigator doesn't have questions, they have theories. Loupe
  is the first tool where the unit of work is a hypothesis rather than a query — you
  describe the scenario you want to test, and the agent builds the Loupe that proves
  or breaks it."

  Do NOT use "show me all companies" as the example. That's a saved view, not a
  hypothesis, and it makes the capability sound like faceted search.

Two rules when you talk about it:

  1. NAME TWO OR THREE CONCRETE OUTPUTS, never "it can do anything." Unbounded
     capability reads as unfocused and gets discounted to zero.
  2. PITCH BOUNDED AGENCY, NOT AUTONOMY. Your market is criminal defence. The
     instant you say "agent that does the work," a domain-aware listener asks what
     happens when it's wrong and who signs their name to it. Answer first:

       The agent runs tools across the case, but it cannot invent a fact.
       Everything it produces is built from grounded claims that carry their
       source, and nothing leaves the system without a human verifying it.

  And if asked whether the agent is just the model, and therefore commoditising:
  THE TOOLS ARE THE MOAT, NOT THE AGENT. A generic agent over a folder of PDFs
  produces confident garbage. The same agent over a grounded claims ledger and a
  set of Loupes produces work you can check. What it can reach is the product.

THE LINE TO USE: "Question-answering AI tells you about your evidence. An agent with
tools produces the work product." Eleven words, and it converts the agent from a
feature into a category distinction.

SAFE GROUND — the toolbox, all of it plainly built: case overview, graph entity
search, schema inspection, entity details and neighbourhoods, pathfinding, full-text
document search, timeline events, financial records, map locations, and safe
read-only Cypher for grouping and aggregation. Specific, checkable, and enough to win
on its own. Two behaviours worth saying out loud in a defence market: the agent ASKS
FOR CLARIFICATION rather than guessing, and IT PROPOSES WHILE THE INVESTIGATOR
DISPOSES — merges and case changes stay under human control. Those describe a
mechanism, not an intention, which is what the courtroom question is really asking for.

THE HYPOTHESIS WORKBENCH — landing before submission. Assembling a Loupe from a
scenario, hunting what breaks the theory, enumerating what's missing, standing
hypotheses that re-evaluate. These are the most quotable claims you have, which makes
them the ones you get asked to demo. One rule: don't say it until it has demoed clean
once. Anything not landed on submission day becomes the roadmap answer — the toolbox
above carries the pitch without it. Blocker 5g.""")
    return s


def slide6(prs):
    s = blank(prs); bg(s)
    kicker(s, "Market and lead customer")
    heading(s, "Every feature was requested by a working\ninvestigator on a live case.",
            size=29)
    rule(s, Inches(2.05), width=Inches(1.1))

    tf = textbox(s, MARGIN_L, Inches(2.35), Inches(6.0), Inches(4.15))
    para(tf, "Our CPO is our design partner. Development has been customer-led "
             "from the first commit — not a roadmap we invented and then "
             "validated, but a backlog generated by real federal casework. "
             "Cases have been worked to completion in the platform, and "
             "**three attorneys on those cases have been given access to it.**",
         size=13, first=True, space_before=0)
    para(tf, "Why this tier is empty — and stays empty.",
         size=15, colour=ACCENT, bold=True, space_before=14)
    para(tf, "Enterprise investigative-intelligence platforms are sold with "
             "configuration and support attached — the right model for agencies "
             "and large institutions, who arrive with budget, procurement and "
             "implementation resource.",
         size=12, colour=MUTED, space_before=7)
    para(tf, "The tier below has the same casework complexity and the same "
             "evidence volumes — and none of that budget. **Loupe is built for "
             "it directly: usable out of the box, by a practice with no "
             "implementation resource at all.**",
         size=12, space_before=7)

    tf2 = textbox(s, Inches(7.4), Inches(2.35), Inches(5.1), Inches(4.15))
    para(tf2, "Beachhead", size=12, colour=ACCENT, bold=True, first=True,
         space_before=0)
    para(tf2, "Boutique forensic and criminal-defence practices — 10–50 people, "
              "Big-Four-class casework without Big-Four tooling budgets.",
         size=12, space_before=3)
    para(tf2, "Expansion", size=12, colour=ACCENT, bold=True, space_before=11)
    para(tf2, "Financial-crime & fraud units · law enforcement & prosecutors · "
              "law firms & disputes teams · corporate investigations & "
              "compliance.",
         size=12, colour=MUTED, space_before=3)
    para(tf2, "Channel", size=12, colour=ACCENT, bold=True, space_before=11)
    para(tf2, "This buyer is organised and reachable. ACFE has ~95k members and "
              "~60k CFEs worldwide, with chapters, conferences and directories — "
              "including an Ireland chapter since 2016. The defence bar is the "
              "same shape: a competitor reached national presence through a "
              "national association and one state bar.",
         size=12, colour=MUTED, space_before=3)
    para(tf2, "Why we know the gap is real", size=12, colour=ACCENT, bold=True,
         space_before=11)
    para(tf2, "**We tried a number of platforms on live federal casework before "
              "we built anything. None of them could work the case.**",
         size=12, space_before=3)

    tf3 = textbox(s, MARGIN_L, Inches(6.75), BODY_W, Inches(0.6))
    para(tf3, "We did not set out to build a platform. We went looking for one, "
              "tried several, and none could work the case.",
         size=16, colour=ACCENT, bold=True, first=True, space_before=0)

    notes(s, """Market sizing is desk research, not primary — label it as such.
Global forensic accounting ~$18–20B, US ~$10.5B, highly fragmented.

A SECOND USE CASE surfaced in discovery and may be the better wedge:
PRE-ENGAGEMENT TRIAGE. A PI-firm CEO (ex-FBI, Tampa Bay) described her sharpest
pain as upstream of casework — free 15-minute consultations, large document sets
from prospects, deciding whether to take the matter without burning senior
hours. Also: 15 audio recordings needing a summary.

Why it matters: it sits on prospect intake material, NOT privileged evidence —
so it can be sold BEFORE the security gate closes. Obvious ROI denominator
(senior hours replaced). Natural front door into the same firm's casework.

It also reframes the buyer. She was not buying a tool for herself — she was
asking whether it makes her JUNIOR investigators effective, benchmarked against
the cost of a junior investigator or overseas staff. That is a
labour-substitution sale, not a software-features sale.

WHAT REMAINS OPEN: what does a 10–50 person practice actually pay, and through
what mechanism — per-matter passed through to the client, or per-seat licence?
The ex-FBI prospect declined to name a price before using the product ("I would
have to use it before I could answer that appropriately"). She is aware of the
~$25k/licence reference point and open to a mutual MSA at low cost, low risk.
Other anchors: Valid8 ~$42k/yr, CaseWare IDEA.

The pricing question is closed by running a paid pilot, not by booking more
calls — which is exactly what slide 9 asks NDRC to fund.""")
    return s


def slide6b(prs):
    """Growth path — four stages, each with the customers and matters it needs."""
    s = blank(prs); bg(s)
    kicker(s, "Growth path")
    heading(s, "Ten million in ARR is 104 firms\nand under 2% of one market.", size=29)
    rule(s, Inches(2.05), width=Inches(1.1))

    tf = textbox(s, MARGIN_L, Inches(2.3), BODY_W, Inches(0.7))
    para(tf, "Priced at a blended $12,000 per matter. A boutique running eight "
             "evidence-heavy matters a year is worth $96,000 annually; an active "
             "practice at twenty is worth $240,000. These figures use the "
             "conservative rate throughout.",
         size=12, colour=MUTED, first=True, space_before=0)

    stages = [
        ("Stage 1 · proof", "Owl & Ireland", "$0.5M", "5 customers", "42 matters / yr",
         "References and a validated price. Not a revenue stage."),
        ("Stage 2 · the engine", "United States", "$5M", "52 customers", "417 matters / yr",
         "0.3–0.9% of 48,000–125,000 evidence-heavy matters a year."),
        ("Stage 3 · second geography", "+ United Kingdom", "$10M", "104 customers", "833 matters / yr",
         "80,200 open Crown Court cases, rising. Same buyer, same channel."),
        ("Stage 4 · expansion", "+ Europe", "$25M", "260 customers", "2,083 matters / yr",
         "$2.41B forensics, $6.81B legal tech. Partner-led per jurisdiction."),
    ]

    col_w = Inches(2.95)
    gap   = Inches(0.19)
    top   = Inches(3.12)
    for i, (phase, name, arr, cust, matters, note) in enumerate(stages):
        left = MARGIN_L + (col_w + gap) * i
        box = s.shapes.add_shape(1, left, top, col_w, Inches(3.34))   # rectangle
        box.fill.solid(); box.fill.fore_color.rgb = PANEL
        box.line.color.rgb = ACCENT_DIM if i == 0 else ACCENT_SOLID
        box.line.width = Pt(1.25)
        box.shadow.inherit = False
        box.text_frame.text = ""

        t = textbox(s, left + Inches(0.16), top + Inches(0.16),
                    col_w - Inches(0.32), Inches(3.0))
        pph = para(t, phase.upper(), size=9, colour=ACCENT, bold=True,
                   first=True, space_before=0)
        for r in pph.runs:
            r.font.name = FONT_M
        para(t, name, size=15, colour=PAPER, bold=True, space_before=8, font=FONT_H)
        para(t, arr + "  ARR", size=25, colour=PAPER, bold=True, space_before=8,
             font=FONT_H)
        pc = para(t, cust + "\n" + matters, size=12, colour=ACCENT, space_before=8)
        for r in pc.runs:
            r.font.name = FONT_M
        para(t, note, size=11, colour=MUTED, space_before=10)

    notes(s, "The point is the middle two rows, not the ARR. 104 customers running "
             "833 matters is under two per cent of the US evidence-heavy pool alone, "
             "before the UK or Europe contribute anything. Against one to five thousand "
             "target practices, none of these stages asks for market dominance — they "
             "ask for a channel that works and a price that holds. Each stage is gated "
             "on one thing: stage 1 a validated price, stage 2 the bar channel "
             "converting, stage 3 the model rebuilt on UK rates, stage 4 partners.")
    return s


def slide7(prs):
    s = blank(prs); bg(s)
    kicker(s, "Team")
    heading(s, "We didn't research this market.\nWe worked in it — from both sides.",
            size=30)
    rule(s, Inches(2.15), width=Inches(1.1))

    people = [
        ("Neil Byrne", "CEO",
         "Seven years at Siren, the Irish investigative-intelligence platform — "
         "the same category, selling to law enforcement, intelligence and "
         "financial-crime teams. **Solutions engineer: managed customer accounts "
         "and built the customisations each client needed to make the platform "
         "fit their process.** Spoke with hundreds of analysts across conference "
         "talks and deployments. Now a sales solutions engineer at Udemy across "
         "large-enterprise and strategic accounts — the same discipline at "
         "enterprise scale. 10+ years in data engineering and AI systems.",
         "Full-time on close."),
        ("Conor Bowles", "CTO",
         "**Architect of the case model.** The approach the platform rests on is "
         "his: extract entities and events from evidence with an LLM at "
         "ingestion, resolve them into a graph, and query that concrete "
         "structure afterwards — so an answer is a traversal over modelled "
         "evidence, not a retrieval over text. He wrote the first commit — LLM "
         "client, graph client and ingestion pipeline — and 240+ since: "
         "case-level isolation enforced in the database, entity resolution, the "
         "split between verified facts and AI inference, and the performance "
         "work that keeps very large cases traversable.",
         "Full-time on close."),
        ("Alexandra Solórzano", "CPO",
         "10+ years as a licensed private investigator on federal criminal "
         "defence and financial fraud casework — and the product's direction, "
         "daily. **Multiple calls a week; the backlog is generated from live "
         "matters as she works them**, which is why development has never run "
         "on a roadmap invented in advance. A grounded visionary: every feature "
         "traces to a real case, and she has run federal cases to completion "
         "inside the platform. US-based.",
         "The domain authority — and the customer the product was built for."),
    ]

    for i, (name, role, bio, flag) in enumerate(people):
        left = MARGIN_L + i * Inches(4.05)
        tf = textbox(s, left, Inches(2.42), Inches(3.6), Inches(4.3))
        para(tf, name, size=19, colour=PAPER, bold=True, first=True,
             space_before=0, font=FONT_H)
        para(tf, role, size=12, colour=ACCENT, bold=True, space_before=3)
        para(tf, bio, size=11, colour=MUTED, space_before=9)
        para(tf, flag, size=11, colour=ACCENT, bold=True, space_before=9)

    tf = textbox(s, MARGIN_L, Inches(6.72), BODY_W, Inches(0.72))
    para(tf, "Seven years building investigative intelligence software for "
             "enterprise buyers, and a decade running federal casework as the "
             "kind of investigator who has to live with the result. "
             "**Our CPO has run federal cases to completion inside this platform.**",
         size=13.5, colour=PAPER, first=True, space_before=0)

    notes(s, """LEAD WITH SIREN. It is the strongest founder-market-fit signal you
have. NDRC will know Siren — Irish, Enterprise Ireland-backed, same category. It
converts you from "engineer who built a thing" to "category-native founder who
has seen this market's buying behaviour for seven years." It pre-answers the
sales-cycle and procurement questions before they're asked.

"Full-time on close" appears twice on purpose. Say it out loud as well as
printing it.

DO NOT HIDE Alex being US-based. Address it in one line: the company is Irish,
the IP is Irish-owned, engineering is in Dublin, and the market is US-first —
which is why the domain founder is where the customers are.""")
    return s


def slide8(prs):
    s = blank(prs); bg(s)
    kicker(s, "Status and traction")
    heading(s, "Loupe is in production use on real federal casework.",
            size=30)
    rule(s, Inches(1.9), width=Inches(1.1))

    tf = textbox(s, MARGIN_L, Inches(2.25), Inches(6.15), Inches(4.9))
    para(tf, "Built inside **Owl Consultancy**, a working US "
             "private-investigations practice, and used there to carry federal "
             "cases **to completion** — multi-gigabyte phone extractions, tens "
             "of thousands of curated financial transactions, full document "
             "corpora. **Three attorneys on those cases have been given access "
             "to it.** Attorneys have retained the practice specifically "
             "because of the platform — unprompted, before any marketing "
             "existed.",
         size=13, first=True, space_before=0)
    para(tf, "This is not a prototype seeking a first user. It is an "
             "application that works, in the hands of the investigators it was "
             "built for, on cases with real stakes.",
         size=15, colour=ACCENT, bold=True, space_before=13)
    para(tf, "First external pilot in motion.", size=13, colour=PAPER,
         bold=True, space_before=14)
    para(tf, "A US private-investigations firm led by a former FBI undercover "
             "agent — clients across Miami, New York, California and the "
             "Midwest — has agreed to send its next large-document matter "
             "through Loupe as a paid trial at cost, and to put a mutual MSA in "
             "front of us. Sourced through casework, not marketing.",
         size=13, colour=MUTED, space_before=4)

    tf2 = textbox(s, Inches(7.55), Inches(2.25), Inches(4.95), Inches(4.9))
    para(tf2, "Built so far, verifiable", size=12, colour=ACCENT, bold=True,
         first=True, space_before=0)
    bullets(tf2, [
        "- ~180,000 lines across a React console, a FastAPI case API and a separate asynchronous evidence engine",
        "- 913 commits since December 2025 — two primary engineers",
        "- Neo4j (case graph) · Postgres (cases, auth, audit) · ChromaDB (retrieval) · Redis (jobs)",
        "- Three AI providers behind one routing policy — the model is a swappable component",
        "- Single-tenant deployment: one isolated stack per customer",
    ], size=12, colour=MUTED, gap=6, first_flag=True)

    para(tf2, "Release discipline", size=12, colour=ACCENT, bold=True,
         space_before=14)
    para(tf2, "Onboarding an external customer's evidence runs behind a "
              "**12-stage security-gated release plan. No external case data "
              "enters the platform until the security, isolation, backup and "
              "legal stages pass.**",
         size=12, colour=PAPER, space_before=4)
    para(tf2, "Roadmap: a 13-epic board takes Loupe from a platform that works "
              "for the practice it was built in to one that scales across many. "
              "Depth, not existence.",
         size=12, colour=MUTED, space_before=10)

    notes(s, """TWO BEATS, IN THIS ORDER — DO NOT INVERT THEM.

FIRST: IT WORKS. Cases closed, attorneys using it, a practice winning business
because of it. That is a further-along position than most of what NDRC will see
this year, and it should be the first thing out of your mouth.

SECOND: THE SECURITY GATE. No external customer's evidence enters until the
isolation, backup and legal stages pass. Most pre-seed teams cannot demonstrate
release discipline at all. Frame it as WHY the external pilot hasn't started
yet — that turns a delay into evidence of seriousness.

ON THE ROADMAP: mention it, don't dwell on it. It is a statement of ambition,
not a list of things Loupe cannot do. If the deck spends more pixels on the
roadmap than on the working product, a reader concludes the product IS the
roadmap.

CLAIMS SAFETY
- DO NOT call the ex-FBI PI firm a signed customer, an LOI, or a pipeline
  value. Nothing is signed. True and sufficient: an agreed next case, an
  at-cost trial, an MSA to be exchanged. This is the only hard prohibition.
- "WCAG 2.1 AA" and "571k-node corpus" — fine if evidenced. Have the audit
  result and load-test output to hand.
- Scale figures: say whether each came from a real case or a test corpus.
- Prefer "verification workflow" over "human-verified facts".
- CI: .github/workflows absent from the branch inspected. If CI runs elsewhere,
  ignore. Otherwise don't claim hard-gating CI — and consider standing it up.

FRAMING RULE FOR THE WHOLE DECK: Loupe is one product, and it works. Never
write a sentence that invites a reader to wonder whether the thing that ran
federal cases is the same thing you are pitching. It is.""")
    return s


def slide9(prs):
    s = blank(prs); bg(s)
    kicker(s, "The ask")
    heading(s, "€100k. What it buys: the first paying customer\noutside the practice that built it.",
            size=29)
    rule(s, Inches(2.15), width=Inches(1.1))

    tf = textbox(s, MARGIN_L, Inches(2.42), Inches(6.35), Inches(1.15))
    para(tf, "The platform works and has closed real federal cases. What "
             "stands between it and external revenue is the **security gate** — "
             "the isolation, backup and legal stages that let another firm's "
             "privileged evidence enter the system — and the pilot itself.",
         size=14, first=True, space_before=0)

    tfa = textbox(s, MARGIN_L, Inches(3.62), Inches(6.35), Inches(3.0))
    para(tfa, "Use of funds", size=12, colour=ACCENT, bold=True, first=True,
         space_before=0)
    bullets(tfa, [
        "- **Two founders full-time** — clearing the security gate and running the agreed pilot to a signed contract. The pilot candidate is already secured.",
        "- **The security evidence a firm's counsel asks for** — Cyber Essentials, an independent penetration test and a written security package, plus starting the SOC 2 observation window. Cheap and fast; full certification is bought when a deal requires it.",
        "- **Single-tenant infrastructure** for the first external customers — one instance each, so it scales with customers rather than ahead of them.",
        "- **Processing and inference** across pilot matters. The per-matter cost model is what the pilot establishes.",
    ], size=12, colour=PAPER, gap=6, first_flag=True)

    tf2 = textbox(s, Inches(7.65), Inches(2.42), Inches(4.85), Inches(4.2))
    para(tf2, "What we want from NDRC beyond capital",
         size=12, colour=ACCENT, bold=True, first=True, space_before=0)
    bullets(tf2, [
        "- **Go-to-market guidance.** The channel is identified — bar associations and professional bodies — and pricing is per-matter rather than per-seat. Both need pressure-testing by people who have built a repeatable motion.",
        "- Dublin base at Dogpatch Labs",
        "- EIR time on pricing structure and enterprise sales motion",
        "- Introductions into Irish and UK professional-services buyers — ACFE Ireland, Chartered Accountants Ireland forensic group, Law Society criminal law committee",
    ], size=12, colour=PAPER, gap=7, first_flag=True)

    tf3 = textbox(s, MARGIN_L, Inches(6.78), BODY_W, Inches(0.62))
    para(tf3, "We are not asking anyone to fund the invention of a product. We "
              "are asking them to fund the distance between **works** and "
              "**sold.**",
         size=17, colour=ACCENT, bold=True, first=True, space_before=0)

    notes(s, """DO NOT put an hours figure on this slide, and do not pre-empt an
arithmetic problem you don't have. This is a COMMERCIALISATION raise, not a
build raise — the easier of the two to underwrite, and it happens to be true.

If the roadmap comes up: it is the path from serving one practice to serving
many, deliberately ambitious because the category rewards depth. Present it as
where the company goes, never as what the product still lacks. If asked what
€100k funds against a 265-ticket board: the gate and the pilot, and the rest is
sequenced behind revenue from customers you will have by then.

THE GROSS-MARGIN QUESTION — be ready for it.
Loupe has a real variable cost per case: AI processing, roughly $70 to ingest a
1,600-page document. A buyer has already asked whether the licence covers AI
processing or tokens are billed separately. It is not yet answered. Do not hide
it. Credible position:

  Every case carries a measurable AI processing cost. We meter it today.
  Whether it sits inside the licence or is passed through is a pricing decision
  we are taking from pilot data rather than guessing — and it is one of the
  questions this round exists to answer.

Two things make this a strength: (1) you MEASURE it, which most applicants
cannot; (2) the cost is direct evidence of the product claim — the price is
high because the system reads everything, which is precisely what a $20 chat
subscription does not do.

Have a rough per-case unit economic ready: cost to process a representative
matter versus the senior/junior hours it displaces. You don't need a final
price. You need to show you know the shape of the P&L.""")
    return s


# ---------------------------------------------------------------- main

def main():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    for fn in (slide1, slide2, slide3, slide4, slide5,
               slide6, slide6b, slide7, slide8, slide9):
        fn(prs)

    out = "Loupe-NDRC-deck.pptx"
    prs.save(out)
    print(f"wrote {out} — {len(prs.slides.__iter__.__self__._sldIdLst)} slides")


if __name__ == "__main__":
    main()
