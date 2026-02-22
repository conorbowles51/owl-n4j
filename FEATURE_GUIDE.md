# OWL Platform — Feature Guide & Verification Walkthrough

> **Purpose:** Step-by-step guide for using and verifying the 14 features recently implemented in the OWL Investigation Platform. Each section explains what was built, where to find it, exactly how to use it, and how to confirm it's working.
>
> **Prerequisites:** You should be logged in as `neil.byrne@gmail.com` with the "Operation Silver Bridge" case loaded.

---

## Table of Contents

1. [Correct Transaction Amounts in Financial Dashboard](#1-correct-transaction-amounts-in-financial-dashboard)
2. [Bulk Categorization in Financial Dashboard](#2-bulk-categorization-in-financial-dashboard)
3. [Sub-Transaction Grouping](#3-sub-transaction-grouping)
4. [Filter by Entity in Financial Dashboard](#4-filter-by-entity-in-financial-dashboard)
5. [Entity Summary on Case Dashboard](#5-entity-summary-on-case-dashboard)
6. [AI Chat Analyses More Documents](#6-ai-chat-analyses-more-documents)
7. [Faster Table with Bulk Merge & Edit](#7-faster-table-with-bulk-merge--edit)
8. [Fix / Remove Locations on Map](#8-fix--remove-locations-on-map)
9. [Document Viewer Opens in Front (Portal Fix)](#9-document-viewer-opens-in-front-portal-fix)
10. [AI Creates Fewer / Less Noisy Entities](#10-ai-creates-fewer--less-noisy-entities)
11. [AI Insights — Generate, Accept & Reject](#11-ai-insights--generate-accept--reject)
12. [Clarified "Case Files" vs "All Evidence" Sections](#12-clarified-case-files-vs-all-evidence-sections)
13. [Export Financial Transactions to PDF](#13-export-financial-transactions-to-pdf)
14. [Save AI Chat Responses as Case Notes](#14-save-ai-chat-responses-as-case-notes)

---

## 1. Correct Transaction Amounts in Financial Dashboard

**What it does:** Lets you fix incorrect dollar amounts on any transaction directly in the table, with a full audit trail (original amount preserved, correction reason recorded, visual indicator).

**Where to find it:** Financial Dashboard → Transaction table → any Amount cell.

### How to use it

1. Navigate to the **Financial** view (click the dollar icon in the left sidebar).
2. Find any transaction in the table and **click on its dollar amount**.
3. The amount cell transforms into an **editable number input**.
4. Type the corrected amount and press **Enter** (or click the green checkmark).
5. A small prompt appears asking: **"Why is this being corrected?"** — type your reason (e.g., "Typo in source document, actual amount was $500K").
6. Click **Save**.

### How to verify it worked

- The amount cell now shows the new value.
- A small **amber pencil icon** (✏️) appears next to the corrected amount.
- **Hover over the pencil icon** — a tooltip shows:
  - Original amount (e.g., "$3,850,000")
  - Your correction reason
  - Who made the correction
- The original amount is preserved in the database and never lost.

---

## 2. Bulk Categorization in Financial Dashboard

**What it does:** Lets you select multiple transactions at once and assign them all to the same category in one action.

**Where to find it:** Financial Dashboard → Transaction table → row checkboxes → batch toolbar.

### How to use it

1. In the **Financial** view, use the **checkboxes** on the left side of the table to select two or more transactions.
2. A **batch action toolbar** appears above the table showing how many transactions are selected.
3. In the toolbar, click the **category dropdown** (it has a Tag icon).
4. Select the category you want to assign (e.g., "Wire Transfer", "Shell Company", "Legitimate").
5. All selected transactions are immediately updated with the new category.

### How to verify it worked

- Each selected transaction's category badge updates to the new category with its colour.
- You can also use the **"Set From"** / **"Set To"** buttons in the batch toolbar to bulk-assign the from-entity or to-entity on multiple transactions at once.
- Click **"Clear selection"** to deselect all rows when done.

---

## 3. Sub-Transaction Grouping

**What it does:** Lets you group related transactions under a parent transaction. For example, a $1.3M house purchase can be the parent, with $900K loan, $200K gift, and $200K fees as children.

**Where to find it:** Financial Dashboard → right-click any transaction → "Group as Sub-Transaction", OR expand a parent row with the chevron.

### How to use it

**To create a group:**

1. In the **Financial** table, **right-click** on the transaction you want to be the **parent** (e.g., the $1.3M house purchase).
2. In the context menu, click **"Group as Sub-Transaction"** (has a link icon).
3. The **Sub-Transaction Modal** opens showing:
   - The parent transaction at the top with its amount.
   - A **searchable list** of all other transactions in the case.
4. **Check the boxes** next to the transactions you want as children (e.g., the $900K loan, $200K gift, $200K fees).
5. As you select children, a **running total** is shown at the bottom. If the children's total doesn't match the parent amount, a **yellow warning** appears.
6. Click **"Link X Transaction(s)"** to save.

**To view a group:**

1. Parent transactions now show a **▶ chevron** on the left side of their row.
2. Click the **chevron** to expand — it becomes **▼** and the child transactions appear as **indented rows** below, each prefixed with **↳**.

**To remove a child from a group:**

1. Right-click on any **child transaction** (one with the ↳ prefix).
2. Click **"Remove from group"** (shown in red).
3. The child becomes an independent transaction again.

### How to verify it worked

- Parent rows show the ▶ expand chevron.
- Expanding shows indented child rows with ↳ prefix.
- The running total in the modal updates as you select/deselect children.
- Removing a child makes it a standalone row again.

---

## 4. Filter by Entity in Financial Dashboard

**What it does:** Lets you filter the transaction table to only show transactions involving a specific person, company, or account.

**Where to find it:** Financial Dashboard → Filter panel (top of the view).

### How to use it

1. In the **Financial** view, look at the **filter panel** at the top of the page (if collapsed, click the filter toggle to expand it).
2. Find the **Entity filter** field.
3. Start typing an entity name (e.g., "Marco Delgado" or "Solaris Property Group").
4. Select the entity from the dropdown suggestions.
5. The table immediately filters to show only transactions where that entity appears as a From or To party.

You can also filter the **From** and **To** entities on individual transactions:

1. Click the **pencil icon** (✏️) on any transaction's From or To cell.
2. An entity editor opens with a search field.
3. Search for and select the correct entity.
4. The cell updates with the new entity.

### How to verify it worked

- The table row count decreases to show only matching transactions.
- Clear the filter to see all transactions again.
- The pencil icon on From/To cells opens the entity editor.

---

## 5. Entity Summary on Case Dashboard

**What it does:** Adds a "Key Entities" section to the Case Overview dashboard showing all entities in the case, grouped by type (People, Companies, Organisations, Banks, Bank Accounts, etc.) with their summaries, fact counts, and insight counts.

**Where to find it:** Case Dashboard (Workspace view) → scroll down to the **"Key Entities"** section.

### How to use it

1. Navigate to the **Workspace** / **Case Overview** view (click the briefcase icon in the sidebar).
2. Scroll down past the Client Profile and Uploaded Documents sections.
3. You'll see the **Key Entities** section with:
   - **Tabs** across the top: "All", "People" (👥), "Companies" (🏢), and other entity types — each tab shows a count.
   - A **search bar** to filter entities by name.
   - A **sort dropdown** (top-right) to sort by: Name, Type, Facts, or Insights.
4. Click any **tab** to filter to that entity type.
5. Each entity card shows:
   - Entity name and type badge
   - Summary text
   - Number of verified facts
   - Number of AI insights

### How to verify it worked

- The tabs show accurate counts per entity type.
- Clicking "People" shows only Person entities.
- Search filters in real time as you type.
- Sorting by "Facts" puts entities with the most verified facts first.

---

## 6. AI Chat Analyses More Documents

**What it does:** The AI chat now retrieves and analyses up to **50 documents** (up from 10) and considers up to **25 verified facts** (up from 10) when answering questions. The context budget was increased from 12K to 80K tokens.

**Where to find it:** AI Chat panel (right sidebar).

### How to use it

1. Open the **AI Chat** panel (click the chat bubble icon in the sidebar, or it may already be in a side panel).
2. Ask a **cross-document question** like:
   - *"What connections exist between Solaris Property Group and the Cayman Islands across all evidence?"*
   - *"Summarize all financial irregularities found across every document in this case."*
3. The AI now pulls from **all 10 documents** in the case (previously it might have only used the top 10 most relevant chunks).

### How to verify it worked

- Ask a question that requires knowledge from multiple documents.
- The response should reference entities and facts from different source files.
- If the response includes a pipeline trace or debug info (expand the trace section), you'll see more retrieved passages than before.
- Responses should be more comprehensive and accurate than before the change.

---

## 7. Faster Table with Bulk Merge & Edit

**What it does:** The entity table now uses **pagination** for large datasets (instead of rendering all 170+ rows at once) and supports **bulk merge** (select 2 entities → merge) and **bulk edit** (select multiple → change a property on all).

**Where to find it:** Graph view → Table View tab (the table icon).

### How to use it

**Pagination:**

1. Switch to **Table View** in the graph panel.
2. At the bottom of the table, you'll see **pagination controls**: first/prev/next/last page buttons and a "Showing X–Y of Z entities" indicator.
3. Click the page navigation buttons to move through pages.

**Bulk Merge (exactly 2 entities):**

1. Use the **checkboxes** on the left of each row to select **exactly 2** entities that you believe are duplicates.
2. A toolbar appears at the top. The **"Merge 2"** button (with a merge icon) becomes active.
3. Click **"Merge 2"**.
4. The **Merge Entities Modal** opens with a side-by-side comparison:
   - Choose which entity's **name** to keep (Entity 1, Entity 2, or Both).
   - Choose which entity's **summary** to keep.
   - Check/uncheck individual **facts** and **insights** to include in the merged entity.
   - Add any **custom fields**.
5. Click **"Merge Entities"** to combine them into one.

**Bulk Edit (2+ entities):**

1. Select **2 or more** entities using the checkboxes.
2. Click the **"Bulk Edit"** button (pencil icon) in the toolbar.
3. A modal opens with:
   - A **property dropdown** — select which field to change (name, summary, notes, type, description).
   - A **new value input** — type the new value.
   - A **preview** showing what will change.
4. Click **"Apply"** to update all selected entities at once.

### How to verify it worked

- Pagination: the table loads instantly even with 170+ entities. Page controls work.
- Merge: after merging, only one entity remains. Search for the old name — it should be gone.
- Bulk Edit: after editing, all selected entities show the new value in the chosen field.

---

## 8. Fix / Remove Locations on Map

**What it does:** Lets you correct inaccurate AI-extracted location coordinates or remove bogus locations from the map entirely, using a right-click context menu.

**Where to find it:** Map View → right-click any location pin.

### How to use it

**To edit a location:**

1. Navigate to the **Map** view (click the map icon in the sidebar).
2. Find the location pin you want to correct.
3. **Right-click** on the pin.
4. A context menu appears with two options:
   - **"Edit Location"** (pencil icon)
   - **"Remove from Map"** (trash icon)
5. Click **"Edit Location"**.
6. A modal appears with three fields:
   - **Location Name** — the display name for this pin.
   - **Latitude** — the latitude coordinate.
   - **Longitude** — the longitude coordinate.
7. Correct the values (e.g., change latitude from 0 to 25.7617 for Miami).
8. Click **"Save"** (green checkmark button).

**To remove a location:**

1. Right-click the pin.
2. Click **"Remove from Map"** (trash icon).
3. The pin disappears from the map. The entity still exists in the graph — only its location data is removed.

### How to verify it worked

- After editing: the pin moves to the correct position on the map.
- After removing: the pin disappears. The entity still shows up in graph/table views — only the map pin is gone.
- Refresh the map to confirm changes persisted.

---

## 9. Document Viewer Opens in Front (Portal Fix)

**What it does:** Previously, when viewing a document from inside a modal (like the Merge Entities modal or the Map view), the document viewer would open *behind* the modal, forcing you to close the modal and lose your place. Now the document viewer uses a **React portal** to always render on top of everything.

**Where to find it:** Anywhere you click to view a source document — especially from the Merge Entities modal or Map view.

### How to use it

1. Go to the **Graph** view and run a **duplicate entity scan** (Entity Resolution tab).
2. When comparing two entities for merging, click on any **source document link** (e.g., "View in corporate_records.pdf").
3. The **Document Viewer** opens as a **full-screen overlay** that appears *on top of* the merge modal.
4. You can read the document, navigate pages, then **close it** (click X or press Escape).
5. You're returned to the merge modal exactly where you left off — no need to re-run the duplicate scan.

### How to verify it worked

- Open any modal (merge, map edit, etc.) and then open a document from within it.
- The document viewer should appear **on top** of the modal, not behind it.
- Closing the document viewer should return you to the modal.
- The same fix applies when viewing documents from the Map view.

---

## 10. AI Creates Fewer / Less Noisy Entities

**What it does:** The entity extraction prompts were tightened with strict quality rules, and a `max_entities_per_chunk` limit of 25 was added across all extraction profiles. The fuzzy matching threshold was raised from 0.7 to 0.88 to reduce false-positive duplicate suggestions.

**Where to find it:** This is a behind-the-scenes improvement. You'll notice it when ingesting **new** documents.

### How to verify it (on next ingestion)

1. When you next ingest a new document, compare the number of entities extracted to previous ingestions.
2. You should see **fewer, higher-quality entities** — less noise from:
   - Table headers or column names being extracted as entities.
   - Generic terms like "the investigation" or "the transaction" becoming entities.
   - Duplicates with slightly different names.
3. The entity extraction now follows strict rules:
   - Minimum 3 words for a name (except proper nouns).
   - Must be a real-world entity, not a category or concept.
   - No duplicates within the same chunk.
   - Only significant entities (mentioned 2+ times or central to the narrative).

**Note:** This improvement only applies to **newly ingested** documents. Previously extracted entities are not retroactively cleaned up (though you can use the merge and delete tools to clean them manually).

---

## 11. AI Insights — Generate, Accept & Reject

**What it does:** A new Insights Panel lets the AI analyse your case entities and generate investigative insights (inconsistencies, hidden connections, defense opportunities, Brady/Giglio material, patterns). You can then accept insights (promoting them to verified facts) or reject them.

**Where to find it:** Case Dashboard → **Insights** section (scroll down), or the Insights panel in the workspace sidebar.

### How to use it

**Generate insights:**

1. Navigate to the **Case Dashboard** (Workspace view).
2. Scroll to the **Insights** section.
3. Click the **"Generate"** button (has a sparkle ✨ icon).
4. Wait while the AI analyses your top entities (this may take 30–60 seconds as it calls the LLM for each entity).
5. Insight cards appear, grouped by entity.

**Review an insight:**

Each insight card shows:
- **Entity name** and type badge at the top.
- **Insight text** — the AI's finding.
- **Confidence badge** — High (green), Medium (amber), or Low (red).
- **Category badge** — inconsistency, connection, defense_opportunity, brady_giglio, or pattern.
- **Expandable reasoning** — click to see why the AI generated this insight.

**Accept an insight (promote to verified fact):**

1. Find an insight you agree with.
2. Click the **✅ Accept** button (green checkmark) on the insight card.
3. The insight is converted into a **verified fact** on that entity, attributed to you as the verifier.

**Reject an insight:**

1. Find an insight you disagree with or find unhelpful.
2. Click the **❌ Reject** button (red X) on the insight card.
3. The insight is permanently removed.

**Bulk actions:**

- **"Accept X High"** — accepts all high-confidence insights at once.
- **"Reject X Low"** — rejects all low-confidence insights at once.

### How to verify it worked

- After accepting: go to the entity's detail panel (click it in the graph). The insight text now appears in the **Verified Facts** section with your name as verifier.
- After rejecting: the insight card disappears. Re-fetch insights to confirm it's gone.
- After generating: insight cards appear with valid confidence levels and categories.

---

## 12. Clarified "Case Files" vs "All Evidence" Sections

**What it does:** The confusing section labels on the Case Dashboard were renamed:
- **"Case Documents"** → **"Uploaded Documents"** with subtitle: *"Files you have added to this case and processed for analysis"*
- **"All Evidence"** → **"Evidence Files"** with subtitle: *"Prosecution discovery and other evidence documents uploaded for analysis"*

**Where to find it:** Case Dashboard (Workspace view) → scroll through the sections.

### How to verify it worked

1. Navigate to the **Workspace / Case Overview**.
2. Look for the **"Uploaded Documents"** section — this shows supplementary files you've manually added to the case (notes, reports, etc.).
3. Look for the **"Evidence Files"** section — this shows the core evidence files that have been processed through the AI extraction pipeline.
4. Each section now has a clear subtitle explaining what it contains.

---

## 13. Export Financial Transactions to PDF

**What it does:** Generates a formatted PDF report of the financial transactions in the case, including summary cards, a detailed transaction table, and notes on any corrected amounts or sub-transaction groupings.

**Where to find it:** Financial Dashboard → **"Export PDF"** button (download icon) in the top-right header area.

### How to use it

1. Navigate to the **Financial** view.
2. Apply any **filters** you want (by type, category, date range, entity) — the PDF will export what's currently visible.
3. Click the **Download icon** (📥) in the toolbar area next to the Refresh button.
4. A new browser tab opens with the generated PDF, or your browser's download dialog appears.

The PDF includes:
- **Branded header** with case name and generation date.
- **Summary cards** — total transaction count, total amount, etc.
- **Full transaction table** — A4 landscape format with all visible transactions.
- **Corrected amount indicators** — transactions with corrected amounts show a pencil icon and footnote with the original amount and reason.
- **Sub-transaction formatting** — child transactions are indented with ↳ prefix.

### How to verify it worked

- The PDF opens and displays correctly.
- Transaction data matches what's shown in the table.
- Corrected amounts are flagged in the PDF.
- Sub-transactions appear as indented children under their parent.

**Note:** This feature requires the WeasyPrint system libraries to be installed. If you see an error, run `brew install pango glib gobject-introspection` in your terminal and restart the backend.

---

## 14. Save AI Chat Responses as Case Notes

**What it does:** Lets you save any useful AI chat response directly as an investigative note in the Case Dashboard, so you don't lose valuable analysis.

**Where to find it:** AI Chat panel → below any assistant message.

### How to use it

1. Open the **AI Chat** panel and ask a question.
2. After the AI responds, look **below the response** for a small **"Save as note"** button (has a bookmark/plus icon 🔖).
3. Click **"Save as note"**.
4. A **modal** appears with:
   - **Title** — pre-filled with a summary of the question (editable).
   - **Content** — pre-filled with the AI's full response (editable).
5. Edit the title or content if you want to trim or annotate it.
6. Click **"Save"**.
7. A brief **green checkmark** (✅) confirmation appears where the save button was, confirming the note was saved.

### How to verify it worked

- After saving, navigate to the **Case Dashboard** (Workspace view).
- Scroll to the **Notes** section.
- Your saved note should appear with the title you gave it and the AI's response as the content.
- The note is a full investigative note — you can edit, categorize, or delete it like any other note.

---

## Quick Reference: Where to Find Each Feature

| # | Feature | Location |
|---|---|---|
| 1 | Correct amounts | Financial → click any amount cell |
| 2 | Bulk categorize | Financial → select rows → batch toolbar → category dropdown |
| 3 | Sub-transactions | Financial → right-click row → "Group as Sub-Transaction" |
| 4 | Filter by entity | Financial → filter panel → entity filter field |
| 5 | Entity summary | Workspace → "Key Entities" section |
| 6 | AI analyses more docs | AI Chat → ask cross-document questions |
| 7 | Bulk merge/edit | Table View → select rows → "Merge 2" or "Bulk Edit" buttons |
| 8 | Fix/remove map pins | Map → right-click pin → "Edit Location" or "Remove from Map" |
| 9 | Doc viewer on top | Any modal → click document link → viewer opens on top |
| 10 | Less noisy extraction | Automatic on next ingestion |
| 11 | AI insights | Workspace → "Insights" section → "Generate" button |
| 12 | Clarified sections | Workspace → "Uploaded Documents" / "Evidence Files" |
| 13 | PDF export | Financial → Download icon (top-right) |
| 14 | Save chat as note | AI Chat → "Save as note" button below any AI response |

---

*Guide created for OWL Investigation Platform — February 2026*
