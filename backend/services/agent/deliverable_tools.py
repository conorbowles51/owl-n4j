"""Creation, discovery, incremental revision and calculation tools for the agent workspace."""
from __future__ import annotations

import copy
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from services.agent.calculation_workspace import calculate
from services.agent.claim_validation import CLAIM_INSTRUCTIONS, apply_claim_validation, resolve_source_reference
from services.agent.deliverables import edit_sections, get_path, new_artifact, revise_artifact, dependency_metadata, sections_in


class ListArgs(BaseModel):
    search: str = ""
    include_versions: bool = False
    offset: int = Field(0, ge=0)
    limit: int = Field(30, ge=1, le=200)


class ReadArgs(BaseModel):
    artifact_id: str
    section_id: str | None = Field(None, description="Read one report section by its stable ID, including nested sections. Prefer this when a check names a section ID. Supply either section_id or path, not both.")
    path: str | None = Field(None, description="Dot path within the saved content, such as sections.0.content or rows. Omit for the complete content. Optional data/value response-envelope prefixes are accepted when they are not real payload fields. Use next_read exactly to continue a list.")
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=500)
    include_check_details: bool = Field(False, description="Include the full internal evidence/calculation receipts. By default return revision, source handles and actionable check issues alongside the requested content, with an explicit handle for the full metadata.")


class CreateArgs(BaseModel):
    kind: str = Field(description="report, table, chart, graph, map, workbook, presentation, interactive, timeline, matrix or diagram. Maps use data.locations:[{name,latitude,longitude}]. Charts use data.rows plus chart_type,x_key,y_keys. Diagrams use nodes:[{id,label}] and links:[{source,target,label}].")
    title: str = Field(min_length=1, max_length=255)
    data: dict[str, Any] = Field(description="Renderer payload. Reports: sections with id,heading,content,embeds. Workbook: sheets with name,columns,rows. Presentation: slides with title,content,notes,embeds. Interactive: static html, static_content, rows/columns for searchable sortable data, interactions:{inputs:[{key,label,value,min?,max?,step?}],calculations:[{key,label,expression,decimals?}]} for trusted scenarios; expression supports arithmetic + - * / and parentheses on input/calculation keys. Raw scripts never execute. Matrix/timeline: rows,columns. Diagram: nodes,links. " + CLAIM_INSTRUCTIONS)
    required_items: list[str] = Field(default_factory=list, description="User-requested subjects or coverage that must survive revisions.")
    source_result_ids: list[str] = Field(default_factory=list)
    separate_copy_reason: str | None = Field(None, description="Only when the investigator requested a distinct deliverable with the same title and kind as saved work: record that reason. Ordinary corrections and follow-ups must revise the existing artifact instead.")
    data_refs: dict[str, dict[str, str]] = Field(default_factory=dict, description="Copy full saved data directly into payload target paths: {'sheets.0.rows':{'result_id':'res_id','path':'value'}} or {'rows':{'artifact_id':'id','path':'rows'}}. Never retype a preview. Target paths address dict keys and list indices; source IDs must be available in this conversation. Copied inputs and source hashes are retained.")


class ReviseArgs(BaseModel):
    artifact_id: str
    expected_revision: int = Field(ge=1)
    data: dict[str, Any] = Field(description="Complete revised payload; retain unrelated content and update claims and coverage when their content changes. " + CLAIM_INSTRUCTIONS)
    title: str | None = None
    revision_note: str = ""
    data_refs: dict[str, dict[str, str]] = Field(default_factory=dict, description="Target payload path to {result_id or artifact_id,path?}; copy complete saved data server-side before revising, with source fingerprint receipts.")


class EditArgs(BaseModel):
    artifact_id: str
    expected_revision: int = Field(ge=1)
    operations: list[dict[str, Any]] = Field(description="Atomic stable-ID edits at any nesting depth: append {action:'append',section:{...},parent_section_id?:id}; replace {action:'replace',section_id,section:{...}} preserves unmentioned children and embeds (supply [] to remove them); remove {action:'remove',section_id}; move {action:'move',section_id,index,target_parent_section_id?:id|null}. Move defaults to the existing parent; null moves to the report root. Index is the position after removal. Also {action:'set_document',fields:{purpose,scope,audience,language,document_metadata,document_layout,open_questions,sources,included_items}} and {action:'add_evidence',claim_bindings:[...],coverage:[...],numeric_claims:[...]}. Evidence records merge by stable id/item, preserving unrelated records. Add evidence alongside drafted sections without rewriting the whole report. IDs stay stable. Embeds remain pinned; to deliberately keep an older source after reviewing a newer one, set embed.dependency_review={decision:'retain_pinned',latest_artifact_id,reason}.")
    revision_note: str = ""


class AppendArgs(BaseModel):
    artifact_id: str
    expected_revision: int = Field(ge=1)
    rows: list[dict[str, Any]] | None = None
    rows_ref: dict[str, str] | None = Field(None, description="Alternative to rows: {result_id or artifact_id,path?}, resolving the complete saved batch server-side. Supply exactly one of rows or rows_ref.")
    path: str = "rows"


class CalculateArgs(BaseModel):
    expression: str = Field(description="Bounded Python expression; sum, len, min, max, abs, round, sorted, decimal, str, int, float, range(up to100000items), row indexing, comprehensions. No imports, attributes, files or network. e.g. sum([decimal(r['amount']) for r in rows]). Generated rows from range are synthetic assumptions, never source evidence.")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Explicit assumptions/constants; evidence data should use input_refs.")
    input_refs: dict[str, dict[str, str]] = Field(default_factory=dict, description="Variable to {artifact_id or result_id, path(optional)}. Reads the complete referenced data, not a preview.")


class InspectExportArgs(BaseModel):
    artifact_id: str
    format: Literal["pdf"] = "pdf"
    min_pages: int | None = Field(None, ge=1)
    max_pages: int | None = Field(None, ge=1)


def make_deliverable_tools(context):
    def artifact(artifact_id):
        found = context.artifact_store.get(artifact_id)
        if found is None:
            raise ValueError("Artifact is not available in this conversation. List the saved artifacts first.")
        from services.agent.conversation_read_tools import restore_artifact_results
        restore_artifact_results(context, found)
        return found

    def current(previous):
        family = previous.get("metadata", {}).get("deliverable_id", previous["id"])
        revisions = [a for a in context.artifact_store.values()
                     if a.get("metadata", {}).get("deliverable_id", a["id"]) == family]
        latest = max(revisions, key=lambda a: int(a.get("metadata", {}).get("revision", 1)))
        if latest["id"] != previous["id"]:
            raise ValueError("A newer revision exists: " + latest["id"] + ". Read it before editing.")

    def save(name, value):
        apply_claim_validation(value, context.result_store, context.artifact_store)
        meta = value["metadata"]
        return context.result(name, {"artifact_id": value["id"], "deliverable_id": meta["deliverable_id"],
            "revision": meta["revision"], "validation": meta["validation"]},
            summary=f"Saved draft {value['title']} (revision {meta['revision']}). " +
                    ("Revise the listed issues before calling it complete." if meta["validation"]["issues"] else "Structural and declared evidence checks passed; source truth and render review remain separate."), artifact=value)

    def hydrate(data):
        data = copy.deepcopy(data)
        def walk(container):
            if isinstance(container, list):
                for child in container:
                    walk(child)
            elif isinstance(container, dict):
                for embed in container.get("embeds", []):
                    if embed.get("artifact_id") and "data" not in embed:
                        original = artifact(embed["artifact_id"])
                        embed.update(type=original["type"], title=original["title"], available=True,
                                     data=copy.deepcopy(original["data"]), metadata=copy.deepcopy(original.get("metadata", {})))
                for key, child in container.items():
                    if key != "embeds":
                        walk(child)
        walk(data)
        return data

    def input_dependencies(reference, seen=None):
        if not isinstance(reference, dict):
            return []
        seen = set() if seen is None else seen
        kind = 'artifact_id' if reference.get('artifact_id') else 'result_id'
        identity = reference.get(kind)
        if not identity or (kind, identity) in seen:
            return []
        seen.add((kind, identity))
        dependencies = []
        if kind == 'artifact_id':
            original = artifact(identity)
            dependencies.append({'artifact_id': identity})
            for receipt in original.get('metadata', {}).get('input_receipts', []):
                dependencies.extend(input_dependencies(receipt.get('reference') or {}, seen))
            for binding in original.get('data', {}).get('claim_bindings', []):
                dependencies.extend(input_dependencies(binding.get('source') or {}, seen))
        else:
            original = context.result_store.get(identity, {})
            if isinstance(original, dict) and isinstance(original.get('input_refs'), dict):
                for child in (original.get('input_refs') or {}).values():
                    dependencies.extend(input_dependencies(child, seen))
        return dependencies

    def copy_inputs(data, references):
        data = copy.deepcopy(data)
        nested = data.pop('data_refs', {})
        if not isinstance(nested, dict):
            raise ValueError('data_refs must map target paths to saved source references.')
        references = dict(references or {})
        for key, value in nested.items():
            if key in references and references[key] != value:
                raise ValueError('Conflicting data references were supplied for ' + key)
            references[key] = value
        receipts = []
        for target_path, reference in (references or {}).items():
            parts = target_path.split(".")
            if not target_path or len(parts) > 32 or any(not part or part in {"__proto__", "prototype", "constructor"} for part in parts):
                raise ValueError("Data target paths must contain explicit dot-separated keys and list indices.")
            _, selected, receipt = resolve_source_reference(reference, context.result_store, context.artifact_store)
            parent = data
            for index, part in enumerate(parts):
                final = index == len(parts) - 1
                replacement = copy.deepcopy(selected) if final else ([] if parts[index + 1].isdigit() else {})
                if isinstance(parent, list):
                    if not part.isdigit() or int(part) > len(parent):
                        raise ValueError("A data target list index is out of range; provide its parent structure.")
                    key = int(part)
                    if key == len(parent):
                        parent.append(replacement)
                    elif final:
                        parent[key] = replacement
                    parent = parent[key]
                elif isinstance(parent, dict):
                    if final or part not in parent:
                        parent[part] = replacement
                    parent = parent[part]
                else:
                    raise ValueError("A data target path crosses a scalar value.")
            receipts.append({"purpose": "saved_input_copy", "target_path": target_path,
                             "reference": copy.deepcopy(reference), 'artifact_dependencies': input_dependencies(reference), **receipt})
        return data, receipts

    def retain_input_receipts(value, receipts):
        history = copy.deepcopy(value["metadata"].get("input_receipts", []))
        for receipt in receipts:
            history.append({**receipt, "applied_in_revision": value["metadata"]["revision"]})
        value["metadata"]["input_receipts"] = history
        return value

    def list_artifacts(search="", include_versions=False, offset=0, limit=30):
        rows = list(context.artifact_store.values())
        if not include_versions:
            latest = {}
            for a in rows:
                key = a.get("metadata", {}).get("deliverable_id", a["id"])
                if key not in latest or a.get("metadata", {}).get("revision", 1) > latest[key].get("metadata", {}).get("revision", 1):
                    latest[key] = a
            rows = list(latest.values())
        rows = [a for a in rows if search.casefold() in a.get("title", "").casefold()]
        return context.result("list_artifacts", {"total": len(rows), "offset": offset,
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "artifacts": [{**{k: v for k, v in a.items() if k not in {"data", "metadata"}},
                           "metadata": dependency_metadata(a, context.artifact_store)} for a in rows[offset:offset + limit]]},
            summary=f"Found {len(rows)} saved artifacts.")

    def read_artifact(artifact_id, path=None, offset=0, limit=50, include_check_details=False, section_id=None):
        a = artifact(artifact_id)
        if section_id and path:
            raise ValueError('Choose section_id or path for this read, not both.')
        if path:
            prefix, _, suffix = path.partition('.')
            if prefix in {'data', 'value'} and prefix not in a['data']:
                path = suffix or None
        if section_id:
            matching = [section for section in sections_in(a['data']) if section.get('id') == section_id]
            if len(matching) != 1:
                raise ValueError(f'Section {section_id!r} is absent or ambiguous. Read sections to inspect the saved IDs.')
            value = matching[0]
        else:
            try:
                value = get_path(a["data"], path) if path else a["data"]
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ValueError(f"Saved content has no path {path!r}. Use a content-relative path or omit path to read the root. Available root fields: {', '.join(a['data'])}.") from exc
        metadata = dependency_metadata(a, context.artifact_store)
        metadata.setdefault('completion_review', {
            'status': 'not_recorded_in_artifact',
            'issues': [],
            'scope': 'No completion-review receipt is stored in this artifact metadata. This does not mean the report passed. '
                     'Use the current completion issues supplied by the runtime; after drafting and export inspection, '
                     'finish the drafting turn so automatic source review can run. Do not guess additional metadata paths.'})
        content_metadata = {'deliverable_id', 'revision', 'previous_revision_id', 'status', 'source_case_ids',
            'source_result_ids', 'required_items', 'validation', 'completion_review', 'dependency_review', 'revision_note'}
        omitted = [] if include_check_details else [key for key in metadata if key not in content_metadata]
        data = {"artifact_id": a["id"], "title": a["title"],
            "metadata": metadata if include_check_details else {key: value for key, value in metadata.items() if key in content_metadata},
            "path": path}
        if section_id:
            data['section_id'] = section_id
        if omitted:
            data['metadata_details'] = {'omitted_fields': omitted,
                'read_full_metadata': {'artifact_id': a['id'], 'path': path, 'section_id': section_id, 'offset': offset, 'limit': limit,
                                       'include_check_details': True}}
        if isinstance(value, list):
            data.update(value=value[offset:offset + limit], total=len(value), offset=offset,
                        next_offset=offset + limit if offset + limit < len(value) else None,
                        next_read={'artifact_id': a['id'], 'path': path, 'offset': offset + limit, 'limit': limit,
                                   'include_check_details': include_check_details}
                            if offset + limit < len(value) else None)
        else:
            data["value"] = value
        return context.result("read_artifact", data, summary="Read saved artifact content; full list length and continuation are explicit.")

    def create_artifact(kind, title, data, required_items=None, source_result_ids=None, data_refs=None, separate_copy_reason=None):
        same_title = {}
        for previous in context.artifact_store.values():
            if previous.get('type') != kind.strip().lower() or previous.get('title', '').strip().casefold() != title.strip().casefold():
                continue
            meta = previous.get('metadata') or {}
            family = meta.get('deliverable_id', previous['id'])
            if family not in same_title or meta.get('revision', 1) > same_title[family].get('metadata', {}).get('revision', 1):
                same_title[family] = previous
        if same_title and not str(separate_copy_reason or '').strip():
            targets = '; '.join(f"artifact_id={item['id']}, expected_revision={item.get('metadata', {}).get('revision', 1)}" for item in same_title.values())
            raise ValueError('A saved deliverable already has this title and kind. Read and revise it to retain its history: '
                             + targets + '. Use separate_copy_reason only for an explicitly requested independent copy.')
        for source in source_result_ids or []:
            if source not in context.result_store:
                raise ValueError("A cited tool result is not available: " + source)
        data, receipts = copy_inputs(data, data_refs)
        value = new_artifact(kind, title, hydrate(data), requirements=required_items,
                             metadata={"source_result_ids": source_result_ids or []})
        if separate_copy_reason:
            value['metadata']['separate_copy_reason'] = separate_copy_reason.strip()
        return save("create_artifact", retain_input_receipts(value, receipts))

    def revise(artifact_id, expected_revision, data, title=None, revision_note="", data_refs=None):
        previous = artifact(artifact_id)
        current(previous)
        data, receipts = copy_inputs(data, data_refs)
        value = revise_artifact(previous, hydrate(data), expected_revision=expected_revision, title=title, revision_note=revision_note)
        return save("revise_artifact", retain_input_receipts(value, receipts))

    def edit(artifact_id, expected_revision, operations, revision_note=""):
        previous = artifact(artifact_id)
        current(previous)
        return save("edit_report_sections", edit_sections(previous, expected_revision=expected_revision,
                                                           operations=hydrate({"operations": operations})["operations"], revision_note=revision_note))

    def append(artifact_id, expected_revision, rows=None, path="rows", rows_ref=None):
        previous = artifact(artifact_id)
        current(previous)
        data = copy.deepcopy(previous["data"])
        target = get_path(data, path)
        if not isinstance(target, list):
            raise ValueError("Choose a list of rows to append to.")
        if (rows is None) == (rows_ref is None):
            raise ValueError("Supply exactly one of rows or rows_ref.")
        receipts = []
        if rows_ref is not None:
            _, rows, receipt = resolve_source_reference(rows_ref, context.result_store, context.artifact_store)
            receipts.append({"purpose": "appended_saved_batch", "target_path": path,
                             "start_index": len(target), "reference": copy.deepcopy(rows_ref),
                             'artifact_dependencies': input_dependencies(rows_ref), **receipt})
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("An appended batch must contain a list of row objects.")
        rows = copy.deepcopy(rows)
        for receipt in receipts:
            receipt["row_count"] = len(rows)
        target.extend(rows)
        value = revise_artifact(previous, data, expected_revision=expected_revision, revision_note=f"Appended {len(rows)} rows.")
        return save("append_artifact_rows", retain_input_receipts(value, receipts))

    def compute(expression, inputs=None, input_refs=None):
        variables = copy.deepcopy(inputs or {})
        for name, ref in (input_refs or {}).items():
            if ref.get("artifact_id"):
                value = artifact(ref["artifact_id"])["data"]
            elif ref.get("result_id") in context.result_store:
                value = context.result_store[ref["result_id"]]
            else:
                raise ValueError("Calculation input reference is unavailable.")
            variables[name] = get_path(value, ref["path"]) if ref.get("path") else value
        result = calculate(expression, variables)
        result["input_refs"] = input_refs or {}
        result["assumptions"] = inputs or {}
        return context.result("calculate_artifact_data", result, summary="Calculated from the full specified inputs; expression and input fingerprint retained.")

    def inspect(artifact_id, format="pdf", min_pages=None, max_pages=None):
        from services.agent.render_checks import inspect_export
        checks = inspect_export(artifact(artifact_id), export_format=format, min_pages=min_pages, max_pages=max_pages)
        return context.result("inspect_artifact_export", checks,
                              summary=f"Rendered the saved PDF: {checks['page_count']} pages. " +
                              ("Revise the listed issues, then inspect the new revision." if checks["issues"] else "Page, boundary and content-presence checks passed; visual review and source truth remain separate."))

    definitions = [
        ("list_artifacts", list_artifacts, ListArgs, "Find any saved artifact in this conversation, including early work; latest revisions by default."),
        ("read_artifact", read_artifact, ReadArgs, "Read saved content before editing. Read report sections by stable section_id, or lists by content-relative path and exact next_read. Compact metadata retains actionable issues; full audit receipts remain explicitly available."),
        ("create_artifact", create_artifact, CreateArgs, "Create a custom report, workbook, presentation, diagram, interactive HTML or other supported artifact. Long reports can start with sections then use edit_report_sections. Tables can grow with append_artifact_rows. Check returned validation."),
        ("revise_artifact", revise, ReviseArgs, "Save a new immutable revision of an existing artifact. Preserve unrelated content; requires the latest revision."),
        ("edit_report_sections", edit, EditArgs, "Incrementally build or revise a long report without replacing unrelated sections. Stable section IDs, append/replace/remove/move."),
        ("append_artifact_rows", append, AppendArgs, "Append a complete batch to a saved dataset/workbook list. Existing rows are retained; no preview truncation."),
        ("calculate_artifact_data", compute, CalculateArgs, "Execute bounded deterministic analysis code over full saved data. Use decimal for exact monetary arithmetic; no files, network or application access."),
        ("inspect_artifact_export", inspect, InspectExportArgs, "Render the full saved artifact as a PDF in memory; inspect actual page count, page bounds and source-data/text presence. Supply min_pages/max_pages from the user's requested length. Re-run after revision. This does not establish visual quality or source truth."),
    ]
    tools = []
    for name, fn, schema, description in definitions:
        def guarded(_fn=fn, _name=name, **kwargs):
            try:
                return _fn(**kwargs)
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                return context.result(_name, {"error": str(exc)}, summary="No change saved: " + str(exc), status="error", error=str(exc))
        tools.append(StructuredTool.from_function(guarded, name=name, description=description, args_schema=schema))
    return tools
