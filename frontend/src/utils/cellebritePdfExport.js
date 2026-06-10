/**
 * Cellebrite Device Report PDF Export Utility
 *
 * Exports the per-device summaries from the Cellebrite Report tab to a PDF —
 * the same honest, traffic-derived profile shown in the on-screen summary
 * cards (assigned owner / dominant user, activity window, counts, recovered
 * aliases). Client-side jsPDF only (no backend), per spike #50.
 *
 * Mirrors the jsPDF setup, branding, helpers and footer of theoryPdfExport.js.
 */

import jsPDF from 'jspdf';

// Owl brand colors (subset used here) — same palette as theoryPdfExport.js.
const OWL_COLORS = {
  blue: {
    50: [232, 240, 247],
    100: [197, 217, 236],
    300: [117, 165, 210],
    600: [45, 111, 168],
    700: [36, 94, 143],
    800: [29, 77, 118],
    900: [15, 47, 74],
  },
  emerald: { 600: [5, 150, 105] },
  amber: { 600: [217, 119, 6] },
};

/**
 * Load logo as base64 image (same helper as theoryPdfExport.js).
 */
async function loadLogoAsBase64() {
  try {
    const response = await fetch('/owl-logo.webp');
    if (!response.ok) return null;
    const blob = await response.blob();
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch (err) {
    console.error('Failed to load logo:', err);
    return null;
  }
}

// "C1".."C9" label out of the report name, mirroring the card/table heuristic.
function deviceLabel(d) {
  const m = (d.report_name || '').match(/_(C\d+[a-z]?)_|^(C\d+-\d+)/i);
  return m ? (m[1] || m[2]) : (d.evidence_number || d.report_key || 'Device');
}

function ownerNumber(pu) {
  if (!pu) return '';
  const key = pu.key;
  const m = key && /^phone-(\d{7,15})$/.exec(String(key));
  return m ? `+${m[1]}` : ((pu.numbers && pu.numbers[0]) || '');
}

function ownerName(d) {
  const pu = d.primary_user || {};
  const nameIsNum = pu.name && /^[+(]?\d[\d\s().-]{5,}$/.test(String(pu.name).trim());
  const trafficName = (pu.name && !nameIsNum) ? pu.name : null;
  return d.assigned_owner || trafficName || '(unnamed)';
}

const fmtDate = (ts) => (ts ? String(ts).slice(0, 10) : '—');

// Format a callout/event timestamp for the report. Callout timestamps are
// stored as the event's raw timestamp (may be ISO, may be a date-only string).
// Show a readable date+time when parseable, falling back to the raw string,
// then to an em-dash.
const fmtEventTs = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts);
  if (!Number.isNaN(d.getTime())) {
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }
  return String(ts);
};

/**
 * Export the Cellebrite device report to PDF.
 *
 * Backward-compat note (S3-09): this function originally had the positional
 * signature `(caseName, devicesArray, createdAt)`. It now ALSO accepts an
 * options object `(caseName, { devices, callouts, visualizations, createdAt })`.
 * The second argument is normalized at runtime:
 *   - If it's an Array, we treat it as the legacy `devices` positional arg and
 *     read `createdAt` from the third positional argument.
 *   - Otherwise it's treated as the options object (and the third arg is
 *     ignored).
 * This keeps every existing caller (e.g. older callers passing a devices
 * array) working unchanged while letting new callers pass extra sections.
 *
 * @param {string} caseName - Case name (or case id when only the id is known).
 * @param {Array|Object} [optsOrDevices] - Either the legacy devices array, or
 *   an options object: { devices, callouts, visualizations, createdAt }.
 * @param {string|Date} [maybeCreatedAt] - Legacy positional createdAt; only
 *   used when the second argument is an Array.
 * @param {Array}  [optsOrDevices.devices=[]] - Device objects from getDeviceReport.
 * @param {Array}  [optsOrDevices.callouts=[]] - Flagged callouts (S3-07),
 *   each { event_node_key, note, event_summary, event_timestamp, ... }.
 * @param {Array}  [optsOrDevices.visualizations=[]] - Images to embed, each
 *   { title, dataUrl } where dataUrl is a PNG/JPEG data URL (S3-08).
 * @param {string|Date} [optsOrDevices.createdAt] - Generation timestamp.
 */
export async function exportCellebriteReportToPDF(caseName, optsOrDevices = {}, maybeCreatedAt = new Date()) {
  // ---- Normalize args for backward compatibility (see JSDoc above) ----
  let devices;
  let callouts;
  let visualizations;
  let createdAt;
  if (Array.isArray(optsOrDevices)) {
    // Legacy positional call: (caseName, devicesArray, createdAt).
    devices = optsOrDevices;
    callouts = [];
    visualizations = [];
    createdAt = maybeCreatedAt || new Date();
  } else {
    // New options-object call.
    const opts = optsOrDevices || {};
    devices = Array.isArray(opts.devices) ? opts.devices : [];
    callouts = Array.isArray(opts.callouts) ? opts.callouts : [];
    visualizations = Array.isArray(opts.visualizations) ? opts.visualizations : [];
    createdAt = opts.createdAt || new Date();
  }

  const doc = new jsPDF('p', 'mm', 'a4');
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 15;
  const contentWidth = pageWidth - (margin * 2);
  let yPosition = margin;

  const logoBase64 = await loadLogoAsBase64();

  const checkPageBreak = (requiredHeight) => {
    if (yPosition + requiredHeight > pageHeight - margin) {
      doc.addPage();
      yPosition = margin;
      return true;
    }
    return false;
  };

  const addWrappedText = (text, x, y, maxWidth, fontSize = 11, lineHeight = 6) => {
    doc.setFontSize(fontSize);
    const lines = doc.splitTextToSize(String(text), maxWidth);
    doc.text(lines, x, y);
    return lines.length * lineHeight;
  };

  const addSubsectionHeader = (title) => {
    checkPageBreak(14);
    yPosition += 5;
    doc.setFontSize(13);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(...OWL_COLORS.blue[700]);
    doc.text(title, margin, yPosition);
    yPosition += 5;
    doc.setDrawColor(...OWL_COLORS.blue[300]);
    doc.setLineWidth(0.4);
    doc.line(margin, yPosition, pageWidth - margin, yPosition);
    yPosition += 5;
    doc.setFont(undefined, 'normal');
    doc.setFontSize(11);
    doc.setTextColor(0, 0, 0);
  };

  const addLine = (text, indent = 5, fontSize = 10) => {
    doc.setFontSize(fontSize);
    doc.setTextColor(0, 0, 0);
    // Wrap to the page width so long values (owner names, the counts line,
    // examiner, etc.) don't run off the right edge and get clipped. jsPDF's
    // doc.text() does NOT wrap on its own — without splitTextToSize a long
    // single line is simply drawn past the margin and lost ("cut off").
    const x = margin + indent;
    const maxWidth = contentWidth - indent;
    const lines = doc.splitTextToSize(String(text), maxWidth);
    // Page-break per line so a multi-line value that crosses the page edge
    // continues on the next page instead of vanishing past the bottom.
    for (const line of lines) {
      checkPageBreak(7);
      doc.text(line, x, yPosition);
      yPosition += 6;
    }
  };

  // ---- Cover page with Owl branding (mirrors theoryPdfExport) ----
  doc.setFillColor(...OWL_COLORS.blue[900]);
  doc.rect(0, 0, pageWidth, 50, 'F');

  if (logoBase64) {
    try {
      doc.addImage(logoBase64, 'WEBP', pageWidth / 2 - 15, 10, 30, 30);
    } catch (err) {
      console.warn('Could not add logo image:', err);
    }
  }

  doc.setTextColor(255, 255, 255);
  doc.setFontSize(22);
  doc.setFont(undefined, 'bold');
  doc.text('DEVICE REPORT', pageWidth / 2, 45, { align: 'center' });

  doc.setFontSize(10);
  doc.setFont(undefined, 'normal');
  doc.text('Owl Consultancy Group', pageWidth / 2, 52, { align: 'center' });

  // Main content area
  doc.setTextColor(0, 0, 0);
  yPosition = 70;
  doc.setFontSize(20);
  doc.setFont(undefined, 'bold');
  doc.setTextColor(...OWL_COLORS.blue[800]);
  // Wrap the title so a long case name doesn't run off the page edge.
  const titleLines = doc.splitTextToSize(String(caseName || 'Cellebrite Report'), contentWidth);
  doc.text(titleLines, margin, yPosition);
  yPosition += 12 + (titleLines.length - 1) * 9;

  // Metadata badges
  doc.setFontSize(11);
  doc.setFont(undefined, 'normal');
  doc.setTextColor(0, 0, 0);

  const genDate = new Date(createdAt).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  });
  doc.setFillColor(...OWL_COLORS.blue[50]);
  doc.roundedRect(margin, yPosition - 4, 70, 6, 1, 1, 'F');
  doc.setTextColor(...OWL_COLORS.blue[700]);
  doc.setFont(undefined, 'bold');
  doc.text('Generated:', margin + 2, yPosition);
  doc.setTextColor(0, 0, 0);
  doc.setFont(undefined, 'normal');
  doc.text(genDate, margin + 26, yPosition);
  yPosition += 8;

  doc.setFillColor(...OWL_COLORS.blue[100]);
  doc.roundedRect(margin, yPosition - 4, 50, 6, 1, 1, 'F');
  doc.setTextColor(...OWL_COLORS.blue[800]);
  doc.setFont(undefined, 'bold');
  doc.text('Devices:', margin + 2, yPosition);
  doc.setTextColor(0, 0, 0);
  doc.setFont(undefined, 'normal');
  doc.text(String(devices.length), margin + 24, yPosition);
  yPosition += 8;

  // Contents line — reflects which sections this run actually includes.
  const contentsParts = ['Device Summary'];
  if (callouts.length) contentsParts.push('Key Events / Callouts');
  if (visualizations.length) contentsParts.push('Investigation Visualizations');
  doc.setFillColor(...OWL_COLORS.blue[50]);
  doc.roundedRect(margin, yPosition - 4, contentWidth, 6, 1, 1, 'F');
  doc.setTextColor(...OWL_COLORS.blue[700]);
  doc.setFont(undefined, 'bold');
  doc.setFontSize(9);
  doc.text('Contents:', margin + 2, yPosition);
  doc.setTextColor(0, 0, 0);
  doc.setFont(undefined, 'normal');
  doc.text(contentsParts.join('  ·  '), margin + 22, yPosition);
  yPosition += 10;

  doc.setFontSize(11);
  const intro =
    "Each phone's assigned owner (investigator-set) shown with the dominant user "
    + "by traffic, recovered aliases, in/out communications and the activity window. "
    + 'Numbers are shown beside names.';
  yPosition += addWrappedText(intro, margin, yPosition, contentWidth, 10, 6) + 4;

  doc.setDrawColor(...OWL_COLORS.blue[300]);
  doc.setLineWidth(0.5);
  doc.line(margin, yPosition, pageWidth - margin, yPosition);
  yPosition += 8;

  // ---- Section 2: Device Summary (one block per device) ----
  addSubsectionHeader('Device Summary');
  if (!devices.length) {
    addLine('No devices to report on.', 0, 11);
  }

  devices.forEach((d) => {
    const pu = d.primary_user || {};
    // Keep a device's heading + first lines together when near a page edge.
    checkPageBreak(40);
    addSubsectionHeader(`${deviceLabel(d)} — ${d.device_model || 'Unknown device'}`);

    if (d.examiner) addLine(`Examiner: ${d.examiner}`);

    const num = ownerNumber(pu);
    const numTag = num
      ? (pu.matches_device_number ? ' (device #)' : ' (inferred)')
      : '';
    addLine(`Owner / dominant user: ${ownerName(d)}${num ? ` — ${num}${numTag}` : ''}`);

    addLine(`Activity window: ${fmtDate(d.activity_first)} -> ${fmtDate(d.activity_last)}`);

    addLine(
      `Counts: ${(d.contact_entries || 0).toLocaleString()} contacts · `
      + `${(d.messages || 0).toLocaleString()} messages · `
      + `${(d.calls_in || 0).toLocaleString()}/${(d.calls_out || 0).toLocaleString()} calls (in/out)`,
    );

    const aliases = pu.aliases || [];
    if (aliases.length) {
      checkPageBreak(7);
      const aliasHeight = addWrappedText(
        `Saved as (${aliases.length}): ${aliases.join(', ')}`,
        margin + 5, yPosition, contentWidth - 5, 10, 6,
      );
      yPosition += aliasHeight;
    } else {
      addLine('Saved as: no saved name (own number)');
    }

    const devNums = d.device_numbers || [];
    if (devNums.length) {
      checkPageBreak(7);
      const dnHeight = addWrappedText(
        `Device numbers: ${devNums.join(', ')}${d.imei ? ` · IMEI ${d.imei}` : ''}`,
        margin + 5, yPosition, contentWidth - 5, 10, 6,
      );
      yPosition += dnHeight;
    } else if (d.imei) {
      addLine(`IMEI: ${d.imei}`);
    }

    yPosition += 4;
  });

  // ---- Section 3: Key Events / Callouts (S3-09) ----
  // The events the investigator flagged for the report. Always render the
  // section header so the report reads consistently; when nothing is flagged
  // show a muted note rather than omitting it (keeps the contents line honest).
  addSubsectionHeader('Key Events / Callouts');
  if (callouts.length) {
    // Already sorted chronologically by the API, but sort defensively so the
    // PDF order can't depend on caller behaviour.
    const ordered = [...callouts].sort((a, b) => {
      const ta = a && a.event_timestamp ? String(a.event_timestamp) : '';
      const tb = b && b.event_timestamp ? String(b.event_timestamp) : '';
      return ta < tb ? -1 : ta > tb ? 1 : 0;
    });
    ordered.forEach((c, idx) => {
      // Keep each callout's timestamp + first line together near a page edge.
      checkPageBreak(18);
      // Timestamp line (bold, blue).
      doc.setFontSize(10);
      doc.setFont(undefined, 'bold');
      doc.setTextColor(...OWL_COLORS.blue[700]);
      doc.text(`${idx + 1}. ${fmtEventTs(c.event_timestamp)}`, margin + 5, yPosition);
      yPosition += 6;
      doc.setFont(undefined, 'normal');
      doc.setTextColor(0, 0, 0);
      // Event summary snapshot (denormalised at flag time).
      if (c.event_summary) {
        checkPageBreak(7);
        yPosition += addWrappedText(c.event_summary, margin + 9, yPosition, contentWidth - 9, 10, 6);
      }
      // Investigator note (if any), set off in amber italic.
      if (c.note) {
        checkPageBreak(7);
        doc.setFont(undefined, 'italic');
        doc.setTextColor(...OWL_COLORS.amber[600]);
        yPosition += addWrappedText(`Note: ${c.note}`, margin + 9, yPosition, contentWidth - 9, 10, 6);
        doc.setFont(undefined, 'normal');
        doc.setTextColor(0, 0, 0);
      }
      yPosition += 4;
    });
  } else {
    doc.setFontSize(10);
    doc.setTextColor(...OWL_COLORS.blue[600]);
    doc.setFont(undefined, 'italic');
    checkPageBreak(7);
    doc.text('No callouts flagged.', margin + 5, yPosition);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(0, 0, 0);
    yPosition += 6;
  }

  // ---- Section 4: Investigation Visualizations (S3-08) ----
  // Each visualization is { title, dataUrl } — a PNG/JPEG data URL captured
  // upstream. Omit the whole section when none are supplied.
  if (visualizations.length) {
    addSubsectionHeader('Investigation Visualizations');
    visualizations.forEach((viz) => {
      if (!viz || !viz.dataUrl) return;
      if (viz.title) {
        checkPageBreak(8);
        doc.setFontSize(11);
        doc.setFont(undefined, 'bold');
        doc.setTextColor(...OWL_COLORS.blue[800]);
        doc.text(String(viz.title), margin + 5, yPosition);
        doc.setFont(undefined, 'normal');
        doc.setTextColor(0, 0, 0);
        yPosition += 6;
      }
      try {
        // Detect format from the data URL header; default to PNG.
        const fmt = /^data:image\/jpe?g/i.test(viz.dataUrl) ? 'JPEG' : 'PNG';
        // Read natural pixel dimensions so we can preserve aspect ratio.
        const props = doc.getImageProperties(viz.dataUrl);
        const imgW = contentWidth;
        let imgH = props.height ? (props.width ? (props.height * imgW) / props.width : imgW * 0.6) : imgW * 0.6;
        // Cap height so a tall image doesn't overflow a fresh page.
        const maxH = pageHeight - margin - 25;
        let drawW = imgW;
        if (imgH > maxH) {
          drawW = props.width ? (props.width * maxH) / props.height : imgW;
          imgH = maxH;
        }
        checkPageBreak(imgH + 6);
        const xOffset = (contentWidth - drawW) / 2;
        doc.addImage(viz.dataUrl, fmt, margin + xOffset, yPosition, drawW, imgH);
        yPosition += imgH + 8;
      } catch (err) {
        console.error('Error adding visualization image:', err);
        checkPageBreak(7);
        doc.setFontSize(10);
        doc.setTextColor(...OWL_COLORS.blue[600]);
        doc.text('Visualization could not be included.', margin + 5, yPosition);
        doc.setTextColor(0, 0, 0);
        yPosition += 6;
      }
    });
  }

  // ---- Footer on every page (mirrors theoryPdfExport) ----
  const addFooter = (pageNum) => {
    doc.setDrawColor(...OWL_COLORS.blue[300]);
    doc.setLineWidth(0.3);
    doc.line(margin, pageHeight - 15, pageWidth - margin, pageHeight - 15);

    if (pageNum === 1 && logoBase64) {
      try {
        doc.addImage(logoBase64, 'WEBP', margin, pageHeight - 12, 8, 8);
      } catch (err) {
        // Logo failed, continue without it
      }
    }

    doc.setFontSize(8);
    doc.setTextColor(...OWL_COLORS.blue[600]);
    doc.setFont(undefined, 'normal');
    doc.text(
      `Owl Consultancy Group - Device Report - Page ${pageNum}`,
      pageWidth / 2,
      pageHeight - 8,
      { align: 'center' },
    );
    doc.setTextColor(0, 0, 0);
  };

  const totalPages = doc.internal.pages.length - 1;
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i);
    addFooter(i);
  }

  const safeCase = String(caseName || 'case').replace(/[^a-z0-9]/gi, '_');
  doc.save(`cellebrite-report-${safeCase}.pdf`);
}
