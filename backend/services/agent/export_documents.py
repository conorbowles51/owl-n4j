"""One complete document view for browser, paged PDF and editable Word exports."""
from __future__ import annotations

import base64
import html
import io
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from services.agent.export_visuals import visual_svg, svg_png
from services.pdf_fetch import data_only

ASSETS = Path(__file__).resolve().parents[2] / "assets"
BRAND_RED = "B41624"
VISUAL_TYPES = {"graph", "diagram", "chart", "map"}
TABLE_TYPES = {"table", "matrix", "timeline"}


@lru_cache(maxsize=1)
def _export_glyphs():
    from fontTools.ttLib import TTFont
    characters=set()
    for filename in ('loupe/IBMPlexSans.ttf','loupe/SpaceGrotesk.ttf','loupe/IBMPlexMono.ttf'):
        with TTFont(ASSETS/'fonts'/filename) as font:
            characters.update(font.getBestCmap())
    return characters


def ensure_supported_glyphs(title,payload):
    """Do not silently replace unsupported scripts with missing-glyph boxes."""
    supported=_export_glyphs()
    def strings(value):
        if isinstance(value,str):yield value
        elif isinstance(value,list):
            for item in value:yield from strings(item)
        elif isinstance(value,dict):
            for key,item in value.items():
                yield str(key)
                yield from strings(item)
    missing={ord(c) for value in [str(title),*strings(payload)] for c in value
             if not c.isspace() and unicodedata.category(c) not in {'Cc','Cf'} and ord(c) not in supported}
    if missing:
        codes=', '.join(f'U+{code:04X}' for code in sorted(missing)[:12])
        raise ValueError('The bundled Loupe export fonts lack characters '+codes+'. Install an approved font for the requested script before completing this export; no partial document was returned.')


def safe_href(value):
    value = str(value or "").strip()
    return value if urlsplit(value).scheme.lower() in {"http", "https", "mailto", "doc", "txn", "rec", "artifact"} or value.startswith("#") else ""


def sections(payload):
    """Preserve depth and order, including nested sections from incremental authoring."""
    def visit(items, depth=2):
        for item in items or []:
            if not isinstance(item, dict):
                continue
            yield {**item, "level": item.get("level", depth)}
            yield from visit(item.get("sections") or item.get("children"), min(depth+1, 6))
    return list(visit(payload.get("sections")))


def metadata(payload):
    return payload.get("document_metadata") or payload.get("metadata") or {}


def document_layout(payload):
    """Independent composition choices; a brief never needs a separate cover or contents."""
    layout = payload.get('document_layout') or {}
    if not isinstance(layout, dict):
        raise ValueError('Document layout must be an object.')
    long = len(sections(payload)) > 3
    result = {'cover': layout.get('cover', 'page' if long else 'inline'),
              'contents': layout.get('contents', long), 'density': layout.get('density', 'comfortable'),
              'page_size': layout.get('page_size', 'A4'), 'orientation': layout.get('orientation', 'portrait')}
    for key, options in {'cover': {'inline', 'page'}, 'density': {'compact', 'comfortable'},
                         'page_size': {'A4', 'Letter'}, 'orientation': {'portrait', 'landscape'}}.items():
        if result[key] not in options:
            raise ValueError(f'Unsupported document {key}; choose one of {", ".join(sorted(options))}.')
    if not isinstance(result['contents'], bool):
        raise ValueError('Document contents must be true or false.')
    return result


@lru_cache(maxsize=1)
def font_css():
    definitions=[]
    for family, filename, weight in [("Loupe Body", "loupe/IBMPlexSans.ttf", "100 900"),
                                     ("Loupe Heading", "loupe/SpaceGrotesk.ttf", "300 700"),
                                     ("Loupe Mono", "loupe/IBMPlexMono.ttf", "400"),
                                     ("Loupe Unicode", "NotoSans-Regular.ttf", "400")]:
        data=base64.b64encode((ASSETS/"fonts"/filename).read_bytes()).decode()
        definitions.append(f"@font-face{{font-family:'{family}';font-weight:{weight};src:url(data:font/ttf;base64,{data})}}")
    return "".join(definitions)


@lru_cache(maxsize=1)
def brand_logo():
    return (ASSETS/'brand'/'loupe-lockup.svg').read_text(encoding='utf-8')


def markdown_html(content):
    from markdown_it import MarkdownIt
    parser=MarkdownIt("commonmark", {"html": False, "linkify": False, "breaks": True}).enable("table")
    parser.validateLink=lambda value: bool(safe_href(value))
    tokens=parser.parse(str(content or ""))
    if any(child.type=='image' for token in tokens for child in token.children or []):
        raise ValueError('Markdown image resources cannot be fetched by the offline exporter. Supply the visual as an embedded chart, map, diagram or an isolated HTML artifact; no incomplete export was returned.')
    return parser.renderer.render(tokens,parser.options,{})


def _dict_rows(value):
    return [r for r in value or [] if isinstance(r,dict)]


def _data_table(kind, data):
    from services.agent.exports import _rows_for_artifact, _columns_for_artifact
    rows=_rows_for_artifact(kind,data)
    return _columns_for_artifact(kind,data,rows),rows


def column_bands(columns, width=6):
    if len(columns)<=width:
        return [columns]
    # Repeat the identifying first column to keep horizontal continuations readable.
    return [[columns[0],*columns[i:i+width-1]] for i in range(1,len(columns),width-1)]


def table_html(columns,rows,labels=None):
    from services.agent.exports import _cell_value,_flatten_dict
    labels=labels or {}
    parts=[]
    if not columns:
        return '<p class="source-note">No table columns.</p>'
    bands=column_bands(columns)
    for band_index,band in enumerate(bands):
        if len(bands)>1:
            parts.append(f'<p class="source-note">Column group {band_index+1} of {len(bands)}. The first column repeats for reference. All {len(rows):,} records are included.</p>')
        parts.append('<table><thead><tr>'+''.join(f'<th>{html.escape(str(labels.get(c,c)))}</th>' for c in band)+'</tr></thead><tbody>')
        for row in rows:
            flat=_flatten_dict(row)
            texts=[_cell_value(flat.get(c)) for c in band]
            # A single very long cell must not create an indivisible row taller than a page.
            chunks=[re.findall(r'[\s\S]{1,650}',text) or [""] for text in texts]
            for n in range(max(map(len,chunks))):
                cells=[c[n] if n<len(c) else "" for c in chunks]
                if n and not cells[0]:
                    cells[0]=texts[0]+' (continued)'
                parts.append('<tr>'+''.join('<td>'+html.escape(value).replace('\n','<br>')+'</td>' for value in cells)+'</tr>')
        parts.append('</tbody></table>')
    return ''.join(parts)


def embed_html(embed):
    kind=str(embed.get("type") or "table")
    data=embed.get("data") or {}
    if not embed.get("available",True):
        raise ValueError(f"Required exhibit is unavailable: {embed.get('title','Untitled')}")
    title=str(embed.get("title") or "Exhibit")
    caption=str(embed.get("caption") or "")
    parts=[f'<div class="exhibit"><h4>{html.escape(title)}</h4>']
    if kind in VISUAL_TYPES:
        parts.append('<figure>'+visual_svg(kind,data,title))
        if caption:
            parts.append('<figcaption>'+html.escape(caption)+'</figcaption>')
        parts.append('</figure>')
        # Full records make a dense figure auditable without replacing the actual visual.
        columns,rows=_data_table(kind,data)
        if rows:
            parts.append('<details open><summary>Source data</summary>'+table_html(columns,rows)+'</details>')
    elif kind in TABLE_TYPES:
        if caption:
            parts.append('<p class="source-note">'+html.escape(caption)+'</p>')
        columns,rows=_data_table(kind,data)
        labels={c["key"]:c.get("label",c["key"]) for c in data.get("columns",[]) if isinstance(c,dict) and "key" in c}
        parts.append(table_html(columns,rows,labels))
    elif kind=="interactive":
        from services.agent.export_office import scenario_values
        from services.agent.deliverables import static_content_text
        parts.append('<p class="source-note">Static view. Interactive controls are available in the HTML artifact.</p>')
        parts.append(markdown_html(static_content_text(data.get("static_content"))))
        results=scenario_values(data)
        inputs=(data.get('interactions') or {}).get('inputs',[])
        if inputs:parts.append('<h5>Saved assumptions</h5>'+table_html(['label','value'],[{'label':i.get('label') or i.get('key'),'value':i.get('value',0)} for i in inputs]))
        if results:parts.append('<h5>Scenario results</h5>'+table_html(['label','value','expression'],results))
        columns,rows=_data_table(kind,data)
        if rows:
            parts.append(table_html(columns,rows))
        if not data.get("static_content") and not rows and not results:
            raise ValueError("This interactive artifact needs static_content or source rows for a static export")
    elif kind=="workbook":
        for sheet in data.get("sheets",[]):
            parts.append('<h5>'+html.escape(str(sheet.get("name") or "Sheet"))+'</h5>')
            columns,rows=_data_table("table",sheet)
            parts.append(table_html(columns,rows))
            if sheet.get("formulas"):
                parts.append('<h5>Workbook formulas</h5>'+table_html(["cell","formula"],sheet["formulas"]))
    else:
        raise ValueError(f"No document renderer is registered for {kind}")
    if data.get("notes"):
        parts.append('<p class="source-note">'+html.escape(str(data['notes']))+'</p>')
    parts.append('</div>')
    return ''.join(parts)


def document_html(title,payload,portable=True):
    ensure_supported_glyphs(title,payload)
    title=str(payload.get("title") or title or "Loupe report")
    meta=metadata(payload)
    case=str(meta.get("case_label") or "")
    classification=str(meta.get("classification") or "")
    version=str(meta.get("version") or "")
    document_sections=sections(payload)
    layout=document_layout(payload)
    css=font_css()+"""
    @page{size:A4;margin:18mm 15mm 19mm;@top-left{content:string(case-label);font:8pt 'Loupe Mono';color:#71747c}
      @bottom-left{content:string(classification);font:8pt 'Loupe Body';color:#71747c}
      @bottom-right{content:'Loupe · ' counter(page) ' / ' counter(pages);font:8pt 'Loupe Mono';color:#71747c}}
    *{box-sizing:border-box}body{font:11pt/1.45 'Loupe Body','Loupe Unicode',sans-serif;color:#202126;margin:0;background:white}
    .case-label{string-set:case-label content()}.classification{string-set:classification content()}
    h1,h2,h3,h4,h5,h6{font-family:'Loupe Heading','Loupe Unicode',sans-serif;line-height:1.16;break-after:avoid;font-weight:600}
    h1{font-size:32pt;letter-spacing:-1pt;margin:18mm 0 8mm}h2{font-size:21pt;margin:12mm 0 4mm}h3{font-size:16pt;margin:8mm 0 3mm}
    h4,h5,h6{font-size:12pt;margin:6mm 0 3mm}p{margin:0 0 3mm;orphans:3;widows:3}a{color:#b41624;text-decoration:underline;overflow-wrap:anywhere}
    .brand{width:38mm;margin:0 0 8mm}.brand svg{display:block;width:100%;height:auto}
    .cover{margin-bottom:12mm}.cover.long{break-after:page;padding-top:12mm;min-height:210mm}
    .eyebrow,.source-note,figcaption{font:9pt/1.4 'Loupe Body';color:#62656e}.eyebrow{font-family:'Loupe Mono';letter-spacing:.8pt;text-transform:uppercase;color:#b41624}
    .purpose{font-size:14pt;max-width:155mm}.metadata{margin-top:16mm;padding-top:5mm;border-top:1pt solid #b41624}
    .toc{break-after:page}.toc a{text-decoration:none;color:#202126}.toc li{margin:3mm 0}.toc a::after{content:leader('.') target-counter(attr(href),page)}
    .section{margin-bottom:5mm}.section.chapter{break-before:page}.exhibit{margin:5mm 0 8mm}figure{margin:0;break-inside:avoid}svg{max-width:100%;height:auto}
    figcaption{margin:3mm 0}table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:8.5pt;margin:3mm 0 6mm}
    th{background:#f1f2f5;color:#202126;font-weight:600;border-bottom:1pt solid #b41624;text-align:left}
    th,td{padding:2mm 2.2mm;vertical-align:top;overflow-wrap:anywhere}td{border-bottom:.4pt solid #dfe1e6}td p{margin:0}thead{display:table-header-group}
    tr{break-inside:avoid}tbody tr:nth-child(even){background:#fafafb}blockquote{border-left:2pt solid #b41624;margin:4mm 0;padding-left:4mm}
    pre{white-space:pre-wrap;overflow-wrap:anywhere;font:9pt 'Loupe Mono'}code{font-family:'Loupe Mono';font-size:.85em}
    .sources li{margin-bottom:3mm;overflow-wrap:anywhere}.source-note{break-after:avoid}summary{font:9pt 'Loupe Mono';color:#71747c;margin:2mm 0}
    @media screen{body{max-width:900px;padding:36px;margin:auto}.cover.long{min-height:0}.toc a::after{content:none}table{font-size:13px} .section.chapter{border-top:1px solid #dfe1e6;margin-top:40px}}
    @media(max-width:600px){body{padding:18px}h1{font-size:30px}table{font-size:11px}th,td{padding:5px}}
    """
    css += f"@page{{size:{layout['page_size']} {layout['orientation']}}}"
    if layout['density']=='compact':
        css += "body{font-size:10.5pt;line-height:1.35}h1{font-size:25pt;margin:5mm 0}h2{font-size:15pt;margin:5mm 0 2mm}h3{font-size:12pt;margin:4mm 0 2mm}.brand{width:28mm;margin-bottom:4mm}.cover{margin-bottom:5mm}.purpose{font-size:11pt}.metadata{margin-top:4mm;padding-top:3mm}.section{margin-bottom:3mm}"
    csp="default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'; frame-src 'none'"
    parts=['<!doctype html><html lang="'+html.escape(str(payload.get('language') or 'en'),quote=True)+'"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<meta http-equiv="Content-Security-Policy" content="'+html.escape(csp,quote=True)+'">',
           '<title>'+html.escape(title)+'</title><style>'+css+'</style></head><body>',
           '<header class="cover'+(' long' if layout['cover']=='page' else '')+'"><div class="brand">'+brand_logo()+'</div>',
           '<p class="eyebrow case-label">'+html.escape(case or 'Investigation report')+'</p><h1>'+html.escape(title)+'</h1>']
    if payload.get('purpose'):
        parts.append('<p class="purpose">'+html.escape(str(payload['purpose']))+'</p>')
    if case or classification or version or payload.get('audience'):
        parts.append('<div class="metadata">')
        if classification:parts.append('<p class="classification">'+html.escape(classification)+'</p>')
        if version:parts.append('<p>Version '+html.escape(version)+'</p>')
        if payload.get('audience'):parts.append('<p>Prepared for '+html.escape(str(payload['audience']))+'</p>')
        parts.append('</div>')
    parts.append('</header>')
    if layout['contents']:
        parts.append('<nav class="toc" aria-label="Contents"><h2>Contents</h2><ol>')
        parts.extend(f'<li><a href="#section-{i}">{html.escape(str(s.get("heading") or "Section"))}</a></li>' for i,s in enumerate(document_sections))
        parts.append('</ol></nav>')
    if payload.get('scope'):
        parts.append('<h2>Scope</h2>'+markdown_html(payload['scope']))
    if payload.get('included_items'):
        parts.append('<h3>Coverage</h3><ul>'+''.join('<li>'+html.escape(str(x))+'</li>' for x in payload['included_items'])+'</ul>')
    for i,s in enumerate(document_sections):
        level=max(2,min(int(s.get('level') or 2),6))
        cls='section chapter' if s.get('page_break_before') else 'section'
        parts.append(f'<section class="{cls}" id="section-{i}"><h{level}>'+html.escape(str(s.get('heading') or 'Section'))+f'</h{level}>')
        parts.append(markdown_html(s.get('content')))
        parts.extend(embed_html(e) for e in _dict_rows(s.get('embeds')))
        parts.append('</section>')
    if payload.get('open_questions'):
        parts.append('<h2>Open questions</h2><ul>'+''.join('<li>'+html.escape(str(x))+'</li>' for x in payload['open_questions'])+'</ul>')
    if payload.get('sources'):
        parts.append('<h2>Sources</h2><ol class="sources">')
        for s in payload['sources']:
            if not isinstance(s,dict):s={'label':str(s)}
            label=html.escape(str(s.get('label') or s.get('title') or s.get('url') or 'Source'))
            url=safe_href(s.get('url'))
            parts.append('<li>'+('<a href="'+html.escape(url,quote=True)+'">'+label+'</a>' if url else label)+(' — '+html.escape(str(s['locator'])) if s.get('locator') else '')+'</li>')
        parts.append('</ol>')
    return ''.join(parts)+'</body></html>'


@lru_cache(maxsize=1)
def offline_fetcher():
    """WeasyPrint must never fetch case-controlled network URLs or local files: embedded data resources only."""
    return data_only('Only embedded data resources may be rendered')


def document_pdf(title,payload):
    from weasyprint import HTML
    return HTML(string=document_html(title,payload),url_fetcher=offline_fetcher()).write_pdf()


def _word_inline(paragraph,content):
    """Editable runs and actual hyperlink relationships, never raw Markdown tokens."""
    from markdown_it import MarkdownIt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE
    parser=MarkdownIt('commonmark',{'html':False})
    parser.validateLink=lambda v:bool(safe_href(v))
    tokens=parser.parseInline(str(content or ''))[0].children or []
    bold=italic=False
    link=None
    for token in tokens:
        if token.type=='image':raise ValueError('Markdown image resources cannot be fetched by the offline Word exporter; use an embedded visual artifact.')
        if token.type=='strong_open':bold=True
        elif token.type=='strong_close':bold=False
        elif token.type=='em_open':italic=True
        elif token.type=='em_close':italic=False
        elif token.type=='link_open':link=safe_href(token.attrGet('href'))
        elif token.type=='link_close':link=None
        elif token.type in ('softbreak','hardbreak'):paragraph.add_run().add_break()
        elif token.type in ('text','code_inline','image','html_inline'):
            text=token.content
            if link:
                rel=paragraph.part.relate_to(link,RELATIONSHIP_TYPE.HYPERLINK,is_external=True)
                h=OxmlElement('w:hyperlink');h.set(qn('r:id'),rel)
                r=OxmlElement('w:r');props=OxmlElement('w:rPr');color=OxmlElement('w:color');color.set(qn('w:val'),BRAND_RED);props.append(color)
                r.append(props);t=OxmlElement('w:t');t.text=text;r.append(t);h.append(r);paragraph._p.append(h)
            else:
                r=paragraph.add_run(text);r.bold=bold;r.italic=italic
                if token.type=='code_inline':r.font.name='IBM Plex Mono'


def word_markdown(document,content):
    from markdown_it import MarkdownIt
    parser=MarkdownIt('commonmark',{'html':False}).enable('table')
    tokens=parser.parse(str(content or ''))
    list_depth=0;ordered=False;heading=None;in_table=False;table_rows=[];row=[];current_cell=None
    for token in tokens:
        if token.type=='table_open':in_table=True;table_rows=[]
        elif token.type=='tr_open':row=[]
        elif token.type in ('th_open','td_open'):current_cell=''
        elif token.type=='inline' and in_table:current_cell=token.content
        elif token.type in ('th_close','td_close'):row.append(current_cell or '')
        elif token.type=='tr_close':table_rows.append(row)
        elif token.type=='table_close':
            in_table=False
            if table_rows:word_table(document,table_rows[0],[dict(zip(table_rows[0],r)) for r in table_rows[1:]])
        elif token.type in ('bullet_list_open','ordered_list_open'):list_depth+=1;ordered=token.type=='ordered_list_open'
        elif token.type in ('bullet_list_close','ordered_list_close'):list_depth-=1
        elif token.type=='heading_open':heading=min(int(token.tag[1:]),6)
        elif token.type=='heading_close':heading=None
        elif token.type=='inline' and not in_table:
            p=document.add_paragraph(style=f'Heading {heading}' if heading else ('List Number' if ordered else 'List Bullet') if list_depth else None)
            _word_inline(p,token.content)
        elif token.type in ('fence','code_block'):
            p=document.add_paragraph();r=p.add_run(token.content);r.font.name='IBM Plex Mono'


def word_table(document,columns,rows,labels=None):
    from docx.shared import Pt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from services.agent.exports import _cell_value,_flatten_dict
    labels=labels or {}
    for band_index,band in enumerate(column_bands(columns)):
        if not band:continue
        if len(columns)>6:document.add_paragraph(f'Column group {band_index+1}; first column repeats for reference.',style='Caption')
        table=document.add_table(rows=1,cols=len(band));table.style='Table Grid'
        head=table.rows[0]
        repeat=OxmlElement('w:tblHeader');head._tr.get_or_add_trPr().append(repeat)
        for i,key in enumerate(band):
            head.cells[i].text=str(labels.get(key,key))
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'F1F2F5');head.cells[i]._tc.get_or_add_tcPr().append(shade)
            for r in head.cells[i].paragraphs[0].runs:r.bold=True;r.font.size=Pt(9)
        for row in rows:
            flat=_flatten_dict(row);cells=table.add_row().cells
            for i,key in enumerate(band):
                cells[i].paragraphs[0].add_run(_cell_value(flat.get(key)))
                for p in cells[i].paragraphs:
                    p.paragraph_format.space_after=Pt(3)
                    for r in p.runs:r.font.size=Pt(9)
        document.add_paragraph()


def word_embed(document,embed):
    from docx.shared import Inches
    kind=str(embed.get('type') or 'table');data=embed.get('data') or {};title=str(embed.get('title') or 'Exhibit')
    if not embed.get('available',True):raise ValueError(f'Required exhibit is unavailable: {title}')
    document.add_paragraph(f'Embedded {kind}: {title}',style='Heading 4')
    if kind in VISUAL_TYPES:
        document.add_picture(io.BytesIO(svg_png(visual_svg(kind,data,title))),width=Inches(6.5))
        if embed.get('caption'):document.add_paragraph(str(embed['caption']),style='Caption')
        if kind=='chart':document.add_paragraph(f"Chart type: {data.get('chart_type','bar')}; {len(data.get('rows') or [])} source row(s)",style='Caption')
        columns,rows=_data_table(kind,data)
        if rows:word_table(document,columns,rows)
    elif kind in TABLE_TYPES:
        if embed.get('caption'):document.add_paragraph(str(embed['caption']),style='Caption')
        columns,rows=_data_table(kind,data)
        word_table(document,columns,rows,{c['key']:c.get('label',c['key']) for c in data.get('columns',[]) if isinstance(c,dict) and 'key' in c})
    elif kind=='workbook':
        for sheet in data.get('sheets',[]):
            document.add_heading(str(sheet.get('name') or 'Sheet'),level=4)
            columns,rows=_data_table('table',sheet);word_table(document,columns,rows)
            if sheet.get('formulas'):word_table(document,['cell','formula'],sheet['formulas'])
    elif kind=='interactive':
        from services.agent.export_office import scenario_values
        from services.agent.deliverables import static_content_text
        document.add_paragraph('Static view. Interactive controls are available in the HTML artifact.',style='Caption')
        word_markdown(document,static_content_text(data.get('static_content')))
        results=scenario_values(data);inputs=(data.get('interactions') or {}).get('inputs',[])
        if inputs:word_table(document,['label','value'],[{'label':i.get('label') or i.get('key'),'value':i.get('value',0)} for i in inputs])
        if results:word_table(document,['label','value','expression'],results)
        columns,rows=_data_table(kind,data)
        if rows:word_table(document,columns,rows)
        if not data.get('static_content') and not rows and not results:raise ValueError('Interactive artifact has no static content')
    else:raise ValueError(f'No Word renderer is registered for {kind}')
    if data.get('notes'):document.add_paragraph(str(data['notes']),style='Caption')


def document_docx(title,payload):
    ensure_supported_glyphs(title,payload)
    from docx import Document
    from docx.shared import Mm,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    layout=document_layout(payload)
    doc=Document();sec=doc.sections[0]
    width,height=(210,297) if layout['page_size']=='A4' else (215.9,279.4)
    if layout['orientation']=='landscape':width,height=height,width
    sec.page_width=Mm(width);sec.page_height=Mm(height)
    sec.top_margin=Mm(18);sec.bottom_margin=Mm(19);sec.left_margin=sec.right_margin=Mm(15)
    normal=doc.styles['Normal'];normal.font.name='IBM Plex Sans';normal.font.size=Pt(11)
    normal.paragraph_format.line_spacing=1.36;normal.paragraph_format.space_after=Pt(6)
    compact=layout['density']=='compact'
    if compact:
        normal.font.size=Pt(10.5);normal.paragraph_format.line_spacing=1.25;normal.paragraph_format.space_after=Pt(4)
    for name,size in [('Title',32),('Heading 1',24),('Heading 2',20),('Heading 3',16),('Heading 4',12),('Heading 5',11),('Heading 6',11)]:
        style=doc.styles[name];style.font.name='Space Grotesk';style.font.size=Pt(size);style.font.color.rgb=RGBColor.from_string('202126');style.paragraph_format.keep_with_next=True
        style.font.italic=False;style.font.underline=False
        if compact:
            style.font.size=Pt(min(size,24 if name=='Title' else 15 if name in ('Heading 1','Heading 2') else 12))
            style.paragraph_format.space_before=Pt(8);style.paragraph_format.space_after=Pt(4)
        for node in list(style.element.iter(qn('w:pBdr'))):node.getparent().remove(node)
        for fonts in style.element.iter(qn('w:rFonts')):
            for attribute in list(fonts.attrib):
                if 'theme' in attribute.lower():del fonts.attrib[attribute]
    doc.styles['Caption'].font.name='IBM Plex Sans';doc.styles['Caption'].font.size=Pt(9);doc.styles['Caption'].font.color.rgb=RGBColor.from_string('62656E')
    meta=metadata(payload)
    header=sec.header.paragraphs[0];header.add_run().add_picture(io.BytesIO(svg_png(brand_logo(),1)),width=Mm(27))
    if meta.get('case_label'):header.add_run('   '+str(meta['case_label'])).font.size=Pt(9)
    footer=sec.footer.paragraphs[0];footer.add_run(str(meta.get('classification') or '')+'   ')
    footer.add_run('Page ')
    for field in ('PAGE','NUMPAGES'):
        if field=='NUMPAGES':footer.add_run(' / ')
        node=OxmlElement('w:fldSimple');node.set(qn('w:instr'),field);footer._p.append(node)
    doc.add_heading(str(payload.get('title') or title or 'Loupe report'),level=0)
    if payload.get('purpose'):word_markdown(doc,payload['purpose'])
    if payload.get('audience'):doc.add_paragraph('Prepared for '+str(payload['audience']))
    if meta.get('version'):doc.add_paragraph('Version '+str(meta['version']))
    ss=sections(payload)
    if layout['cover']=='page':doc.add_page_break()
    if layout['contents']:
        doc.add_heading('Contents',level=1)
        toc=OxmlElement('w:fldSimple');toc.set(qn('w:instr'),'TOC \\o "1-6" \\h \\z \\u')
        # Cached readable contents also work in viewers that do not refresh Word fields.
        for s in ss:
            r=OxmlElement('w:r');t=OxmlElement('w:t');t.text=str(s.get('heading') or 'Section');r.append(t);r.append(OxmlElement('w:br'));toc.append(r)
        doc.add_paragraph()._p.append(toc);doc.add_page_break()
    if payload.get('scope'):doc.add_heading('Scope',level=1);word_markdown(doc,payload['scope'])
    if payload.get('included_items'):
        doc.add_heading('Coverage',level=2)
        for item in payload['included_items']:doc.add_paragraph(str(item),style='List Bullet')
    for s in ss:
        if s.get('page_break_before'):doc.add_page_break()
        doc.add_heading(str(s.get('heading') or 'Section'),level=max(1,min(int(s.get('level') or 2),6)))
        word_markdown(doc,s.get('content'))
        for e in _dict_rows(s.get('embeds')):word_embed(doc,e)
    if payload.get('open_questions'):
        doc.add_heading('Open questions',level=1)
        for item in payload['open_questions']:doc.add_paragraph(str(item),style='List Bullet')
    if payload.get('sources'):
        doc.add_heading('Sources',level=1)
        for source in payload['sources']:
            if not isinstance(source,dict):source={'label':str(source)}
            label=str(source.get('label') or source.get('title') or source.get('url') or 'Source')
            url=safe_href(source.get('url'))
            _word_inline(doc.add_paragraph(style='List Number'),f'[{label}]({url})' if url else label)
            if source.get('locator'):doc.add_paragraph(str(source['locator']),style='Caption')
    settings=doc.settings.element;update=OxmlElement('w:updateFields');update.set(qn('w:val'),'true');settings.append(update)
    buffer=io.BytesIO();doc.save(buffer);return _embed_word_fonts(buffer.getvalue())


def _embed_word_fonts(content):
    """Embed OFL fonts so recipient machines need no font download or installation."""
    import zipfile,uuid
    from lxml import etree
    W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    PR='http://schemas.openxmlformats.org/package/2006/relationships'
    CT='http://schemas.openxmlformats.org/package/2006/content-types'
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        entries={n:source.read(n) for n in source.namelist()}
    fonts=etree.fromstring(entries['word/fontTable.xml'])
    rels=etree.Element('{'+PR+'}Relationships',nsmap={None:PR})
    types=etree.fromstring(entries['[Content_Types].xml'])
    etree.SubElement(types,'{'+CT+'}Default',Extension='odttf',ContentType='application/vnd.openxmlformats-officedocument.obfuscatedFont')
    for index,(family,filename) in enumerate([('IBM Plex Sans','IBMPlexSans.ttf'),('Space Grotesk','SpaceGrotesk.ttf'),('IBM Plex Mono','IBMPlexMono.ttf')]):
        key=uuid.uuid5(uuid.NAMESPACE_URL,'loupe-font:'+filename);mask=key.bytes[::-1]
        data=bytearray((ASSETS/'fonts'/'loupe'/filename).read_bytes())
        for n in range(min(32,len(data))):data[n]^=mask[n%16]
        dest=f'fonts/loupe-{index}.odttf';entries['word/'+dest]=bytes(data)
        font=next((f for f in fonts if f.get('{'+W+'}name')==family),None)
        if font is None:font=etree.SubElement(fonts,'{'+W+'}font',{'{'+W+'}name':family})
        etree.SubElement(font,'{'+W+'}embedRegular',{'{'+R+'}id':f'rIdLoupe{index}','{'+W+'}fontKey':'{'+str(key).upper()+'}'})
        etree.SubElement(rels,'{'+PR+'}Relationship',Id=f'rIdLoupe{index}',Type=R+'/font',Target=dest)
    entries['word/fontTable.xml']=etree.tostring(fonts,xml_declaration=True,encoding='UTF-8',standalone=True)
    entries['word/_rels/fontTable.xml.rels']=etree.tostring(rels,xml_declaration=True,encoding='UTF-8',standalone=True)
    entries['[Content_Types].xml']=etree.tostring(types,xml_declaration=True,encoding='UTF-8',standalone=True)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in entries.items():archive.writestr(name,data)
    return out.getvalue()
