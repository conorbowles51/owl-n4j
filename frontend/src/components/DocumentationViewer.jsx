import React, { useState, useEffect, useRef } from 'react';
import { X, BookOpen } from 'lucide-react';

/**
 * DocumentationViewer Component
 * 
 * Displays the user guide documentation in a modal
 */
export default function DocumentationViewer({ isOpen, onClose }) {
  const [content, setContent] = useState('');
  const [toc, setToc] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const contentRef = useRef(null);
  const scrollContainerRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      loadDocumentation();
    }
  }, [isOpen]);

  // Handle anchor link clicks and scroll to sections
  useEffect(() => {
    if (!isOpen || !contentRef.current || !scrollContainerRef.current) return;

    const handleClick = (e) => {
      const link = e.target.closest('a');
      if (!link) return;

      const href = link.getAttribute('href');
      if (!href) return;

      // Handle internal anchor links (starting with #)
      if (href.startsWith('#')) {
        e.preventDefault();
        e.stopPropagation();
        const id = href.substring(1);
        scrollToSection(id);
      }
      // External links will open in new tab (default behavior)
    };

    const container = contentRef.current;
    container.addEventListener('click', handleClick);
    return () => container.removeEventListener('click', handleClick);
  }, [isOpen, content]);

  const scrollToSection = (id) => {
    if (!contentRef.current || !scrollContainerRef.current) return;
    
    const element = contentRef.current.querySelector(`#${id}`);
    if (element && scrollContainerRef.current) {
      const scrollContainer = scrollContainerRef.current;
      const containerRect = scrollContainer.getBoundingClientRect();
      const elementRect = element.getBoundingClientRect();
      const scrollTop = scrollContainer.scrollTop;
      const elementTop = elementRect.top - containerRect.top + scrollTop;
      
      scrollContainer.scrollTo({
        top: elementTop - 20,
        behavior: 'smooth'
      });
    }
  };

  const loadDocumentation = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/USER_GUIDE.md');
      if (!response.ok) {
        throw new Error('Failed to load documentation');
      }
      const text = await response.text();
      setContent(text);
      
      // Extract table of contents
      const tocItems = extractTOC(text);
      setToc(tocItems);
    } catch (err) {
      console.error('Failed to load documentation:', err);
      setError(err.message || 'Failed to load documentation');
    } finally {
      setLoading(false);
    }
  };

  // Extract table of contents from markdown
  const extractTOC = (markdown) => {
    const tocItems = [];
    const lines = markdown.split('\n');
    let inTOC = false;
    
    for (const line of lines) {
      // Check if we're in the TOC section
      if (line.match(/^##?\s+Table of Contents/i)) {
        inTOC = true;
        continue;
      }
      
      // Stop when we hit the first section after TOC (but not horizontal rules)
      if (inTOC && line.match(/^##\s+/) && !line.match(/^---/)) {
        break;
      }
      
      // Extract TOC items (numbered list items with links)
      if (inTOC && line.match(/^\d+\.\s+\[(.+)\]\(#(.+)\)/)) {
        const match = line.match(/^\d+\.\s+\[(.+)\]\(#(.+)\)/);
        if (match) {
          tocItems.push({
            text: match[1],
            id: match[2],
            level: 1
          });
        }
      }
    }
    
    return tocItems;
  };

  // Convert markdown to HTML (simple conversion)
  const markdownToHtml = (markdown) => {
    // Remove table of contents section from content before processing
    const lines = markdown.split('\n');
    let html = '';
    let skipTOC = false;
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      
      // Start skipping when we hit the TOC header
      if (line.match(/^##?\s+Table of Contents/i)) {
        skipTOC = true;
        continue;
      }
      
      // Stop skipping when we hit the next section (##) or horizontal rule (---)
      if (skipTOC) {
        if (line.match(/^##\s+/) || line.match(/^---$/)) {
          skipTOC = false;
          // Include the horizontal rule or next section header
          if (line.match(/^---$/)) {
            continue; // Skip the horizontal rule too
          }
        } else {
          continue; // Skip TOC content lines
        }
      }
      
      html += line + '\n';
    }
    
    // Helper function to create anchor-friendly ID from text
    const createId = (text) => {
      return text
        .toLowerCase()
        .replace(/[^\w\s-]/g, '') // Remove special characters
        .replace(/\s+/g, '-') // Replace spaces with hyphens
        .replace(/-+/g, '-') // Replace multiple hyphens with single
        .trim();
    };
    
    // Headers with IDs for anchor links
    html = html.replace(/^### (.*$)/gim, (match, text) => {
      const id = createId(text);
      return `<h3 id="${id}" class="text-lg font-semibold text-owl-blue-900 mt-6 mb-3 scroll-mt-4">${text}</h3>`;
    });
    html = html.replace(/^## (.*$)/gim, (match, text) => {
      const id = createId(text);
      return `<h2 id="${id}" class="text-xl font-bold text-owl-blue-900 mt-8 mb-4 border-b border-light-200 pb-2 scroll-mt-4">${text}</h2>`;
    });
    html = html.replace(/^# (.*$)/gim, (match, text) => {
      const id = createId(text);
      return `<h1 id="${id}" class="text-2xl font-bold text-owl-blue-900 mt-8 mb-4 scroll-mt-4">${text}</h1>`;
    });
    
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-dark-800">$1</strong>');
    
    // Italic
    html = html.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>');
    
    // Code blocks
    html = html.replace(/```[\s\S]*?```/g, (match) => {
      const code = match.replace(/```/g, '').trim();
      return `<pre class="bg-light-100 border border-light-300 rounded-lg p-4 overflow-x-auto my-4"><code class="text-sm font-mono">${code}</code></pre>`;
    });
    
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code class="bg-light-100 px-1.5 py-0.5 rounded text-sm font-mono">$1</code>');
    
    // Links - handle internal anchor links differently
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, text, href) => {
      if (href.startsWith('#')) {
        // Internal anchor link - no target="_blank"
        return `<a href="${href}" class="text-owl-blue-600 hover:underline cursor-pointer">${text}</a>`;
      } else {
        // External link - open in new tab
        return `<a href="${href}" class="text-owl-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">${text}</a>`;
      }
    });
    
    // Lists
    html = html.replace(/^\d+\.\s+(.*$)/gim, '<li class="ml-6 mb-1">$1</li>');
    html = html.replace(/^-\s+(.*$)/gim, '<li class="ml-6 mb-1 list-disc">$1</li>');
    html = html.replace(/(<li.*<\/li>)/s, '<ul class="list-disc ml-6 mb-4 space-y-1">$1</ul>');
    
    // Paragraphs
    html = html.split('\n\n').map(para => {
      if (para.trim() && !para.match(/^<[hul]/) && !para.match(/^<pre/)) {
        return `<p class="mb-4 text-light-700 leading-relaxed">${para.trim()}</p>`;
      }
      return para;
    }).join('\n');
    
    // Horizontal rules
    html = html.replace(/^---$/gim, '<hr class="my-6 border-light-200" />');
    
    return html;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-full max-w-6xl max-h-[90vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-200 bg-light-50 flex-shrink-0">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-owl-blue-700" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              User Guide
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-light-200 text-light-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Two-column layout */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left sidebar - Table of Contents */}
          <div className="w-64 border-r border-light-200 bg-light-50 flex-shrink-0 overflow-y-auto">
            <div className="p-4 sticky top-0">
              <h3 className="text-sm font-semibold text-owl-blue-900 mb-4 uppercase tracking-wide">
                Contents
              </h3>
              <nav className="space-y-0.5">
                {toc.length > 0 ? (
                  toc.map((item, index) => (
                    <button
                      key={index}
                      onClick={() => scrollToSection(item.id)}
                      className="w-full text-left px-3 py-1.5 text-sm text-light-700 hover:bg-white hover:text-owl-blue-700 rounded transition-colors"
                    >
                      {item.text}
                    </button>
                  ))
                ) : (
                  <div className="text-xs text-light-500 px-3 py-2">
                    Loading contents...
                  </div>
                )}
              </nav>
            </div>
          </div>

          {/* Right content - Scrollable */}
          <div 
            ref={scrollContainerRef}
            className="flex-1 overflow-y-auto p-6"
          >
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="text-light-600">Loading documentation...</div>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                {error}
              </div>
            ) : (
              <div 
                ref={contentRef}
                className="prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: markdownToHtml(content) }}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

