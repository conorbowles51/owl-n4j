import React, { useState, useEffect, useRef } from 'react';
import { X, BookOpen, ChevronDown, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

/**
 * DocumentationViewer Component
 * 
 * Displays the user guide documentation in a modal
 */
export default function DocumentationViewer({ isOpen, onClose }) {
  const [content, setContent] = useState('');
  const [toc, setToc] = useState([]);
  const [expandedSections, setExpandedSections] = useState(new Set());
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

  // Extract table of contents from markdown - now extracts h2 and h3 headers
  const extractTOC = (markdown) => {
    const tocItems = [];
    const lines = markdown.split('\n');
    let skipUntilHR = false;
    let currentSection = null;
    
    // Helper function to create anchor-friendly ID from text
    const createId = (text) => {
      return text
        .toLowerCase()
        .replace(/[^\w\s-]/g, '') // Remove special characters
        .replace(/\s+/g, '-') // Replace spaces with hyphens
        .replace(/-+/g, '-') // Replace multiple hyphens with single
        .trim();
    };
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      
      // Start skipping when we hit the TOC header
      if (line.match(/^##?\s+Table of Contents/i)) {
        skipUntilHR = true;
        continue;
      }
      
      // Stop skipping when we hit the horizontal rule after TOC
      if (skipUntilHR) {
        if (line.match(/^---$/)) {
          skipUntilHR = false;
          continue;
        }
        // Skip everything in TOC section
        continue;
      }
      
      // Extract h2 headers (main sections)
      const h2Match = line.match(/^##\s+(.+)$/);
      if (h2Match) {
        const text = h2Match[1].trim();
        const id = createId(text);
        currentSection = {
          text,
          id,
          level: 1,
          subsections: []
        };
        tocItems.push(currentSection);
        continue;
      }
      
      // Extract h3 headers (subsections)
      const h3Match = line.match(/^###\s+(.+)$/);
      if (h3Match && currentSection) {
        const text = h3Match[1].trim();
        const id = createId(text);
        currentSection.subsections.push({
          text,
          id,
          level: 2
        });
      }
    }
    
    return tocItems;
  };

  // Remove table of contents section from markdown content
  const removeTOC = (markdown) => {
    const lines = markdown.split('\n');
    let result = [];
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
          // Include the next section header, but skip the horizontal rule
          if (line.match(/^---$/)) {
            continue; // Skip the horizontal rule too
          }
        } else {
          continue; // Skip TOC content lines
        }
      }
      
      result.push(line);
    }
    
    return result.join('\n');
  };
  
  // Helper function to create anchor-friendly ID from text
  const createId = (text) => {
    return text
      .toLowerCase()
      .replace(/[^\w\s-]/g, '') // Remove special characters
      .replace(/\s+/g, '-') // Replace spaces with hyphens
      .replace(/-+/g, '-') // Replace multiple hyphens with single
      .trim();
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
                  toc.map((item, index) => {
                    const hasSubsections = item.subsections && item.subsections.length > 0;
                    const isExpanded = expandedSections.has(item.id);
                    
                    return (
                      <div key={index} className="space-y-0.5">
                        <button
                          onClick={() => {
                            if (hasSubsections) {
                              // Toggle expansion
                              setExpandedSections(prev => {
                                const next = new Set(prev);
                                if (next.has(item.id)) {
                                  next.delete(item.id);
                                } else {
                                  next.add(item.id);
                                }
                                return next;
                              });
                            }
                            // Always scroll to section when clicking
                            scrollToSection(item.id);
                          }}
                          className="w-full text-left px-3 py-1.5 text-sm text-light-700 hover:bg-white hover:text-owl-blue-700 rounded transition-colors flex items-center gap-2"
                        >
                          {hasSubsections && (
                            <span className="flex-shrink-0">
                              {isExpanded ? (
                                <ChevronDown className="w-3 h-3" />
                              ) : (
                                <ChevronRight className="w-3 h-3" />
                              )}
                            </span>
                          )}
                          <span className="flex-1">{item.text}</span>
                        </button>
                        {hasSubsections && isExpanded && (
                          <div className="ml-4 space-y-0.5">
                            {item.subsections.map((subsection, subIndex) => (
                              <button
                                key={subIndex}
                                onClick={() => scrollToSection(subsection.id)}
                                className="w-full text-left px-3 py-1.5 text-xs text-light-600 hover:bg-white hover:text-owl-blue-600 rounded transition-colors"
                              >
                                {subsection.text}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
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
                className="prose prose-sm prose-headings:text-owl-blue-900 prose-headings:font-bold prose-p:text-light-700 prose-p:leading-relaxed prose-p:mb-4 prose-strong:text-dark-800 prose-strong:font-semibold prose-a:text-owl-blue-600 prose-a:no-underline hover:prose-a:underline prose-code:bg-light-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:font-mono prose-pre:bg-light-100 prose-pre:border prose-pre:border-light-300 prose-pre:rounded-lg prose-pre:p-4 prose-pre:overflow-x-auto prose-pre:my-4 prose-ul:list-disc prose-ul:ml-6 prose-ul:mb-4 prose-ul:space-y-1 prose-ol:list-decimal prose-ol:ml-6 prose-ol:mb-4 prose-ol:space-y-1 prose-li:mb-1 prose-hr:my-6 prose-hr:border-light-200 max-w-none"
              >
                <ReactMarkdown
                  components={{
                    h1: ({ node, children, ...props }) => {
                      const text = String(children);
                      const id = createId(text);
                      return <h1 id={id} className="text-3xl font-bold text-owl-blue-900 mt-10 mb-6 scroll-mt-4" {...props}>{children}</h1>;
                    },
                    h2: ({ node, children, ...props }) => {
                      const text = String(children);
                      const id = createId(text);
                      return <h2 id={id} className="text-2xl font-bold text-owl-blue-900 mt-8 mb-4 border-b border-light-200 pb-2 scroll-mt-4" {...props}>{children}</h2>;
                    },
                    h3: ({ node, children, ...props }) => {
                      const text = String(children);
                      const id = createId(text);
                      return <h3 id={id} className="text-xl font-bold text-owl-blue-900 mt-6 mb-3 scroll-mt-4" {...props}>{children}</h3>;
                    },
                    h4: ({ node, children, ...props }) => {
                      const text = String(children);
                      const id = createId(text);
                      return <h4 id={id} className="text-lg font-bold text-owl-blue-900 mt-5 mb-2 scroll-mt-4" {...props}>{children}</h4>;
                    },
                    h5: ({ node, children, ...props }) => {
                      const text = String(children);
                      const id = createId(text);
                      return <h5 id={id} className="text-base font-bold text-owl-blue-900 mt-4 mb-2 scroll-mt-4" {...props}>{children}</h5>;
                    },
                    h6: ({ node, children, ...props }) => {
                      const text = String(children);
                      const id = createId(text);
                      return <h6 id={id} className="text-sm font-bold text-owl-blue-900 mt-3 mb-2 scroll-mt-4" {...props}>{children}</h6>;
                    },
                    a: ({ node, href, children, ...props }) => {
                      if (href?.startsWith('#')) {
                        return (
                          <a 
                            href={href} 
                            className="text-owl-blue-600 hover:underline cursor-pointer"
                            onClick={(e) => {
                              e.preventDefault();
                              const id = href.substring(1);
                              scrollToSection(id);
                            }}
                            {...props}
                          >
                            {children}
                          </a>
                        );
                      }
                      return (
                        <a 
                          href={href} 
                          className="text-owl-blue-600 hover:underline" 
                          target="_blank" 
                          rel="noopener noreferrer"
                          {...props}
                        >
                          {children}
                        </a>
                      );
                    },
                    code: ({ node, inline, className, children, ...props }) => {
                      if (inline) {
                        return (
                          <code className="bg-light-100 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                            {children}
                          </code>
                        );
                      }
                      return (
                        <code className="text-sm font-mono" {...props}>
                          {children}
                        </code>
                      );
                    },
                  }}
                >
                  {removeTOC(content)}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

