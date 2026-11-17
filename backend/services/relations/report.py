"""The report of one group's analysis, in the casework report's look: light ground, same privilege marking (lx-overlaps F).

It holds the items; each analysis run and its result; the candidate links, graded, weak ones as weak, each with the
chance beside it; the pairs with no link found, with what was searched and what was out of reach; the explanations
as a model reading with the model's name until a person accepts them; and what a person accepted.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from services.snapshot_report import PRIVILEGE_BASIS, privilege_label

LEVEL_WORDS = {"strong": "Strong", "moderate": "Moderate", "weak": "Weak", "faint": "Faint"}
KIND_WORDS = {"time_proximity": "Close in time", "sequence": "Order of events", "shared_identifier": "Same number, email or name",
              "same_amount": "Same amount", "place_overlap": "Same place, same time", "relay_chain": "Relay",
              "shared_silence": "Both quiet at once", "together_apart": "Alternating use"}


def _e(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _labels(result: dict) -> dict[str, str]:
    return {i["ref"]: i["label"] for i in result["items"]}


def _names(members: list[str], labels: dict[str, str]) -> str:
    return "; ".join(_e(labels.get(m, m[:8])) for m in members)


REPORT_CANDIDATES = 300
REPORT_NO_LINKS = 100


def render_html(*, case_name: str, generated_by: str, group: dict, run: dict, privilege_marking: str = "unmarked") -> str:
    result = run.get("result") or {}
    if not result:
        raise ValueError("This group has no finished analysis to report.")
    labels = _labels(result)
    label = privilege_label(privilege_marking)
    c = result["counts"]
    items = "".join(f"<li>{_e(i['label'])} <span class='sub'>{_e(i['type'].replace('_', ' '))}"
                    + (f" · {_e(i['at'][:16].replace('T', ' '))}" if i.get("at") else " · no date on record") + "</span></li>"
                    for i in result["items"])
    analyses = "".join(f"<tr><td>{_e(a['title'])}</td><td>{a['pairs']:,}</td><td>{a['found']:,}</td><td>{_e(a.get('note', ''))}</td></tr>"
                       for a in result["analyses"])
    shown_cands = result["candidates"][:REPORT_CANDIDATES]
    shown_nolinks = result["no_links"][:REPORT_NO_LINKS]
    clipped = ((f"<p class='says'>This report lists the {len(shown_cands):,} strongest of {len(result['candidates']):,} candidate links. "
                "The rest are on the screen.</p>") if len(result["candidates"]) > len(shown_cands) else "")
    clipped_no = ((f"<p class='says'>This report lists {len(shown_nolinks):,} of {len(result['no_links']):,} pairs with no link found. "
                   "The rest are on the screen.</p>") if len(result["no_links"]) > len(shown_nolinks) else "")
    cands = "".join(
        f"<li class='cand {x['strength']}'><span class='who'>{LEVEL_WORDS[x['strength']]} · {_e(KIND_WORDS.get(x['kind'], x['kind']))}</span> "
        f"<span class='sub'>{_names(x['members'], labels)}</span>{_e(' '.join(x['reasons']))}"
        + (f"<span class='sub chance'>Chance: {_e(x['chance']['words'])}</span>" if x["chance"].get("words") else "") + "</li>"
        for x in shown_cands) or "<li class='muted'>No candidate link was found.</li>"
    nolinks = "".join(
        f"<li><span class='sub'>{_names(n['members'], labels)}</span>{_e(n['says'])}"
        + "".join(f"<span class='sub'>Searched: {_e(s)}</span>" for s in n["searched"])
        + "".join(f"<span class='sub'>Out of reach: {_e(s)}</span>" for s in n["out_of_reach"]) + "</li>"
        for n in shown_nolinks) or "<li class='muted'>Every pair has at least one candidate link.</li>"
    reach = "".join(f"<li>{_e(o['analysis'])}: {_e(o['reason'])}</li>" for o in result["out_of_reach"])
    hyp = run.get("hypotheses")
    if hyp:
        rows = []
        for h in hyp["items"]:
            accepted = h.get("accepted")
            rows.append(
                f"<li><span class='who'>{_e(h['kind'].replace('_', ' ').capitalize())}</span> {_e(h['statement'])}"
                + (f"<span class='sub'>Predicts: {_e(h['predicts'])}</span>" if h.get("predicts") else "")
                + "".join(f"<span class='sub'>For: {_e(x['cite'])} {_e(x['text'])}</span>" for x in h["for"])
                + "".join(f"<span class='sub'>Against: {_e(x['cite'])} {_e(x['text'])}</span>" for x in h["against"])
                + f"<span class='sub'>Would tell it apart: {_e(h['distinguishing_record'])}</span>"
                + f"<span class='sub'>Searched: {_e(h['search'])}</span>"
                + (f"<span class='sub accepted'>Accepted by {_e(accepted['by'])} as {_e(accepted['relationship'])}.</span>" if accepted
                   else "<span class='sub'>Not confirmed by a person.</span>") + "</li>")
        hyp_html = (f"<p class='model'>A model reading by {_e(hyp.get('model'))}. {_e(hyp['status'])}</p><ol>{''.join(rows)}</ol>"
                    + (f"<p>{_e(hyp['no_links'])}</p>" if hyp.get("no_links") else ""))
    else:
        hyp_html = "<p class='muted'>No explanations have been drafted for this group.</p>"
    footer = label if privilege_marking in ("confidential", "privileged_confidential") else "Loupe link analysis report"
    when = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 portrait; margin: 1.5cm 1.4cm 1.6cm;
        @bottom-left {{ content: "{html.escape(footer)}"; font-size: 9px; color: #475569; }}
        @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font-size: 9px; color: #475569; }} }}
      body {{ font-family: sans-serif; font-size: 10px; color: #1e293b; background: #fff; }}
      h1 {{ font-size: 22px; margin: 4px 0; }} h2 {{ font-size: 15px; margin-top: 18px; border-bottom: 1px solid #cbd5e1; }}
      .eyebrow {{ font-size: 9px; letter-spacing: 1px; text-transform: uppercase; color: #64748b; }}
      .marking {{ border: 1.5px solid #0f172a; padding: 6px 10px; margin: 10px 0; font-size: 11px; }}
      .marking span {{ display: block; color: #475569; font-size: 9px; }}
      .sub {{ display: block; color: #475569; font-size: 9px; }} .who {{ font-weight: bold; }} .muted {{ color: #64748b; }}
      li {{ margin-bottom: 4px; break-inside: avoid; }} table {{ border-collapse: collapse; width: 100%; }}
      td, th {{ border: 1px solid #cbd5e1; padding: 2px 5px; text-align: left; }}
      .model {{ border-left: 2px solid #a78bfa; padding-left: 6px; }} .says {{ font-weight: bold; }}
    </style></head><body>
      <div class="eyebrow">Link analysis report</div>
      <h1>{_e(case_name or 'Case')}</h1>
      <p>Generated by {_e(generated_by)} on {_e(when)} · {c['items']:,} items · {c['candidates']:,} candidate links · {c['no_links']:,} pairs with no link found</p>
      <div class="marking"><strong>{_e(label)}</strong><span>{_e(PRIVILEGE_BASIS)}</span></div>
      <p class="says">{_e(result['says'])}</p>
      <h2>The items ({c['items']:,})</h2><ul>{items}</ul>
      <h2>Analyses run</h2><table><tr><th>Analysis</th><th>Pairs covered</th><th>Links found</th><th>Note</th></tr>{analyses}</table>
      {'<h3>Out of reach</h3><ul>' + reach + '</ul>' if reach else ''}
      <h2>Candidate links ({c['candidates']:,})</h2><p class="muted">Strongest first. Weak links are listed as weak.</p>{clipped}<ul>{cands}</ul>
      <h2>Pairs with no link found ({c['no_links']:,})</h2><p class="muted">Each says what was searched. It is not proof that no link exists.</p>{clipped_no}<ul>{nolinks}</ul>
      <h2>How they could be linked</h2>{hyp_html}
    </body></html>"""


def render_pdf(**kwargs: Any) -> bytes:
    from weasyprint import HTML

    from services.pdf_fetch import deny_all
    return HTML(string=render_html(**kwargs), url_fetcher=deny_all("Reports cannot load external or local resources.")).write_pdf()
