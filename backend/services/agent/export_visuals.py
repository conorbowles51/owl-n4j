"""Offline, deterministic vector exhibits. No model-authored SVG or remote URLs are executed."""
from __future__ import annotations

import html
import math
import textwrap
from typing import Any

PALETTE = ["#b41624", "#5571c8", "#8060a9", "#238a88", "#b37a2e", "#c25778", "#2c8197"]
SEMANTIC = {"person": "#5571c8", "organization": "#8060a9", "organisation": "#8060a9",
            "location": "#238a88", "account": "#b37a2e", "financial": "#b37a2e"}


def _text(x: float, y: float, value: Any, size=13, color="#202126", anchor="start") -> str:
    return f'<text x="{x:.2f}" y="{y:.2f}" font-family="sans-serif" font-size="{size}" fill="{color}" text-anchor="{anchor}">{html.escape(str(value))}</text>'


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"A chart value is not numeric: {str(value)[:80]}") from None
    if not math.isfinite(result):
        raise ValueError("Chart values must be finite numbers")
    return result


def _base(width: int, height: int, title: str, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img"><title>{html.escape(title)}</title>'
            '<rect width="100%" height="100%" fill="#ffffff"/>' + body + '</svg>')


def visual_svg(kind: str, data: dict, title: str = "") -> str:
    if kind == "chart":
        return _chart(data, title)
    if kind in ("graph", "diagram"):
        return _graph(data, title)
    if kind == "map":
        return _map(data, title)
    raise ValueError(f"{kind} does not have a vector export")


def _chart(data: dict, title: str) -> str:
    rows = data.get("rows") or []
    if not rows:
        raise ValueError("The chart has no source rows")
    shape = data.get("chart_type", "bar")
    if shape not in {"bar", "stacked_bar", "line", "area", "pie", "donut", "scatter"}:
        raise ValueError(f"Unsupported chart shape: {shape}")
    xkey = data.get("x_key") or data.get("category_key") or next(iter(rows[0]))
    keys = data.get("y_keys") or [s["key"] for s in data.get("series", [])]
    if not keys:
        keys = [data.get("value_key") or next((k for k, v in rows[0].items() if isinstance(v, (int, float))), "value")]
    series = {s["key"]: s.get("label") or s["key"] for s in data.get("series", [])}
    width, height = 960, 550
    body = _text(32, 34, title, 20)
    if shape in ("pie", "donut"):
        vals = [_number(r.get(keys[0], 0)) for r in rows]
        if any(v < 0 for v in vals) or sum(vals) <= 0:
            raise ValueError("Pie and donut charts require nonnegative values with a positive total")
        # Every category is present; the legend grows rather than losing tail categories.
        height = max(height, 90 + len(rows) * 25)
        cx, cy, radius, angle = 280, 285, 190, -math.pi / 2
        for i, (row, val) in enumerate(zip(rows, vals)):
            end = angle + 2 * math.pi * val / sum(vals)
            if val == sum(vals):
                body += f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{PALETTE[i % len(PALETTE)]}"/>'
            elif val:
                a, b = (cx + radius * math.cos(angle), cy + radius * math.sin(angle)), (cx + radius * math.cos(end), cy + radius * math.sin(end))
                body += f'<path d="M {cx} {cy} L {a[0]} {a[1]} A {radius} {radius} 0 {int(end-angle > math.pi)} 1 {b[0]} {b[1]} Z" fill="{PALETTE[i % len(PALETTE)]}" stroke="white"/>'
            body += f'<rect x="540" y="{74+i*25}" width="12" height="12" fill="{PALETTE[i % len(PALETTE)]}"/>'
            body += _text(562, 85+i*25, f'{row.get(xkey, i+1)}: {val:,.2f}', 12)
            angle = end
        if shape == "donut":
            body += f'<circle cx="{cx}" cy="{cy}" r="100" fill="white"/>'
            body += _text(cx, cy, f'{sum(vals):,.2f}', 22, anchor="middle")
        return _base(width, height, title, body)

    values = [[_number(r.get(k, 0)) for k in keys] for r in rows]
    if shape == "stacked_bar":
        lower = min(0, *(sum(v for v in vs if v < 0) for vs in values))
        upper = max(0, *(sum(v for v in vs if v > 0) for vs in values))
    else:
        lower, upper = min(0, *(v for vs in values for v in vs)), max(0, *(v for vs in values for v in vs))
    span = upper - lower or 1
    left, right, top, bottom = 100, 920, 105, 420
    yy = lambda v: bottom - (v - lower) / span * (bottom-top)
    for step in range(6):
        v = lower + span * step / 5
        y = yy(v)
        body += f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="#e4e5e9"/>' + _text(left-12, y+4, f'{v:,.2f}', 11, anchor="end")
    slot = (right-left) / max(1, len(rows))
    # Keep source data complete; label a readable interval on dense charts.
    label_every = max(1, math.ceil(len(rows) / 10))
    for i, row in enumerate(rows):
        if i % label_every == 0 or i == len(rows)-1:
            for j, line in enumerate(textwrap.wrap(str(row.get(xkey, i+1)), 16)):
                body += _text(left+(i+.5)*slot, bottom+22+j*14, line, 11, anchor="middle")
    for si, key in enumerate(keys):
        color = PALETTE[si % len(PALETTE)]
        if shape in ("line", "area", "scatter"):
            if shape == "scatter":
                xs = [_number(r.get(xkey)) for r in rows]
                xmin, xmax = min(xs), max(xs)
                points = [(left+(x-xmin)/(xmax-xmin or 1)*(right-left), yy(v[si])) for x, v in zip(xs, values)]
                # Numeric x axis, not categorical placement.
                for step in range(6):
                    body += _text(left+step/5*(right-left), bottom+60, f'{xmin+(xmax-xmin)*step/5:,.2f}', 11, anchor="middle")
            else:
                points = [(left+(i+.5)*slot, yy(v[si])) for i, v in enumerate(values)]
            point_text = ' '.join(f'{x:.2f},{y:.2f}' for x,y in points)
            if shape == "area":
                body += f'<polygon points="{points[0][0]},{yy(0)} {point_text} {points[-1][0]},{yy(0)}" fill="{color}" fill-opacity=".15"/>'
            if shape != "scatter":
                body += f'<polyline points="{point_text}" fill="none" stroke="{color}" stroke-width="2.5"/>'
            for x,y in points:
                body += f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"/>'
        else:
            for i, vs in enumerate(values):
                val = vs[si]
                base = sum(v for v in vs[:si] if (v >= 0) == (val >= 0)) if shape == "stacked_bar" else 0
                bar_width = slot*.75/(1 if shape == "stacked_bar" else len(keys))
                x = left + i*slot+slot*.125 + (0 if shape == "stacked_bar" else si*bar_width)
                y = min(yy(base), yy(base+val))
                body += f'<rect x="{x}" y="{y}" width="{bar_width}" height="{abs(yy(base+val)-yy(base))}" fill="{color}"/>'
        lx = 100+(si % 4)*205
        ly = 65+(si//4)*22
        body += f'<rect x="{lx}" y="{ly-10}" width="12" height="12" fill="{color}"/>' + _text(lx+19, ly, series.get(key,key), 12)
    body += _text(510, 525, data.get("x_label") or xkey, 12, anchor="middle")
    return _base(width, height, title, body)


def _graph(data: dict, title: str) -> str:
    nodes = data.get("nodes") or []
    links = data.get("links") or data.get("edges") or []
    if not nodes:
        raise ValueError("The diagram has no nodes")
    cols=min(5,max(1,math.ceil(math.sqrt(len(nodes)))))
    width = max(640, cols*320)
    height = max(280, math.ceil(len(nodes)/cols)*190+90)
    positions = {}
    body = '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#71747c"/></marker></defs>' + _text(30, 35, title, 20)
    for i,n in enumerate(nodes):
        positions[str(n.get("id") or n.get("key") or i)] = (width/(cols*2)+(i%cols)*width/cols, 120+(i//cols)*190)
    for edge in links:
        def ident(v): return str(v.get("id") or v.get("key")) if isinstance(v,dict) else str(v)
        a, b = positions.get(ident(edge.get("source"))), positions.get(ident(edge.get("target")))
        if a is None or b is None:
            raise ValueError("A diagram relationship refers to a node that is not present")
        label=edge.get("label") or edge.get("type") or ""
        if a[1]==b[1]:
            mid=a[1]+78
            body+=f'<path d="M {a[0]} {a[1]+36} V {mid} H {b[0]} V {b[1]+41}" fill="none" stroke="#9a9da5" stroke-width="1.6" marker-end="url(#arrow)"/>'
            body+=_text((a[0]+b[0])/2,mid+16,label,11,anchor="middle")
        else:
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy) or 1
            ex,ey=b[0]-dx/length*50,b[1]-dy/length*45
            body+=f'<line x1="{a[0]}" y1="{a[1]}" x2="{ex}" y2="{ey}" stroke="#9a9da5" stroke-width="1.6" marker-end="url(#arrow)"/>'
            body+=_text((a[0]+b[0])/2,(a[1]+b[1])/2-8,label,10,anchor="middle")
    for i,n in enumerate(nodes):
        x,y=positions[str(n.get("id") or n.get("key") or i)]
        color=SEMANTIC.get(str(n.get("type") or "").lower(),"#72757e")
        body += f'<rect x="{x-95}" y="{y-36}" width="190" height="72" rx="5" fill="white" stroke="{color}" stroke-width="2"/>'
        label=str(n.get("label") or n.get("name") or n.get("key") or n.get("id") or i)
        lines=textwrap.wrap(label,26) or [""]
        for j,line in enumerate(lines):
            body += _text(x,y-8+(j-(len(lines)-1)/2)*14,line,12,anchor="middle")
        body += _text(x,y+25,n.get("type") or "Entity",10,color,anchor="middle")
    return _base(width,height,title,body)


def _map(data: dict, title: str) -> str:
    locations=data.get("locations") or data.get("points") or data.get("rows") or []
    points=[]
    for i,l in enumerate(locations):
        lat,lon=_number(l.get("latitude",l.get("lat"))),_number(l.get("longitude",l.get("lng",l.get("lon"))))
        if not -90<=lat<=90 or not -180<=lon<=180:
            raise ValueError("Map coordinates are outside latitude/longitude bounds")
        points.append((lon,lat,str(l.get("name") or l.get("label") or i+1)))
    if not points:
        raise ValueError("The map has no located records")
    lo,hi=min(p[0] for p in points),max(p[0] for p in points)
    bottom,top=min(p[1] for p in points),max(p[1] for p in points)
    dx,dy=max(hi-lo,.02),max(top-bottom,.02)
    lo-=dx*.15;hi+=dx*.15;bottom-=dy*.15;top+=dy*.15
    body=_text(30,32,title,20)+_text(30,55,"Geographic plot · latitude / longitude · no external basemap",12,"#71747c")
    for n in range(6):
        x,y=90+n*154,110+n*70
        body+=f'<line x1="{x}" y1="110" x2="{x}" y2="460" stroke="#e4e5e9"/>'
        body+=f'<line x1="90" y1="{y}" x2="860" y2="{y}" stroke="#e4e5e9"/>'
        body+=_text(x,485,f'{lo+(hi-lo)*n/5:.4f}°',11,anchor="middle")
        body+=_text(80,y+4,f'{top-(top-bottom)*n/5:.4f}°',11,anchor="end")
    for i,(lon,lat,name) in enumerate(points):
        x,y=90+(lon-lo)/(hi-lo)*770,460-(lat-bottom)/(top-bottom)*350
        body+=f'<circle cx="{x}" cy="{y}" r="7" fill="#238a88" stroke="white" stroke-width="2"/>'
        body+=_text(x+10,y-8,f'{i+1}. {name}',12)
    notes = list(dict.fromkeys(str(data[key]).strip() for key in ('description', 'notes', 'note') if data.get(key)))
    lines = [line for note in notes for line in textwrap.wrap(note, 110)]
    for index, line in enumerate(lines):
        body += _text(30, 530 + index * 17, line, 12, '#71747c')
    return _base(960, max(530, 550 + len(lines) * 17) if lines else 530, title, body)


def svg_png(svg: str, scale: float = 1.5) -> bytes:
    import fitz
    with fitz.open(stream=svg.encode("utf-8"),filetype="svg") as vector:
        pdf=vector.convert_to_pdf()
    with fitz.open(stream=pdf,filetype="pdf") as doc:
        return doc[0].get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes("png")
