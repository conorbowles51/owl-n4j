#!/usr/bin/env node
/**
 * Generate a PDF version of the User Guide with Owl Consultancy Group branding.
 */

const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const FRONTEND_ROOT = path.join(PROJECT_ROOT, 'frontend');
const GUIDE_PATH = path.join(PROJECT_ROOT, 'USER_GUIDE.md');
const LOGO_PATH = path.join(PROJECT_ROOT, 'frontend', 'public', 'owl-logo.webp');
const OUTPUT_PATH = path.join(PROJECT_ROOT, 'USER_GUIDE.pdf');
const CSS_PATH = path.join(__dirname, 'user_guide_styles.css');

// Try to load md-to-pdf from local node_modules
const mdToPdfPath = path.join(FRONTEND_ROOT, 'node_modules', 'md-to-pdf');
const { mdToPdf } = require(mdToPdfPath);

// Check if logo exists
const logoExists = fs.existsSync(LOGO_PATH);
let logoBase64 = null;

if (logoExists) {
  const logoData = fs.readFileSync(LOGO_PATH);
  logoBase64 = logoData.toString('base64');
}

// Read markdown
const markdownContent = fs.readFileSync(GUIDE_PATH, 'utf-8');

// Prepend cover page to markdown
const coverPage = logoBase64
  ? `![Owl Consultancy Group Logo](data:image/webp;base64,${logoBase64})

# Owl Investigation Platform

## User Guide

---

*Owl Consultancy Group*  
*2024*

---

`
  : `# Owl Investigation Platform

## User Guide

---

*Owl Consultancy Group*  
*2024*

---

`;

const fullMarkdown = coverPage + markdownContent;

// PDF options with styling
const pdfOptions = {
  pdf_options: {
    format: 'A4',
    margin: {
      top: '2cm',
      right: '1.5cm',
      bottom: '2cm',
      left: '1.5cm',
    },
    printBackground: true,
  },
  stylesheet: CSS_PATH,
};

async function generatePDF() {
  try {
    console.log(`Generating PDF: ${OUTPUT_PATH}`);
    
    const pdf = await mdToPdf(
      { content: fullMarkdown },
      pdfOptions
    );
    
    if (pdf) {
      fs.writeFileSync(OUTPUT_PATH, pdf.content);
      console.log(`✓ PDF generated successfully: ${OUTPUT_PATH}`);
      return true;
    } else {
      console.log('✗ Error generating PDF');
      return false;
    }
  } catch (error) {
    console.error('Error generating PDF:', error);
    return false;
  }
}

// Run
generatePDF().then(success => {
  process.exit(success ? 0 : 1);
});

