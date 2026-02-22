#!/usr/bin/env python3
"""Convert a Markdown file to a styled HTML file that can be printed to PDF."""
import markdown
import sys

input_file = sys.argv[1] if len(sys.argv) > 1 else "FEATURE_GUIDE.md"
output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".md", ".html")

with open(input_file, "r") as f:
    md_text = f.read()

html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc"])

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>OWL Platform — Feature Guide</title>
<style>
  @page {{
    size: A4;
    margin: 20mm 18mm;
  }}
  @media print {{
    body {{ font-size: 10pt; }}
    h1 {{ page-break-before: avoid; }}
    h2 {{ page-break-before: always; }}
    h2:first-of-type {{ page-break-before: avoid; }}
    table {{ page-break-inside: avoid; }}
    pre {{ page-break-inside: avoid; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    color: #1a1a2e;
    line-height: 1.65;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px 20px;
    background: #fff;
  }}
  h1 {{
    font-size: 26pt;
    color: #0f3460;
    border-bottom: 3px solid #0f3460;
    padding-bottom: 12px;
    margin-bottom: 6px;
  }}
  h2 {{
    font-size: 16pt;
    color: #16213e;
    border-bottom: 2px solid #e0e0e0;
    padding-bottom: 8px;
    margin-top: 40px;
  }}
  h3 {{
    font-size: 12pt;
    color: #533483;
    margin-top: 24px;
  }}
  blockquote {{
    border-left: 4px solid #0f3460;
    background: #f0f4ff;
    margin: 0 0 20px 0;
    padding: 12px 18px;
    color: #333;
    font-size: 10pt;
  }}
  blockquote p {{ margin: 4px 0; }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 9.5pt;
  }}
  th {{
    background: #0f3460;
    color: white;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
  }}
  td {{
    padding: 7px 12px;
    border-bottom: 1px solid #e0e0e0;
  }}
  tr:nth-child(even) td {{
    background: #f8f9fc;
  }}
  code {{
    background: #f0f0f5;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 9pt;
    font-family: "SF Mono", Menlo, Consolas, monospace;
  }}
  strong {{ color: #16213e; }}
  em {{ color: #555; }}
  hr {{
    border: none;
    border-top: 1px solid #d0d0d0;
    margin: 30px 0;
  }}
  ol, ul {{
    padding-left: 24px;
  }}
  li {{
    margin-bottom: 5px;
  }}
  a {{
    color: #0f3460;
    text-decoration: none;
  }}
  .footer {{
    margin-top: 40px;
    text-align: center;
    font-size: 9pt;
    color: #999;
  }}
</style>
</head>
<body>
{html_body}
<div class="footer">
  OWL Investigation Platform — Feature Guide — Generated February 2026
</div>
</body>
</html>
"""

with open(output_file, "w") as f:
    f.write(html)

print(f"Created {output_file}")
print(f"To save as PDF: open {output_file} in your browser → File → Print → Save as PDF")
