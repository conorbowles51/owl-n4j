"""The report of one group's analysis, in the casework report's look: light ground, same privilege marking (lx-overlaps F).

It holds the Corroborate result when the run asked a question: the level and the rule's reasons, the comparison grid
with the records behind each cell, every check made, who else was searched and was not in the pattern, the records
missing, and the story lanes of each instance. Then the items; each analysis run and its result; the candidate links, graded, weak ones as weak, each with the
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
# The screen's words for the Corroborate result (frontend_v2 features/corroborate/ResultView.tsx), so both say the same.
CELL_MARK = {"present": "●", "absent": "○", "no_data": "?"}
CHECK_WORDS = {"routine": "Routine contact", "household": "Shared household", "workplace": "Shared workplace",
               "stock_phrase": "Stock phrase", "busy_place": "Busy place", "clock_zone": "Clock or time zone",
               "recycled_number": "Recycled number", "same_name": "Another person of the same name",
               "shared_device": "Shared device", "duplicate_copy": "Duplicate copies", "received_media": "Received media"}
OUTCOME_WORDS = {"checked": "Checked, nothing found", "ruled_out": "Ruled out", "weighed_low": "Weighed low",
                 "no_data": "No data to check"}


def _corroboration_html(c: dict, lanes: list[dict] | None) -> str:
    """The Corroborate result as the screen shows it. Each grid cell gives its records; each instance its lanes."""
    level = c["level"]
    instances = ([{**i, "side": "Incident"} for i in c["comparison"]["incident"]]
                 + [{**i, "side": "Ordinary"} for i in c["comparison"]["ordinary"]])
    keys = {i["id"]: f"{i['side'][0]}{n}" for n, i in enumerate(instances, 1)}
    out = [f"<h2>Corroborate: {_e(level['name'])}</h2><p class='muted'>{_e(c['question']['text'])}</p>",
           f"<p class='says'>{_e(level['sentence'])}</p>",
           "<p class='muted'>Set by a stated rule from the signals below, not by a model.</p>",
           "<h3>What was present, and on which instances</h3>", f"<p class='muted'>{_e(c['comparison']['words'])}</p>"]
    if c["grid"]:
        head = "".join(f"<th>{keys[i['id']]}</th>" for i in instances)
        rows = []
        for r in c["grid"]:
            notes = ((f"<span class='sub'>Weighed low: {_e(r.get('why_low'))}</span>" if r.get("weight") != "full" else "")
                     + (f"<span class='sub'>Shown, not weighed: {_e(r.get('why_context'))}</span>" if r.get("context") else "")
                     + ("<span class='sub'>Chose the other instances; not evidence</span>" if r.get("picked_by") else ""))
            cells = "".join(f"<td>{CELL_MARK.get(r['cells'].get(i['id'], 'no_data'), '?')}</td>" for i in instances)
            rows.append(f"<tr><td>{_e(r['label'])}{notes}</td>{cells}<td>{r['incident']['present']} of {r['incident']['of']}</td>"
                        f"<td>{r['ordinary']['present']} of {r['ordinary']['of']}</td></tr>")
        out.append(f"<table class='grid'><tr><th>Signal</th>{head}<th>Incident</th><th>Ordinary</th></tr>{''.join(rows)}</table>"
                   "<p class='muted'>● present · ○ checked and absent · ? no data (counts neither way)</p>")
        out.append("<h3>The instances and the records behind each mark</h3><ul>")
        for i in instances:
            cited = []
            for r in c["grid"]:
                refs = r.get("records", {}).get(i["id"]) or []
                if r["cells"].get(i["id"]) == "present" and refs:
                    total = (r.get("record_counts") or {}).get(i["id"], len(refs))
                    more = f" (the first {len(refs):,} of {total:,})" if total > len(refs) else ""
                    cited.append(f"<span class='sub'>{_e(r['label'])}{more}: {_e(', '.join(refs))}</span>")
            out.append(f"<li><span class='who'>{keys[i['id']]} {_e(i['side'])}: {_e(i['label'])}</span>"
                       + (f"<span class='sub'>{_e(i['start'][:16].replace('T', ' '))} to {_e(i['end'][:16].replace('T', ' '))}</span>"
                          if i.get("start") and i.get("end") else "")
                       + ("".join(cited) or "<span class='sub'>No signal present.</span>") + "</li>")
        out.append("</ul>")
    else:
        out.append("<p>No signal was present on any instance.</p>")
    out.append("<h3>What raises it, and what lowers it</h3><ul>" + "".join(f"<li>{_e(r)}</li>" for r in level["reasons"]) + "</ul>")
    out.append(f"<h3>Checks made ({len(c['checks']):,})</h3><ul>" + "".join(
        f"<li><span class='who'>{_e(CHECK_WORDS.get(k['check'], k['check']))}</span>: {_e(OUTCOME_WORDS.get(k['outcome'], k['outcome']))}. "
        f"{_e(k.get('words'))}" + (f"<span class='sub'>Records: {_e(', '.join(k['records']))}</span>" if k.get("records") else "")
        + "</li>" for k in c["checks"]) + "</ul>")
    out.append("<h3>Not in this pattern</h3>" + ("<ul>" + "".join(
        f"<li><span class='who'>{_e(n['who'])}</span> {_e(n['says'])}"
        + "".join(f"<span class='sub'>Searched: {_e(x)}</span>" for x in n.get("searched", []))
        + "".join(f"<span class='sub'>Out of reach: {_e(x)}</span>" for x in n.get("out_of_reach") or []) + "</li>"
        for n in c["not_in_pattern"]) + "</ul>" if c["not_in_pattern"] else "<p>No one else was searched.</p>"))
    out.append("<h3>Records missing</h3>" + ("<ul>" + "".join(f"<li>{_e(g['words'])}</li>" for g in c["gaps"]) + "</ul>"
                                          if c["gaps"] else "<p>No gap was found in the records for these instances.</p>"))
    if lanes is not None:
        out.append("<h3>Story lanes</h3><p class='muted'>For each instance, the records the grid cites, in time order, "
                   "one lane per person.</p>")
        for lane_set in lanes:
            inst = lane_set["instance"]
            out.append(f"<h4>{keys.get(inst['id'], '')} {_e(inst['label'])}</h4>")
            if lane_set.get("error"):
                out.append(f"<p class='says'>{_e(lane_set['error'])}</p>")
                continue
            if not lane_set["lanes"]:
                out.append("<p class='muted'>No record is cited for this instance.</p>")
            for lane in lane_set["lanes"]:
                out.append(f"<p class='who'>{_e(lane['label'])}</p><ol class='lane'>" + "".join(
                    f"<li value='{e['n']}'>{_e(e['at'][:10] if e.get('day_only') else e['at'][:16].replace('T', ' '))} · "
                    f"{_e(e['kind_words'])}" + (f" with {_e(', '.join(e['with']))}" if e.get("with") else "")
                    + f"<span class='sub'>{_e(e['text'])}</span></li>" for e in lane["events"]) + "</ol>")
            if lane_set.get("not_laid_out"):
                gone = lane_set["not_laid_out"]
                out.append(f"<p class='says'>{len(gone):,} cited records could not be read again for this instance: "
                           f"{_e(', '.join(g['ref'] for g in gone))}</p>")
    return "".join(out)


def render_html(*, case_name: str, generated_by: str, group: dict, run: dict, privilege_marking: str = "unmarked",
                lanes: list[dict] | None = None) -> str:
    result = run.get("result") or {}
    corroboration = result.get("corroboration")
    if not result or ("counts" not in result and not corroboration):
        raise ValueError("This group has no finished analysis to report.")
    label = privilege_label(privilege_marking)
    corro_html = _corroboration_html(corroboration, lanes) if corroboration else ""
    if "counts" not in result:
        # The Corroborate result is stored before the link analysis runs; a run stopped between the two has only it.
        return _page(case_name, generated_by, privilege_marking, label, corro_html
                     + "<h2>Link analysis</h2><p class='says'>The link analysis did not finish for this run, so this "
                       "report has no candidate links. Run the analysis again to add them.</p>", "")
    labels = _labels(result)
    c = result["counts"]
    items = "".join(f"<li>{_e(i['label'])} <span class='sub'>{_e(i['type'].replace('_', ' '))}"
                    + (f" · {_e(i['at'][:(10 if i.get('precision') == 'day' else 16)].replace('T', ' '))}" if i.get("at") else " · no date on record") + "</span></li>"
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
    body = f"""<p class="says">{_e(result['says'])}</p>
      {corro_html}
      <h2>The items ({c['items']:,})</h2><ul>{items}</ul>
      <h2>Analyses run</h2><table><tr><th>Analysis</th><th>Pairs covered</th><th>Links found</th><th>Note</th></tr>{analyses}</table>
      {'<h3>Out of reach</h3><ul>' + reach + '</ul>' if reach else ''}
      <h2>Candidate links ({c['candidates']:,})</h2><p class="muted">Strongest first. Weak links are listed as weak.</p>{clipped}<ul>{cands}</ul>
      <h2>Pairs with no link found ({c['no_links']:,})</h2><p class="muted">Each says what was searched. It is not proof that no link exists.</p>{clipped_no}<ul>{nolinks}</ul>
      <h2>How they could be linked</h2>{hyp_html}"""
    counts = (f" · {c['items']:,} items · {c['candidates']:,} candidate links · {c['no_links']:,} pairs with no link found")
    return _page(case_name, generated_by, privilege_marking, label, body, counts)


def _page(case_name: str, generated_by: str, privilege_marking: str, label: str, body: str, counts: str) -> str:
    footer = label if privilege_marking in ("confidential", "privileged_confidential") else "Loupe Corroborate report"
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
      h3 {{ font-size: 12px; margin-top: 12px; }} h4 {{ font-size: 11px; margin: 8px 0 2px; }}
      table.grid td, table.grid th {{ font-size: 9px; padding: 1px 3px; }} tr {{ break-inside: avoid; }}
    </style></head><body>
      <div class="eyebrow">Corroborate report</div>
      <h1>{_e(case_name or 'Case')}</h1>
      <p>Generated by {_e(generated_by)} on {_e(when)}{counts}</p>
      <div class="marking"><strong>{_e(label)}</strong><span>{_e(PRIVILEGE_BASIS)}</span></div>
      {body}
    </body></html>"""


def render_pdf(**kwargs: Any) -> bytes:
    from weasyprint import HTML

    from services.pdf_fetch import deny_all
    return HTML(string=render_html(**kwargs), url_fetcher=deny_all("Reports cannot load external or local resources.")).write_pdf()
