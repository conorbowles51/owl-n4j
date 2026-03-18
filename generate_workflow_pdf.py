#!/usr/bin/env python3
"""Generate a branded PDF from USER_WORKFLOW_GUIDES.md"""

import markdown
from weasyprint import HTML
from pathlib import Path

MD_FILE = Path(__file__).parent / "USER_WORKFLOW_GUIDES.md"
OUT_FILE = Path(__file__).parent / "OWL_USER_WORKFLOW_GUIDES.pdf"

md_text = MD_FILE.read_text(encoding="utf-8")
body_html = markdown.markdown(
    md_text,
    extensions=["tables", "fenced_code", "toc", "attr_list"],
)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4;
    margin: 25mm 20mm 25mm 20mm;
    @top-left {{
        content: "OWL Investigation Platform";
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #1e3a5f;
    }}
    @top-right {{
        content: "User Workflow Guides";
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #6b7280;
    }}
    @bottom-center {{
        content: counter(page);
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #6b7280;
    }}
}}
@page :first {{
    @top-left {{ content: ""; }}
    @top-right {{ content: ""; }}
    @bottom-center {{ content: ""; }}
    margin-top: 0;
}}

* {{ box-sizing: border-box; }}

body {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.6;
    color: #1f2937;
    max-width: 100%;
}}

/* ── Cover Page ── */
.cover-page {{
    page-break-after: always;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    height: 100vh;
    text-align: center;
    padding: 60px 40px;
}}
.cover-logo {{
    width: 120px;
    height: 120px;
    border-radius: 24px;
    background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 40px auto;
    box-shadow: 0 8px 32px rgba(30, 58, 95, 0.3);
}}
.cover-logo-text {{
    font-size: 48pt;
    font-weight: 800;
    color: white;
    letter-spacing: -2px;
}}
.cover-title {{
    font-size: 28pt;
    font-weight: 700;
    color: #1e3a5f;
    margin-bottom: 12px;
    letter-spacing: -0.5px;
}}
.cover-subtitle {{
    font-size: 14pt;
    color: #6b7280;
    margin-bottom: 60px;
    font-weight: 400;
}}
.cover-meta {{
    font-size: 9pt;
    color: #9ca3af;
    border-top: 1px solid #e5e7eb;
    padding-top: 20px;
    width: 300px;
}}
.cover-divider {{
    width: 60px;
    height: 4px;
    background: linear-gradient(90deg, #1e3a5f, #2563eb);
    border-radius: 2px;
    margin: 0 auto 40px auto;
}}

/* ── Headings ── */
h1 {{
    font-size: 20pt;
    font-weight: 700;
    color: #1e3a5f;
    border-bottom: 3px solid #2563eb;
    padding-bottom: 8px;
    margin-top: 36px;
    margin-bottom: 16px;
    page-break-after: avoid;
}}
h2 {{
    font-size: 16pt;
    font-weight: 700;
    color: #1e3a5f;
    margin-top: 30px;
    margin-bottom: 12px;
    page-break-after: avoid;
    border-left: 4px solid #2563eb;
    padding-left: 12px;
}}
h3 {{
    font-size: 12pt;
    font-weight: 600;
    color: #374151;
    margin-top: 20px;
    margin-bottom: 8px;
    page-break-after: avoid;
}}
h4 {{
    font-size: 10pt;
    font-weight: 600;
    color: #4b5563;
    margin-top: 16px;
    margin-bottom: 6px;
}}

/* ── Body Text ── */
p {{
    margin: 0 0 10px 0;
    orphans: 3;
    widows: 3;
}}
strong {{
    color: #1e3a5f;
}}
a {{
    color: #2563eb;
    text-decoration: none;
}}

/* ── Lists ── */
ul, ol {{
    margin: 6px 0 12px 0;
    padding-left: 20px;
}}
li {{
    margin-bottom: 4px;
}}

/* ── Tables ── */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0 16px 0;
    font-size: 9pt;
    page-break-inside: avoid;
}}
thead {{
    background: linear-gradient(135deg, #1e3a5f 0%, #1e4a7a 100%);
}}
th {{
    color: white;
    font-weight: 600;
    padding: 8px 12px;
    text-align: left;
    border: 1px solid #1e3a5f;
}}
td {{
    padding: 7px 12px;
    border: 1px solid #d1d5db;
    vertical-align: top;
}}
tbody tr:nth-child(even) {{
    background: #f0f4ff;
}}
tbody tr:nth-child(odd) {{
    background: #ffffff;
}}

/* ── Code Blocks ── */
code {{
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 8.5pt;
    background: #f3f4f6;
    padding: 1px 4px;
    border-radius: 3px;
    color: #1e3a5f;
}}
pre {{
    background: #f8f9fb;
    border: 1px solid #e5e7eb;
    border-left: 4px solid #2563eb;
    border-radius: 6px;
    padding: 14px 16px;
    overflow-x: auto;
    font-size: 8pt;
    line-height: 1.5;
    margin: 10px 0 16px 0;
    page-break-inside: avoid;
}}
pre code {{
    background: none;
    padding: 0;
    font-size: 8pt;
}}

/* ── Blockquotes (used for version note) ── */
blockquote {{
    background: linear-gradient(135deg, #eff6ff 0%, #f0f4ff 100%);
    border-left: 4px solid #2563eb;
    margin: 16px 0;
    padding: 12px 16px;
    border-radius: 0 6px 6px 0;
    color: #374151;
    font-style: normal;
}}
blockquote p {{
    margin: 0;
}}

/* ── Horizontal Rules ── */
hr {{
    border: none;
    border-top: 2px solid #e5e7eb;
    margin: 24px 0;
}}

/* ── Keyboard shortcuts ── */
kbd {{
    background: #f3f4f6;
    border: 1px solid #d1d5db;
    border-radius: 3px;
    padding: 1px 5px;
    font-family: 'SF Mono', 'Menlo', monospace;
    font-size: 8pt;
    box-shadow: 0 1px 0 #d1d5db;
}}

/* ── Page breaks before each major section ── */
h2 {{
    page-break-before: auto;
}}

/* ── TOC styling ── */
.toc {{
    background: #f8f9fb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 20px 24px;
    margin: 20px 0;
}}
.toc ul {{
    list-style: none;
    padding-left: 0;
}}
.toc li {{
    margin-bottom: 6px;
    padding-left: 0;
}}
.toc a {{
    color: #1e3a5f;
    font-weight: 500;
}}
</style>
</head>
<body>

<!-- Cover Page -->
<div class="cover-page">
    <div class="cover-logo">
        <span class="cover-logo-text">OWL</span>
    </div>
    <div class="cover-divider"></div>
    <div class="cover-title">User Workflow Guides</div>
    <div class="cover-subtitle">Investigation Platform — Complete Reference</div>
    <div class="cover-meta">
        February 2026 &nbsp;·&nbsp; Version 1.0<br>
        Confidential — For Authorised Users Only
    </div>
</div>

<!-- Content -->
{body_html}

</body>
</html>"""

print("Generating PDF...")
HTML(string=html).write_pdf(str(OUT_FILE))
print(f"Done → {OUT_FILE}")
