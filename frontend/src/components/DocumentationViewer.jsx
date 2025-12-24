import React, { useState, useEffect, useRef } from 'react';
import { X, BookOpen, ChevronDown, ChevronRight, Search, ChevronUp, ChevronLeft } from 'lucide-react';
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
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [currentResultIndex, setCurrentResultIndex] = useState(-1);
  const [highlightedContent, setHighlightedContent] = useState('');
  const [activeSectionId, setActiveSectionId] = useState(null);
  const contentRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const searchResultsRefs = useRef([]);

  useEffect(() => {
    if (isOpen) {
      loadDocumentation();
    } else {
      // Reset active section when closing
      setActiveSectionId(null);
    }
  }, [isOpen]);

  // Set initial active section when content loads
  useEffect(() => {
    if (!isOpen || !content || !contentRef.current || activeSectionId) return;
    
    // Set the first section as active when content first loads
    const firstHeading = contentRef.current.querySelector('h2, h3, h4, h5, h6');
    if (firstHeading && firstHeading.id) {
      setActiveSectionId(firstHeading.id);
      expandTOCToSection(firstHeading.id);
    }
  }, [content, isOpen, activeSectionId]);

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

  // Find which section (h2, h3, or h4) contains a given element
  const findSectionForElement = (element) => {
    if (!element || !contentRef.current) return null;
    
    let current = element;
    while (current && current !== contentRef.current) {
      if (current.tagName && ['H2', 'H3', 'H4', 'H5', 'H6'].includes(current.tagName)) {
        return current.id;
      }
      current = current.parentElement;
    }
    
    // If not found, look for nearest heading above
    const allHeadings = contentRef.current.querySelectorAll('h2, h3, h4, h5, h6');
    let nearestHeading = null;
    let nearestDistance = Infinity;
    
    const elementTop = element.getBoundingClientRect().top;
    
    allHeadings.forEach(heading => {
      const headingTop = heading.getBoundingClientRect().top;
      const distance = elementTop - headingTop;
      if (distance >= 0 && distance < nearestDistance) {
        nearestDistance = distance;
        nearestHeading = heading;
      }
    });
    
    return nearestHeading ? nearestHeading.id : null;
  };

  // Expand TOC sections to reveal a given section ID
  const expandTOCToSection = (sectionId) => {
    if (!sectionId) return;
    
    // Find the section in TOC structure
    for (const section of toc) {
      if (section.id === sectionId) {
        // Expand this section
        setExpandedSections(prev => new Set([...prev, section.id]));
        return;
      }
      
      // Check subsections
      for (const subsection of section.subsections || []) {
        if (subsection.id === sectionId) {
          // Expand parent section and subsection
          const subsectionKey = `${section.id}-${subsection.id}`;
          setExpandedSections(prev => new Set([...prev, section.id, subsectionKey]));
          return;
        }
        
        // Check sub-subsections
        for (const subsubsection of subsection.subsubsections || []) {
          if (subsubsection.id === sectionId) {
            // Expand all parent sections
            const subsectionKey = `${section.id}-${subsection.id}`;
            setExpandedSections(prev => new Set([...prev, section.id, subsectionKey]));
            return;
          }
        }
      }
    }
  };

  const scrollToSection = (id) => {
    if (!contentRef.current || !scrollContainerRef.current) return;
    
    // Expand TOC to show this section
    expandTOCToSection(id);
    
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
      
      // Set as active section
      setActiveSectionId(id);
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

  // Extract table of contents from markdown - extracts h2, h3, and h4 headers
  const extractTOC = (markdown) => {
    const tocItems = [];
    const lines = markdown.split('\n');
    let skipUntilHR = false;
    let currentSection = null;
    let currentSubsection = null;
    
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
        currentSubsection = null; // Reset current subsection
        tocItems.push(currentSection);
        continue;
      }
      
      // Extract h3 headers (subsections)
      const h3Match = line.match(/^###\s+(.+)$/);
      if (h3Match && currentSection) {
        const text = h3Match[1].trim();
        const id = createId(text);
        currentSubsection = {
          text,
          id,
          level: 2,
          subsubsections: []
        };
        currentSection.subsections.push(currentSubsection);
        continue;
      }
      
      // Extract h4 headers (sub-subsections)
      const h4Match = line.match(/^####\s+(.+)$/);
      if (h4Match && currentSubsection) {
        const text = h4Match[1].trim();
        const id = createId(text);
        currentSubsection.subsubsections.push({
          text,
          id,
          level: 3
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

  // Search functionality
  useEffect(() => {
    if (!searchTerm.trim() || !contentRef.current) {
      setSearchResults([]);
      setCurrentResultIndex(-1);
      // Remove all highlights
      removeHighlights();
      return;
    }

    // Wait for content to render, then perform search
    const timeoutId = setTimeout(() => {
      performSearch(searchTerm);
    }, 100);

    return () => clearTimeout(timeoutId);
  }, [searchTerm, content]);

  const performSearch = (term) => {
    if (!contentRef.current) return;

    const container = contentRef.current;
    const textContent = container.textContent || '';
    const regex = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    const matches = [];
    let match;

    // Find all matches in text content
    while ((match = regex.exec(textContent)) !== null) {
      matches.push({
        index: match.index,
        length: match[0].length,
        text: match[0]
      });
    }

    setSearchResults(matches);
    
    if (matches.length > 0) {
      setCurrentResultIndex(0);
      // Highlight and scroll after DOM update
      setTimeout(() => {
        highlightAllMatches(term);
        scrollToSearchResult(0);
      }, 150);
    } else {
      setCurrentResultIndex(-1);
      removeHighlights();
    }
  };

  const highlightAllMatches = (term) => {
    if (!contentRef.current || !term.trim()) return;

    const container = contentRef.current;
    const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedTerm})`, 'gi');
    
    // Use a tree walker to find all text nodes
    const walker = document.createTreeWalker(
      container,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: (node) => {
          // Skip code blocks, pre tags, script, style, and existing marks
          let parent = node.parentElement;
          while (parent && parent !== container) {
            const tagName = parent.tagName;
            if (tagName === 'CODE' || tagName === 'PRE' || 
                tagName === 'SCRIPT' || tagName === 'STYLE' ||
                tagName === 'MARK') {
              return NodeFilter.FILTER_REJECT;
            }
            parent = parent.parentElement;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    const textNodes = [];
    let node;
    while (node = walker.nextNode()) {
      if (node.textContent.trim() && regex.test(node.textContent)) {
        textNodes.push(node);
      }
    }

    // Process text nodes in reverse to maintain indices
    for (let i = textNodes.length - 1; i >= 0; i--) {
      const textNode = textNodes[i];
      const text = textNode.textContent;
      const parent = textNode.parentNode;
      
      if (parent && !parent.hasAttribute('data-search-highlighted') && regex.test(text)) {
        // Create highlighted version
        const highlightedHTML = text.replace(
          regex, 
          '<mark class="bg-yellow-200 text-yellow-900 px-0.5 rounded search-highlight">$1</mark>'
        );
        const wrapper = document.createElement('span');
        wrapper.setAttribute('data-search-highlighted', 'true');
        wrapper.innerHTML = highlightedHTML;
        parent.replaceChild(wrapper, textNode);
      }
    }
  };

  const removeHighlights = () => {
    if (!contentRef.current) return;
    
    // Remove all mark elements
    const marks = contentRef.current.querySelectorAll('mark.search-highlight');
    marks.forEach(mark => {
      const parent = mark.parentNode;
      if (parent) {
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
      }
    });
    
    // Remove wrapper spans
    const wrappers = contentRef.current.querySelectorAll('[data-search-highlighted]');
    wrappers.forEach(wrapper => {
      const parent = wrapper.parentNode;
      if (parent) {
        while (wrapper.firstChild) {
          parent.insertBefore(wrapper.firstChild, wrapper);
        }
        parent.removeChild(wrapper);
      }
    });
    
    // Normalize all text nodes
    if (contentRef.current) {
      contentRef.current.normalize();
    }
  };

  const scrollToSearchResult = (index) => {
    if (searchResults.length === 0 || index < 0 || index >= searchResults.length) return;
    if (!contentRef.current || !scrollContainerRef.current) return;

    const highlights = contentRef.current.querySelectorAll('mark.search-highlight');
    if (highlights.length === 0) return;

    // Remove previous current highlight
    highlights.forEach(mark => {
      mark.classList.remove('search-result-current', 'bg-yellow-400', 'ring-2', 'ring-yellow-600');
      mark.classList.add('bg-yellow-200');
    });

    // Highlight current result
    if (highlights[index]) {
      const currentMark = highlights[index];
      currentMark.classList.remove('bg-yellow-200');
      currentMark.classList.add('search-result-current', 'bg-yellow-400', 'ring-2', 'ring-yellow-600');
      
      // Find which section contains this result
      const sectionId = findSectionForElement(currentMark);
      if (sectionId) {
        // Expand TOC to show this section
        expandTOCToSection(sectionId);
        // Set as active section
        setActiveSectionId(sectionId);
      }
      
      // Scroll to the highlighted element
      const scrollContainer = scrollContainerRef.current;
      const containerRect = scrollContainer.getBoundingClientRect();
      const markRect = currentMark.getBoundingClientRect();
      const scrollTop = scrollContainer.scrollTop;
      const markTop = markRect.top - containerRect.top + scrollTop;

      scrollContainer.scrollTo({
        top: markTop - 100, // Offset to show context above
        behavior: 'smooth'
      });
    }
  };

  const handleSearchChange = (e) => {
    const term = e.target.value;
    setSearchTerm(term);
  };

  const handleNextResult = () => {
    if (searchResults.length === 0) return;
    const nextIndex = (currentResultIndex + 1) % searchResults.length;
    setCurrentResultIndex(nextIndex);
    scrollToSearchResult(nextIndex);
  };

  const handlePreviousResult = () => {
    if (searchResults.length === 0) return;
    const prevIndex = currentResultIndex <= 0 ? searchResults.length - 1 : currentResultIndex - 1;
    setCurrentResultIndex(prevIndex);
    scrollToSearchResult(prevIndex);
  };

  const handleClearSearch = () => {
    setSearchTerm('');
    setSearchResults([]);
    setCurrentResultIndex(-1);
    removeHighlights();
  };

  // Track active section based on scroll position
  useEffect(() => {
    if (!isOpen || !contentRef.current || !scrollContainerRef.current) return;

    const container = scrollContainerRef.current;
    const headings = contentRef.current.querySelectorAll('h2, h3, h4, h5, h6');
    
    if (headings.length === 0) return;

    const observerOptions = {
      root: container,
      rootMargin: '-120px 0px -60% 0px', // Trigger when heading is near the top (accounting for header)
      threshold: [0, 0.25, 0.5, 0.75, 1.0]
    };

    const observerCallback = (entries) => {
      // Find the heading that's closest to the top of the viewport
      let activeHeading = null;
      let minDistanceFromTop = Infinity;
      const containerRect = container.getBoundingClientRect();
      const viewportTop = containerRect.top + 120; // Account for header offset

      entries.forEach(entry => {
        if (entry.isIntersecting && entry.target.id) {
          const rect = entry.boundingClientRect;
          const headingTop = rect.top;
          
          // Only consider headings that are reasonably close to the viewport top
          // (not way above or way below)
          const distanceFromTop = headingTop - viewportTop;
          
          // Prefer headings that are at or just above the viewport top
          // But ignore ones that are too far above (more than 200px)
          if (distanceFromTop <= 50 && distanceFromTop >= -200) {
            const absDistance = Math.abs(distanceFromTop);
            if (absDistance < minDistanceFromTop) {
              minDistanceFromTop = absDistance;
              activeHeading = entry.target;
            }
          }
        }
      });

      // Only update if we found an active heading
      // This ensures the previous active section stays highlighted if no new one is found
      if (activeHeading && activeHeading.id) {
        const sectionId = activeHeading.id;
        // Update the active section - this will persist until changed
        setActiveSectionId(prevId => {
          if (prevId !== sectionId) {
            expandTOCToSection(sectionId);
            return sectionId;
          }
          // Keep the current section highlighted (return current value)
          return prevId;
        });
      }
      // Important: If no active heading is found, we do NOT update the state
      // This means the previous active section will remain highlighted
    };

    const observer = new IntersectionObserver(observerCallback, observerOptions);
    
    headings.forEach(heading => {
      if (heading.id) {
        observer.observe(heading);
      }
    });

    // Also handle scroll events for more responsive tracking
    const handleScroll = () => {
      const containerRect = container.getBoundingClientRect();
      const viewportTopOffset = 120; // Offset for header and search bar
      const viewportTop = containerRect.top + viewportTopOffset;
      const maxDistanceAbove = 150; // Maximum distance above viewport to consider

      // Find the heading that's closest to the viewport top
      let activeHeading = null;
      let closestHeading = null;
      let minDistance = Infinity;

      headings.forEach(heading => {
        if (!heading.id) return;
        
        // Get position relative to viewport
        const headingRect = heading.getBoundingClientRect();
        const headingTop = headingRect.top;
        const headingBottom = headingRect.bottom;
        
        // Calculate distance from viewport top
        const distanceFromTop = headingTop - viewportTop;
        
        // Get heading level (h2 = 2, h3 = 3, etc.) for prioritization
        const headingLevel = parseInt(heading.tagName.charAt(1)) || 6;
        
        // Consider headings that are:
        // 1. Above the viewport but not too far (within maxDistanceAbove)
        // 2. At or just below the viewport top (within 100px)
        if (distanceFromTop <= 100 && distanceFromTop >= -maxDistanceAbove) {
          const absDistance = Math.abs(distanceFromTop);
          // Prioritize by distance, but if distances are similar (within 20px), prefer higher level headings (h2 over h3)
          const adjustedDistance = absDistance - (headingLevel === 2 ? 20 : headingLevel === 3 ? 10 : 0);
          if (adjustedDistance < minDistance) {
            minDistance = adjustedDistance;
            closestHeading = heading;
          }
        }
        
        // Also track headings that are currently visible in the viewport
        // and are above the viewport top (for sections that span multiple viewport heights)
        if (headingTop <= viewportTop && headingBottom > containerRect.top) {
          // This heading is visible and spans across the viewport top
          // Prefer higher level headings when multiple are visible
          if (!activeHeading) {
            activeHeading = heading;
          } else {
            const currentTop = activeHeading.getBoundingClientRect().top;
            const currentLevel = parseInt(activeHeading.tagName.charAt(1)) || 6;
            // Prefer heading that's closer to viewport top, or if similar, prefer higher level
            if (headingTop > currentTop || (Math.abs(headingTop - currentTop) < 50 && headingLevel < currentLevel)) {
              activeHeading = heading;
            }
          }
        }
      });

      // Prefer the closest heading, otherwise use the active heading
      const finalHeading = closestHeading || activeHeading;
      
      // If we're at the very top of the document, use the first heading
      if (!finalHeading && container.scrollTop < 50 && headings.length > 0) {
        activeHeading = headings[0];
      } else if (finalHeading) {
        activeHeading = finalHeading;
      }
      
      // Only update if we found an active heading
      // This ensures the previous active section stays highlighted if no new one is found
      if (activeHeading && activeHeading.id) {
        const sectionId = activeHeading.id;
        // Update the active section - this will persist until changed
        setActiveSectionId(prevId => {
          if (prevId !== sectionId) {
            expandTOCToSection(sectionId);
            return sectionId;
          }
          // Keep the current section highlighted (return current value)
          return prevId;
        });
      }
      // Important: If no active heading is found, we do NOT update the state
      // This means the previous active section will remain highlighted
    };

    // Throttle scroll handler for better performance
    let scrollTimeout = null;
    const throttledHandleScroll = () => {
      if (scrollTimeout) return;
      scrollTimeout = setTimeout(() => {
        handleScroll();
        scrollTimeout = null;
      }, 50); // Update every 50ms
    };

    container.addEventListener('scroll', throttledHandleScroll, { passive: true });
    // Initial check
    handleScroll();

    return () => {
      observer.disconnect();
      container.removeEventListener('scroll', throttledHandleScroll);
      if (scrollTimeout !== null) {
        clearTimeout(scrollTimeout);
        scrollTimeout = null;
      }
    };
  }, [isOpen, content, toc]);

  // Handle keyboard shortcuts for search navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      // Only handle if search has results
      if (searchResults.length === 0) return;
      
      // Enter to go to next result (when search input is focused)
      if (e.key === 'Enter' && e.target.tagName === 'INPUT' && !e.shiftKey) {
        e.preventDefault();
        const nextIndex = (currentResultIndex + 1) % searchResults.length;
        setCurrentResultIndex(nextIndex);
        setTimeout(() => scrollToSearchResult(nextIndex), 50);
      }
      
      // Shift+Enter to go to previous result
      if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.shiftKey) {
        e.preventDefault();
        const prevIndex = currentResultIndex <= 0 ? searchResults.length - 1 : currentResultIndex - 1;
        setCurrentResultIndex(prevIndex);
        setTimeout(() => scrollToSearchResult(prevIndex), 50);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, searchResults.length, currentResultIndex]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-full max-w-6xl max-h-[90vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex flex-col border-b border-light-200 bg-light-50 flex-shrink-0">
          <div className="flex items-center justify-between px-6 py-4">
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
          
          {/* Search Bar */}
          <div className="px-6 pb-4">
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-light-500" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={handleSearchChange}
                  placeholder="Search documentation..."
                  className="w-full pl-10 pr-4 py-2 text-sm border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                />
                {searchTerm && (
                  <button
                    onClick={handleClearSearch}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-light-400 hover:text-light-600"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              
              {searchResults.length > 0 && (
                <div className="flex items-center gap-2 bg-white border border-light-300 rounded-lg px-2 py-1">
                  <button
                    onClick={handlePreviousResult}
                    disabled={searchResults.length === 0}
                    className="p-1 hover:bg-light-100 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Previous result"
                  >
                    <ChevronUp className="w-4 h-4 text-light-600" />
                  </button>
                  <span className="text-xs text-light-600 min-w-[60px] text-center">
                    {currentResultIndex + 1} / {searchResults.length}
                  </span>
                  <button
                    onClick={handleNextResult}
                    disabled={searchResults.length === 0}
                    className="p-1 hover:bg-light-100 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Next result"
                  >
                    <ChevronDown className="w-4 h-4 text-light-600" />
                  </button>
                </div>
              )}
            </div>
            {searchTerm && searchResults.length === 0 && (
              <p className="text-xs text-light-500 mt-2 ml-1">No results found</p>
            )}
          </div>
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
                        <div className="flex items-center gap-1">
                          {hasSubsections ? (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
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
                              }}
                              className="p-1 hover:bg-light-200 rounded transition-colors flex-shrink-0"
                              title={isExpanded ? "Collapse section" : "Expand section"}
                            >
                              {isExpanded ? (
                                <ChevronDown className="w-3 h-3 text-light-600" />
                              ) : (
                                <ChevronRight className="w-3 h-3 text-light-600" />
                              )}
                            </button>
                          ) : (
                            <span className="w-5 flex-shrink-0" />
                          )}
                          <button
                            onClick={() => {
                              // Always scroll to section when clicking text
                              scrollToSection(item.id);
                            }}
                            className={`flex-1 text-left px-2 py-1.5 text-sm rounded transition-colors ${
                              activeSectionId === item.id
                                ? 'bg-owl-blue-100 text-owl-blue-900 font-semibold'
                                : 'text-light-700 hover:bg-white hover:text-owl-blue-700'
                            }`}
                          >
                            {item.text}
                          </button>
                        </div>
                        {hasSubsections && isExpanded && (
                          <div className="ml-4 space-y-0.5">
                            {item.subsections.map((subsection, subIndex) => {
                              const hasSubSubsections = subsection.subsubsections && subsection.subsubsections.length > 0;
                              const subsectionKey = `${item.id}-${subsection.id}`;
                              const isSubExpanded = expandedSections.has(subsectionKey);
                              
                              return (
                                <div key={subIndex} className="space-y-0.5">
                                  <div className="flex items-center gap-1">
                                    {hasSubSubsections ? (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          // Toggle subsection expansion
                                          setExpandedSections(prev => {
                                            const next = new Set(prev);
                                            if (next.has(subsectionKey)) {
                                              next.delete(subsectionKey);
                                            } else {
                                              next.add(subsectionKey);
                                            }
                                            return next;
                                          });
                                        }}
                                        className="p-1 hover:bg-light-200 rounded transition-colors flex-shrink-0"
                                        title={isSubExpanded ? "Collapse subsection" : "Expand subsection"}
                                      >
                                        {isSubExpanded ? (
                                          <ChevronDown className="w-2.5 h-2.5 text-light-600" />
                                        ) : (
                                          <ChevronRight className="w-2.5 h-2.5 text-light-600" />
                                        )}
                                      </button>
                                    ) : (
                                      <span className="w-4 flex-shrink-0" />
                                    )}
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        // Always scroll to subsection when clicking text
                                        scrollToSection(subsection.id);
                                      }}
                                      className={`flex-1 text-left px-2 py-1.5 text-xs rounded transition-colors ${
                                        activeSectionId === subsection.id
                                          ? 'bg-owl-blue-100 text-owl-blue-900 font-semibold'
                                          : 'text-light-600 hover:bg-white hover:text-owl-blue-600'
                                      }`}
                                    >
                                      {subsection.text}
                                    </button>
                                  </div>
                                  {hasSubSubsections && isSubExpanded && (
                                    <div className="ml-4 space-y-0.5">
                                      {subsection.subsubsections.map((subsubsection, subSubIndex) => (
                                        <button
                                          key={subSubIndex}
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            scrollToSection(subsubsection.id);
                                          }}
                                          className={`w-full text-left px-3 py-1 text-xs rounded transition-colors ${
                                            activeSectionId === subsubsection.id
                                              ? 'bg-owl-blue-100 text-owl-blue-900 font-semibold'
                                              : 'text-light-500 hover:bg-white hover:text-owl-blue-500'
                                          }`}
                                        >
                                          {subsubsection.text}
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
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
                    // Wrap text nodes to allow highlighting
                    p: ({ node, children, ...props }) => {
                      return <p {...props}>{children}</p>;
                    },
                    li: ({ node, children, ...props }) => {
                      return <li {...props}>{children}</li>;
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

