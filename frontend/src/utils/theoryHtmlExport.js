/**
 * Theory HTML Export Utility
 * 
 * Exports theories to HTML format with all attached items, graphs, and timelines
 * Includes Owl Consultancy Group branding and logo
 */

/**
 * Load logo as base64 data URL
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
 * Load document summary
 */
async function loadDocumentSummary(filename, caseId) {
  try {
    const { evidenceAPI } = await import('../services/api');
    const result = await evidenceAPI.getSummary(filename, caseId);
    return result.has_summary && result.summary ? result.summary : null;
  } catch (err) {
    console.warn('Failed to load document summary:', err);
    return null;
  }
}

/**
 * Load document/image as base64
 */
async function loadDocumentAsBase64(evidenceId) {
  try {
    const response = await fetch(`/api/evidence/${evidenceId}/file`);
    if (!response.ok) return null;
    const blob = await response.blob();
    
    // Check if it's an image
    if (blob.type.startsWith('image/')) {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.onerror = () => resolve(null);
        reader.readAsDataURL(blob);
      });
    }
    return null;
  } catch (err) {
    console.warn('Failed to load document as base64:', err);
    return null;
  }
}

/**
 * Export theory to HTML
 * 
 * @param {Object} theory - The theory data
 * @param {Object} attachedItems - All attached items (evidence, witnesses, notes, etc.)
 * @param {Object} graphData - Theory graph data (nodes and links)
 * @param {Array} timelineEvents - Timeline events
 * @param {string} graphCanvasDataUrl - Optional base64 data URL of graph canvas
 * @param {string} timelineCanvasDataUrl - Optional base64 data URL of timeline canvas
 * @param {string} mapCanvasDataUrl - Optional base64 data URL of map canvas
 * @param {string} caseId - Case ID for loading document summaries and images
 */
export async function exportTheoryToHTML(
  theory,
  attachedItems,
  graphData = null,
  timelineEvents = [],
  graphCanvasDataUrl = null,
  timelineCanvasDataUrl = null,
  mapCanvasDataUrl = null,
  caseId = null
) {
  // Load logo as base64
  const logoBase64 = await loadLogoAsBase64();
  
  // Load document summaries and images
  const documentData = {};
  if (caseId) {
    // Load summaries and images for evidence
    if (attachedItems.evidence && attachedItems.evidence.length > 0) {
      for (const file of attachedItems.evidence) {
        if (file.id) {
          const [summary, imageData] = await Promise.all([
            loadDocumentSummary(file.original_filename || file.filename, caseId),
            loadDocumentAsBase64(file.id),
          ]);
          documentData[file.id] = { summary, imageData };
        }
      }
    }
    
    // Load summaries and images for documents
    if (attachedItems.documents && attachedItems.documents.length > 0) {
      for (const doc of attachedItems.documents) {
        if (doc.id) {
          const [summary, imageData] = await Promise.all([
            loadDocumentSummary(doc.original_filename || doc.filename, caseId),
            loadDocumentAsBase64(doc.id),
          ]);
          documentData[doc.id] = { summary, imageData };
        }
      }
    }
  }
  // Format date helper
  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown date';
    try {
      const date = new Date(dateString);
      return date.toLocaleString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  // Format short date
  const formatShortDate = (dateString) => {
    if (!dateString) return 'Unknown date';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  // Escape HTML
  const escapeHtml = (text) => {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  };

  // Build HTML sections
  let html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Investigation Theory: ${escapeHtml(theory.title || 'Untitled Theory')} - Owl Consultancy Group</title>
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.6;
      color: #1f2937;
      background: #ffffff;
    }
    
    .container {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0;
    }
    
    /* Cover Page */
    .cover-page {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      background: linear-gradient(135deg, #0f2f4a 0%, #1d4d76 100%);
      color: white;
      text-align: center;
      padding: 3rem;
      page-break-after: always;
    }
    
    .cover-logo {
      max-width: 200px;
      height: auto;
      margin-bottom: 2rem;
      filter: brightness(0) invert(1);
    }
    
    .cover-title {
      font-size: 2.5rem;
      font-weight: bold;
      margin-bottom: 1rem;
      text-transform: uppercase;
      letter-spacing: 2px;
    }
    
    .cover-subtitle {
      font-size: 1.2rem;
      opacity: 0.9;
      margin-bottom: 3rem;
    }
    
    .cover-theory-title {
      font-size: 2rem;
      font-weight: 600;
      margin-bottom: 2rem;
      padding: 2rem;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      backdrop-filter: blur(10px);
    }
    
    .cover-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      justify-content: center;
      margin-top: 2rem;
    }
    
    .meta-badge {
      padding: 0.5rem 1rem;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 20px;
      font-size: 0.9rem;
    }
    
    /* Content Page */
    .content-page {
      padding: 3rem 2rem;
      page-break-before: always;
    }
    
    /* Section Headers */
    .section-header {
      font-size: 1.75rem;
      font-weight: bold;
      color: #1d4d76;
      margin-top: 3rem;
      margin-bottom: 1.5rem;
      padding-bottom: 0.5rem;
      border-bottom: 3px solid #2d6fa8;
    }
    
    .subsection-header {
      font-size: 1.25rem;
      font-weight: 600;
      color: #245e8f;
      margin-top: 2rem;
      margin-bottom: 1rem;
    }
    
    /* Theory Details */
    .theory-details {
      background: #f8fafc;
      padding: 2rem;
      border-radius: 8px;
      margin-bottom: 2rem;
      border-left: 4px solid #357dbe;
    }
    
    .detail-item {
      margin-bottom: 1rem;
    }
    
    .detail-label {
      font-weight: 600;
      color: #1d4d76;
      margin-bottom: 0.25rem;
    }
    
    .detail-value {
      color: #4b5563;
    }
    
    /* Lists */
    .list-item {
      padding: 0.75rem;
      margin-bottom: 0.5rem;
      background: #ffffff;
      border-left: 3px solid #357dbe;
      border-radius: 4px;
    }
    
    /* Evidence/Witness/Document Cards */
    .item-card {
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    
    .item-card-header {
      display: flex;
      justify-content: space-between;
      align-items: start;
      margin-bottom: 1rem;
    }
    
    .item-title {
      font-size: 1.1rem;
      font-weight: 600;
      color: #1d4d76;
    }
    
    .item-meta {
      font-size: 0.875rem;
      color: #6b7280;
      margin-top: 0.5rem;
    }
    
    /* Graph Section */
    .graph-container {
      text-align: center;
      margin: 2rem 0;
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 1.5rem;
    }
    
    .graph-image {
      max-width: 100%;
      height: auto;
      border-radius: 4px;
    }
    
    /* Timeline */
    .timeline {
      position: relative;
      padding-left: 2rem;
      margin: 2rem 0;
    }
    
    .timeline::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 2px;
      background: #357dbe;
    }
    
    .timeline-event {
      position: relative;
      margin-bottom: 2rem;
      padding-left: 2rem;
    }
    
    .timeline-event::before {
      content: '';
      position: absolute;
      left: -1.5rem;
      top: 0.25rem;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #357dbe;
      border: 2px solid #ffffff;
      box-shadow: 0 0 0 2px #357dbe;
    }
    
    .timeline-event-header {
      display: flex;
      align-items: center;
      gap: 1rem;
      margin-bottom: 0.5rem;
    }
    
    .timeline-event-date {
      font-size: 0.875rem;
      color: #6b7280;
      font-weight: 500;
    }
    
    .timeline-event-type {
      display: inline-block;
      padding: 0.25rem 0.75rem;
      background: #e8f0f7;
      color: #1d4d76;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    
    .timeline-event-title {
      font-weight: 600;
      color: #1f2937;
      margin-bottom: 0.25rem;
    }
    
    .timeline-event-desc {
      color: #6b7280;
      font-size: 0.9rem;
    }
    
    /* Footer */
    .footer {
      margin-top: 4rem;
      padding-top: 2rem;
      border-top: 1px solid #e5e7eb;
      text-align: center;
      color: #6b7280;
      font-size: 0.875rem;
    }
    
    /* Print Styles */
    @media print {
      .cover-page {
        page-break-after: always;
      }
      
      .content-page {
        page-break-before: always;
      }
      
      .section-header {
        page-break-after: avoid;
      }
      
      .item-card {
        page-break-inside: avoid;
      }
    }
  </style>
</head>
<body>
  <!-- Cover Page -->
  <div class="cover-page">
    ${logoBase64 ? `<img src="${logoBase64}" alt="Owl Consultancy Group" class="cover-logo" />` : '<div class="cover-logo" style="font-size: 3rem; font-weight: bold;">🦉</div>'}
    <div class="cover-title">Investigation Theory</div>
    <div class="cover-subtitle">Owl Consultancy Group</div>
    <div class="cover-theory-title">${escapeHtml(theory.title || 'Untitled Theory')}</div>
    <div class="cover-meta">
      ${theory.type ? `<span class="meta-badge">Type: ${escapeHtml(theory.type)}</span>` : ''}
      ${theory.confidence_score !== undefined && theory.confidence_score !== null ? `<span class="meta-badge">Confidence: ${theory.confidence_score}/100</span>` : ''}
      ${theory.created_at ? `<span class="meta-badge">Created: ${formatShortDate(theory.created_at)}</span>` : ''}
    </div>
  </div>
  
  <!-- Content Page -->
  <div class="content-page">
    <div class="container">
      <!-- Theory Details -->
      <div class="theory-details">
        ${theory.hypothesis ? `
          <div class="detail-item">
            <div class="detail-label">Hypothesis</div>
            <div class="detail-value">${escapeHtml(theory.hypothesis)}</div>
          </div>
        ` : ''}
        
        ${theory.supporting_evidence && theory.supporting_evidence.length > 0 ? `
          <div class="detail-item">
            <div class="detail-label">Supporting Evidence</div>
            <ul style="list-style: none; padding-left: 0;">
              ${theory.supporting_evidence.map(ev => `<li class="list-item">${escapeHtml(ev)}</li>`).join('')}
            </ul>
          </div>
        ` : ''}
        
        ${theory.counter_arguments && theory.counter_arguments.length > 0 ? `
          <div class="detail-item">
            <div class="detail-label">Counter Arguments</div>
            <ul style="list-style: none; padding-left: 0;">
              ${theory.counter_arguments.map(arg => `<li class="list-item">${escapeHtml(arg)}</li>`).join('')}
            </ul>
          </div>
        ` : ''}
        
        ${theory.next_steps && theory.next_steps.length > 0 ? `
          <div class="detail-item">
            <div class="detail-label">Next Steps</div>
            <ul style="list-style: none; padding-left: 0;">
              ${theory.next_steps.map(step => `<li class="list-item">${escapeHtml(step)}</li>`).join('')}
            </ul>
          </div>
        ` : ''}
      </div>
      
      <!-- Evidence -->
      ${attachedItems.evidence && attachedItems.evidence.length > 0 ? `
        <div class="section-header">Attached Evidence</div>
        ${attachedItems.evidence.map((file, idx) => {
          const data = documentData[file.id] || {};
          return `
          <div class="item-card">
            <div class="item-card-header">
              <div>
                <div class="item-title">${idx + 1}. ${escapeHtml(file.original_filename || file.filename || `Evidence ${file.id}`)}</div>
                <div class="item-meta">
                  ${file.size ? `Size: ${(file.size / 1024).toFixed(1)} KB` : ''}
                  ${file.processed_at ? ` • Processed: ${formatShortDate(file.processed_at)}` : ''}
                  ${file.status ? ` • Status: ${escapeHtml(file.status)}` : ''}
                </div>
                ${data.summary ? `
                  <div class="detail-value" style="margin-top: 1rem; padding: 1rem; background: #f8fafc; border-radius: 4px; border-left: 3px solid #357dbe;">
                    <div class="detail-label" style="margin-bottom: 0.5rem;">Summary</div>
                    ${escapeHtml(data.summary)}
                  </div>
                ` : ''}
                ${data.imageData ? `
                  <div style="margin-top: 1rem;">
                    <img src="${data.imageData}" alt="${escapeHtml(file.original_filename || file.filename)}" style="max-width: 100%; height: auto; border-radius: 4px; border: 1px solid #e5e7eb;" />
                  </div>
                ` : ''}
              </div>
            </div>
          </div>
        `;
        }).join('')}
      ` : ''}
      
      <!-- Witnesses -->
      ${attachedItems.witnesses && attachedItems.witnesses.length > 0 ? `
        <div class="section-header">Attached Witnesses</div>
        ${attachedItems.witnesses.map((witness, idx) => `
          <div class="item-card">
            <div class="item-title">${idx + 1}. ${escapeHtml(witness.name || 'Unknown Witness')}</div>
            <div class="item-meta">
              ${witness.role ? `Role: ${escapeHtml(witness.role)}` : ''}
              ${witness.organization ? ` • Organization: ${escapeHtml(witness.organization)}` : ''}
              ${witness.status ? ` • Status: ${escapeHtml(witness.status)}` : ''}
              ${witness.credibility_rating ? ` • Credibility: ${witness.credibility_rating}/5` : ''}
              ${witness.interviews && witness.interviews.length > 0 ? ` • Interviews: ${witness.interviews.length}` : ''}
            </div>
          </div>
        `).join('')}
      ` : ''}
      
      <!-- Notes -->
      ${attachedItems.notes && attachedItems.notes.length > 0 ? `
        <div class="section-header">Attached Notes</div>
        ${attachedItems.notes.map((note, idx) => {
          const noteContent = note.content || '';
          return `
          <div class="item-card">
            <div class="item-title">Note ${idx + 1}</div>
            ${note.created_at ? `<div class="item-meta" style="margin-bottom: 0.5rem;">Created: ${formatShortDate(note.created_at)}</div>` : ''}
            ${note.updated_at && note.updated_at !== note.created_at ? `<div class="item-meta" style="margin-bottom: 0.5rem;">Updated: ${formatShortDate(note.updated_at)}</div>` : ''}
            <div class="detail-value" style="white-space: pre-wrap; margin-top: 0.5rem; padding: 1rem; background: #f8fafc; border-radius: 4px; border-left: 3px solid #357dbe;">
              ${escapeHtml(noteContent)}
            </div>
          </div>
        `;
        }).join('')}
      ` : ''}
      
      <!-- Tasks -->
      ${attachedItems.tasks && attachedItems.tasks.length > 0 ? `
        <div class="section-header">Attached Tasks</div>
        ${attachedItems.tasks.map((task, idx) => `
          <div class="item-card">
            <div class="item-title">${idx + 1}. ${escapeHtml(task.title || 'Untitled Task')}</div>
            ${task.description ? `<div class="detail-value" style="margin-top: 0.5rem;">${escapeHtml(task.description)}</div>` : ''}
            <div class="item-meta">
              ${task.priority ? `Priority: ${escapeHtml(task.priority)}` : ''}
              ${task.due_date ? ` • Due: ${formatShortDate(task.due_date)}` : ''}
              ${task.status ? ` • Status: ${escapeHtml(task.status)}` : ''}
            </div>
          </div>
        `).join('')}
      ` : ''}
      
      <!-- Documents -->
      ${attachedItems.documents && attachedItems.documents.length > 0 ? `
        <div class="section-header">Attached Documents</div>
        ${attachedItems.documents.map((document, idx) => {
          const data = documentData[document.id] || {};
          const summary = data.summary || document.summary;
          return `
          <div class="item-card">
            <div class="item-title">${idx + 1}. ${escapeHtml(document.original_filename || document.filename || `Document ${document.id}`)}</div>
            ${summary ? `
              <div class="detail-value" style="margin-top: 1rem; padding: 1rem; background: #f8fafc; border-radius: 4px; border-left: 3px solid #357dbe;">
                <div class="detail-label" style="margin-bottom: 0.5rem;">Summary</div>
                ${escapeHtml(summary)}
              </div>
            ` : ''}
            ${data.imageData ? `
              <div style="margin-top: 1rem;">
                <img src="${data.imageData}" alt="${escapeHtml(document.original_filename || document.filename)}" style="max-width: 100%; height: auto; border-radius: 4px; border: 1px solid #e5e7eb;" />
              </div>
            ` : ''}
          </div>
        `;
        }).join('')}
      ` : ''}
      
      <!-- Snapshots -->
      ${attachedItems.snapshots && attachedItems.snapshots.length > 0 ? `
        <div class="section-header">Attached Snapshots</div>
        ${attachedItems.snapshots.map((snapshot, idx) => {
          const overviewNodes = snapshot.overview?.nodes ?? (Array.isArray(snapshot.overview) ? snapshot.overview : null);
          const subgraphNodes = snapshot.subgraph?.nodes;
          const nodes = overviewNodes && overviewNodes.length ? overviewNodes : (subgraphNodes && subgraphNodes.length ? subgraphNodes : []);
          const timeline = Array.isArray(snapshot.timeline) ? snapshot.timeline : [];
          const chatHistory = Array.isArray(snapshot.chat_history) ? snapshot.chat_history : [];
          const citations = snapshot.citations && typeof snapshot.citations === 'object' ? snapshot.citations : {};
          const citationValues = Object.values(citations).filter(cite => {
            if (typeof cite === 'string') return true;
            if (cite && typeof cite === 'object') {
              if ('node_key' in cite || 'node_name' in cite || 'node_type' in cite) return false;
              return true;
            }
            return false;
          });
          
          return `
          <div class="item-card">
            <div class="item-title">${idx + 1}. ${escapeHtml(snapshot.name || 'Unnamed Snapshot')}</div>
            <div class="item-meta" style="margin-bottom: 1rem;">
              ${snapshot.timestamp ? `Created: ${formatShortDate(snapshot.timestamp)}` : ''}
              ${nodes.length > 0 ? ` • ${nodes.length} nodes` : ''}
              ${timeline.length > 0 ? ` • ${timeline.length} timeline events` : ''}
              ${chatHistory.length > 0 ? ` • ${chatHistory.length} chat messages` : ''}
            </div>
            
            ${snapshot.notes ? `
              <div class="detail-item" style="margin-bottom: 1rem;">
                <div class="detail-label">Notes</div>
                <div class="detail-value" style="white-space: pre-wrap;">${escapeHtml(snapshot.notes)}</div>
              </div>
            ` : ''}
            
            ${snapshot.ai_overview ? `
              <div class="detail-item" style="margin-bottom: 1rem;">
                <div class="detail-label">AI Overview</div>
                <div class="detail-value" style="white-space: pre-wrap;">${escapeHtml(snapshot.ai_overview)}</div>
              </div>
            ` : ''}
            
            ${nodes.length > 0 ? `
              <div class="detail-item" style="margin-bottom: 1rem;">
                <div class="detail-label">Node Overview (${nodes.length} nodes)</div>
                <div style="max-height: 300px; overflow-y: auto; margin-top: 0.5rem;">
                  ${nodes.slice(0, 50).map((node, i) => {
                    const nodeName = node?.name || node?.node_name || node?.id || node?.node_key || 'Unnamed node';
                    const nodeSummary = node?.summary || node?.notes || '';
                    return `
                      <div style="padding: 0.5rem; margin-bottom: 0.5rem; background: #ffffff; border-left: 3px solid #357dbe; border-radius: 4px;">
                        <div style="font-weight: 600; color: #1d4d76; margin-bottom: 0.25rem;">${escapeHtml(nodeName)}</div>
                        ${nodeSummary ? `<div style="font-size: 0.875rem; color: #6b7280;">${escapeHtml(nodeSummary)}</div>` : ''}
                      </div>
                    `;
                  }).join('')}
                  ${nodes.length > 50 ? `<div style="padding: 0.5rem; color: #6b7280; font-style: italic;">... and ${nodes.length - 50} more nodes</div>` : ''}
                </div>
              </div>
            ` : ''}
            
            ${citationValues.length > 0 ? `
              <div class="detail-item" style="margin-bottom: 1rem;">
                <div class="detail-label">Source Citations (${citationValues.length})</div>
                <div style="max-height: 200px; overflow-y: auto; margin-top: 0.5rem;">
                  ${citationValues.slice(0, 20).map((cite, i) => {
                    let citationText = '';
                    if (typeof cite === 'string') {
                      citationText = cite;
                    } else if (cite && typeof cite === 'object') {
                      citationText = cite.fact_text || cite.text || cite.summary || cite.description || JSON.stringify(cite);
                    }
                    return `
                      <div style="padding: 0.5rem; margin-bottom: 0.5rem; background: #f8fafc; border-radius: 4px; font-size: 0.875rem;">
                        ${escapeHtml(citationText)}
                      </div>
                    `;
                  }).join('')}
                  ${citationValues.length > 20 ? `<div style="padding: 0.5rem; color: #6b7280; font-style: italic;">... and ${citationValues.length - 20} more citations</div>` : ''}
                </div>
              </div>
            ` : ''}
            
            ${chatHistory.length > 0 ? `
              <div class="detail-item" style="margin-bottom: 1rem;">
                <div class="detail-label">Chat History (${chatHistory.length} messages)</div>
                <div style="max-height: 400px; overflow-y: auto; margin-top: 0.5rem;">
                  ${chatHistory.map((msg, i) => `
                    <div style="padding: 0.75rem; margin-bottom: 0.5rem; background: ${msg.role === 'user' ? '#e8f0f7' : '#ffffff'}; border-left: 3px solid ${msg.role === 'user' ? '#357dbe' : '#9333ea'}; border-radius: 4px;">
                      <div style="font-weight: 600; color: #1d4d76; margin-bottom: 0.25rem; font-size: 0.875rem;">
                        ${msg.role === 'user' ? 'User' : 'Assistant'}
                      </div>
                      <div style="white-space: pre-wrap; font-size: 0.875rem; color: #4b5563;">
                        ${escapeHtml(msg.content || '')}
                      </div>
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : ''}
            
            ${timeline.length > 0 ? `
              <div class="detail-item" style="margin-bottom: 1rem;">
                <div class="detail-label">Timeline Events (${timeline.length})</div>
                <div style="max-height: 300px; overflow-y: auto; margin-top: 0.5rem;">
                  ${timeline.slice(0, 30).map((event, i) => {
                    let eventText = '';
                    if (typeof event === 'string') {
                      eventText = event;
                    } else if (event && typeof event === 'object') {
                      eventText = event.summary || event.description || event.text || JSON.stringify(event);
                    }
                    return `
                      <div style="padding: 0.5rem; margin-bottom: 0.5rem; background: #ffffff; border-left: 3px solid #9333ea; border-radius: 4px; font-size: 0.875rem;">
                        ${escapeHtml(eventText)}
                      </div>
                    `;
                  }).join('')}
                  ${timeline.length > 30 ? `<div style="padding: 0.5rem; color: #6b7280; font-style: italic;">... and ${timeline.length - 30} more events</div>` : ''}
                </div>
              </div>
            ` : ''}
          </div>
        `;
        }).join('')}
      ` : ''}
      
      <!-- Graph -->
      ${graphData && graphData.nodes && graphData.nodes.length > 0 ? `
        <div class="section-header">Theory Graph</div>
        <div class="graph-container">
          <p style="margin-bottom: 1rem; color: #6b7280; font-weight: 600;">
            Nodes: ${graphData.nodes.length} • Relationships: ${graphData.links ? graphData.links.length : 0}
          </p>
          ${graphCanvasDataUrl ? `
            <img src="${graphCanvasDataUrl}" alt="Theory Graph Visualization" class="graph-image" style="border: 2px solid #357dbe; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);" />
          ` : `
            <div style="padding: 2rem; background: #f3f4f6; border-radius: 4px; color: #6b7280; border: 1px solid #e5e7eb;">
              <p style="margin-bottom: 1rem;">Graph visualization not available. ${graphData.nodes.length} nodes found.</p>
              <div style="max-height: 300px; overflow-y: auto;">
                ${graphData.nodes.slice(0, 50).map((node, i) => {
                  const nodeName = node.name || node.key || 'Unnamed node';
                  const nodeType = node.type || 'Unknown';
                  return `
                    <div style="padding: 0.5rem; margin-bottom: 0.5rem; background: #ffffff; border-left: 3px solid #357dbe; border-radius: 4px;">
                      <div style="font-weight: 600; color: #1d4d76;">${escapeHtml(nodeName)}</div>
                      <div style="font-size: 0.875rem; color: #6b7280;">Type: ${escapeHtml(nodeType)}</div>
                    </div>
                  `;
                }).join('')}
                ${graphData.nodes.length > 50 ? `<div style="padding: 0.5rem; color: #6b7280; font-style: italic;">... and ${graphData.nodes.length - 50} more nodes</div>` : ''}
              </div>
            </div>
          `}
        </div>
      ` : ''}
      
      <!-- Timeline -->
      ${timelineEvents && timelineEvents.length > 0 ? `
        <div class="section-header">Timeline</div>
        ${timelineCanvasDataUrl ? `
          <div class="graph-container" style="margin-bottom: 2rem;">
            <h3 class="subsection-header">Visual Timeline</h3>
            <img src="${timelineCanvasDataUrl}" alt="Timeline Visualization" class="graph-image" />
          </div>
        ` : ''}
        ${mapCanvasDataUrl ? `
          <div class="graph-container" style="margin-bottom: 2rem;">
            <h3 class="subsection-header">Map Visualization</h3>
            <img src="${mapCanvasDataUrl}" alt="Map Visualization" class="graph-image" />
          </div>
        ` : ''}
        <h3 class="subsection-header">Timeline Events</h3>
        <div class="timeline">
          ${timelineEvents.map(event => `
            <div class="timeline-event">
              <div class="timeline-event-header">
                <span class="timeline-event-date">${formatDate(event.date)}</span>
                <span class="timeline-event-type">${escapeHtml(event.type || 'Event')}</span>
                ${event.thread ? `<span class="timeline-event-type" style="background: #e9d5ff; color: #9333ea;">${escapeHtml(event.thread)}</span>` : ''}
              </div>
              <div class="timeline-event-title">${escapeHtml(event.title || 'Untitled Event')}</div>
              ${event.description ? `<div class="timeline-event-desc">${escapeHtml(event.description)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      ` : ''}
      
      <!-- Footer -->
      <div class="footer">
        <p>Owl Consultancy Group - Investigation Platform</p>
        <p style="margin-top: 0.5rem; font-size: 0.75rem;">Generated on ${formatDate(new Date().toISOString())}</p>
      </div>
    </div>
  </div>
</body>
</html>`;

  // Create blob and download
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `Theory_${(theory.title || 'Untitled').replace(/[^a-z0-9]/gi, '_')}_${new Date().toISOString().split('T')[0]}.html`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
