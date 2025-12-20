#!/usr/bin/env python3
"""
Generate a PDF version of the User Guide with Owl Consultancy Group branding.
"""

import sys
from pathlib import Path
import markdown
from xhtml2pdf import pisa

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def convert_html_to_pdf(source_html, output_path):
    """Convert HTML string to PDF file."""
    result_file = open(output_path, "w+b")
    
    # Convert HTML to PDF
    pisa_status = pisa.CreatePDF(
        source_html,
        dest=result_file,
        encoding='utf-8'
    )
    
    result_file.close()
    return not pisa_status.err

def generate_pdf():
    """Generate PDF from markdown user guide with branding."""
    
    # Paths
    guide_path = PROJECT_ROOT / "USER_GUIDE.md"
    logo_path = PROJECT_ROOT / "frontend" / "public" / "owl-logo.webp"
    output_path = PROJECT_ROOT / "USER_GUIDE.pdf"
    
    # Check if files exist
    if not guide_path.exists():
        print(f"Error: {guide_path} not found")
        return False
    
    if not logo_path.exists():
        print(f"Warning: {logo_path} not found, PDF will be generated without logo")
        logo_path = None
    
    # Read markdown
    with open(guide_path, 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    
    # Convert markdown to HTML
    md = markdown.Markdown(extensions=['toc', 'tables', 'fenced_code'])
    html_content = md.convert(markdown_content)
    
    # Get logo path for HTML (xhtml2pdf can handle file paths)
    logo_img_tag = ''
    if logo_path:
        logo_img_tag = f'<img src="{logo_path}" alt="Owl Consultancy Group" class="cover-logo" style="max-width: 200px; margin-bottom: 2cm;">'
    
    # Create HTML document with branding
    html_document = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Owl Investigation Platform - User Guide</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm 1.5cm;
        }}
        
        body {{
            font-family: Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
        }}
        
        /* Cover Page */
        .cover-page {{
            page-break-after: always;
            display: block;
            text-align: center;
            padding: 3cm 2cm;
            min-height: 20cm;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        
        .cover-logo {{
            max-width: 200px;
            margin-bottom: 2cm;
            height: auto;
        }}
        
        .cover-title {{
            font-size: 32pt;
            font-weight: bold;
            color: #1e3a5f;
            margin-bottom: 0.5cm;
            margin-top: 1cm;
        }}
        
        .cover-subtitle {{
            font-size: 18pt;
            color: #5a7fa3;
            margin-bottom: 2cm;
        }}
        
        .cover-meta {{
            font-size: 12pt;
            color: #666;
            margin-top: 2cm;
        }}
        
        /* Headings */
        h1 {{
            color: #1e3a5f;
            font-size: 24pt;
            font-weight: bold;
            margin-top: 1.5cm;
            margin-bottom: 0.5cm;
            page-break-after: avoid;
            border-bottom: 3px solid #5a7fa3;
            padding-bottom: 0.3cm;
        }}
        
        h2 {{
            color: #2c5282;
            font-size: 18pt;
            font-weight: bold;
            margin-top: 1.2cm;
            margin-bottom: 0.4cm;
            page-break-after: avoid;
        }}
        
        h3 {{
            color: #3182ce;
            font-size: 14pt;
            font-weight: bold;
            margin-top: 1cm;
            margin-bottom: 0.3cm;
            page-break-after: avoid;
        }}
        
        /* Table of Contents */
        #table-of-contents {{
            page-break-after: always;
            margin-bottom: 1cm;
        }}
        
        #table-of-contents h1 {{
            border-bottom: none;
            margin-top: 0;
        }}
        
        #table-of-contents ul {{
            list-style: none;
            padding-left: 0;
        }}
        
        #table-of-contents li {{
            margin: 0.5cm 0;
            padding-left: 1cm;
        }}
        
        #table-of-contents a {{
            color: #3182ce;
            text-decoration: none;
        }}
        
        /* Content */
        p {{
            margin: 0.5cm 0;
            text-align: justify;
        }}
        
        ul, ol {{
            margin: 0.5cm 0;
            padding-left: 1.5cm;
        }}
        
        li {{
            margin: 0.3cm 0;
        }}
        
        code {{
            background-color: #f5f5f5;
            padding: 2px 6px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            color: #d63384;
        }}
        
        pre {{
            background-color: #f5f5f5;
            border: 1px solid #ddd;
            padding: 1cm;
            page-break-inside: avoid;
            overflow: visible;
        }}
        
        pre code {{
            background-color: transparent;
            padding: 0;
            color: #333;
        }}
        
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1cm 0;
            page-break-inside: avoid;
        }}
        
        th, td {{
            border: 1px solid #ddd;
            padding: 0.5cm;
            text-align: left;
        }}
        
        th {{
            background-color: #1e3a5f;
            color: white;
            font-weight: bold;
        }}
        
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        /* Blockquotes */
        blockquote {{
            border-left: 4px solid #5a7fa3;
            margin: 1cm 0;
            padding-left: 1cm;
            color: #555;
            font-style: italic;
        }}
        
        /* Page breaks */
        .page-break {{
            page-break-before: always;
        }}
        
        /* Avoid breaking */
        h1, h2, h3, h4, h5, h6 {{
            page-break-after: avoid;
        }}
        
        img {{
            max-width: 100%;
            height: auto;
        }}
        
        /* Footer spacing */
        .content {{
            padding-bottom: 1cm;
        }}
        
        strong {{
            font-weight: bold;
        }}
        
        em {{
            font-style: italic;
        }}
    </style>
</head>
<body>
    <!-- Cover Page -->
    <div class="cover-page">
        {logo_img_tag}
        <h1 class="cover-title">Owl Investigation Platform</h1>
        <h2 class="cover-subtitle">User Guide</h2>
        <p class="cover-meta">Owl Consultancy Group<br>2024</p>
    </div>
    
    <!-- Content -->
    <div class="content">
        {html_content}
    </div>
</body>
</html>"""
    
    # Generate PDF
    print(f"Generating PDF: {output_path}")
    
    try:
        success = convert_html_to_pdf(html_document, output_path)
        if success:
            print(f"✓ PDF generated successfully: {output_path}")
            return True
        else:
            print("✗ Error generating PDF")
            return False
    except Exception as e:
        print(f"Error generating PDF: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = generate_pdf()
    sys.exit(0 if success else 1)

