"""The phone export PDF (03 section 12.3): HTML from the same rows the screen shows, drawn by WeasyPrint with the
bundled Noto fonts.

Nothing is cut: bodies wrap and break across pages (no max-height, no text-overflow, no list caps). Every time is
the screen's own string (``time_display`` through ``streams.build_rows``). Before drawing, every code point is
checked against the bundled fonts' character maps; one no font covers prints as a visible ``[U+1F9FF]`` token and
is listed with its count in the appendix "Characters that could not be drawn".
"""
from __future__ import annotations

import html
import os
import unicodedata
from collections import Counter
from functools import lru_cache

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))), "assets", "fonts")
# (family, file, weight): one fallback chain, in this order (03 section 12.3)
FONTS = [
    ("Noto Sans", "NotoSans-Regular.ttf", 400),
    ("Noto Sans", "NotoSans-Bold.ttf", 700),
    ("Noto Sans Arabic", "NotoSansArabic-Regular.ttf", 400),
    ("Noto Sans Hebrew", "NotoSansHebrew-Regular.ttf", 400),
    ("Noto Sans Thai", "NotoSansThai-Regular.ttf", 400),
    ("Noto Sans Devanagari", "NotoSansDevanagari-Regular.ttf", 400),
    ("Noto Sans Math", "NotoSansMath-Regular.ttf", 400),
    ("Noto Sans Symbols", "NotoSansSymbols-Regular.ttf", 400),
    ("Noto Sans Symbols 2", "NotoSansSymbols2-Regular.ttf", 400),
    ("Noto Emoji", "NotoEmoji-Regular.ttf", 400),
    ("Noto Sans Fullwidth", "NotoSansFullwidth-Regular.ttf", 400),  # Noto Sans JP, the fullwidth forms only
    ("Noto Sans SC", "NotoSansSC-Variable.ttf", 400),  # Han (unified and Extension A) and kana
    ("Noto Sans Hangul", "NotoSansHangul-Regular.ttf", 400),  # Noto Sans KR, the Hangul blocks only
]
FAMILY_CHAIN = ", ".join('"%s"' % f for f in dict.fromkeys(f for f, _, _ in FONTS))
# characters that are never drawn as glyphs of their own (joiners, variation selectors, direction marks, controls
# a body may carry); they stay in the text and are not "missing"
_SILENT_CATEGORIES = {"Cf", "Cc", "Zl", "Zp"}


@lru_cache(maxsize=1)
def covered() -> frozenset:
    """Every code point some bundled font has a glyph for."""
    from fontTools.ttLib import TTFont
    out = set()
    for _, name, _ in FONTS:
        font = TTFont(os.path.join(FONT_DIR, name), lazy=True)
        try:
            out.update(font.getBestCmap() or {})
        finally:
            font.close()
    return frozenset(out)


def drawable(text: str, missing: Counter) -> str:
    """The text as it can be drawn: an uncovered code point becomes ``[U+XXXX]`` and is counted in ``missing``."""
    if not text:
        return ""
    cov = covered()
    out = []
    for ch in text:
        cp = ord(ch)
        if cp in cov or ch in "\n\t " or unicodedata.category(ch) in _SILENT_CATEGORIES:
            out.append(ch)
        else:
            token = "[U+%04X]" % cp
            missing[token] += 1
            out.append(token)
    return "".join(out)


def _e(text, missing):
    return html.escape(drawable(text or "", missing))


CSS = """
@page { size: %(page)s; margin: 18mm 16mm 18mm 16mm;
        @bottom-right { content: "Page " counter(page) " of " counter(pages); font-family: %(chain)s;
                        font-size: 8pt; color: #555; } }
html { font-family: %(chain)s; font-size: 9.5pt; line-height: 1.35; color: #111; }
h1 { font-size: 16pt; margin: 0 0 6pt 0; } h2 { font-size: 12pt; margin: 14pt 0 4pt 0; }
h3.day { font-size: 10.5pt; margin: 12pt 0 4pt 0; border-bottom: 0.5pt solid #999; break-after: avoid; }
.cover p, .contains li { margin: 2pt 0; }
.row { margin: 0 0 6pt 0; break-inside: auto; }
.meta { font-size: 8.5pt; color: #333; }
.body { white-space: pre-wrap; overflow-wrap: anywhere; word-break: normal; }
.badges { font-size: 8pt; color: #333; }
.rid { font-size: 7pt; color: #666; }
.origin { font-size: 8pt; font-weight: 700; }
table.appendix { border-collapse: collapse; font-size: 8.5pt; } table.appendix td { padding: 1pt 6pt 1pt 0; }
"""


def font_faces() -> str:
    return "\n".join(
        '@font-face { font-family: "%s"; src: url("file://%s"); font-weight: %d; }'
        % (fam, os.path.join(FONT_DIR, name), weight) for fam, name, weight in FONTS)


def _translation_html(t, missing) -> list:
    """A machine translation under its original (05 17.5): the language it was translated from, the text, and its
    label; a translation of a text corrected since says so."""
    if not t:
        return []
    out = ['<div class="body">%s</div>' % _e("Machine translation from %s: %s" % (
        t.get("detected_language_name") or "another language", t.get("text") or ""), missing),
        '<div class="origin">%s</div>' % _e(t.get("label") or "", missing)]
    if t.get("stale"):
        out.append('<div class="origin">%s</div>' % _e(t.get("stale_words") or "", missing))
    return out


def _row_html(r, missing) -> str:
    t = (r.get("time") or {}).get("full") or "No time recorded"
    who = r.get("line") or ""
    head = " · ".join(x for x in (t, r["phone"]["label"], r.get("app") or "", who) if x)
    parts = ['<div class="row">', '<div class="meta">%s</div>' % _e(head, missing)]
    if r.get("subject"):
        parts.append('<div class="body"><b>%s</b></div>' % _e(r["subject"], missing))
    if r.get("kind") == "call" and r.get("call"):
        parts.append('<div class="body">%s</div>' % _e(r["call"].get("words") or "Call", missing))
    if r.get("body"):
        parts.append('<div class="body">%s</div>' % _e(r["body"], missing))
        parts += _translation_html(r.get("translation"), missing)
    for a in r.get("attachments") or []:
        parts.append('<div class="badges">Attachment: %s%s</div>' % (
            _e(a.get("filename") or "file not named in the report", missing),
            _e(" (%s)" % a["verification"], missing) if a.get("verification") else ""))
        for t in a.get("machine_texts") or []:
            what = "Transcript" if t["kind"] == "transcript" else "Text read from the image"
            parts.append('<div class="body">%s: %s</div>' % (_e(what, missing), _e(t["text"] or "No text was found.",
                                                                                 missing)))
            parts.append('<div class="origin">%s</div>' % _e(t["origin"]["words"] or "", missing))
            parts += _translation_html(t.get("translation"), missing)
    flags = [f for f in (r.get("flags") or []) if f != "Mapped by the system, not yet confirmed"]
    if r.get("interpretation_level") == "applied_unconfirmed":
        parts.append('<div class="origin">Mapped by the system, not yet confirmed</div>')
    copies = r.get("copies") or {}
    if (copies.get("count") or 1) > 1:
        flags.append("Found %d times (%s)" % (copies["count"], ", ".join(copies.get("apps") or [])))
    if flags:
        parts.append('<div class="badges">%s</div>' % _e(" · ".join(flags), missing))
    parts.append('<div class="rid">Record %s-%s</div>' % (_e(r["phone"]["label"], missing),
                                                          _e(r["record_uid"], missing)))
    parts.append("</div>")
    return "".join(parts)


def build_html(*, title, case_name, generated, export_id, contains, days, participants, page="letter", review=None,
               review_threads=None) -> tuple:
    """``days``: [(header words, rows)] in screen order; ``contains``: sentences for "What this export contains";
    ``participants``: [(label, [identifier, ...])]; ``review``: the cover's "Review coverage" sentences and
    ``review_threads`` the coverage summary whose threads the appendix lists (07 J-13 step 6). Returns
    (html, missing Counter)."""
    missing = Counter()
    cover = ['<section class="cover"><h1>%s</h1>' % _e(title, missing),
             "<p>%s</p>" % _e(case_name, missing),
             "<p>%s</p>" % _e(generated, missing),
             "<p>Export %s</p></section>" % _e(export_id, missing),
             '<h2>What this export contains</h2><ul class="contains">']
    cover += ["<li>%s</li>" % _e(s, missing) for s in contains]
    # drawn before the missing-character count is written, so a character they hold is counted too
    review_html = (['<h2>Review coverage</h2><ul class="contains">'] + ["<li>%s</li>" % _e(x, missing) for x in review]
                   + ["</ul>"]) if review else []
    body = []
    for header, rows in days:
        body.append('<h3 class="day">%s</h3>' % _e(header, missing))
        body += [_row_html(r, missing) for r in rows]
    body.append('<h2>Participants</h2><table class="appendix">')
    for label, idents in participants:
        body.append("<tr><td>%s</td><td>%s</td></tr>" % (_e(label, missing), _e(", ".join(idents), missing)))
    body.append("</table>")
    if review_threads:
        body.append('<h2>Review coverage of these threads</h2><table class="appendix">')
        for state, key in (("Not yet reviewed", "not_reviewed"), ("Partly reviewed", "partly_reviewed"),
                           ("Reviewed", "reviewed")):
            for t in review_threads.get(key) or []:
                body.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                    _e(state, missing), _e("%s (%s)" % (t["title"], t["phone"]), missing),
                    _e(t["review"] or "{:,} messages".format(t["messages"]), missing)))
        body.append("</table>")
    # the missing characters are known only now: the cover counts them and the appendix lists every one
    if missing:
        n = sum(missing.values())
        cover.append("<li>%s %s that no bundled font can draw %s as [U+...] and %s listed at the end.</li>" % (
            "{:,}".format(n), "character" if n == 1 else "characters", "prints" if n == 1 else "print",
            "is" if n == 1 else "are"))
        body.append('<h2>Characters that could not be drawn</h2><table class="appendix">')
        for token, k in sorted(missing.items()):
            body.append("<tr><td>%s</td><td>%s</td></tr>" % (token, "{:,}".format(k)))
        body.append("</table>")
    cover.append("</ul>")
    body = cover + review_html + body
    page_css = "A4" if page == "a4" else "letter"
    doc = ("<!doctype html><html><head><meta charset='utf-8'><style>%s\n%s</style></head><body>%s</body></html>"
           % (font_faces(), CSS % {"page": page_css, "chain": FAMILY_CHAIN}, "".join(body)))
    return doc, missing


def local_only(url, *args, **kwargs):
    """WeasyPrint's URL fetcher, limited to the bundled fonts: nothing in an export is fetched from a network."""
    import weasyprint
    path = url[len("file://"):] if url.startswith("file://") else None
    if path is None or not os.path.realpath(path).startswith(os.path.realpath(FONT_DIR) + os.sep):
        raise ValueError("phone exports load only the bundled fonts, not %s" % url.split(":", 1)[0])
    return weasyprint.default_url_fetcher(url, *args, **kwargs)


def render(doc: str) -> bytes:
    import weasyprint
    return weasyprint.HTML(string=doc, base_url=FONT_DIR, url_fetcher=local_only).write_pdf()


RENDER_MEMORY_MB = int(os.environ.get("LOUPE_PHONE_EXPORT_MEMORY_MB", "4096"))
RENDER_TIMEOUT_SECONDS = 3 * 3600


class RenderStopped(RuntimeError):
    pass


def _render_child(doc_path, out_path, memory_mb):
    import resource
    limit = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    with open(doc_path, encoding="utf-8") as fh:
        data = render(fh.read())
    with open(out_path, "wb") as fh:
        fh.write(data)


def render_isolated(doc: str) -> bytes:
    """``render`` in a child process whose address space is capped at ``RENDER_MEMORY_MB``: a document too large to
    lay out fails here with ``RenderStopped`` and the server that asked for it keeps running."""
    import multiprocessing
    import tempfile
    with tempfile.TemporaryDirectory(prefix="phone-export-") as tmp:
        doc_path, out_path = os.path.join(tmp, "doc.html"), os.path.join(tmp, "out.pdf")
        with open(doc_path, "w", encoding="utf-8") as fh:
            fh.write(doc)
        p = multiprocessing.get_context("spawn").Process(target=_render_child,
                                                         args=(doc_path, out_path, RENDER_MEMORY_MB), daemon=True)
        p.start()
        p.join(RENDER_TIMEOUT_SECONDS)
        if p.is_alive():
            p.kill()
            p.join()
            raise RenderStopped("the PDF took longer than %d hours to draw" % (RENDER_TIMEOUT_SECONDS // 3600))
        if p.exitcode != 0 or not os.path.exists(out_path):
            raise RenderStopped("the PDF could not be drawn within %d MB (exit %s)" % (RENDER_MEMORY_MB, p.exitcode))
        with open(out_path, "rb") as fh:
            return fh.read()
