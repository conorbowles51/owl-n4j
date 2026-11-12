"""Complete editable Office exports and a network-isolated portable interactive wrapper."""
from __future__ import annotations

import html
import io
import math
import re
import ast
import json


def workbook_bytes(kind,title,payload):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    from services.agent.exports import _rows_for_artifact,_columns_for_artifact,_flatten_dict,_cell_value
    wb=Workbook();wb.remove(wb.active)
    specs=payload.get('sheets') if kind=='workbook' else [{**payload,'name':title}]
    if not specs:raise ValueError('A workbook requires at least one sheet')
    used=set()
    for si,spec in enumerate(specs):
        name=re.sub(r'[\\/*?:\[\]]',' ',str(spec.get('name') or f'Sheet {si+1}'))[:31].strip() or f'Sheet {si+1}'
        base=name;index=2
        while name.casefold() in used:
            suffix=f' ({index})';name=base[:31-len(suffix)]+suffix;index+=1
        used.add(name.casefold());ws=wb.create_sheet(name)
        rows=_rows_for_artifact('table' if kind=='workbook' else kind,spec)
        columns=_columns_for_artifact('table' if kind=='workbook' else kind,spec,rows)
        if len(rows)>1048575 or len(columns)>16384:
            raise ValueError('The dataset exceeds one Excel worksheet; divide it into named sheets before exporting')
        labels={c['key']:c.get('label') or c['key'] for c in spec.get('columns',[]) if isinstance(c,dict) and 'key' in c}
        for ci,key in enumerate(columns,1):
            c=ws.cell(1,ci,str(labels.get(key,key)));c.font=Font(name='IBM Plex Sans',bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='B41624');c.alignment=Alignment(wrap_text=True,vertical='top')
            ws.column_dimensions[get_column_letter(ci)].width=min(48,max(16,len(str(labels.get(key,key)))+4))
        for ri,row in enumerate(rows,2):
            flat=_flatten_dict(row)
            for ci,key in enumerate(columns,1):
                value=flat.get(key)
                if not isinstance(value,(str,int,float,bool,type(None))):value=_cell_value(value)
                if isinstance(value,str) and len(value)>32767:
                    raise ValueError(f'Cell {get_column_letter(ci)}{ri} exceeds Excel\'s 32,767-character limit; use the complete HTML or Word export')
                if isinstance(value,float) and not math.isfinite(value):raise ValueError('Workbook values must be finite')
                c=ws.cell(ri,ci,value)
                if isinstance(value,str):c.data_type='s'  # Source text is never implicitly executable Excel code.
                c.font=Font(name='IBM Plex Sans',size=11);c.alignment=Alignment(wrap_text=True,vertical='top')
                if ri%2==0:c.fill=PatternFill('solid',fgColor='F5F6F8')
        for item in spec.get('formulas',[]):
            address=str(item.get('cell','')).upper();formula=str(item.get('formula',''))
            if not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}',address) or not formula.startswith('='):
                raise ValueError('Workbook formulas require a valid cell address and an explicit = formula')
            if re.search(r'\[|\]|\||https?://|(?:WEBSERVICE|HYPERLINK|DDE|RTD|IMPORTXML|IMPORTDATA)\s*\(',formula,re.I):
                raise ValueError('External links and network functions are not allowed in generated workbook formulas')
            ws[address]=formula
            ws[address].font=Font(name='IBM Plex Sans',color='B41624')
        ws.freeze_panes='A2';ws.sheet_view.showGridLines=False;ws.print_title_rows='1:1'
        if rows and columns:
            ws.auto_filter.ref=f'A1:{get_column_letter(len(columns))}{len(rows)+1}'
        ws.sheet_properties.pageSetUpPr.fitToPage=True
        ws.page_setup.orientation='landscape' if len(columns)>5 else 'portrait';ws.page_setup.paperSize=ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
        ws.oddFooter.center.text='Loupe · Page &P of &N'
    wb.calculation.fullCalcOnLoad=True;wb.calculation.forceFullCalc=True
    stream=io.BytesIO();wb.save(stream);return stream.getvalue()


def _plain(value):
    from markdown_it import MarkdownIt
    parts=[]
    for token in MarkdownIt('commonmark',{'html':False}).parse(str(value or '')):
        if any(child.type=='image' for child in token.children or []):raise ValueError('Markdown image resources cannot be fetched by the offline presentation exporter; use an embedded visual artifact.')
        if token.type=='inline':parts.append(''.join(t.content if t.type not in ('softbreak','hardbreak') else '\n' for t in token.children or [] if t.type in ('text','code_inline','softbreak','hardbreak')))
        elif token.type in ('fence','code_block'):parts.append(token.content)
    return '\n\n'.join(parts)


def presentation_bytes(kind,title,payload):
    from pptx import Presentation
    from pptx.util import Inches,Pt
    from pptx.dml.color import RGBColor
    from services.agent.export_documents import sections,column_bands,brand_logo
    from services.agent.export_visuals import visual_svg,svg_png
    from services.agent.exports import _rows_for_artifact,_columns_for_artifact,_flatten_dict,_cell_value
    from services.agent.export_slides import wrap_text
    from services.agent.export_documents import ensure_supported_glyphs
    ensure_supported_glyphs(title,payload)
    prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5)
    prs.core_properties.title=str(title)
    slides=list(payload.get('slides') or []) if kind=='presentation' else [{'title':s.get('heading'),'content':s.get('content'),'embeds':s.get('embeds')} for s in sections(payload)]
    if payload.get('sources'):
        source_lines=[]
        for source in payload['sources']:
            if not isinstance(source,dict):source={'label':str(source)}
            source_lines.append('\n'.join(str(source[k]) for k in ('label','title','url','locator') if source.get(k)))
        slides.append({'title':'Sources','content':'\n\n'.join(source_lines)})
    if not slides:raise ValueError('A presentation needs at least one slide or report section')

    def text(slide,x,y,w,h,value,size=20,color='202126',bold=False):
        frame=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)).text_frame
        frame.word_wrap=False;frame.margin_left=frame.margin_right=frame.margin_top=frame.margin_bottom=0
        for i,line in enumerate(str(value).split('\n')):
            p=frame.paragraphs[0] if i==0 else frame.add_paragraph();p.text=line;p.font.name='IBM Plex Sans';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=RGBColor.from_string(color);p.line_spacing=1.2
        return frame

    def new_slide(heading):
        slide=prs.slides.add_slide(prs.slide_layouts[6]);slide.background.fill.solid();slide.background.fill.fore_color.rgb=RGBColor.from_string('F7F7F8')
        slide.shapes.add_picture(io.BytesIO(svg_png(brand_logo(),1)),Inches(.55),Inches(.22),width=Inches(1.15))
        # Fit the complete permitted title instead of clipping a long requested title.
        for size in (28,24,22,20,18,16,14):
            lines=wrap_text(heading,12.15*72,size)
            if len(lines)*size*1.2<=1.05*72:break
        if len(lines)*size*1.2>1.05*72:raise ValueError('This slide title exceeds the readable title area; shorten the title and retain the full text in slide content')
        text(slide,.55,.9,12.15,1.05,'\n'.join(lines),size,'0B0C0F',True)
        line=slide.shapes.add_shape(1,Inches(.55),Inches(6.91),Inches(12.15),Inches(.015));line.fill.solid();line.fill.fore_color.rgb=RGBColor.from_string('D5D7DD');line.line.fill.background()
        text(slide,.55,7.02,10,.2,str(payload.get('document_metadata',{}).get('classification') or 'Loupe presentation'),9,'71747C')
        text(slide,12,7.02,.6,.2,str(len(prs.slides)),9,'71747C')
        return slide

    include_cover = (payload.get('presentation_layout') or {}).get('cover', kind != 'presentation')
    if not isinstance(include_cover, bool):
        raise ValueError('presentation_layout.cover must be true or false.')
    purpose = _plain(payload.get('purpose') or payload.get('description') or '')
    if include_cover:
        cover=new_slide(title)
        purpose_lines=wrap_text(purpose,11.8*72,24)
        if len(purpose_lines)>6:raise ValueError('The presentation purpose is too long for its cover; move the full explanation into content slides')
        text(cover,.65,2.6,11.8,2.8,'\n'.join(purpose_lines),24,'62656E')
    elif purpose:
        slides[0] = {**slides[0], 'content': purpose + '\n\n' + str(slides[0].get('content') or '')}

    def source_table(heading,embed_kind,data):
        rows=_rows_for_artifact(embed_kind,data);cols=_columns_for_artifact(embed_kind,data,rows)
        for band in column_bands(cols,5):
            header_lines=[wrap_text(c,12.15*72/len(band)-15,12) for c in band]
            header_height=max(30,max(map(len,header_lines))*14.4+12)
            if header_height>4.65*72/2:raise ValueError('Presentation column names are too long; use concise labels and preserve full descriptions in slide notes')
            prepared=[]
            for row in rows:
                flat=_flatten_dict(row)
                cells=[wrap_text(_cell_value(flat.get(c)),12.15*72/len(band)-15,12) for c in band]
                row_height=max(27,max(map(len,cells))*14.4+12)
                if row_height>4.65*72-header_height:raise ValueError('A presentation table cell is taller than a slide; use a report for the complete passage')
                prepared.append((cells,row_height))
            batches=[];batch=[];height=header_height
            for prepared_row in prepared:
                if batch and height+prepared_row[1]>4.65*72:
                    batches.append(batch);batch=[];height=header_height
                batch.append(prepared_row);height+=prepared_row[1]
            if batch:batches.append(batch)
            for start,subset in enumerate(batches):
                page=new_slide(heading+(' — continued' if start else ''))
                table=page.shapes.add_table(len(subset)+1,len(band),Inches(.55),Inches(2.0),Inches(12.15),Pt(header_height+sum(item[1] for item in subset))).table
                table.rows[0].height=Pt(header_height)
                for j,lines in enumerate(header_lines):table.cell(0,j).text='\n'.join(lines)
                for ri,(cells,row_height) in enumerate(subset,1):
                    table.rows[ri].height=Pt(row_height)
                    for ci,lines in enumerate(cells):table.cell(ri,ci).text='\n'.join(lines)
                for ri in range(len(subset)+1):
                    for ci in range(len(band)):
                        cell=table.cell(ri,ci);cell.fill.solid();cell.fill.fore_color.rgb=RGBColor.from_string('B41624' if ri==0 else 'FFFFFF' if ri%2 else 'F1F2F5')
                        cell.text_frame.word_wrap=False
                        for p in cell.text_frame.paragraphs:p.font.size=Pt(12);p.font.name='IBM Plex Sans';p.font.color.rgb=RGBColor.from_string('FFFFFF' if ri==0 else '202126');p.line_spacing=1.2

    for spec in slides:
        heading=str(spec.get('title') or 'Section');content=_plain(spec.get('content') or '')
        wrapped=wrap_text(content,11.95*72,20)
        batches=[wrapped[i:i+12] for i in range(0,len(wrapped),12)] or [[]]
        for index,lines in enumerate(batches):
            slide=new_slide(heading+(' — continued' if index else ''))
            text(slide,.65,2.05,11.95,4.55,'\n'.join(lines),20)
            if spec.get('notes'):slide.notes_slide.notes_text_frame.text=str(spec['notes'])
        for embed in spec.get('embeds') or []:
            if not embed.get('available',True):raise ValueError('A presentation exhibit is unavailable')
            ek=embed.get('type');data=embed.get('data') or {};et=str(embed.get('title') or heading)
            if ek in ('graph','diagram','chart','map'):
                slide=new_slide(et);picture=svg_png(visual_svg(ek,data,et))
                from PIL import Image
                with Image.open(io.BytesIO(picture)) as im:ratio=im.width/im.height
                h=min(4.6,11.8/ratio);w=h*ratio
                slide.shapes.add_picture(io.BytesIO(picture),Inches((13.333-w)/2),Inches(2),width=Inches(w),height=Inches(h))
                slide.notes_slide.notes_text_frame.text=str(embed.get('caption') or '')
            elif ek in ('table','matrix','timeline'):source_table(et,ek,data)
            elif ek=='interactive':
                slide=new_slide(et);text(slide,.65,2.05,11.95,4.55,_plain(data.get('static_content') or 'See the interactive HTML artifact.'),20)
            else:raise ValueError(f'No presentation renderer is registered for {ek}')
    out=io.BytesIO();prs.save(out);return out.getvalue()


def scenario_values(payload):
    """Evaluate only arithmetic over explicitly named inputs, never Python source or attribute access."""
    interactions=payload.get('interactions') or {}
    values={}
    for item in interactions.get('inputs',[]):
        key=str(item.get('key') or '')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key):raise ValueError('Scenario input keys must be simple identifiers')
        value=float(item.get('value') or 0)
        if not math.isfinite(value):raise ValueError('Scenario inputs must be finite')
        values[key]=value
    results=[]
    for calc in interactions.get('calculations',[]):
        tree=ast.parse(str(calc.get('expression') or '0'),mode='eval')
        if sum(1 for _ in ast.walk(tree))>128:raise ValueError('Scenario expression is too complex')
        def evaluate(node):
            if isinstance(node,ast.Expression):return evaluate(node.body)
            if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):return float(node.value)
            if isinstance(node,ast.Name) and node.id in values:return values[node.id]
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):return evaluate(node.operand)*(1 if isinstance(node.op,ast.UAdd) else -1)
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                left,right=evaluate(node.left),evaluate(node.right)
                if isinstance(node.op,ast.Add):return left+right
                if isinstance(node.op,ast.Sub):return left-right
                if isinstance(node.op,ast.Mult):return left*right
                return left/right
            raise ValueError('Scenario expressions support numbers, input names and + - * / parentheses only')
        try:value=evaluate(tree)
        except ZeroDivisionError as exc:raise ValueError('A scenario calculation divides by zero') from exc
        if not math.isfinite(value):raise ValueError('Scenario result must be finite')
        key=str(calc.get('key') or '')
        if key:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key):raise ValueError('Scenario calculation keys must be simple identifiers')
            values[key]=value
        results.append({'label':str(calc.get('label') or calc.get('key') or 'Result'),'value':value,'expression':str(calc.get('expression') or '0')})
    return results


def interactive_html(title,payload):
    from services.agent.export_documents import markdown_html,font_css,brand_logo
    from services.agent.deliverables import interactive_document, static_content_text
    from services.agent.exports import _rows_for_artifact,_columns_for_artifact,_flatten_dict
    source=str(payload.get('html') or '')
    if not source and not payload.get('rows') and not payload.get('interactions'):
        raise ValueError('An interactive artifact needs content, rows or declared controls')
    # Raw model-authored HTML has no script capability. The only active code below is this fixed renderer.
    inner=interactive_document(source)
    interactions=payload.get('interactions') or {}
    results=scenario_values(payload)
    rows=_rows_for_artifact('interactive',payload);columns=_columns_for_artifact('interactive',payload,rows)
    manifest=json.dumps({'interactions':interactions,'columns':columns,'rows':[_flatten_dict(r) for r in rows]},ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    policy="default-src 'none'; script-src 'nonce-loupe-controls'; style-src 'unsafe-inline'; frame-src 'self' data:; img-src data:; font-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    parts=['<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'+html.escape(policy,quote=True)+'"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title>',
        '<style>body{margin:0;font:16px/1.5 sans-serif;background:#f7f7f8;color:#202126}header{padding:20px 28px;border-bottom:2px solid #b41624}h1{font-size:28px}iframe{display:block;border:0;width:100%;height:60vh;min-height:360px;background:white}.content{padding:24px;max-width:1100px;margin:auto}label{display:inline-flex;flex-direction:column;margin:10px 22px 10px 0}input,button{font:inherit;padding:8px;border:1px solid #9a9da5;border-radius:4px}button{background:#f1f2f5;color:#202126;cursor:pointer}output{display:block;font-size:22px;font-weight:bold;margin:10px 0;color:#b41624}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;text-align:left;border-bottom:1px solid #dfe1e6}td{overflow-wrap:anywhere}th{background:#eef0f3}.error{color:#b41624}</style></head><body>',
        '<header><div style="width:130px">'+brand_logo()+'</div><h1>'+html.escape(title)+'</h1><p>Local scenario controls and complete source data. Calculations do not change recorded evidence.</p></header>']
    if source:parts.append('<iframe title="Artifact content" sandbox="" referrerpolicy="no-referrer" srcdoc="'+html.escape(inner,quote=True)+'"></iframe>')
    parts.append('<main class="content">'+markdown_html(static_content_text(payload.get('static_content'))))
    if interactions:
        parts.append('<section aria-label="Scenario inputs"><h2>Scenario</h2><div id="controls"></div><div id="results" aria-live="polite"></div>')
        for item in results:parts.append('<noscript><p>'+html.escape(item['label'])+': '+str(item['value'])+'</p></noscript>')
        parts.append('</section>')
    if rows:parts.append('<section><h2>Source records</h2><label>Find records <input id="search" type="search"></label><p id="count" aria-live="polite"></p><div class="table-wrap"><table id="data"></table></div></section>')
    parts.append('<style>'+font_css()+"body{font-family:'Loupe Body',sans-serif}h1,h2{font-family:'Loupe Heading',sans-serif}</style>")
    parts.append('</main><script nonce="loupe-controls" id="manifest" type="application/json">'+manifest+'</script>')
    parts.append('''<script nonce="loupe-controls">
    'use strict';
    const m=JSON.parse(document.getElementById('manifest').textContent), values=Object.create(null);
    function calculate(expression){
      const source=String(expression), tokens=source.match(/[A-Za-z_][A-Za-z0-9_]*|(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?|[()+*/-]/g)||[];
      if(tokens.join('')!==source.replace(/\\s/g,'')||tokens.length>128)throw Error('Invalid expression');
      let n=0;
      function primary(){let t=tokens[n++];if(t==='+'||t==='-')return(t==='-'?-1:1)*primary();if(t==='('){let v=sum();if(tokens[n++]!==')')throw Error('Missing parenthesis');return v;}if(Object.hasOwn(values,t))return values[t];let v=Number(t);if(!Number.isFinite(v))throw Error('Unknown input');return v;}
      function product(){let v=primary();while(tokens[n]==='*'||tokens[n]==='/'){let op=tokens[n++],r=primary();if(op==='/'&&r===0)throw Error('Division by zero');v=op==='*'?v*r:v/r;}return v;}
      function sum(){let v=product();while(tokens[n]==='+'||tokens[n]==='-'){let op=tokens[n++],r=product();v=op==='+'?v+r:v-r;}return v;}
      let result=sum();if(n!==tokens.length||!Number.isFinite(result))throw Error('Invalid result');return result;
    }
    function update(){const panel=document.getElementById('results');if(!panel)return;panel.replaceChildren();for(const c of m.interactions.calculations||[])if(c.key)delete values[c.key];for(const c of m.interactions.calculations||[]){const p=document.createElement('p');p.textContent=c.label||c.key;const o=document.createElement('output');try{const result=calculate(c.expression);if(c.key)values[c.key]=result;o.textContent=result.toLocaleString(undefined,{maximumFractionDigits:Math.min(8,Math.max(0,c.decimals??2))});}catch(e){o.textContent=e.message;o.className='error';}p.append(o);panel.append(p);}}
    for(const spec of m.interactions.inputs||[]){values[spec.key]=Number(spec.value||0);const label=document.createElement('label');label.textContent=spec.label||spec.key;const input=document.createElement('input');input.type='number';input.value=values[spec.key];for(const a of ['min','max','step'])if(spec[a]!==undefined)input[a]=spec[a];input.addEventListener('input',()=>{values[spec.key]=Number(input.value);update();});label.append(input);document.getElementById('controls').append(label);}update();
    let sortKey=null,direction=1;
    const cell=value=>value==null?'':typeof value==='object'?JSON.stringify(value):String(value);
    function table(){const target=document.getElementById('data');if(!target)return;const q=document.getElementById('search').value.toLowerCase();let rows=m.rows.filter(r=>m.columns.some(c=>cell(r[c]).toLowerCase().includes(q)));if(sortKey)rows=rows.slice().sort((a,b)=>cell(a[sortKey]).localeCompare(cell(b[sortKey]),undefined,{numeric:true})*direction);target.replaceChildren();const head=document.createElement('thead'),hr=document.createElement('tr');for(const c of m.columns){const th=document.createElement('th'),button=document.createElement('button');button.textContent=c;button.addEventListener('click',()=>{direction=sortKey===c?-direction:1;sortKey=c;table();});th.append(button);hr.append(th);}head.append(hr);target.append(head);const body=document.createElement('tbody');for(const r of rows){const tr=document.createElement('tr');for(const c of m.columns){const td=document.createElement('td');td.textContent=cell(r[c]);tr.append(td);}body.append(tr);}target.append(body);document.getElementById('count').textContent=rows.length+' of '+m.rows.length+' records';}if(document.getElementById('search'))document.getElementById('search').addEventListener('input',table);table();
    </script></body></html>''')
    return ''.join(parts)
