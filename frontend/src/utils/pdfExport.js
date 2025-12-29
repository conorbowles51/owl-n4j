/**
 * PDF Export Utility
 * 
 * Exports snapshots to PDF format with subgraph, overview, chat history, and timeline
 */

import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

/**
 * Simple markdown to HTML converter
 * Converts basic markdown syntax to HTML
 */
function markdownToHtml(markdown) {
  if (!markdown) return '';
  
  let html = markdown;
  
  // Convert **bold** to <strong>bold</strong>
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  
  // Convert *italic* to <em>italic</em>
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  
  // Convert `code` to <code>code</code>
  html = html.replace(/`(.+?)`/g, '<code>$1</code>');
  
  // Convert ## Heading to <h2>Heading</h2>
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  
  // Convert - list item to <li>list item</li>
  html = html.replace(/^\- (.+)$/gm, '<li>$1</li>');
  // Wrap consecutive <li> in <ul>
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => {
    return '<ul>' + match + '</ul>';
  });
  
  // Convert numbered list
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Wrap consecutive numbered <li> in <ol>
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => {
    if (match.includes('<ul>')) return match; // Skip if already wrapped
    return '<ol>' + match + '</ol>';
  });
  
  // Convert line breaks
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');
  
  // Wrap in paragraph if not already wrapped
  if (!html.startsWith('<')) {
    html = '<p>' + html + '</p>';
  }
  
  return html;
}

/**
 * Strip HTML tags but preserve formatting for plain text rendering
 * This is a fallback if HTML rendering doesn't work well
 */
function stripHtmlTags(html) {
  if (!html) return '';
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  return tmp.textContent || tmp.innerText || '';
}

/**
 * Export snapshot to PDF
 * 
 * @param {Object} snapshot - The snapshot data
 * @param {HTMLCanvasElement} graphCanvas - The canvas element from the graph
 */
export async function exportSnapshotToPDF(snapshot, graphCanvas = null) {
  const doc = new jsPDF('p', 'mm', 'a4');
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 15;
  const contentWidth = pageWidth - (margin * 2);
  let yPosition = margin;

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

  // Title
  doc.setFontSize(20);
  doc.setFont(undefined, 'bold');
  doc.text(snapshot.name || 'Snapshot', margin, yPosition);
  yPosition += 10;

  // Date
  doc.setFontSize(10);
  doc.setFont(undefined, 'normal');
  const dateStr = snapshot.timestamp 
    ? new Date(snapshot.timestamp).toLocaleString() 
    : new Date().toLocaleString();
  doc.text(`Created: ${dateStr}`, margin, yPosition);
  yPosition += 8;

  // User Notes (Introduction)
  if (snapshot.notes) {
    checkPageBreak(30);
    doc.setFontSize(14);
    doc.setFont(undefined, 'bold');
    doc.text('Notes', margin, yPosition);
    yPosition += 8;
    
    doc.setFontSize(11);
    doc.setFont(undefined, 'normal');
    const notesHeight = addWrappedText(snapshot.notes, margin, yPosition, contentWidth);
    yPosition += notesHeight + 10;
  }

  // Subgraph Image (PNG) - with white background and darker colors
  checkPageBreak(100);
  doc.setFontSize(14);
  doc.setFont(undefined, 'bold');
  doc.text('Subgraph Visualization', margin, yPosition);
  yPosition += 8;

  if (graphCanvas) {
    try {
      // Create a new canvas with white background for PDF
      const pdfCanvas = document.createElement('canvas');
      pdfCanvas.width = graphCanvas.width;
      pdfCanvas.height = graphCanvas.height;
      const pdfCtx = pdfCanvas.getContext('2d');
      
      // Fill with white background
      pdfCtx.fillStyle = '#ffffff';
      pdfCtx.fillRect(0, 0, pdfCanvas.width, pdfCanvas.height);
      
      // Draw the original canvas
      pdfCtx.drawImage(graphCanvas, 0, 0);
      
      // Apply color adjustments for better visibility on white background
      // Replace dark background with white, and enhance node colors
      const imageData = pdfCtx.getImageData(0, 0, pdfCanvas.width, pdfCanvas.height);
      const data = imageData.data;
      
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        const a = data[i + 3];
        
        // Replace dark background (dark-950: rgb(3, 7, 18) or similar) with white
        if (r < 50 && g < 50 && b < 50 && a > 0) {
          // This is likely the dark background - make it white
          data[i] = 255;
          data[i + 1] = 255;
          data[i + 2] = 255;
        }
        // Enhance node colors - make them darker and more saturated for visibility
        else if (a > 0 && !(r > 240 && g > 240 && b > 240)) {
          // This is a colored element (node, link, etc.)
          // Increase saturation and darken slightly for better contrast on white
          const brightness = (r + g + b) / 3;
          if (brightness > 100) {
            // Light colors - darken them
            data[i] = Math.max(0, Math.min(255, r * 0.75));
            data[i + 1] = Math.max(0, Math.min(255, g * 0.75));
            data[i + 2] = Math.max(0, Math.min(255, b * 0.75));
          } else {
            // Already dark colors - enhance them slightly
            data[i] = Math.max(0, Math.min(255, r * 1.1));
            data[i + 1] = Math.max(0, Math.min(255, g * 1.1));
            data[i + 2] = Math.max(0, Math.min(255, b * 1.1));
          }
        }
        // Light gray text/labels - make them darker
        else if (r > 200 && g > 200 && b > 200 && r < 250 && a > 0) {
          data[i] = 50;
          data[i + 1] = 50;
          data[i + 2] = 50;
        }
      }
      
      pdfCtx.putImageData(imageData, 0, 0);
      
      // Convert to PNG
      const imgData = pdfCanvas.toDataURL('image/png', 1.0);
      const imgWidth = contentWidth;
      const imgHeight = (pdfCanvas.height * imgWidth) / pdfCanvas.width;
      
      // Limit image height to fit on page
      const maxImgHeight = pageHeight - yPosition - margin - 30;
      const finalImgHeight = Math.min(imgHeight, maxImgHeight);
      const finalImgWidth = (pdfCanvas.width * finalImgHeight) / pdfCanvas.height;

      // Center the image
      const xOffset = (contentWidth - finalImgWidth) / 2;
      
      doc.addImage(imgData, 'PNG', margin + xOffset, yPosition, finalImgWidth, finalImgHeight);
      yPosition += finalImgHeight + 10;
      
      // Add caption
      doc.setFontSize(9);
      doc.setFont(undefined, 'italic');
      doc.text(
        `Subgraph showing ${snapshot.subgraph?.nodes?.length || 0} nodes and ${snapshot.subgraph?.links?.length || 0} relationships`,
        margin,
        yPosition
      );
      yPosition += 6;
    } catch (err) {
      console.error('Error adding graph PNG image:', err);
      doc.setFontSize(10);
      doc.setFont(undefined, 'normal');
      doc.text('Graph image could not be included', margin, yPosition);
      yPosition += 10;
    }
  } else {
    // Fallback if canvas not available
    doc.setFontSize(11);
    doc.setFont(undefined, 'normal');
    doc.text(`Subgraph contains ${snapshot.subgraph?.nodes?.length || 0} nodes and ${snapshot.subgraph?.links?.length || 0} relationships`, margin, yPosition);
    doc.text('(Graph visualization not available)', margin, yPosition + 7);
    yPosition += 15;
  }

  // Overview Section
  if (snapshot.overview && snapshot.overview.nodes && snapshot.overview.nodes.length > 0) {
    checkPageBreak(30);
    doc.setFontSize(14);
    doc.setFont(undefined, 'bold');
    doc.text('Node Overview', margin, yPosition);
    yPosition += 8;

    doc.setFontSize(11);
    doc.setFont(undefined, 'normal');
    
    snapshot.overview.nodes.forEach((node, index) => {
      checkPageBreak(25);
      
      // Node header
      doc.setFont(undefined, 'bold');
      doc.text(`${index + 1}. ${node.name || node.key}`, margin, yPosition);
      yPosition += 7;
      
      doc.setFont(undefined, 'normal');
      if (node.type) {
        doc.text(`Type: ${node.type}`, margin + 5, yPosition);
        yPosition += 6;
      }
      
      if (node.summary) {
        const summaryHeight = addWrappedText(
          `Summary: ${node.summary}`, 
          margin + 5, 
          yPosition, 
          contentWidth - 5,
          10,
          5
        );
        yPosition += summaryHeight + 3;
      }
      
      yPosition += 3;
    });
  }

  // Citations Section
  if (snapshot.citations && Object.keys(snapshot.citations).length > 0) {
    checkPageBreak(30);
    doc.setFontSize(14);
    doc.setFont(undefined, 'bold');
    doc.text('Source Citations', margin, yPosition);
    yPosition += 8;

    doc.setFontSize(11);
    doc.setFont(undefined, 'normal');
    
    Object.values(snapshot.citations).forEach((nodeCitation, index) => {
      checkPageBreak(30);
      
      // Node header
      doc.setFont(undefined, 'bold');
      doc.text(`${index + 1}. ${nodeCitation.node_name || nodeCitation.node_key} (${nodeCitation.node_type})`, margin, yPosition);
      yPosition += 7;
      
      doc.setFont(undefined, 'normal');
      nodeCitation.citations.forEach((citation) => {
        checkPageBreak(15);
        
        const citationText = `${citation.source_doc}${citation.page ? `, page ${citation.page}` : ''} (${citation.type === 'verified_fact' ? 'Verified Fact' : citation.type === 'ai_insight' ? 'AI Insight' : 'Property'})`;
        const citationHeight = addWrappedText(
          `• ${citationText}`,
          margin + 5,
          yPosition,
          contentWidth - 5,
          10,
          5
        );
        yPosition += citationHeight + 2;
        
        if (citation.fact_text) {
          const factHeight = addWrappedText(
            `  "${citation.fact_text.substring(0, 100)}${citation.fact_text.length > 100 ? '...' : ''}"`,
            margin + 10,
            yPosition,
            contentWidth - 10,
            9,
            4
          );
          yPosition += factHeight + 2;
        }
        
        if (citation.verified_by) {
          doc.setFontSize(9);
          doc.text(`  Verified by: ${citation.verified_by}`, margin + 10, yPosition);
          yPosition += 5;
          doc.setFontSize(11);
        }
      });
      
      yPosition += 3;
    });
  }

  // Timeline Section
  checkPageBreak(30);
  doc.setFontSize(14);
  doc.setFont(undefined, 'bold');
  doc.text('Timeline', margin, yPosition);
  yPosition += 8;

  console.log('PDF Export - Timeline data:', {
    hasTimeline: !!snapshot.timeline,
    timelineLength: snapshot.timeline?.length || 0,
    timeline: snapshot.timeline
  });

  if (snapshot.timeline && Array.isArray(snapshot.timeline) && snapshot.timeline.length > 0) {
    doc.setFontSize(11);
    doc.setFont(undefined, 'normal');
    doc.text(`Total events: ${snapshot.timeline.length}`, margin, yPosition);
    yPosition += 8;
    
    // Draw a timeline line
    const timelineStartY = yPosition;
    const timelineLineX = margin + 5;
    const timelineLineWidth = 1;
    
    snapshot.timeline.forEach((event, index) => {
      checkPageBreak(30);
      
      // Timeline marker
      doc.setFillColor(100, 100, 100);
      doc.circle(timelineLineX, yPosition + 2, 2, 'F');
      
      // Event header
      doc.setFont(undefined, 'bold');
      const eventDate = event.date ? new Date(event.date).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric'
      }) : 'Unknown date';
      doc.text(`${eventDate}`, timelineLineX + 8, yPosition);
      
      // Event type
      doc.setFont(undefined, 'normal');
      doc.setFontSize(10);
      doc.text(`- ${event.type || 'Event'}`, timelineLineX + 50, yPosition);
      yPosition += 6;
      
      // Event name
      if (event.name) {
        const nameHeight = addWrappedText(
          event.name, 
          timelineLineX + 8, 
          yPosition, 
          contentWidth - (timelineLineX + 8 - margin),
          10,
          5
        );
        yPosition += nameHeight + 2;
      }
      
      // Event summary
      if (event.summary) {
        doc.setFontSize(9);
        const summaryHeight = addWrappedText(
          event.summary, 
          timelineLineX + 8, 
          yPosition, 
          contentWidth - (timelineLineX + 8 - margin),
          9,
          4
        );
        yPosition += summaryHeight + 2;
      }
      
      // Event amount if available
      if (event.amount) {
        doc.setFontSize(9);
        doc.text(`Amount: ${event.amount}`, timelineLineX + 8, yPosition);
        yPosition += 5;
      }
      
      yPosition += 5;
    });
    
    // Draw timeline line after all events
    doc.setDrawColor(150, 150, 150);
    doc.setLineWidth(timelineLineWidth);
    doc.line(timelineLineX, timelineStartY, timelineLineX, yPosition - 5);
    
  } else {
    doc.setFontSize(11);
    doc.setFont(undefined, 'normal');
    doc.text('No timeline events available for this snapshot.', margin, yPosition);
    yPosition += 10;
  }

  // Chat History Section
  if (snapshot.chat_history && snapshot.chat_history.length > 0) {
    checkPageBreak(30);
    doc.setFontSize(14);
    doc.setFont(undefined, 'bold');
    doc.text('AI Assistant Conversation', margin, yPosition);
    yPosition += 8;

    doc.setFontSize(11);
    
    // Process messages sequentially to handle async HTML rendering
    for (const message of snapshot.chat_history) {
      checkPageBreak(35);
      
      // Message role with styling
      doc.setFont(undefined, 'bold');
      const roleText = message.role === 'user' ? 'User Question' : 'AI Assistant Response';
      const roleColor = message.role === 'user' ? [59, 130, 246] : [6, 182, 212]; // Blue or cyan
      doc.setTextColor(...roleColor);
      doc.text(`${roleText}:`, margin, yPosition);
      doc.setTextColor(0, 0, 0); // Reset to black
      yPosition += 7;
      
      // Message content - convert markdown to HTML for AI responses
      doc.setFont(undefined, 'normal');
      let content = message.content || '';
      
      // For AI assistant messages, convert markdown to HTML and render
      if (message.role === 'assistant' || message.role === 'ai') {
        const htmlContent = markdownToHtml(content);
        
        // Render HTML content using jsPDF's html method if available
        // Otherwise, strip HTML tags and render as plain text
        try {
          // Create a temporary container for HTML rendering
          const tempDiv = document.createElement('div');
          tempDiv.style.position = 'absolute';
          tempDiv.style.left = '-9999px';
          tempDiv.style.width = `${(contentWidth - 5) * 3.779527559}px`; // Convert mm to px (1mm = 3.779527559px)
          tempDiv.style.padding = '10px';
          tempDiv.style.fontSize = '10pt';
          tempDiv.style.fontFamily = 'helvetica, arial, sans-serif';
          tempDiv.style.lineHeight = '1.5';
          tempDiv.style.color = '#000000';
          tempDiv.innerHTML = htmlContent;
          document.body.appendChild(tempDiv);
          
          // Use html2canvas to render HTML to image (await for async processing)
          try {
            const canvas = await html2canvas(tempDiv, {
              scale: 2,
              useCORS: true,
              logging: false,
              backgroundColor: '#ffffff',
              width: tempDiv.offsetWidth,
              height: tempDiv.scrollHeight,
              windowWidth: tempDiv.offsetWidth,
              windowHeight: tempDiv.scrollHeight
            });
            
            const imgData = canvas.toDataURL('image/png');
            const imgWidth = contentWidth - 5;
            const imgHeight = (canvas.height * imgWidth) / canvas.width;
            
            // Check if we need a new page
            if (yPosition + imgHeight > pageHeight - margin) {
              doc.addPage();
              yPosition = margin;
            }
            
            doc.addImage(imgData, 'PNG', margin + 5, yPosition, imgWidth, imgHeight);
            yPosition += imgHeight + 3;
            
            // Clean up
            document.body.removeChild(tempDiv);
          } catch (err) {
            console.warn('Failed to render HTML content, falling back to plain text:', err);
            // Fallback to plain text
            const plainText = stripHtmlTags(htmlContent);
            const contentHeight = addWrappedText(
              plainText, 
              margin + 5, 
              yPosition, 
              contentWidth - 5,
              10,
              5
            );
            yPosition += contentHeight + 3;
            if (document.body.contains(tempDiv)) {
              document.body.removeChild(tempDiv);
            }
          }
        } catch (err) {
          console.warn('Error rendering HTML, using plain text:', err);
          // Fallback to plain text if HTML rendering fails
          const plainText = stripHtmlTags(markdownToHtml(content));
          const contentHeight = addWrappedText(
            plainText, 
            margin + 5, 
            yPosition, 
            contentWidth - 5,
            10,
            5
          );
          yPosition += contentHeight + 3;
        }
      } else {
        // For user messages, render as plain text
        const contentHeight = addWrappedText(
          content, 
          margin + 5, 
          yPosition, 
          contentWidth - 5,
          10,
          5
        );
        yPosition += contentHeight + 3;
      }
      
      // Additional context for AI responses
      if (message.role === 'assistant' && message.contextMode) {
        doc.setFontSize(9);
        doc.setFont(undefined, 'italic');
        doc.setTextColor(100, 100, 100);
        doc.text(`Context: ${message.contextMode}`, margin + 5, yPosition);
        yPosition += 5;
        doc.setTextColor(0, 0, 0);
        doc.setFontSize(11);
      }
      
      yPosition += 5; // Space between messages
    }
  }

  // Save PDF
  const fileName = `${snapshot.name || 'snapshot'}_${new Date().toISOString().split('T')[0]}.pdf`;
  doc.save(fileName);
}

