/**
 * Theory PDF Export Utility
 * 
 * Exports theories to PDF format with all attached items, graphs, and timelines
 * Includes Owl Consultancy Group branding and logo
 */

import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

// Owl brand colors
const OWL_COLORS = {
  blue: {
    50: [232, 240, 247],     // #e8f0f7
    100: [197, 217, 236],    // #c5d9ec
    200: [158, 191, 223],    // #9ebfdf
    300: [117, 165, 210],    // #75a5d2
    400: [85, 145, 200],     // #5591c8
    500: [53, 125, 190],     // #357dbe
    600: [45, 111, 168],     // #2d6fa8
    700: [36, 94, 143],      // #245e8f
    800: [29, 77, 118],      // #1d4d76
    900: [15, 47, 74],       // #0f2f4a
  },
  purple: {
    50: [243, 232, 255],     // #f3e8ff
    100: [233, 213, 255],    // #e9d5ff
    500: [147, 51, 234],     // #9333ea
  },
  orange: {
    50: [255, 247, 237],     // #fff7ed
    100: [255, 237, 213],    // #ffedd5
    500: [249, 115, 22],     // #f97316
  },
};

/**
 * Load logo as base64 image
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

/**
 * Export theory to PDF
 * 
 * @param {Object} theory - The theory data
 * @param {Object} attachedItems - All attached items (evidence, witnesses, notes, etc.)
 * @param {Object} graphData - Theory graph data (nodes and links)
 * @param {Array} timelineEvents - Timeline events
 * @param {HTMLCanvasElement} graphCanvas - Optional canvas element from the graph
 */
export async function exportTheoryToPDF(
  theory,
  attachedItems,
  graphData = null,
  timelineEvents = [],
  graphCanvas = null
) {
  const doc = new jsPDF('p', 'mm', 'a4');
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 15;
  const contentWidth = pageWidth - (margin * 2);
  let yPosition = margin;

  // Load logo
  const logoBase64 = await loadLogoAsBase64();

  // Helper to add a new page if needed
  const checkPageBreak = (requiredHeight) => {
    if (yPosition + requiredHeight > pageHeight - margin) {
      doc.addPage();
      yPosition = margin;
      return true;
    }
    return false;
  };

  // Helper to add text with word wrapping
  const addWrappedText = (text, x, y, maxWidth, fontSize = 11, lineHeight = 7) => {
    doc.setFontSize(fontSize);
    const lines = doc.splitTextToSize(text, maxWidth);
    doc.text(lines, x, y);
    return lines.length * lineHeight;
  };

  // Helper to add a section header
  const addSectionHeader = (title, icon = null) => {
    checkPageBreak(15);
    yPosition += 5;
    doc.setFontSize(16);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(...OWL_COLORS.blue[800]); // Owl blue-800
    doc.text(title, margin, yPosition);
    yPosition += 8;
    doc.setDrawColor(...OWL_COLORS.blue[600]); // Owl blue-600
    doc.setLineWidth(0.8);
    doc.line(margin, yPosition, pageWidth - margin, yPosition);
    yPosition += 5;
    doc.setTextColor(0, 0, 0);
    doc.setFont(undefined, 'normal');
  };

  // Helper to add a subsection header
  const addSubsectionHeader = (title) => {
    checkPageBreak(12);
    yPosition += 5;
    doc.setFontSize(13);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(...OWL_COLORS.blue[700]); // Owl blue-700
    doc.text(title, margin, yPosition);
    yPosition += 6;
    doc.setFont(undefined, 'normal');
    doc.setFontSize(11);
    doc.setTextColor(0, 0, 0);
  };

  // Add cover page with Owl branding
  // Header bar with Owl blue
  doc.setFillColor(...OWL_COLORS.blue[900]); // Owl blue-900
  doc.rect(0, 0, pageWidth, 50, 'F');
  
  // Add logo if available
  if (logoBase64) {
    try {
      doc.addImage(logoBase64, 'WEBP', pageWidth / 2 - 15, 10, 30, 30);
    } catch (err) {
      console.warn('Could not add logo image:', err);
    }
  }
  
  // Title text
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(22);
  doc.setFont(undefined, 'bold');
  doc.text('INVESTIGATION THEORY', pageWidth / 2, 45, { align: 'center' });
  
  // Subtitle
  doc.setFontSize(10);
  doc.setFont(undefined, 'normal');
  doc.text('Owl Consultancy Group', pageWidth / 2, 52, { align: 'center' });
  
  // Main content area
  doc.setTextColor(0, 0, 0);
  yPosition = 70;
  doc.setFontSize(20);
  doc.setFont(undefined, 'bold');
  doc.setTextColor(...OWL_COLORS.blue[800]); // Owl blue-800
  doc.text(theory.title || 'Untitled Theory', margin, yPosition);
  yPosition += 12;
  
  doc.setFontSize(11);
  doc.setFont(undefined, 'normal');
  doc.setTextColor(0, 0, 0);
  
  // Add colored badges for metadata
  if (theory.type) {
    doc.setFillColor(...OWL_COLORS.blue[100]); // Light blue background
    doc.roundedRect(margin, yPosition - 4, 40, 6, 1, 1, 'F');
    doc.setTextColor(...OWL_COLORS.blue[800]);
    doc.setFont(undefined, 'bold');
    doc.text('Type:', margin + 2, yPosition);
    doc.setTextColor(0, 0, 0);
    doc.setFont(undefined, 'normal');
    doc.text(theory.type, margin + 18, yPosition);
    yPosition += 8;
  }
  if (theory.confidence_score !== undefined && theory.confidence_score !== null) {
    doc.setFillColor(...OWL_COLORS.purple[100]); // Light purple
    doc.roundedRect(margin, yPosition - 4, 50, 6, 1, 1, 'F');
    doc.setTextColor(...OWL_COLORS.purple[500]);
    doc.setFont(undefined, 'bold');
    doc.text('Confidence:', margin + 2, yPosition);
    doc.setTextColor(0, 0, 0);
    doc.setFont(undefined, 'normal');
    doc.text(`${theory.confidence_score}/100`, margin + 28, yPosition);
    yPosition += 8;
  }
  if (theory.created_at) {
    const createdDate = new Date(theory.created_at).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
    doc.setFillColor(...OWL_COLORS.blue[50]); // Very light blue
    doc.roundedRect(margin, yPosition - 4, 60, 6, 1, 1, 'F');
    doc.setTextColor(...OWL_COLORS.blue[700]);
    doc.setFont(undefined, 'bold');
    doc.text('Created:', margin + 2, yPosition);
    doc.setTextColor(0, 0, 0);
    doc.setFont(undefined, 'normal');
    doc.text(createdDate, margin + 22, yPosition);
    yPosition += 8;
  }
  
  // Add summary
  if (theory.hypothesis) {
    yPosition += 5;
    addSubsectionHeader('Hypothesis');
    const hypothesisHeight = addWrappedText(theory.hypothesis, margin, yPosition, contentWidth);
    yPosition += hypothesisHeight + 3;
  }

  // Add decorative line before content
  yPosition += 5;
  doc.setDrawColor(...OWL_COLORS.blue[300]); // Light blue accent
  doc.setLineWidth(0.5);
  doc.line(margin, yPosition, pageWidth - margin, yPosition);
  yPosition += 10;

  // Add new page for content
  doc.addPage();
  yPosition = margin;
  
  // Add header with logo on content pages (optional - can be added if needed)

  // Theory Details Section
  addSectionHeader('Theory Details');
  
  if (theory.supporting_evidence && theory.supporting_evidence.length > 0) {
    addSubsectionHeader('Supporting Evidence');
    theory.supporting_evidence.forEach((evidence, idx) => {
      checkPageBreak(8);
      doc.setFontSize(10);
      doc.text(`${idx + 1}. ${evidence}`, margin + 5, yPosition);
      yPosition += 6;
    });
    yPosition += 3;
  }

  if (theory.counter_arguments && theory.counter_arguments.length > 0) {
    addSubsectionHeader('Counter Arguments');
    theory.counter_arguments.forEach((arg, idx) => {
      checkPageBreak(8);
      doc.setFontSize(10);
      doc.text(`${idx + 1}. ${arg}`, margin + 5, yPosition);
      yPosition += 6;
    });
    yPosition += 3;
  }

  if (theory.next_steps && theory.next_steps.length > 0) {
    addSubsectionHeader('Next Steps');
    theory.next_steps.forEach((step, idx) => {
      checkPageBreak(8);
      doc.setFontSize(10);
      doc.text(`${idx + 1}. ${step}`, margin + 5, yPosition);
      yPosition += 6;
    });
    yPosition += 3;
  }

  // Evidence Section
  if (attachedItems.evidence && attachedItems.evidence.length > 0) {
    addSectionHeader('Attached Evidence');
    attachedItems.evidence.forEach((file, idx) => {
      checkPageBreak(20);
      addSubsectionHeader(`${idx + 1}. ${file.original_filename || file.filename || `Evidence ${file.id}`}`);
      doc.setFontSize(10);
      if (file.size) {
        const sizeKB = (file.size / 1024).toFixed(1);
        doc.text(`Size: ${sizeKB} KB`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (file.processed_at) {
        const processedDate = new Date(file.processed_at).toLocaleDateString('en-US');
        doc.text(`Processed: ${processedDate}`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (file.status) {
        doc.text(`Status: ${file.status}`, margin + 5, yPosition);
        yPosition += 5;
      }
      yPosition += 3;
    });
  }

  // Witnesses Section
  if (attachedItems.witnesses && attachedItems.witnesses.length > 0) {
    addSectionHeader('Attached Witnesses');
    attachedItems.witnesses.forEach((witness, idx) => {
      checkPageBreak(25);
      addSubsectionHeader(`${idx + 1}. ${witness.name || 'Unknown Witness'}`);
      doc.setFontSize(10);
      if (witness.role) {
        doc.text(`Role: ${witness.role}`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (witness.organization) {
        doc.text(`Organization: ${witness.organization}`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (witness.status) {
        doc.text(`Status: ${witness.status}`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (witness.credibility_rating) {
        doc.text(`Credibility Rating: ${witness.credibility_rating}/5`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (witness.interviews && witness.interviews.length > 0) {
        doc.text(`Interviews: ${witness.interviews.length}`, margin + 5, yPosition);
        yPosition += 5;
      }
      yPosition += 3;
    });
  }

  // Notes Section
  if (attachedItems.notes && attachedItems.notes.length > 0) {
    addSectionHeader('Attached Notes');
    attachedItems.notes.forEach((note, idx) => {
      checkPageBreak(15);
      addSubsectionHeader(`Note ${idx + 1}`);
      const noteContent = note.content || '';
      const noteHeight = addWrappedText(noteContent, margin + 5, yPosition, contentWidth - 10, 10);
      yPosition += noteHeight + 5;
      if (note.created_at) {
        const noteDate = new Date(note.created_at).toLocaleDateString('en-US');
        doc.setFontSize(9);
        doc.setFont(undefined, 'italic');
        doc.text(`Created: ${noteDate}`, margin + 5, yPosition);
        yPosition += 5;
        doc.setFont(undefined, 'normal');
        doc.setFontSize(10);
      }
      yPosition += 3;
    });
  }

  // Tasks Section
  if (attachedItems.tasks && attachedItems.tasks.length > 0) {
    addSectionHeader('Attached Tasks');
    attachedItems.tasks.forEach((task, idx) => {
      checkPageBreak(20);
      addSubsectionHeader(`${idx + 1}. ${task.title || 'Untitled Task'}`);
      doc.setFontSize(10);
      if (task.description) {
        const descHeight = addWrappedText(task.description, margin + 5, yPosition, contentWidth - 10, 10);
        yPosition += descHeight + 3;
      }
      if (task.priority) {
        doc.text(`Priority: ${task.priority}`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (task.due_date) {
        const dueDate = new Date(task.due_date).toLocaleDateString('en-US');
        doc.text(`Due Date: ${dueDate}`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (task.status) {
        doc.text(`Status: ${task.status}`, margin + 5, yPosition);
        yPosition += 5;
      }
      yPosition += 3;
    });
  }

  // Documents Section
  if (attachedItems.documents && attachedItems.documents.length > 0) {
    addSectionHeader('Attached Documents');
    attachedItems.documents.forEach((document, idx) => {
      checkPageBreak(15);
      addSubsectionHeader(`${idx + 1}. ${document.original_filename || document.filename || `Document ${document.id}`}`);
      doc.setFontSize(10);
      if (document.summary) {
        const summaryHeight = addWrappedText(document.summary, margin + 5, yPosition, contentWidth - 10, 10);
        yPosition += summaryHeight + 3;
      }
      yPosition += 3;
    });
  }

  // Snapshots Section
  if (attachedItems.snapshots && attachedItems.snapshots.length > 0) {
    addSectionHeader('Attached Snapshots');
    attachedItems.snapshots.forEach((snapshot, idx) => {
      checkPageBreak(15);
      addSubsectionHeader(`${idx + 1}. ${snapshot.name || 'Unnamed Snapshot'}`);
      doc.setFontSize(10);
      if (snapshot.timestamp) {
        const snapDate = new Date(snapshot.timestamp).toLocaleDateString('en-US');
        doc.text(`Created: ${snapDate}`, margin + 5, yPosition);
        yPosition += 5;
      }
      if (snapshot.notes) {
        const notesHeight = addWrappedText(snapshot.notes, margin + 5, yPosition, contentWidth - 10, 10);
        yPosition += notesHeight + 3;
      }
      yPosition += 3;
    });
  }

  // Graph Section
  if (graphData && graphData.nodes && graphData.nodes.length > 0) {
    addSectionHeader('Theory Graph');
    doc.setFontSize(10);
    doc.text(`Nodes: ${graphData.nodes.length}`, margin, yPosition);
    yPosition += 6;
    doc.text(`Relationships: ${graphData.links ? graphData.links.length : 0}`, margin, yPosition);
    yPosition += 8;

    // Add graph image if canvas provided
    if (graphCanvas) {
      try {
        checkPageBreak(100);
        const imgData = graphCanvas.toDataURL('image/png', 1.0);
        const imgWidth = contentWidth;
        const imgHeight = (graphCanvas.height * imgWidth) / graphCanvas.width;
        const maxImgHeight = pageHeight - yPosition - margin - 20;
        const finalImgHeight = Math.min(imgHeight, maxImgHeight);
        const finalImgWidth = (graphCanvas.width * finalImgHeight) / graphCanvas.height;
        const xOffset = (contentWidth - finalImgWidth) / 2;
        
        doc.addImage(imgData, 'PNG', margin + xOffset, yPosition, finalImgWidth, finalImgHeight);
        yPosition += finalImgHeight + 10;
      } catch (err) {
        console.error('Error adding graph image:', err);
        doc.text('Graph visualization could not be included', margin, yPosition);
        yPosition += 10;
      }
    } else {
      // List nodes if no canvas
      doc.setFontSize(9);
      graphData.nodes.slice(0, 20).forEach((node, idx) => {
        checkPageBreak(6);
        doc.text(`${idx + 1}. ${node.name || node.key} (${node.type || 'Unknown'})`, margin + 5, yPosition);
        yPosition += 5;
      });
      if (graphData.nodes.length > 20) {
        doc.text(`... and ${graphData.nodes.length - 20} more nodes`, margin + 5, yPosition);
        yPosition += 5;
      }
    }
  }

  // Timeline Section
  if (timelineEvents && timelineEvents.length > 0) {
    addSectionHeader('Timeline');
    doc.setFontSize(10);
    
    // Group by thread
    const eventsByThread = {};
    timelineEvents.forEach(event => {
      const thread = event.thread || 'Other';
      if (!eventsByThread[thread]) {
        eventsByThread[thread] = [];
      }
      eventsByThread[thread].push(event);
    });

    Object.entries(eventsByThread).forEach(([thread, events]) => {
      checkPageBreak(15);
      addSubsectionHeader(thread);
      events.forEach((event, idx) => {
        checkPageBreak(10);
        const eventDate = event.date ? new Date(event.date).toLocaleDateString('en-US') : 'Unknown date';
        doc.setFontSize(9);
        doc.text(`${eventDate}: ${event.title || 'Untitled Event'}`, margin + 5, yPosition);
        if (event.description) {
          yPosition += 4;
          const descHeight = addWrappedText(event.description, margin + 10, yPosition, contentWidth - 15, 9);
          yPosition += descHeight;
        }
        yPosition += 4;
      });
      yPosition += 3;
    });
  }

  // Footer on each page with Owl branding
  const addFooter = (pageNum) => {
    // Footer line
    doc.setDrawColor(...OWL_COLORS.blue[300]); // Light blue line
    doc.setLineWidth(0.3);
    doc.line(margin, pageHeight - 15, pageWidth - margin, pageHeight - 15);
    
    // Footer text with logo if on first page
    if (pageNum === 1 && logoBase64) {
      try {
        doc.addImage(logoBase64, 'WEBP', margin, pageHeight - 12, 8, 8);
      } catch (err) {
        // Logo failed, continue without it
      }
    }
    
    doc.setFontSize(8);
    doc.setTextColor(...OWL_COLORS.blue[600]); // Owl blue-600
    doc.setFont(undefined, 'normal');
    const footerText = `Owl Consultancy Group - Investigation Platform - Page ${pageNum}`;
    doc.text(
      footerText,
      pageWidth / 2,
      pageHeight - 8,
      { align: 'center' }
    );
    doc.setTextColor(0, 0, 0);
  };

  // Add footer to all pages
  const totalPages = doc.internal.pages.length - 1;
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i);
    addFooter(i);
  }

  // Save PDF
  const fileName = `Theory_${(theory.title || 'Untitled').replace(/[^a-z0-9]/gi, '_')}_${new Date().toISOString().split('T')[0]}.pdf`;
  doc.save(fileName);
}
