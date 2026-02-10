import React, { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ChevronRight, X, ChevronsRight, MessageSquare, CheckSquare, Square, Filter, Search, Check, ChevronLeft, ChevronsLeft, Merge, Trash2, Edit, Plus, Link2 } from 'lucide-react';
import { parseSearchQuery, getHighlightTerms } from '../utils/searchParser';
import { highlightMatchedText } from '../utils/highlightText';
import MergeEntitiesModal from './MergeEntitiesModal';
import EditNodeModal from './EditNodeModal';
import AddNodeModal from './AddNodeModal';
import DeleteConfirmationModal from './DeleteConfirmationModal';
import CreateRelationshipModal from './CreateRelationshipModal';

const PREFERRED_COLUMN_ORDER = ['key', 'name', 'type', 'summary', 'notes'];
const RELATIONS_COLUMN_WIDTH = '7rem';
const CHAT_COLUMN_WIDTH = '4rem';
const RELATIONS_COLUMN_STICKY = {
  position: 'sticky',
  right: 0,
  minWidth: RELATIONS_COLUMN_WIDTH,
  width: RELATIONS_COLUMN_WIDTH,
  backgroundColor: '#e8ecf0', // Solid light blue-gray background for control column
  boxShadow: '-2px 0 4px rgba(0,0,0,0.1), inset 1px 0 0 rgba(0,0,0,0.05)',
  borderLeft: '2px solid #cbd5e1',
};
const CHAT_COLUMN_STICKY = {
  position: 'sticky',
  right: RELATIONS_COLUMN_WIDTH,
  minWidth: CHAT_COLUMN_WIDTH,
  width: CHAT_COLUMN_WIDTH,
  backgroundColor: '#e8ecf0', // Solid light blue-gray background for control column
  boxShadow: '-2px 0 4px rgba(0,0,0,0.1), inset 1px 0 0 rgba(0,0,0,0.05)',
  borderLeft: '2px solid #cbd5e1',
};

/**
 * Get color for entity type
 */
function getEntityTypeColor(type) {
  if (!type) return '#6b7280'; // gray
  const typeLower = String(type).toLowerCase();
  const colorMap = {
    person: '#3b82f6', // blue
    company: '#10b981', // green
    organization: '#10b981',
    location: '#f59e0b', // amber
    address: '#f59e0b',
    event: '#8b5cf6', // purple
    document: '#ef4444', // red
    email: '#ec4899', // pink
    phone: '#06b6d4', // cyan
    date: '#6366f1', // indigo
    financial: '#14b8a6', // teal
    account: '#14b8a6',
  };
  return colorMap[typeLower] || '#6b7280';
}

/**
 * Get color for relation type
 */
function getRelationTypeColor(type) {
  if (!type) return '#9ca3af'; // gray
  const typeLower = String(type).toLowerCase().replace(/_/g, '');
  const colorMap = {
    relatedto: '#6b7280',
    worksfor: '#3b82f6',
    owns: '#10b981',
    locatedin: '#f59e0b',
    contacted: '#ec4899',
    mentionedin: '#ef4444',
    partof: '#8b5cf6',
    connectedto: '#6366f1',
    associatedwith: '#14b8a6',
  };
  return colorMap[typeLower] || '#9ca3af';
}

/**
 * Flatten a node into a key-value map for table display.
 * Includes top-level fields and properties; stringifies objects/arrays.
 */
function flattenNode(node) {
  const out = {};
  if (!node) return out;
  for (const k of ['key', 'id', 'name', 'type', 'summary', 'notes']) {
    const v = node[k];
    if (v !== undefined && v !== null) out[k] = v;
  }
  const props = node.properties || {};
  for (const k of Object.keys(props)) {
    if (out[k] !== undefined) continue;
    const v = props[k];
    if (v !== undefined && v !== null) {
      out[k] = typeof v === 'object' ? JSON.stringify(v) : v;
    }
  }
  return out;
}

/**
 * Collect all column keys from nodes and return sorted list.
 */
function collectColumns(nodes) {
  const set = new Set();
  for (const n of nodes) {
    const flat = flattenNode(n);
    for (const k of Object.keys(flat)) set.add(k);
  }
  const rest = [...set].filter((k) => !PREFERRED_COLUMN_ORDER.includes(k)).sort();
  const ordered = PREFERRED_COLUMN_ORDER.filter((k) => set.has(k));
  return [...ordered, ...rest];
}

/**
 * Get related nodes for a given node key from graph links.
 * Returns { nodes, relationTypes } where relationTypes[key] = [type, ...].
 */
function getRelated(nodeKey, nodes, links) {
  const nodeMap = new Map(nodes.map((n) => [n.key, n]));
  const relTypes = {};
  const seen = new Set();
  const related = [];
  for (const l of links || []) {
    const src = typeof l.source === 'object' ? l.source?.key : l.source;
    const tgt = typeof l.target === 'object' ? l.target?.key : l.target;
    const type = l.type || 'RELATED_TO';
    let other = null;
    if (src === nodeKey) other = tgt;
    else if (tgt === nodeKey) other = src;
    if (!other || other === nodeKey) continue;
    const n = nodeMap.get(other);
    if (!n) continue;
    if (!relTypes[other]) relTypes[other] = [];
    if (!relTypes[other].includes(type)) relTypes[other].push(type);
    if (seen.has(other)) continue;
    seen.add(other);
    related.push(n);
  }
  return { nodes: related, relationTypes: relTypes };
}

/**
 * GraphTableView
 *
 * Tabular view of graph nodes. Rows = nodes, columns = node fields.
 * Each row can expand relations to the right; new panels show related nodes
 * with same columns. Collapse removes that panel and all panels to the right.
 */
export default function GraphTableView({
  graphData,
  onNodeClick,
  selectedNodeKeys = [],
  className = '',
  onOpenChat, // Callback to open chat with selected nodes
  isChatOpen = false, // Whether chat panel is open
  resultGraphData = null, // AI assistant result graph data
  tableViewState = null, // Persisted table view state
  onTableViewStateChange = null, // Callback to save table view state
  searchTerm = '', // Current filter/search query for match highlighting in cells
  caseId = null, // Case ID for API calls
  onMergeNodes = null, // Callback to merge nodes: (sourceKey, targetKey, mergedData) => Promise
  onDeleteNodes = null, // Callback to delete nodes: (nodes) => Promise
  onUpdateNode = null, // Callback to update node: (nodeKey, updates) => Promise
  onNodeCreated = null, // Callback when node is created: (nodeKey) => void
  onGraphRefresh = null, // Callback to refresh graph data: () => Promise
}) {
  const { nodes: rawNodes = [], links = [] } = graphData || {};
  // Always create new array reference to ensure React detects changes
  const nodes = useMemo(() => [...rawNodes], [rawNodes]);
  const searchHighlightTerms = useMemo(() => {
    const t = (searchTerm || '').trim();
    if (!t) return [];
    const ast = parseSearchQuery(t);
    return ast ? getHighlightTerms(ast) : [];
  }, [searchTerm]);
  // Signature of current row set so we reliably sync main panel when filter/data changes
  const nodesSignature = useMemo(
    () => (nodes || []).map((n) => n.key).sort().join(','),
    [nodes]
  );

  // Initialize panels - restore from persisted state if available, otherwise create main panel
  const [panels, setPanels] = useState(() => {
    if (tableViewState?.panels && Array.isArray(tableViewState.panels) && tableViewState.panels.length > 0) {
      return tableViewState.panels;
    }
    return nodes.length ? [{ type: 'main', nodes, parentIndex: null, parentRowKey: null, relationTypes: {}, breadcrumb: [] }] : [];
  });
  
  const [highlightedKeys, setHighlightedKeys] = useState(new Set()); // Temporary highlights (e.g., from breadcrumb clicks)
  const [breadcrumbHighlightedKeys, setBreadcrumbHighlightedKeys] = useState(new Set()); // Persistent highlights for breadcrumb rows
  const [selectedRowKeys, setSelectedRowKeys] = useState(new Set(selectedNodeKeys));
  const [checkboxSelectedKeys, setCheckboxSelectedKeys] = useState(new Set()); // Checkbox-selected rows for bulk operations
  
  // Modal states
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showCreateRelationshipModal, setShowCreateRelationshipModal] = useState(false);
  const [mergeEntity1, setMergeEntity1] = useState(null);
  const [mergeEntity2, setMergeEntity2] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [relationshipSourceNodes, setRelationshipSourceNodes] = useState([]);
  
  // Restore selectedPanels from persisted state
  const [selectedPanels, setSelectedPanels] = useState(() => {
    if (tableViewState?.selectedPanels instanceof Set) {
      return new Set(tableViewState.selectedPanels);
    }
    if (Array.isArray(tableViewState?.selectedPanels)) {
      return new Set(tableViewState.selectedPanels);
    }
    return new Set();
  });
  
  const [chatFocusedRowKey, setChatFocusedRowKey] = useState(null); // Track which row was clicked for chat
  
  // Restore columnFilters from persisted state
  const [columnFilters, setColumnFilters] = useState(() => {
    if (tableViewState?.columnFilters instanceof Map) {
      return new Map(tableViewState.columnFilters);
    }
    if (tableViewState?.columnFilters && typeof tableViewState.columnFilters === 'object') {
      return new Map(Object.entries(tableViewState.columnFilters));
    }
    return new Map();
  });
  
  // Restore pagination state from persisted state
  const [paginationState, setPaginationState] = useState(() => {
    if (tableViewState?.paginationState && typeof tableViewState.paginationState === 'object') {
      return new Map(Object.entries(tableViewState.paginationState).map(([k, v]) => [parseInt(k), v]));
    }
    return new Map();
  });
  
  const [openFilterDropdown, setOpenFilterDropdown] = useState(null); // { panelIndex, column } or null
  const rowRefs = useRef(new Map()); // Refs for scrolling to rows
  const mainScrollContainerRef = useRef(null); // Ref for the main horizontal scroll container
  const filterDropdownRef = useRef(null); // Ref for filter dropdown to handle outside clicks
  const prevResultGraphDataRef = useRef(null); // Track previous result graph to detect changes
  const prevPanelsLengthRef = useRef(0);
  const lastClickWasFromRelationsRef = useRef(false); // So we can re-apply scroll-right after Selected panel appears
  
  // Initialize default pagination for panels that don't have it
  useEffect(() => {
    setPaginationState((prev) => {
      const next = new Map(prev);
      let changed = false;
      panels.forEach((_, index) => {
        if (!next.has(index)) {
          next.set(index, { pageSize: 100, currentPage: 1, viewAll: false });
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [panels.length]);
  
  // Cache for filtered datasets per panel: Map<panelIndex, filteredNodes[]>
  const filteredDataCache = useRef(new Map());
  // Cache for unique values per column per panel: Map<`${panelIndex}-${column}`, Set<values>>
  const uniqueValuesCache = useRef(new Map());

  // When a relations panel is added (e.g. expanding from main), scroll viewport to the right so the new panel is visible.
  // Runs after commit so layout is done; fixes scroll not moving when filter is active (timing/layout).
  useEffect(() => {
    if (panels.length <= 1) {
      prevPanelsLengthRef.current = panels.length;
      return;
    }
    const lastPanel = panels[panels.length - 1];
    const didAddRelationsPanel = lastPanel?.type === 'relations' && panels.length > prevPanelsLengthRef.current;
    prevPanelsLengthRef.current = panels.length;

    if (!didAddRelationsPanel) return;

    const timeoutId = setTimeout(() => {
      let el = mainScrollContainerRef.current;
      if (!el) el = document.querySelector('[data-table-scroll-container="true"]');
      if (!el) {
        const tableView = document.querySelector('[class*="GraphTableView"]');
        if (tableView) el = tableView.querySelector('.overflow-x-auto') || tableView.querySelector('.overflow-auto');
      }
      if (el) {
        const maxScroll = Math.max(0, el.scrollWidth - el.clientWidth);
        el.scrollLeft = maxScroll;
        el.scrollTo({ left: maxScroll, behavior: 'smooth' });
      }
    }, 200);

    return () => clearTimeout(timeoutId);
  }, [panels]);

  // Save state when it changes (debounced to avoid too many updates)
  // Exclude results panel from persisted state since it's dynamic based on AI queries
  useEffect(() => {
    if (onTableViewStateChange) {
      const timeoutId = setTimeout(() => {
        const panelsToSave = panels.filter(p => p.type !== 'results'); // Don't persist results panel
        onTableViewStateChange({
          panels: panelsToSave,
          selectedPanels: Array.from(selectedPanels), // Convert Set to Array for serialization
          columnFilters: Object.fromEntries(columnFilters), // Convert Map to Object for serialization
          paginationState: Object.fromEntries(paginationState), // Convert Map to Object for serialization
        });
      }, 100);
      return () => clearTimeout(timeoutId);
    }
  }, [panels, selectedPanels, columnFilters, paginationState, onTableViewStateChange]);

  // Sync main panel to current graphData.nodes so search filter hides/shows rows (not just relations)
  // Also updates node data when properties change (e.g., after editing)
  // Use a ref to track previous nodes signature to detect any changes
  const prevNodesSignatureRef = useRef(nodesSignature);
  const prevNodesLengthRef = useRef(nodes.length);
  const prevNodesHashRef = useRef('');
  
  // Create a hash of node data to detect property changes
  const nodesHash = useMemo(() => {
    return nodes.map(n => `${n.key}:${JSON.stringify(n)}`).join('|');
  }, [nodes]);
  
  useEffect(() => {
    // Always update if signature, length, or hash changed
    const signatureChanged = prevNodesSignatureRef.current !== nodesSignature;
    const lengthChanged = prevNodesLengthRef.current !== nodes.length;
    const hashChanged = prevNodesHashRef.current !== nodesHash;
    
    if (!signatureChanged && !lengthChanged && !hashChanged && nodes.length > 0) {
      // No changes detected, skip update
      return;
    }
    
    prevNodesSignatureRef.current = nodesSignature;
    prevNodesLengthRef.current = nodes.length;
    prevNodesHashRef.current = nodesHash;
    
    if (!nodes.length) {
      setPanels([]);
      return;
    }
    const mainPanelFromData = () => [{ type: 'main', nodes: [...nodes], parentIndex: null, parentRowKey: null, relationTypes: {}, breadcrumb: [] }];

    setPanels((prev) => {
      if (prev.length === 0) {
        return mainPanelFromData();
      }
      const main = prev[0];
      if (main?.type === 'main') {
        const prevKeys = new Set((main.nodes || []).map((n) => n.key));
        const curKeys = new Set(nodes.map((n) => n.key));
        const sameSet = prevKeys.size === curKeys.size && [...curKeys].every((k) => prevKeys.has(k));
        if (!sameSet) {
          // Filter or data changed; hide non-matching rows by replacing main panel with current nodes
          return mainPanelFromData();
        } else {
          // Same set of keys, but node data might have changed (e.g., properties updated)
          // Update the main panel's nodes with the latest data while preserving other panels
          const updatedPanels = [...prev];
          updatedPanels[0] = { ...main, nodes: [...nodes] }; // Create new array reference
          return updatedPanels;
        }
      }
      // When no persisted state, only init when empty (theory table: avoid wiping expanded relations)
      if (!tableViewState?.panels || tableViewState.panels.length === 0) {
        return prev;
      }
      return prev;
    });
  }, [nodesSignature, tableViewState, nodes, nodes.length, nodesHash]);

  useEffect(() => {
    setSelectedRowKeys(new Set(selectedNodeKeys));
  }, [selectedNodeKeys]);

  const columns = useMemo(() => collectColumns(nodes), [nodes]);

  const expandRelations = useCallback(
    (panelIndex, rowKey, isMultiSelect = false) => {
      const { nodes: related, relationTypes } = getRelated(rowKey, nodes, links);
      if (related.length === 0) return;
      
      // Get parent panel to build breadcrumb
      setPanels((prev) => {
        const parentPanel = prev[panelIndex];
        const currentNode = nodes.find((n) => n.key === rowKey);
        const currentNodeName = currentNode?.name || currentNode?.key || rowKey;
        const currentNodeType = currentNode?.type || '';
        
        // Build breadcrumb path: if parent is main panel, start new breadcrumb; otherwise extend parent's breadcrumb
        let breadcrumb;
        if (parentPanel?.type === 'main') {
          // Starting from main panel: breadcrumb is just the starting node
          breadcrumb = [{ key: rowKey, name: currentNodeName, type: currentNodeType }];
        } else if (parentPanel?.breadcrumb) {
          // Extending from a relations panel: add current node to parent's breadcrumb
          breadcrumb = [...parentPanel.breadcrumb, { key: rowKey, name: currentNodeName, type: currentNodeType }];
        } else {
          // Fallback: just the current node
          breadcrumb = [{ key: rowKey, name: currentNodeName, type: currentNodeType }];
        }
        
        const newPanel = {
          type: 'relations',
          nodes: related,
          parentIndex: panelIndex,
          parentRowKey: rowKey,
          relationTypes,
          breadcrumb,
        };
        
        if (isMultiSelect) {
          // Multi-select: add as a new relations panel at the end, keeping all existing panels
          // Check if this exact relation panel already exists (same parent and row key)
          const existingIndex = prev.findIndex(
            (p) => p.type === 'relations' && p.parentRowKey === rowKey && p.parentIndex === panelIndex
          );
          if (existingIndex !== -1) return prev; // Already expanded, don't duplicate
          // Append the new relations panel at the end
          const newPanels = [...prev, newPanel];
          
          // Scroll is handled by useEffect when panels change so it runs after layout (reliable with filter)
          return newPanels;
        } else {
          // Single select: replace all relations panels after current one with just this new panel
          const mainPanelIndex = prev.findIndex((p) => p.type === 'main');
          if (mainPanelIndex === -1) return [...prev, newPanel];
          // Keep main panel and panels up to current, then add new relations panel
          const newPanels = [...prev.slice(0, panelIndex + 1), newPanel];
          
          // Scroll is handled by useEffect when panels change so it runs after layout (reliable with filter)
          return newPanels;
        }
      });
    },
    [nodes, links]
  );

  const collapsePanel = useCallback((panelIndex) => {
    if (panelIndex <= 0) return;
    // If collapsing a relations panel, only remove that specific panel
    // If collapsing the main panel, remove everything after it
    setPanels((prev) => {
      const panel = prev[panelIndex];
      if (panel?.type === 'main') {
        return prev.slice(0, panelIndex + 1);
      } else {
        // Remove just this relations panel, keep others
        return [...prev.slice(0, panelIndex), ...prev.slice(panelIndex + 1)];
      }
    });
  }, []);

  const parentName = useCallback(
    (parentKey) => {
      const n = nodes.find((x) => x.key === parentKey);
      return n?.name || n?.key || parentKey;
    },
    [nodes]
  );

  const handleBreadcrumbClick = useCallback((crumbKey, allBreadcrumbKeys = []) => {
    // Highlight all breadcrumb keys briefly
    const keysToHighlight = allBreadcrumbKeys.length > 0 ? allBreadcrumbKeys : [crumbKey];
    setHighlightedKeys(new Set(keysToHighlight));
    
    // Clear highlight after 2 seconds
    setTimeout(() => {
      setHighlightedKeys(new Set());
    }, 2000);
  }, []);

  const handleRowClick = useCallback((node, panel, event) => {
    // Clear/set scroll-follow ref synchronously so the "re-apply scroll right" effect
    // doesn't fire when selection changes after a left-table click (would cause jumping)
    const isMainPanel = panel && panel.type === 'main';
    if (isMainPanel) {
      lastClickWasFromRelationsRef.current = false;
    } else if (panel && panel.type === 'relations') {
      lastClickWasFromRelationsRef.current = true;
    }

    if (onNodeClick) {
      onNodeClick(node, panel, event);
    }
    // Toggle selection
    setSelectedRowKeys((prev) => {
      const next = new Set(prev);
      if (next.has(node.key)) {
        next.delete(node.key);
      } else {
        next.add(node.key);
      }
      return next;
    });
    
    // If clicking a row in a relations table, highlight all breadcrumb rows
    if (panel && panel.type === 'relations' && panel.breadcrumb && panel.breadcrumb.length > 0) {
      const breadcrumbKeys = panel.breadcrumb.map(crumb => crumb.key);
      setBreadcrumbHighlightedKeys(new Set(breadcrumbKeys));
    } else if (panel && panel.type === 'main') {
      // If clicking in main table, clear breadcrumb highlights
      setBreadcrumbHighlightedKeys(new Set());
    }
    
    // Scroll viewport based on which table was clicked (same logic as chat click)
    requestAnimationFrame(() => {
      setTimeout(() => {
        let mainScrollContainer = mainScrollContainerRef.current;
        
        // Fallback: try to find the scroll container if ref isn't set
        if (!mainScrollContainer) {
          mainScrollContainer = document.querySelector('[data-table-scroll-container="true"]');
          if (!mainScrollContainer) {
            const tableViewContainer = document.querySelector('[class*="GraphTableView"]');
            if (tableViewContainer) {
              mainScrollContainer = tableViewContainer.querySelector('.overflow-x-auto') || 
                                   tableViewContainer.querySelector('.overflow-auto') ||
                                   tableViewContainer.closest('.overflow-x-auto') ||
                                   tableViewContainer.closest('.overflow-auto');
            }
          }
        }
        
        if (mainScrollContainer && panel) {
          const isMain = panel.type === 'main';
          if (isMain) {
            // Left table: scroll to position 0 (leftmost)
            mainScrollContainer.scrollLeft = 0;
            mainScrollContainer.scrollTo({
              left: 0,
              behavior: 'smooth',
            });
          } else {
            // Right table: scroll to rightmost
            const maxScroll = Math.max(0, mainScrollContainer.scrollWidth - mainScrollContainer.clientWidth);
            mainScrollContainer.scrollLeft = maxScroll;
            mainScrollContainer.scrollTo({
              left: maxScroll,
              behavior: 'smooth',
            });
          }
        }
      }, 100);
    });
  }, [onNodeClick, panels]);

  // When Selected panel appears after a right-table row click, container may resize; re-apply scroll-right so table stays at far right
  const relationsPanelCount = panels.filter((p) => p.type === 'relations').length;
  useEffect(() => {
    if (relationsPanelCount === 0 || !lastClickWasFromRelationsRef.current) return;
    const timeoutId = setTimeout(() => {
      lastClickWasFromRelationsRef.current = false;
      let el = mainScrollContainerRef.current;
      if (!el) el = document.querySelector('[data-table-scroll-container="true"]');
      if (el) {
        const maxScroll = Math.max(0, el.scrollWidth - el.clientWidth);
        el.scrollLeft = maxScroll;
      }
    }, 180);
    return () => clearTimeout(timeoutId);
  }, [selectedNodeKeys, relationsPanelCount]);

  // Handle chat icon click for a single row
  const handleRowChatClick = useCallback((node, panel, event) => {
    console.log('handleRowChatClick called', { nodeKey: node?.key, panelType: panel?.type, hasOnOpenChat: !!onOpenChat });
    event.stopPropagation();
    if (!onOpenChat) {
      console.warn('onOpenChat is not available');
      return;
    }
    
    // Set the focused row for scrolling
    setChatFocusedRowKey(node.key);
    
    // Include only the clicked node and its breadcrumb trail
    const nodeMap = new Map();
    // Add clicked node first
    nodeMap.set(node.key, node);
    
    // Add breadcrumb nodes (the trail that led to this row)
    if (panel.breadcrumb && panel.breadcrumb.length > 0) {
      for (const crumb of panel.breadcrumb) {
        if (!nodeMap.has(crumb.key)) {
          const breadcrumbNode = nodes.find((n) => n.key === crumb.key);
          if (breadcrumbNode) {
            nodeMap.set(crumb.key, breadcrumbNode);
          }
        }
      }
    }
    
    onOpenChat(Array.from(nodeMap.values()));
    
    console.log('About to scroll, panel type:', panel?.type);
    
    // Scroll viewport based on which table was clicked
    // Use requestAnimationFrame to ensure DOM is ready
    requestAnimationFrame(() => {
      setTimeout(() => {
        console.log('Inside scroll timeout');
        const rowElement = rowRefs.current.get(node.key);
        let mainScrollContainer = mainScrollContainerRef.current;
        
        console.log('Scroll attempt:', {
          hasRef: !!mainScrollContainerRef.current,
          panelType: panel?.type,
          panelIndex: panel ? panels.indexOf(panel) : -1,
          hasRowElement: !!rowElement
        });
        
        // Fallback: try to find the scroll container if ref isn't set
        if (!mainScrollContainer) {
          // Try data attribute first
          mainScrollContainer = document.querySelector('[data-table-scroll-container="true"]');
          
          // Try multiple selectors to find the scroll container
          if (!mainScrollContainer) {
            const tableViewContainer = document.querySelector('[class*="GraphTableView"]');
            if (tableViewContainer) {
              mainScrollContainer = tableViewContainer.querySelector('.overflow-x-auto') || 
                                   tableViewContainer.querySelector('.overflow-auto') ||
                                   tableViewContainer.closest('.overflow-x-auto') ||
                                   tableViewContainer.closest('.overflow-auto');
            }
          }
        }
        
        // Also try finding by going up from the row element
        if (!mainScrollContainer && rowElement) {
          let parent = rowElement.parentElement;
          while (parent && parent !== document.body) {
            if (parent.hasAttribute('data-table-scroll-container')) {
              mainScrollContainer = parent;
              break;
            }
            const style = window.getComputedStyle(parent);
            if (style.overflowX === 'auto' || style.overflowX === 'scroll') {
              mainScrollContainer = parent;
              break;
            }
            parent = parent.parentElement;
          }
        }
        
        if (mainScrollContainer) {
          // Check if this is the main panel (left table) or a relations panel (right table)
          const isMainPanel = panel && panel.type === 'main';
          
          console.log('Scrolling:', {
            isMainPanel,
            currentScroll: mainScrollContainer.scrollLeft,
            scrollWidth: mainScrollContainer.scrollWidth,
            clientWidth: mainScrollContainer.clientWidth,
            element: mainScrollContainer
          });
          
          // Force immediate scroll first to ensure it works
          if (isMainPanel) {
            // Left table: scroll to position 0 (leftmost)
            mainScrollContainer.scrollLeft = 0;
            mainScrollContainer.scrollTo({
              left: 0,
              behavior: 'smooth',
            });
          } else {
            // Right table: scroll to rightmost position
            const maxScroll = Math.max(0, mainScrollContainer.scrollWidth - mainScrollContainer.clientWidth);
            mainScrollContainer.scrollLeft = maxScroll;
            mainScrollContainer.scrollTo({
              left: maxScroll,
              behavior: 'smooth',
            });
          }
          
          // Also scroll the row into view within the panel (centered vertically)
          if (rowElement) {
            rowElement.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
          }
          
          // Clear focus highlight after scroll animation completes
          setTimeout(() => {
            setChatFocusedRowKey(null);
          }, 1000);
        } else {
          console.error('Could not find main scroll container for table view scrolling', {
            ref: mainScrollContainerRef.current,
            panelType: panel?.type,
            rowElement: !!rowElement
          });
        }
      }, 100);
    });
  }, [onOpenChat, nodes]);

  // Handle "Query All" button click for a panel
  const handlePanelQueryAll = useCallback((panel, event) => {
    event.stopPropagation();
    if (!onOpenChat) return;
    
    // Include all rows in the table + all breadcrumb nodes from tables before it
    const nodeMap = new Map();
    
    // Add all panel nodes (all rows in this table)
    const panelNodes = panel.nodes || [];
    for (const node of panelNodes) {
      nodeMap.set(node.key, node);
    }
    
    // Add all breadcrumb nodes (the navigation path that led to this table)
    if (panel.breadcrumb && panel.breadcrumb.length > 0) {
      for (const crumb of panel.breadcrumb) {
        if (!nodeMap.has(crumb.key)) {
          const breadcrumbNode = nodes.find((n) => n.key === crumb.key);
          if (breadcrumbNode) {
            nodeMap.set(crumb.key, breadcrumbNode);
          }
        }
      }
    }
    
    onOpenChat(Array.from(nodeMap.values()));
    
    // Scroll viewport based on which table was clicked
    // Use requestAnimationFrame to ensure DOM is ready
    requestAnimationFrame(() => {
      setTimeout(() => {
        let mainScrollContainer = mainScrollContainerRef.current;
        
        // Fallback: try to find the scroll container if ref isn't set
        if (!mainScrollContainer) {
          // Try multiple selectors to find the scroll container
          const tableViewContainer = document.querySelector('[class*="GraphTableView"]');
          if (tableViewContainer) {
            mainScrollContainer = tableViewContainer.querySelector('.overflow-x-auto') || 
                                 tableViewContainer.querySelector('.overflow-auto') ||
                                 tableViewContainer.closest('.overflow-x-auto') ||
                                 tableViewContainer.closest('.overflow-auto');
          }
        }
        
        if (mainScrollContainer) {
          // Check if this is the main panel (left table) or a relations panel (right table)
          const isMainPanel = panel && panel.type === 'main';
          
          if (isMainPanel) {
            // Left table: scroll to position 0 (leftmost)
            mainScrollContainer.scrollTo({
              left: 0,
              behavior: 'smooth',
            });
          } else {
            // Right table: scroll to rightmost position
            const maxScroll = Math.max(0, mainScrollContainer.scrollWidth - mainScrollContainer.clientWidth);
            mainScrollContainer.scrollTo({
              left: maxScroll,
              behavior: 'smooth',
            });
          }
        } else {
          console.warn('Could not find main scroll container for table view scrolling', {
            ref: mainScrollContainerRef.current,
            panelType: panel?.type
          });
        }
      }, 100);
    });
  }, [onOpenChat, nodes, panels]);

  // Handle panel selection toggle for multi-table query
  const handlePanelSelectToggle = useCallback((panelIndex) => {
    setSelectedPanels((prev) => {
      const next = new Set(prev);
      if (next.has(panelIndex)) {
        next.delete(panelIndex);
      } else {
        next.add(panelIndex);
      }
      return next;
    });
  }, []);

  // Handle query selected panels
  const handleQuerySelectedPanels = useCallback(() => {
    if (!onOpenChat || selectedPanels.size === 0) return;
    
    const allNodes = new Map(); // Use Map to deduplicate by key
    for (const panelIndex of selectedPanels) {
      const panel = panels[panelIndex];
      if (panel) {
        // Add all rows in this panel
        const panelNodes = panel.nodes || [];
        for (const node of panelNodes) {
          allNodes.set(node.key, node);
        }
        
        // Add all breadcrumb nodes from this panel (navigation path)
        if (panel.breadcrumb && panel.breadcrumb.length > 0) {
          for (const crumb of panel.breadcrumb) {
            if (!allNodes.has(crumb.key)) {
              const breadcrumbNode = nodes.find((n) => n.key === crumb.key);
              if (breadcrumbNode) {
                allNodes.set(crumb.key, breadcrumbNode);
              }
            }
          }
        }
      }
    }
    
    onOpenChat(Array.from(allNodes.values()));
  }, [onOpenChat, selectedPanels, panels, nodes]);

  // Handle column filter change
  const handleColumnFilterChange = useCallback((panelIndex, column, filterConfig) => {
    setColumnFilters(prev => {
      const next = new Map(prev);
      const key = `${panelIndex}-${column}`;
      if (filterConfig === null) {
        next.delete(key);
      } else {
        next.set(key, filterConfig);
      }
      return next;
    });
  }, []);

  // Handle filter dropdown open/close
  const handleFilterDropdownToggle = useCallback((panelIndex, column, event) => {
    event.stopPropagation();
    const key = `${panelIndex}-${column}`;
    if (openFilterDropdown && openFilterDropdown.key === key) {
      setOpenFilterDropdown(null);
    } else {
      setOpenFilterDropdown({
        key,
        panelIndex,
        column,
      });
    }
  }, [openFilterDropdown]);
  
  // Handle clear filter
  const handleClearFilter = useCallback((panelIndex, column, event) => {
    event.stopPropagation();
    handleColumnFilterChange(panelIndex, column, null);
  }, [handleColumnFilterChange]);

  // Get filtered dataset for a panel (with caching and sequential filtering)
  // This applies all filters sequentially, so each filter sees the results of previous filters
  const getFilteredNodes = useCallback((panelIndex, panelNodesRaw, columns, relationTypes) => {
    const cacheKey = `${panelIndex}-${Array.from(columnFilters.keys()).filter(k => k.startsWith(`${panelIndex}-`)).sort().join(',')}`;
    
    // Check cache first
    if (filteredDataCache.current.has(cacheKey)) {
      return filteredDataCache.current.get(cacheKey);
    }
    
    // Apply filters sequentially - each filter works on the already-filtered dataset
    let filtered = panelNodesRaw;
    
    // Get all filter keys for this panel, sorted by column order
    const filterKeys = columns
      .map(col => `${panelIndex}-${col}`)
      .filter(key => columnFilters.has(key));
    
    // Apply each filter in sequence
    for (const key of filterKeys) {
      const filterConfig = columnFilters.get(key);
      if (filterConfig && filterConfig.selectedValues && filterConfig.selectedValues.length > 0) {
        const column = key.split('-').slice(1).join('-'); // Get column name from key
        filtered = filtered.filter(node => {
          let value;
          if (column === 'Relation') {
            const relTypes = relationTypes && relationTypes[node.key];
            value = relTypes && relTypes.length > 0 ? relTypes.join(', ') : null;
          } else {
            const flat = flattenNode(node);
            value = flat[column];
          }
          const normalizedValue = value === null || value === undefined ? null : value;
          const isIncluded = filterConfig.selectedValues.includes(normalizedValue);
          
          return filterConfig.mode === 'include' ? isIncluded : !isIncluded;
        });
      }
    }
    
    // Cache the result
    filteredDataCache.current.set(cacheKey, filtered);
    
    // Limit cache size to prevent memory issues
    if (filteredDataCache.current.size > 50) {
      const firstKey = filteredDataCache.current.keys().next().value;
      filteredDataCache.current.delete(firstKey);
    }
    
    return filtered;
  }, [columnFilters]);

  // Get unique values for a column in a panel (from already-filtered dataset, not raw)
  // This ensures sequential filtering - each filter shows values from previously filtered data
  const getUniqueValuesForColumn = useCallback((panelIndex, column, panelNodesRaw, relationTypes, columns) => {
    // Get the filtered dataset up to (but not including) this column
    // This means we show unique values from the dataset that has all OTHER filters applied
    const cacheKey = `${panelIndex}-${column}-${Array.from(columnFilters.keys())
      .filter(k => k.startsWith(`${panelIndex}-`) && !k.endsWith(`-${column}`))
      .sort()
      .join(',')}`;
    
    // Check cache first
    if (uniqueValuesCache.current.has(cacheKey)) {
      return Array.from(uniqueValuesCache.current.get(cacheKey)).sort((a, b) => {
        if (a === null) return 1;
        if (b === null) return -1;
        return String(a).localeCompare(String(b));
      });
    }
    
    // Get filtered nodes excluding the current column's filter
    const otherFilterKeys = columns
      .map(col => `${panelIndex}-${col}`)
      .filter(key => columnFilters.has(key) && !key.endsWith(`-${column}`));
    
    let filtered = panelNodesRaw;
    for (const key of otherFilterKeys) {
      const filterConfig = columnFilters.get(key);
      if (filterConfig && filterConfig.selectedValues && filterConfig.selectedValues.length > 0) {
        const col = key.split('-').slice(1).join('-');
        filtered = filtered.filter(node => {
          let value;
          if (col === 'Relation') {
            const relTypes = relationTypes && relationTypes[node.key];
            value = relTypes && relTypes.length > 0 ? relTypes.join(', ') : null;
          } else {
            const flat = flattenNode(node);
            value = flat[col];
          }
          const normalizedValue = value === null || value === undefined ? null : value;
          const isIncluded = filterConfig.selectedValues.includes(normalizedValue);
          return filterConfig.mode === 'include' ? isIncluded : !isIncluded;
        });
      }
    }
    
    // Extract unique values from the filtered dataset
    const values = new Set();
    filtered.forEach(node => {
      let value;
      if (column === 'Relation') {
        const relTypes = relationTypes && relationTypes[node.key];
        value = relTypes && relTypes.length > 0 ? relTypes.join(', ') : null;
      } else {
        const flat = flattenNode(node);
        value = flat[column];
      }
      values.add(value === null || value === undefined ? null : value);
    });
    
    // Cache the result
    uniqueValuesCache.current.set(cacheKey, values);
    
    // Limit cache size
    if (uniqueValuesCache.current.size > 100) {
      const firstKey = uniqueValuesCache.current.keys().next().value;
      uniqueValuesCache.current.delete(firstKey);
    }
    
    return Array.from(values).sort((a, b) => {
      if (a === null) return 1;
      if (b === null) return -1;
      return String(a).localeCompare(String(b));
    });
  }, [columnFilters]);

  // Apply filters to panel nodes (uses cached filtered dataset)
  const applyFiltersToNodes = useCallback((panelIndex, panelNodesRaw, columns, relationTypes) => {
    return getFilteredNodes(panelIndex, panelNodesRaw, columns, relationTypes);
  }, [getFilteredNodes]);
  
  // Clear caches when filters change
  useEffect(() => {
    filteredDataCache.current.clear();
    uniqueValuesCache.current.clear();
  }, [columnFilters]);

  // Get selected nodes from checkbox selection
  const getSelectedNodes = useCallback(() => {
    return nodes.filter(n => checkboxSelectedKeys.has(n.key));
  }, [nodes, checkboxSelectedKeys]);

  // Get all nodes from the table (from all panels)
  const getAllTableNodes = useCallback(() => {
    const allTableNodes = [];
    panels.forEach(panel => {
      if (panel.nodes && Array.isArray(panel.nodes)) {
        allTableNodes.push(...panel.nodes);
      }
    });
    // Deduplicate by key
    const nodeMap = new Map();
    allTableNodes.forEach(node => {
      if (node.key && !nodeMap.has(node.key)) {
        nodeMap.set(node.key, node);
      }
    });
    return Array.from(nodeMap.values());
  }, [panels]);

  // Handle checkbox toggle
  const handleCheckboxToggle = useCallback((nodeKey, checked) => {
    setCheckboxSelectedKeys(prev => {
      const next = new Set(prev);
      if (checked) {
        next.add(nodeKey);
      } else {
        next.delete(nodeKey);
      }
      return next;
    });
  }, []);

  // Handle select all / deselect all
  const handleSelectAll = useCallback((panelNodes) => {
    const allKeys = new Set(panelNodes.map(n => n.key));
    setCheckboxSelectedKeys(allKeys);
  }, []);

  const handleDeselectAll = useCallback(() => {
    setCheckboxSelectedKeys(new Set());
  }, []);

  // Handle merge action
  const handleMerge = useCallback(() => {
    const selected = getSelectedNodes();
    if (selected.length < 2) {
      alert('Please select at least 2 nodes to merge');
      return;
    }
    setMergeEntity1(selected[0]);
    setMergeEntity2(selected[1]);
    setShowMergeModal(true);
  }, [getSelectedNodes]);

  // Handle delete action
  const handleDelete = useCallback(() => {
    const selected = getSelectedNodes();
    if (selected.length === 0) {
      alert('Please select at least one node to delete');
      return;
    }
    setShowDeleteModal(true);
  }, [getSelectedNodes]);

  // Handle edit action
  const handleEdit = useCallback(() => {
    const selected = getSelectedNodes();
    if (selected.length === 0) {
      alert('Please select at least one node to edit');
      return;
    }
    setShowEditModal(true);
  }, [getSelectedNodes]);

  // Handle add action
  const handleAdd = useCallback(() => {
    setShowAddModal(true);
  }, []);

  // Handle merge confirmation
  const handleMergeConfirm = useCallback(async (sourceKey, targetKey, mergedData) => {
    if (!onMergeNodes) {
      alert('Merge functionality is not available');
      return;
    }
    try {
      await onMergeNodes(sourceKey, targetKey, mergedData);
      setCheckboxSelectedKeys(new Set());
      setShowMergeModal(false);
      if (onGraphRefresh) {
        await onGraphRefresh();
      }
    } catch (err) {
      console.error('Failed to merge nodes:', err);
      throw err;
    }
  }, [onMergeNodes, onGraphRefresh]);

  // Handle delete confirmation
  const handleDeleteConfirm = useCallback(async (nodesToDelete) => {
    if (!onDeleteNodes) {
      alert('Delete functionality is not available');
      return;
    }
    setIsDeleting(true);
    try {
      await onDeleteNodes(nodesToDelete);
      setCheckboxSelectedKeys(new Set());
      setShowDeleteModal(false);
      // onDeleteNodes already refreshes the graph, but call onGraphRefresh to ensure table updates
      if (onGraphRefresh) {
        await onGraphRefresh();
      }
    } catch (err) {
      console.error('Failed to delete nodes:', err);
      alert(`Failed to delete nodes: ${err.message}`);
    } finally {
      setIsDeleting(false);
    }
  }, [onDeleteNodes, onGraphRefresh]);

  // Handle edit save
  const handleEditSave = useCallback(async (nodeKey, updates) => {
    if (!onUpdateNode) {
      alert('Update functionality is not available');
      return;
    }
    try {
      await onUpdateNode(nodeKey, updates);
      if (onGraphRefresh) {
        await onGraphRefresh();
      }
    } catch (err) {
      console.error('Failed to update node:', err);
      throw err;
    }
  }, [onUpdateNode, onGraphRefresh]);

  // Handle node created
  const handleNodeCreated = useCallback(async (nodeKey) => {
    setShowAddModal(false);
    if (onNodeCreated) {
      await onNodeCreated(nodeKey);
    }
    if (onGraphRefresh) {
      await onGraphRefresh();
    }
  }, [onNodeCreated, onGraphRefresh]);

  // Handle relationship created
  const handleRelationshipCreated = useCallback(async (cypher) => {
    setShowCreateRelationshipModal(false);
    setRelationshipSourceNodes([]);
    if (onGraphRefresh) {
      await onGraphRefresh();
    }
  }, [onGraphRefresh]);

  // Handle add relationship from edit/add modal
  const handleAddRelationship = useCallback((sourceNodes) => {
    setRelationshipSourceNodes(sourceNodes);
    setShowCreateRelationshipModal(true);
  }, []);

  // Add/update results panel when resultGraphData changes (must run before any conditional return)
  useEffect(() => {
    if (resultGraphData && resultGraphData.nodes && resultGraphData.nodes.length > 0) {
      // Check if this is a new result graph
      const isNewResultGraph = !prevResultGraphDataRef.current || 
        prevResultGraphDataRef.current.nodes.length !== resultGraphData.nodes.length ||
        prevResultGraphDataRef.current.nodes.some((n, i) => n.key !== resultGraphData.nodes[i]?.key);
      
      if (isNewResultGraph) {
        setPanels((prev) => {
          // Remove any existing results panel
          const withoutResults = prev.filter((p) => p.type !== 'results');
          // Add new results panel at the end
          return [
            ...withoutResults,
            {
              type: 'results',
              nodes: resultGraphData.nodes || [],
              parentIndex: null,
              parentRowKey: null,
              relationTypes: {},
              breadcrumb: [],
            },
          ];
        });
        prevResultGraphDataRef.current = resultGraphData;
        
        // Scroll to show the results panel
        requestAnimationFrame(() => {
          setTimeout(() => {
            let mainScrollContainer = mainScrollContainerRef.current;
            if (!mainScrollContainer) {
              mainScrollContainer = document.querySelector('[data-table-scroll-container="true"]');
            }
            if (mainScrollContainer) {
              const maxScroll = Math.max(0, mainScrollContainer.scrollWidth - mainScrollContainer.clientWidth);
              mainScrollContainer.scrollLeft = maxScroll;
              mainScrollContainer.scrollTo({
                left: maxScroll,
                behavior: 'smooth',
              });
            }
          }, 100);
        });
      } else {
        // Update existing results panel nodes if resultGraphData exists but hasn't changed significantly
        setPanels((prev) => {
          const resultsPanelIndex = prev.findIndex((p) => p.type === 'results');
          if (resultsPanelIndex >= 0) {
            const updated = [...prev];
            updated[resultsPanelIndex] = {
              ...updated[resultsPanelIndex],
              nodes: resultGraphData.nodes || [],
            };
            return updated;
          }
          return prev;
        });
      }
    } else if (!resultGraphData && prevResultGraphDataRef.current) {
      // Remove results panel if resultGraphData is cleared
      setPanels((prev) => prev.filter((p) => p.type !== 'results'));
      prevResultGraphDataRef.current = null;
    }
  }, [resultGraphData]);

  if (nodes.length === 0) {
    return (
      <div className={`flex items-center justify-center text-light-500 p-8 ${className}`}>
        <p>No graph data to display in table view.</p>
      </div>
    );
  }

  // Separate main panel from relations panels and results panel
  const mainPanel = panels.find((p) => p.type === 'main');
  const relationsPanels = panels.filter((p) => p.type === 'relations');
  const resultsPanel = panels.find((p) => p.type === 'results');

  return (
    <div className={`flex flex-col h-full bg-white ${isChatOpen ? 'overflow-x-auto overflow-y-auto min-w-0' : 'overflow-x-auto overflow-y-auto min-w-0'} ${className}`}>
      {/* Multi-select query button */}
      {selectedPanels.size > 0 && (
        <div className="flex-shrink-0 px-4 py-2 bg-owl-blue-50 border-b border-light-200 flex items-center justify-between">
          <span className="text-sm text-owl-blue-900 font-medium">
            {selectedPanels.size} table{selectedPanels.size > 1 ? 's' : ''} selected for AI query
          </span>
          <button
            onClick={handleQuerySelectedPanels}
            className="flex items-center gap-2 px-3 py-1.5 bg-owl-blue-600 text-white rounded hover:bg-owl-blue-700 transition-colors text-sm font-medium shadow-sm"
          >
            <MessageSquare className="w-4 h-4" />
            Query Selected Tables
          </button>
        </div>
      )}

      {/* Table Tools Toolbar */}
      <div className="flex-shrink-0 px-4 py-2 bg-light-50 border-b border-light-200 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-light-700 font-medium">
            {checkboxSelectedKeys.size > 0 ? `${checkboxSelectedKeys.size} selected` : 'Table Tools'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleAdd}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-owl-blue-600 text-white rounded hover:bg-owl-blue-700 transition-colors text-sm font-medium"
            title="Add new node"
          >
            <Plus className="w-4 h-4" />
            Add
          </button>
          <button
            onClick={handleEdit}
            disabled={checkboxSelectedKeys.size === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-owl-blue-600 text-white rounded hover:bg-owl-blue-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            title="Edit selected nodes"
          >
            <Edit className="w-4 h-4" />
            Edit
          </button>
          <button
            onClick={handleMerge}
            disabled={checkboxSelectedKeys.size < 2}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-owl-blue-600 text-white rounded hover:bg-owl-blue-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            title="Merge selected nodes (requires 2+ selected)"
          >
            <Merge className="w-4 h-4" />
            Merge
          </button>
          <button
            onClick={handleDelete}
            disabled={checkboxSelectedKeys.size === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white rounded hover:bg-red-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            title="Delete selected nodes"
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </button>
        </div>
      </div>
      
      <div 
        ref={(el) => {
          mainScrollContainerRef.current = el;
          // Also store in a data attribute for easier finding
          if (el) {
            el.setAttribute('data-table-scroll-container', 'true');
          }
        }}
        className={`flex-1 overflow-x-auto overflow-y-auto`}
      >
        <div className="flex min-w-max h-full gap-0">
          {/* Main panel */}
          {mainPanel && (
            <div 
              data-panel-index={panels.indexOf(mainPanel)}
              data-panel-type="main"
              className="flex-shrink-0"
            >
              <PanelTable
                key="main"
                panelIndex={panels.indexOf(mainPanel)}
                panel={mainPanel}
                columns={columns}
                nodes={nodes}
                links={links}
                selectedNodeKeys={Array.from(selectedRowKeys)}
                highlightedKeys={highlightedKeys}
                breadcrumbHighlightedKeys={breadcrumbHighlightedKeys}
                onNodeClick={handleRowClick}
                onExpand={expandRelations}
                onCollapse={collapsePanel}
                parentName={parentName}
                getRelated={(k) => getRelated(k, nodes, links)}
                onBreadcrumbClick={handleBreadcrumbClick}
                onRowChatClick={handleRowChatClick}
                onPanelQueryAll={handlePanelQueryAll}
                onPanelSelectToggle={handlePanelSelectToggle}
                isPanelSelected={selectedPanels.has(panels.indexOf(mainPanel))}
                onOpenChat={onOpenChat}
                chatFocusedRowKey={chatFocusedRowKey}
                rowRefs={rowRefs}
                columnFilters={columnFilters}
                onColumnFilterChange={handleColumnFilterChange}
                onFilterDropdownToggle={handleFilterDropdownToggle}
                onFilterDropdownClose={() => setOpenFilterDropdown(null)}
                openFilterDropdown={openFilterDropdown}
                getUniqueValuesForColumn={getUniqueValuesForColumn}
                applyFiltersToNodes={applyFiltersToNodes}
                searchHighlightTerms={searchHighlightTerms}
                paginationState={paginationState}
                onPaginationChange={setPaginationState}
                columns={columns}
                checkboxSelectedKeys={Array.from(checkboxSelectedKeys)}
                onCheckboxToggle={handleCheckboxToggle}
                onSelectAll={handleSelectAll}
                onDeselectAll={handleDeselectAll}
              />
            </div>
          )}
          
          {/* Relations panels - stacked vertically on the right */}
          {relationsPanels.length > 0 && (
            <div className="flex flex-col flex-shrink-0 border-l border-light-300 min-w-[420px] w-max max-w-[50vw] overflow-y-auto">
              {relationsPanels.map((panel) => {
                const panelIndex = panels.indexOf(panel);
                return (
                  <div 
                    key={panelIndex} 
                    data-panel-index={panelIndex}
                    data-panel-type="relations"
                    className="flex-shrink-0 border-b border-light-300 last:border-b-0"
                  >
                    <PanelTable
                      panelIndex={panelIndex}
                      panel={panel}
                      columns={columns}
                      nodes={nodes}
                      links={links}
                      selectedNodeKeys={Array.from(selectedRowKeys)}
                      highlightedKeys={highlightedKeys}
                      breadcrumbHighlightedKeys={breadcrumbHighlightedKeys}
                      onNodeClick={handleRowClick}
                      onExpand={expandRelations}
                      onCollapse={collapsePanel}
                      parentName={parentName}
                      getRelated={(k) => getRelated(k, nodes, links)}
                      isStacked={true}
                      onBreadcrumbClick={handleBreadcrumbClick}
                      onRowChatClick={handleRowChatClick}
                      onPanelQueryAll={handlePanelQueryAll}
                      onPanelSelectToggle={handlePanelSelectToggle}
                      isPanelSelected={selectedPanels.has(panelIndex)}
                      onOpenChat={onOpenChat}
                      chatFocusedRowKey={chatFocusedRowKey}
                      rowRefs={rowRefs}
                      columnFilters={columnFilters}
                      onColumnFilterChange={handleColumnFilterChange}
                      onFilterDropdownToggle={handleFilterDropdownToggle}
                      onFilterDropdownClose={() => setOpenFilterDropdown(null)}
                      openFilterDropdown={openFilterDropdown}
                      getUniqueValuesForColumn={getUniqueValuesForColumn}
                      applyFiltersToNodes={applyFiltersToNodes}
                      searchHighlightTerms={searchHighlightTerms}
                      paginationState={paginationState}
                      onPaginationChange={setPaginationState}
                      checkboxSelectedKeys={Array.from(checkboxSelectedKeys)}
                      onCheckboxToggle={handleCheckboxToggle}
                      onSelectAll={handleSelectAll}
                      onDeselectAll={handleDeselectAll}
                    />
                  </div>
                );
              })}
            </div>
          )}
          
          {/* Results panel - AI assistant results */}
          {resultsPanel && (
            <div 
              data-panel-index={panels.indexOf(resultsPanel)}
              data-panel-type="results"
              className="flex-shrink-0 border-l-4 border-purple-400 bg-purple-50/30 min-w-[420px] w-max max-w-[50vw]"
            >
              <PanelTable
                panelIndex={panels.indexOf(resultsPanel)}
                panel={resultsPanel}
                columns={columns}
                nodes={nodes}
                links={links}
                selectedNodeKeys={Array.from(selectedRowKeys)}
                highlightedKeys={highlightedKeys}
                breadcrumbHighlightedKeys={breadcrumbHighlightedKeys}
                onNodeClick={handleRowClick}
                onExpand={expandRelations}
                onCollapse={collapsePanel}
                parentName={parentName}
                getRelated={(k) => getRelated(k, nodes, links)}
                isStacked={false}
                onBreadcrumbClick={handleBreadcrumbClick}
                onRowChatClick={handleRowChatClick}
                onPanelQueryAll={handlePanelQueryAll}
                onPanelSelectToggle={handlePanelSelectToggle}
                isPanelSelected={false} // Results panel cannot be selected
                onOpenChat={onOpenChat}
                chatFocusedRowKey={chatFocusedRowKey}
                rowRefs={rowRefs}
                columnFilters={columnFilters}
                onColumnFilterChange={handleColumnFilterChange}
                onFilterDropdownToggle={handleFilterDropdownToggle}
                onFilterDropdownClose={() => setOpenFilterDropdown(null)}
                openFilterDropdown={openFilterDropdown}
                getUniqueValuesForColumn={getUniqueValuesForColumn}
                applyFiltersToNodes={applyFiltersToNodes}
                isResultsPanel={true} // Mark as results panel for special styling
                searchHighlightTerms={searchHighlightTerms}
                paginationState={paginationState}
                onPaginationChange={setPaginationState}
                columns={columns}
                checkboxSelectedKeys={Array.from(checkboxSelectedKeys)}
                onCheckboxToggle={handleCheckboxToggle}
                onSelectAll={handleSelectAll}
                onDeselectAll={handleDeselectAll}
              />
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      <MergeEntitiesModal
        isOpen={showMergeModal}
        onClose={() => {
          setShowMergeModal(false);
          setMergeEntity1(null);
          setMergeEntity2(null);
        }}
        onSuccess={() => {
          setShowMergeModal(false);
          setMergeEntity1(null);
          setMergeEntity2(null);
        }}
        entity1={mergeEntity1}
        entity2={mergeEntity2}
        onMerge={handleMergeConfirm}
      />

      <EditNodeModal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        nodes={getSelectedNodes()}
        onSave={handleEditSave}
        caseId={caseId}
        onRelationshipCreated={handleRelationshipCreated}
        tableNodes={getAllTableNodes()}
      />

      <AddNodeModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onNodeCreated={handleNodeCreated}
        caseId={caseId}
        onRelationshipCreated={handleRelationshipCreated}
        tableNodes={nodes} // Use all nodes from graphData, not just panel nodes
        tableColumns={columns}
      />

      <DeleteConfirmationModal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        nodes={getSelectedNodes()}
        onConfirm={handleDeleteConfirm}
        isDeleting={isDeleting}
      />

      <CreateRelationshipModal
        isOpen={showCreateRelationshipModal}
        onClose={() => {
          setShowCreateRelationshipModal(false);
          setRelationshipSourceNodes([]);
        }}
        sourceNodes={relationshipSourceNodes}
        targetNodes={[]} // Will be selected in the modal
        onRelationshipCreated={handleRelationshipCreated}
        caseId={caseId}
      />
    </div>
  );
}

function PanelTable({
  panelIndex,
  panel,
  columns,
  links,
  nodes,
  selectedNodeKeys = [],
  highlightedKeys = new Set(),
  breadcrumbHighlightedKeys = new Set(),
  onNodeClick,
  onExpand,
  onCollapse,
  parentName,
  getRelated,
  isStacked = false,
  onBreadcrumbClick,
  onRowChatClick,
  onPanelQueryAll,
  onPanelSelectToggle,
  isPanelSelected = false,
  onOpenChat,
  chatFocusedRowKey = null,
  rowRefs,
  columnFilters = new Map(),
  onColumnFilterChange,
  onFilterDropdownToggle,
  onFilterDropdownClose,
  openFilterDropdown,
  getUniqueValuesForColumn,
  applyFiltersToNodes,
  isResultsPanel = false, // Whether this is the AI assistant results panel
  searchHighlightTerms = [], // Terms from current filter/search for highlighting matches in cells
  paginationState = new Map(), // Pagination state per panel
  onPaginationChange, // Callback to update pagination state
  checkboxSelectedKeys = [], // Checkbox-selected node keys
  onCheckboxToggle = null, // Callback: (nodeKey, checked) => void
  onSelectAll = null, // Callback: (panelNodes) => void
  onDeselectAll = null, // Callback: () => void
}) {
  const isMain = panel.type === 'main';
  const { nodes: panelNodesRaw, parentRowKey, relationTypes, breadcrumb = [] } = panel;
  const allCols = relationTypes && Object.keys(relationTypes).length
    ? ['Relation', ...columns]
    : columns;
  
  // Apply filters to nodes (works on full dataset)
  const panelNodesFiltered = applyFiltersToNodes ? applyFiltersToNodes(panelIndex, panelNodesRaw, allCols, relationTypes) : panelNodesRaw;
  
  // Pagination logic
  const pagination = paginationState.get(panelIndex) || { pageSize: 100, currentPage: 1, viewAll: false };
  const { pageSize, currentPage, viewAll } = pagination;
  
  // Calculate pagination
  const totalRows = panelNodesFiltered.length;
  const totalPages = viewAll ? 1 : Math.max(1, Math.ceil(totalRows / pageSize));
  const startIndex = viewAll ? 0 : (currentPage - 1) * pageSize;
  const endIndex = viewAll ? totalRows : startIndex + pageSize;
  const panelNodes = viewAll ? panelNodesFiltered : panelNodesFiltered.slice(startIndex, endIndex);
  
  // Pagination handlers
  const handlePageChange = useCallback((newPage) => {
    if (onPaginationChange) {
      onPaginationChange((prev) => {
        const next = new Map(prev);
        next.set(panelIndex, { ...pagination, currentPage: newPage });
        return next;
      });
    }
  }, [panelIndex, pagination, onPaginationChange]);
  
  const handlePageSizeChange = useCallback((newPageSize) => {
    if (onPaginationChange) {
      onPaginationChange((prev) => {
        const next = new Map(prev);
        next.set(panelIndex, { pageSize: newPageSize, currentPage: 1, viewAll: false });
        return next;
      });
    }
  }, [panelIndex, onPaginationChange]);
  
  const handleViewAllToggle = useCallback(() => {
    if (onPaginationChange) {
      onPaginationChange((prev) => {
        const next = new Map(prev);
        next.set(panelIndex, { ...pagination, viewAll: !viewAll, currentPage: 1 });
        return next;
      });
    }
  }, [panelIndex, pagination, viewAll, onPaginationChange]);
  
  // Update pagination state when filtered data changes
  useEffect(() => {
    if (!viewAll && currentPage > totalPages && totalPages > 0) {
      handlePageChange(totalPages);
    }
  }, [totalPages, currentPage, viewAll, handlePageChange]);

  // Get relation type for breadcrumb segments between two nodes
  const getRelationTypeForBreadcrumb = (fromKey, toKey) => {
    for (const l of links || []) {
      const src = typeof l.source === 'object' ? l.source?.key : l.source;
      const tgt = typeof l.target === 'object' ? l.target?.key : l.target;
      if ((src === fromKey && tgt === toKey) || (src === toKey && tgt === fromKey)) {
        return l.type || 'RELATED_TO';
      }
    }
    return 'RELATED_TO';
  };
  
  // Get relation types for a node from its parent
  const getRelationTypesForNode = (nodeKey, parentKey) => {
    const types = [];
    for (const l of links || []) {
      const src = typeof l.source === 'object' ? l.source?.key : l.source;
      const tgt = typeof l.target === 'object' ? l.target?.key : l.target;
      if ((src === parentKey && tgt === nodeKey) || (src === nodeKey && tgt === parentKey)) {
        const type = l.type || 'RELATED_TO';
        if (!types.includes(type)) types.push(type);
      }
    }
    return types.length > 0 ? types : ['RELATED_TO'];
  };

  return (
    <div className={`flex flex-shrink-0 flex-col ${isStacked ? 'border-r-0' : 'border-r'} ${isResultsPanel ? 'border-purple-300' : 'border-light-200'} ${isResultsPanel ? 'bg-purple-50/40' : 'bg-light-50/50'} min-w-[420px] w-max ${isStacked ? 'max-w-[50vw]' : 'max-w-[50vw]'}`}>
      {/* Panel header: breadcrumbs + collapse */}
      <div className={`flex flex-col border-b ${isResultsPanel ? 'border-purple-300 bg-purple-100/50' : 'border-light-200 bg-white'} sticky top-0 z-10`}>
        {!isMain && breadcrumb.length > 0 && (
          <div 
            className="px-3 py-1.5 bg-light-50 border-b border-light-200 cursor-pointer hover:bg-light-100 transition-colors"
            onClick={() => {
              if (onBreadcrumbClick) {
                const allBreadcrumbKeys = breadcrumb.map(c => c.key);
                onBreadcrumbClick(null, allBreadcrumbKeys);
              }
            }}
          >
            <div className="flex items-center gap-1.5 flex-wrap text-xs">
              {breadcrumb.map((crumb, idx) => {
                const isLast = idx === breadcrumb.length - 1;
                const entityColor = getEntityTypeColor(crumb.type);
                const nextCrumb = breadcrumb[idx + 1];
                const relationTypes = nextCrumb 
                  ? getRelationTypesForNode(nextCrumb.key, crumb.key)
                  : [];
                const primaryRelationType = relationTypes[0];
                const relationColor = primaryRelationType ? getRelationTypeColor(primaryRelationType) : null;

                return (
                  <React.Fragment key={idx}>
                    <span
                      className="inline-flex items-center px-2 py-0.5 rounded font-medium text-white text-xs shadow-sm cursor-pointer hover:opacity-90 transition-opacity"
                      style={{ backgroundColor: entityColor }}
                      title={crumb.type ? `Type: ${crumb.type} - Click to highlight` : 'Click to highlight'}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onBreadcrumbClick) {
                          // Highlight all breadcrumb keys up to and including this one
                          const allBreadcrumbKeys = breadcrumb.slice(0, idx + 1).map(c => c.key);
                          onBreadcrumbClick(crumb.key, allBreadcrumbKeys);
                        }
                      }}
                    >
                      {crumb.name || crumb.key}
                    </span>
                    {!isLast && (
                      <>
                        <span className="text-light-400" style={{ color: relationColor || '#9ca3af' }}>
                          <ChevronsRight className="w-3 h-3" />
                        </span>
                        {primaryRelationType && (
                          <span
                            className="inline-flex items-center px-1.5 py-0.5 rounded text-white text-xs font-medium shadow-sm"
                            style={{ backgroundColor: relationColor || '#9ca3af' }}
                            title={relationTypes.length > 1 ? `Relations: ${relationTypes.join(', ')}` : `Relation: ${primaryRelationType}`}
                          >
                            {primaryRelationType}
                            {relationTypes.length > 1 && ` +${relationTypes.length - 1}`}
                          </span>
                        )}
                        <span className="text-light-400" style={{ color: relationColor || '#9ca3af' }}>
                          <ChevronsRight className="w-3 h-3" />
                        </span>
                      </>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        )}
        <div className="flex items-center justify-between px-3 py-2">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {onPanelSelectToggle && !isMain && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onPanelSelectToggle(panelIndex);
                }}
                className={`p-1.5 rounded transition-colors flex-shrink-0 ${
                  isPanelSelected 
                    ? 'bg-owl-blue-100 text-owl-blue-700 hover:bg-owl-blue-200' 
                    : 'hover:bg-light-200 text-light-600 hover:text-owl-blue-700'
                }`}
                title={isPanelSelected ? 'Deselect this table for multi-query' : 'Select this table for multi-query (Ctrl/Cmd+click to select multiple)'}
              >
                {isPanelSelected ? (
                  <CheckSquare className="w-4 h-4" />
                ) : (
                  <Square className="w-4 h-4" />
                )}
              </button>
            )}
            <span className={`text-sm font-medium truncate ${isResultsPanel ? 'text-purple-900' : 'text-owl-blue-900'}`}>
              {isResultsPanel ? (
                <span className="flex items-center gap-2">
                  <span className="inline-flex items-center px-2 py-0.5 rounded bg-purple-600 text-white text-xs font-semibold">
                    AI
                  </span>
                  <span>Assistant Results ({totalRows} nodes)</span>
                </span>
              ) : isMain ? (
                `All nodes (${totalRows})`
              ) : (
                `Relations of "${parentName(parentRowKey)}" (${totalRows})`
              )}
            </span>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {onPanelQueryAll && (
              <button
                type="button"
                onClick={(e) => onPanelQueryAll(panel, e)}
                className="flex items-center gap-1.5 px-2 py-1 text-xs rounded hover:bg-owl-blue-50 text-owl-blue-600 hover:text-owl-blue-700 transition-colors"
                title="Query all rows in this table (including breadcrumb context)"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Query All</span>
              </button>
            )}
            {!isMain && (
              <button
                type="button"
                onClick={() => onCollapse(panelIndex)}
                className="p-1 rounded hover:bg-light-200 text-light-600 hover:text-owl-blue-700 transition-colors"
                title="Collapse this panel"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
        
        {/* Pagination Controls */}
        {totalRows > 0 && (
          <div className="px-3 py-2 border-b border-light-200 bg-light-50 flex items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-light-600">Rows per page:</span>
              <select
                value={viewAll ? 'all' : pageSize}
                onChange={(e) => {
                  const value = e.target.value;
                  if (value === 'all') {
                    handleViewAllToggle();
                  } else {
                    handlePageSizeChange(parseInt(value));
                  }
                }}
                className="px-2 py-1 border border-light-300 rounded bg-white text-owl-blue-900 focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              >
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="250">250</option>
                <option value="500">500</option>
                <option value="1000">1000</option>
                <option value="all">All</option>
              </select>
            </div>
            
            {!viewAll && totalPages > 1 && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handlePageChange(1)}
                  disabled={currentPage === 1}
                  className="p-1 rounded hover:bg-light-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="First page"
                >
                  <ChevronsLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handlePageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="p-1 rounded hover:bg-light-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Previous page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-light-700 px-2">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => handlePageChange(currentPage + 1)}
                  disabled={currentPage >= totalPages}
                  className="p-1 rounded hover:bg-light-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Next page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handlePageChange(totalPages)}
                  disabled={currentPage >= totalPages}
                  className="p-1 rounded hover:bg-light-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Last page"
                >
                  <ChevronsRight className="w-4 h-4" />
                </button>
              </div>
            )}
            
            <div className="text-light-600">
              Showing {viewAll ? totalRows : `${startIndex + 1}-${Math.min(endIndex, totalRows)}`} of {totalRows} rows
            </div>
          </div>
        )}
      </div>

      <div className="overflow-auto flex-1 min-w-0">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-light-100 sticky top-0 z-10">
            <tr>
              {onCheckboxToggle && (
                <th className="border-b border-r border-light-200 px-2 py-1.5 text-center font-medium text-light-700 w-12">
                  <div className="flex items-center justify-center gap-1">
                    <input
                      type="checkbox"
                      checked={panelNodes.length > 0 && panelNodes.every(n => checkboxSelectedKeys.includes(n.key))}
                      onChange={(e) => {
                        if (e.target.checked && onSelectAll) {
                          onSelectAll(panelNodes);
                        } else if (!e.target.checked && onDeselectAll) {
                          onDeselectAll();
                        }
                      }}
                      className="w-4 h-4 text-owl-blue-600 border-light-300 rounded focus:ring-owl-blue-500"
                      title={panelNodes.length > 0 && panelNodes.every(n => checkboxSelectedKeys.includes(n.key)) ? 'Deselect all' : 'Select all'}
                    />
                  </div>
                </th>
              )}
              {allCols.map((col) => {
                const filterKey = `${panelIndex}-${col}`;
                const filterConfig = columnFilters.get(filterKey);
                const hasActiveFilter = filterConfig && filterConfig.selectedValues && filterConfig.selectedValues.length > 0;
                const isFilterOpen = openFilterDropdown && openFilterDropdown.key === filterKey;
                const uniqueValues = getUniqueValuesForColumn ? getUniqueValuesForColumn(panelIndex, col, panelNodesRaw, relationTypes, allCols) : [];
                
                return (
                  <th
                    key={col}
                    data-filter-trigger={`${panelIndex}-${col}`}
                    className="border-b border-r border-light-200 px-2 py-1.5 text-left font-medium text-light-700 whitespace-nowrap max-w-[200px] relative"
                    title={col}
                  >
                    <div className="flex items-center gap-1">
                      <span className="truncate flex-1">{col}</span>
                      <div className="flex items-center gap-0.5 flex-shrink-0">
                        {hasActiveFilter && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onColumnFilterChange && onColumnFilterChange(panelIndex, col, null);
                            }}
                            className="p-0.5 rounded hover:bg-light-200 transition-colors text-owl-blue-600"
                            title={`Clear filter (${filterConfig.selectedValues.length} values)`}
                          >
                            <X className="w-3 h-3" />
                          </button>
                        )}
                        <button
                          type="button"
                          data-filter-button={`${panelIndex}-${col}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            onFilterDropdownToggle && onFilterDropdownToggle(panelIndex, col, e);
                          }}
                          className={`p-0.5 rounded transition-colors flex-shrink-0 ${
                            isFilterOpen 
                              ? 'text-owl-blue-600 bg-owl-blue-50' 
                              : hasActiveFilter 
                              ? 'text-owl-blue-600 hover:bg-light-200' 
                              : 'text-light-400 hover:bg-light-200'
                          }`}
                          title={
                            isFilterOpen 
                              ? 'Close filter' 
                              : hasActiveFilter 
                              ? `Filter active (${filterConfig.selectedValues.length} values) - Click to change` 
                              : 'Filter column'
                          }
                        >
                          <Filter className={`w-3.5 h-3.5 ${isFilterOpen ? 'rotate-180' : ''} transition-transform`} />
                        </button>
                      </div>
                    </div>
                    {isFilterOpen && (
                      <FilterDropdownPortal
                        column={col}
                        panelIndex={panelIndex}
                        uniqueValues={uniqueValues}
                        filterConfig={filterConfig}
                        onFilterChange={onColumnFilterChange}
                        onClose={onFilterDropdownClose}
                        triggerSelector={`th[data-filter-trigger="${panelIndex}-${col}"]`}
                      />
                    )}
                  </th>
                );
              })}
              <th
                className="border-b border-l border-light-200 px-2 py-1.5 text-left font-medium text-light-700 z-10"
                style={{
                  ...RELATIONS_COLUMN_STICKY,
                  backgroundColor: '#d1d9e3', // Solid darker blue-gray for header
                }}
              >
                Relations
              </th>
              {onRowChatClick && (
                <th
                  className="border-b border-l border-light-200 px-2 py-1.5 text-center font-medium text-light-700 z-10"
                  style={{
                    ...CHAT_COLUMN_STICKY,
                    backgroundColor: '#d1d9e3', // Solid darker blue-gray for header
                  }}
                >
                  Chat
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {panelNodes.map((node) => {
              const flat = flattenNode(node);
              const { nodes: related } = getRelated(node.key);
              const hasRelations = related.length > 0;
              const relLabel = relationTypes[node.key]
                ? relationTypes[node.key].join(', ')
                : '';
              
              const isSelected = selectedNodeKeys.includes(node.key);
              const isCheckboxSelected = checkboxSelectedKeys.includes(node.key);
              const isTemporarilyHighlighted = highlightedKeys.has(node.key);
              const isBreadcrumbHighlighted = breadcrumbHighlightedKeys.has(node.key);
              const isHighlighted = isTemporarilyHighlighted || isBreadcrumbHighlighted;
              const entityType = node.type || '';
              const entityColor = getEntityTypeColor(entityType);
              
              // Determine row background color
              // Priority: checkbox selected > click selected > breadcrumb > temporary highlight
              let rowBgColor = 'bg-white';
              let rowStyle = {};
              let rowClassName = '';
              
              if (isCheckboxSelected) {
                // Checkbox selected: use stronger highlight with border
                rowBgColor = '';
                rowStyle = {
                  backgroundColor: `${entityColor}20`, // ~12% opacity for checkbox selection
                };
                rowClassName = 'ring-2 ring-owl-blue-400 ring-offset-1'; // Blue ring to indicate checkbox selection
              } else if (isSelected) {
                // Click selected: use entity type color with low opacity
                rowBgColor = '';
                rowStyle = {
                  backgroundColor: `${entityColor}15`, // ~8% opacity
                };
              } else if (isBreadcrumbHighlighted) {
                // Breadcrumb highlighted: use entity type color with medium opacity, persistent
                rowBgColor = '';
                rowStyle = {
                  backgroundColor: `${entityColor}25`, // ~15% opacity for persistent highlight
                };
              } else if (isTemporarilyHighlighted) {
                // Temporarily highlighted: use entity type color with medium opacity for brief highlight
                rowBgColor = '';
                rowStyle = {
                  backgroundColor: `${entityColor}40`, // ~25% opacity
                };
              }

              const isChatFocused = chatFocusedRowKey === node.key;
              
              return (
                <tr
                  key={node.key}
                  ref={(el) => {
                    if (el && rowRefs) {
                      rowRefs.current.set(node.key, el);
                    }
                  }}
                  className={`border-b border-light-200 hover:bg-owl-blue-50/50 transition-all duration-300 ${
                    rowBgColor
                  } ${onNodeClick ? 'cursor-pointer' : ''} ${isHighlighted ? 'animate-pulse' : ''} ${isChatFocused ? 'ring-2 ring-owl-blue-500 ring-offset-2' : ''} ${rowClassName}`}
                  style={rowStyle}
                  onClick={(e) => onNodeClick && onNodeClick(node, panel, e)}
                >
                  {onCheckboxToggle && (
                    <td
                      className="border-r border-light-200 px-2 py-1 text-center align-top"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={checkboxSelectedKeys.includes(node.key)}
                        onChange={(e) => onCheckboxToggle(node.key, e.target.checked)}
                        className="w-4 h-4 text-owl-blue-600 border-light-300 rounded focus:ring-owl-blue-500"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                  )}
                  {allCols.map((col) => (
                    <td
                      key={col}
                      className="border-r border-light-200 px-2 py-1 text-light-800 max-w-[200px] truncate align-top"
                      title={String(flat[col] ?? '')}
                      style={{
                        backgroundColor: isCheckboxSelected
                          ? `${entityColor}20`
                          : isSelected 
                          ? `${entityColor}15` 
                          : isHighlighted 
                          ? `${entityColor}40` 
                          : 'transparent',
                      }}
                    >
                      {col === 'Relation'
                        ? (searchHighlightTerms.length ? highlightMatchedText(relLabel, searchHighlightTerms) : relLabel)
                        : (searchHighlightTerms.length ? highlightMatchedText(flat[col] ?? '—', searchHighlightTerms) : (flat[col] ?? '—'))}
                    </td>
                  ))}
                  <td
                    className={`border-l border-light-200 px-2 py-1 align-top z-10`}
                    style={{
                      ...RELATIONS_COLUMN_STICKY,
                      backgroundColor: isCheckboxSelected
                        ? '#c8d8eb' // More tinted for checkbox selection
                        : isSelected 
                        ? '#d4e1f0' // Slightly tinted blue-gray when selected
                        : isHighlighted 
                        ? '#c8d8eb' // More tinted when highlighted
                        : '#e8ecf0', // Solid light blue-gray for control column
                    }}
                  >
                    {hasRelations ? (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          const isMultiSelect = e.ctrlKey || e.metaKey;
                          onExpand(panelIndex, node.key, isMultiSelect);
                        }}
                        className="flex items-center gap-1.5 text-owl-blue-600 hover:text-owl-blue-800 hover:underline font-medium"
                        title={`Expand ${related.length} relation(s) (Ctrl/Cmd+click to add multiple)`}
                      >
                        <ChevronRight className="w-4 h-4 flex-shrink-0" />
                        <span>{related.length}</span>
                      </button>
                    ) : (
                      <span className="text-light-400 text-xs">—</span>
                    )}
                  </td>
                  {onRowChatClick && (
                    <td
                      className={`border-l border-light-200 px-2 py-1 align-top z-10 text-center`}
                      style={{
                        ...CHAT_COLUMN_STICKY,
                        backgroundColor: isCheckboxSelected
                          ? '#c8d8eb' // More tinted for checkbox selection
                          : isSelected 
                          ? '#d4e1f0' // Slightly tinted blue-gray when selected
                          : breadcrumbHighlightedKeys.has(node.key)
                          ? '#c8d8eb' // More tinted for breadcrumb highlight
                          : highlightedKeys.has(node.key) 
                          ? '#c8d8eb' // More tinted when highlighted
                          : '#e8ecf0', // Solid light blue-gray for control column
                      }}
                    >
                      <button
                        type="button"
                        onClick={(e) => onRowChatClick(node, panel, e)}
                        className="p-1.5 rounded hover:bg-owl-blue-50 text-owl-blue-600 hover:text-owl-blue-700 transition-colors"
                        title="Query this row in AI Assistant (includes breadcrumb context)"
                      >
                        <MessageSquare className="w-4 h-4" />
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Filter Dropdown Portal Component
 * Renders the filter dropdown using a portal to escape overflow containers
 */
function FilterDropdownPortal({
  column,
  panelIndex,
  uniqueValues,
  filterConfig,
  onFilterChange,
  onClose,
  triggerSelector,
}) {
  const [position, setPosition] = useState({ left: 0, top: 0 });

  useEffect(() => {
    const updatePosition = () => {
      const triggerElement = document.querySelector(triggerSelector);
      if (triggerElement) {
        const rect = triggerElement.getBoundingClientRect();
        setPosition({
          left: rect.left,
          top: rect.bottom + window.scrollY + 4,
        });
      }
    };

    updatePosition();
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);

    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [triggerSelector]);

  return createPortal(
    <div
      className="fixed z-[9999]"
      style={{
        left: `${position.left}px`,
        top: `${position.top}px`,
      }}
    >
      <ColumnFilterDropdown
        column={column}
        panelIndex={panelIndex}
        uniqueValues={uniqueValues}
        filterConfig={filterConfig}
        onFilterChange={onFilterChange}
        onClose={onClose}
      />
    </div>,
    document.body
  );
}

/**
 * Column Filter Dropdown Component
 * Excel-like filter with search, multi-select, and include/exclude modes
 */
function ColumnFilterDropdown({
  column,
  panelIndex,
  uniqueValues,
  filterConfig,
  onFilterChange,
  onClose,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedValues, setSelectedValues] = useState(new Set(filterConfig?.selectedValues || []));
  const [filterMode, setFilterMode] = useState(filterConfig?.mode || 'include'); // 'include' or 'exclude'
  const dropdownRef = useRef(null);

  // Filter unique values based on search term
  const filteredValues = useMemo(() => {
    if (!searchTerm) return uniqueValues;
    const term = searchTerm.toLowerCase();
    return uniqueValues.filter(val => 
      String(val).toLowerCase().includes(term)
    );
  }, [uniqueValues, searchTerm]);

  // Handle value toggle
  const toggleValue = useCallback((value) => {
    setSelectedValues(prev => {
      const next = new Set(prev);
      if (next.has(value)) {
        next.delete(value);
      } else {
        next.add(value);
      }
      return next;
    });
  }, []);

  // Apply filter
  const handleApply = useCallback(() => {
    onFilterChange(panelIndex, column, {
      mode: filterMode,
      selectedValues: Array.from(selectedValues),
    });
    onClose();
  }, [panelIndex, column, filterMode, selectedValues, onFilterChange, onClose]);

  // Clear filter
  const handleClear = useCallback(() => {
    onFilterChange(panelIndex, column, null);
    setSelectedValues(new Set());
    onClose();
  }, [panelIndex, column, onFilterChange, onClose]);

  // Select all visible
  const handleSelectAll = useCallback(() => {
    setSelectedValues(new Set(filteredValues));
  }, [filteredValues]);

  // Deselect all
  const handleDeselectAll = useCallback(() => {
    setSelectedValues(new Set());
  }, []);

  // Close on outside click (but not when clicking the filter button)
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        // Check if the click is on a filter button - if so, don't close (let the toggle handle it)
        const target = event.target;
        const filterButton = target?.closest?.('button[data-filter-button]');
        if (!filterButton) {
          onClose();
        }
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const hasActiveFilter = filterConfig && filterConfig.selectedValues && filterConfig.selectedValues.length > 0;

  return (
    <div
      ref={dropdownRef}
      className="bg-white border border-light-300 rounded-lg shadow-xl min-w-[280px] max-w-[400px] max-h-[500px] flex flex-col"
    >
      {/* Header */}
      <div className="p-3 border-b border-light-200">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm text-light-900">Filter {column}</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-4 h-4 text-light-600" />
          </button>
        </div>
        
        {/* Mode toggle */}
        <div className="flex gap-2 mb-3">
          <button
            onClick={() => setFilterMode('include')}
            className={`flex-1 px-3 py-1.5 text-xs rounded transition-colors ${
              filterMode === 'include'
                ? 'bg-owl-blue-500 text-white'
                : 'bg-light-100 text-light-700 hover:bg-light-200'
            }`}
          >
            Include
          </button>
          <button
            onClick={() => setFilterMode('exclude')}
            className={`flex-1 px-3 py-1.5 text-xs rounded transition-colors ${
              filterMode === 'exclude'
                ? 'bg-owl-blue-500 text-white'
                : 'bg-light-100 text-light-700 hover:bg-light-200'
            }`}
          >
            Exclude
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-light-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search values..."
            className="w-full pl-8 pr-3 py-1.5 text-sm border border-light-300 rounded focus:outline-none focus:border-owl-blue-500"
          />
        </div>
      </div>

      {/* Values list */}
      <div className="flex-1 overflow-y-auto p-2">
        <div className="flex items-center justify-between mb-2 px-2">
          <span className="text-xs text-light-600">
            {filteredValues.length} value{filteredValues.length !== 1 ? 's' : ''}
          </span>
          <div className="flex gap-2">
            <button
              onClick={handleSelectAll}
              className="text-xs text-owl-blue-600 hover:text-owl-blue-700"
            >
              Select All
            </button>
            <button
              onClick={handleDeselectAll}
              className="text-xs text-owl-blue-600 hover:text-owl-blue-700"
            >
              Deselect All
            </button>
          </div>
        </div>
        <div className="space-y-1 max-h-[300px] overflow-y-auto">
          {filteredValues.length === 0 ? (
            <div className="text-center py-4 text-sm text-light-500">
              No values found
            </div>
          ) : (
            filteredValues.map((value) => {
              const isSelected = selectedValues.has(value);
              const displayValue = value === null || value === undefined ? '(empty)' : String(value);
              return (
                <label
                  key={value}
                  className="flex items-center gap-2 px-2 py-1.5 hover:bg-light-50 rounded cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleValue(value)}
                    className="w-4 h-4 text-owl-blue-600 border-light-300 rounded focus:ring-owl-blue-500"
                  />
                  <span className="text-sm text-light-700 flex-1 truncate" title={displayValue}>
                    {displayValue}
                  </span>
                </label>
              );
            })
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-light-200 flex items-center justify-between gap-2">
        <button
          onClick={handleClear}
          className="px-3 py-1.5 text-xs text-light-600 hover:text-light-800 transition-colors"
          disabled={!hasActiveFilter}
        >
          Clear
        </button>
        <button
          onClick={handleApply}
          className="px-4 py-1.5 text-xs bg-owl-blue-600 text-white rounded hover:bg-owl-blue-700 transition-colors"
        >
          Apply ({selectedValues.size})
        </button>
      </div>
    </div>
  );
}
