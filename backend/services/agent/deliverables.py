"""Versioned agent deliverables and structural completion checks.

Payloads remain compatible with stored artifacts. Resource ceilings reject a write explicitly;
they never select the first N rows, sections or outputs. Revisions are immutable snapshots.
"""
from __future__ import annotations

import copy
import json
import re
import uuid
import html
import hashlib
from html.parser import HTMLParser
from decimal import Decimal, InvalidOperation
from typing import Any

ARTIFACT_TYPES = frozenset({"report", "table", "chart", "graph", "map", "workbook",
                            "presentation", "interactive", "timeline", "matrix", "diagram"})
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
ARTIFACT_CHECK_VERSION = 2


def _validation_payload_hash(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, default=str).encode('utf8')).hexdigest()


def static_content_text(value):
    """Tolerate paragraph wrappers in a declared readable alternative, without running HTML."""
    text = str(value or '')
    if re.match(r'^\s*<(?:p|div|section)\b', text, re.I):
        text = re.sub(r'</?(?:p|div|section)\b[^>]*>|<br\s*/?>', '\n\n', text, flags=re.I)
        text = html.unescape(text).strip()
    return text


def bounded_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("An artifact needs an object containing its content.")
    try:
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("Artifact content must contain finite JSON values.") from exc
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("This revision exceeds 16 MiB. Split the data into named companion artifacts; nothing was saved.")
    return json.loads(encoded)


def sections_in(data: dict):
    for key in ("sections", "children"):
        items = data.get(key, [])
        if not isinstance(items, list):
            raise ValueError("Nested sections must be lists of section objects.")
        for section in items:
            if not isinstance(section, dict):
                raise ValueError("Each report section must be an object.")
            yield section
            yield from sections_in(section)


def get_path(data: Any, path: str) -> Any:
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("A boolean is not an amount.")
    return Decimal(re.sub(r"[$£€,\s]", "", str(value)))


def validate_artifact(kind: str, data: dict, requirements: list[str] | None = None) -> dict:
    """Return falsifiable checks, not a claim of independently verified source truth."""
    issues: list[str] = []
    warnings: list[str] = []
    if kind not in ARTIFACT_TYPES:
        issues.append("Unsupported artifact type.")
    bounded_payload(data)
    sections = list(sections_in(data))
    ids = [s.get("id") for s in sections if s.get("id")]
    if len(ids) != len(set(ids)):
        issues.append("Section identifiers must be unique.")
    if kind == "report":
        if not sections:
            issues.append("The report has no sections yet.")
        for s in sections:
            heading = s.get("heading") or "Untitled section"
            if s.get("sections") and s.get("children"):
                issues.append(f"{heading}: use one nested section collection, sections or children, so every child is rendered.")
            if not (str(s.get("content") or "").strip() or s.get("embeds") or s.get("sections") or s.get("children")):
                issues.append(f"{heading}: this section is empty.")
            content = str(s.get('content') or '')
            if content.count('\\n') >= 3 and content.count('\n') < 2:
                issues.append(f'{heading}: the prose contains literal escaped line breaks. Use real paragraph and table line breaks so the report renders correctly.')
            if len(re.findall(r'^\s*\|.*\|\s*$', content, re.M)) >= 3:
                from markdown_it import MarkdownIt
                blocks = MarkdownIt('commonmark', {'html': False}).enable('table').parse(content)
                if any(block.type == 'inline' and len(re.findall(r'^\s*\|.*\|\s*$', block.content, re.M)) >= 3 for block in blocks):
                    issues.append(f'{heading}: a pipe-delimited table is not valid Markdown. Put its header on a new line and add the separator row so PDF, Word and the viewer render a table.')
            if re.search(r"\btable\b", heading, re.I) and not s.get("embeds") and not re.search(r"\|.+\|", s.get("content", "")):
                issues.append(f"{heading}: a table was promised but no table is present.")
            for embed in s.get("embeds", []):
                if embed.get("available") is False or not embed.get("data"):
                    issues.append(f"{heading}: an embedded artifact is missing.")
    if kind in {"table", "matrix", "timeline", "chart"} and not data.get("rows"):
        issues.append("The artifact has no data rows.")
    if kind == "workbook" and not data.get("sheets"):
        issues.append("The workbook has no sheets.")
    if kind == 'workbook':
        for sheet in data.get('sheets') or []:
            if not isinstance(sheet, dict) or not isinstance(sheet.get('rows', []), list):
                issues.append('Each workbook sheet needs a row list.')
            elif not sheet.get('rows') and sheet.get('empty_template') is not True:
                issues.append(f"The worksheet {sheet.get('name') or 'Untitled'} is empty. Populate the requested data, or explicitly mark an intentionally blank template with empty_template:true.")
    if data.get('data_refs'):
        issues.append('Saved data references have not been copied into this draft. Resolve them through the artifact creation or revision tool before completing it.')
    if kind == "presentation" and not data.get("slides"):
        issues.append("The presentation has no slides.")
    if kind in {"graph", "diagram"}:
        nodes = data.get("nodes", [])
        keys = {str(n.get("id", n.get("key", ""))) for n in nodes}
        if not nodes:
            issues.append("The diagram has no nodes.")
        for link in data.get("links", []):
            if any(str(link.get(k, link.get(k + "_key", ""))) not in keys for k in ("source", "target")):
                issues.append("A diagram connection refers to a missing node.")
                break
    if kind == "interactive":
        if not (str(data.get("html", "")).strip() or data.get("rows") or data.get("interactions")):
            issues.append("The interactive artifact has no layout, data or controls.")
        if not str(data.get("static_content", "")).strip():
            warnings.append("Add a static explanation for print and non-interactive exports.")
        if data.get('interactions'):
            from services.agent.export_office import scenario_values
            try:
                scenario_values(data)
            except (ValueError, TypeError, KeyError, SyntaxError, ArithmeticError) as exc:
                issues.append(f'The interactive controls cannot calculate: {exc}')
    if kind in {'map', 'graph', 'diagram', 'chart'}:
        from services.agent.export_visuals import visual_svg
        try:
            visual_svg(kind, data)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            issues.append(f'The {kind} cannot render: {exc}')
    # Requirements are explicit user-supplied coverage labels, never inferred from a model's 'done'.
    visible = {key: value for key, value in data.items()
               if key not in {"required_items", "included_items", "numeric_checks", "metadata", "coverage", "claim_bindings", "numeric_claims"}}
    text = json.dumps(visible, ensure_ascii=False).casefold()
    missing = [r for r in requirements or [] if str(r).casefold() not in text]
    issues.extend(f"Required coverage is missing: {r}" for r in missing)
    assertions = data.get("numeric_checks", [])
    for check in assertions:
        try:
            values = get_path(data, check["rows_path"])
            total = sum((_decimal(get_path(row, check["column"])) for row in values), Decimal(0))
            expected = _decimal(get_path(data, check["value_path"]))
            if abs(total - expected) > Decimal(str(check.get("tolerance", "0.005"))):
                issues.append(f"Calculation mismatch: {check.get('label', check['value_path'])}: {expected} versus {total}.")
        except (ValueError, TypeError, KeyError, IndexError, InvalidOperation):
            issues.append("A calculation check refers to missing or non-numeric data.")
    return {"status": "needs_revision" if issues else "structural_checks_passed", "issues": issues,
            "check_version": ARTIFACT_CHECK_VERSION,
            "data_sha256": _validation_payload_hash(data),
            "warnings": warnings, "checks": {"required_items": len(requirements or []),
            "sections": len(sections), "numeric_checks": len(assertions)},
            "source_review": "not_established", "render_review": "not_established"}


def new_artifact(kind: str, title: str, data: dict, *, requirements=None, metadata=None) -> dict:
    if kind not in ARTIFACT_TYPES:
        raise ValueError("Choose a supported artifact renderer.")
    title = str(title).strip()
    if not title or len(title) > 255:
        raise ValueError("Give the artifact a title of 1–255 characters.")
    payload = bounded_payload(data)
    if kind == 'interactive' and 'static_content' in payload:
        payload['static_content'] = static_content_text(payload['static_content'])
    for section in sections_in(payload):
        section.setdefault("id", str(uuid.uuid4()))
    artifact_id = str(uuid.uuid4())
    meta = dict(metadata or {})
    # Evidence/render receipts describe one immutable payload. Editing invalidates them.
    meta.pop("claim_evidence", None)
    meta.pop("render_inspection", None)
    meta.pop("dependency_review", None)
    meta.update(deliverable_id=artifact_id, revision=1, required_items=list(requirements or []),
                validation=validate_artifact(kind, payload, requirements), status="draft")
    return {"id": artifact_id, "type": kind, "title": title, "data": payload, "metadata": meta}


def revise_artifact(previous: dict, data: dict, *, expected_revision: int, title=None, revision_note="") -> dict:
    meta = previous.get("metadata") or {}
    if expected_revision != int(meta.get("revision", 1)):
        raise ValueError("This artifact has changed. Open the current revision before editing.")
    artifact = new_artifact(previous["type"], title or previous["title"], data,
                            requirements=meta.get("required_items", []), metadata=meta)
    artifact["metadata"].update(deliverable_id=meta.get("deliverable_id", previous["id"]),
        revision=expected_revision + 1, previous_revision_id=previous["id"], revision_note=revision_note)
    return artifact


def edit_sections(previous: dict, *, expected_revision: int, operations: list[dict], revision_note="") -> dict:
    if previous["type"] != "report":
        raise ValueError("Section edits apply to a report.")
    data = copy.deepcopy(previous["data"])
    data.setdefault("sections", [])

    def locate(section_id):
        matches = []
        def walk(parent):
            for key in ("sections", "children"):
                for index, section in enumerate(parent.get(key, [])):
                    if section.get("id") == section_id:
                        matches.append((parent[key], index, section))
                    walk(section)
        walk(data)
        if len(matches) != 1:
            raise ValueError("The requested section does not exist or its ID is ambiguous; no changes were applied.")
        return matches[0]

    def children(parent_id):
        if parent_id is None:
            return data["sections"]
        parent = locate(parent_id)[2]
        if parent.get("sections") and parent.get("children"):
            raise ValueError("The target parent has ambiguous nested collections; use a single sections list.")
        key = "children" if parent.get("children") or "children" in parent and "sections" not in parent else "sections"
        return parent.setdefault(key, [])

    def check_ids():
        ids = [s.get("id") for s in sections_in(data)]
        if len(ids) != len(set(ids)):
            raise ValueError("Section IDs must be unique across the full report; no changes were applied.")

    # Assign IDs to legacy descendants before the first operation, once in this revision.
    for section in sections_in(data):
        section.setdefault("id", str(uuid.uuid4()))
    check_ids()
    for op in operations:
        action = op.get("action")
        if action == "set_document":
            values = op.get("fields")
            allowed = {"purpose", "scope", "audience", "language", "document_metadata", "document_layout", "open_questions", "sources", "included_items"}
            if not isinstance(values, dict) or set(values) - allowed:
                raise ValueError("Document fields may update presentation, scope, sources and open questions; edit sections by stable ID.")
            data.update(copy.deepcopy(values))
        elif action == "add_evidence":
            for field, identity in (("claim_bindings", ("id",)), ("coverage", ("item",)),
                                    ("numeric_claims", ("binding_id", "section_id", "content_path"))):
                incoming = op.get(field, [])
                if not isinstance(incoming, list) or any(not isinstance(item, dict) or not item.get(identity[0]) for item in incoming):
                    raise ValueError("Evidence records need stable claim IDs, coverage items or numeric binding IDs.")
                records = data.setdefault(field, [])
                for item in incoming:
                    key = tuple(item.get(part) for part in identity)
                    matches = [i for i, record in enumerate(records) if tuple(record.get(part) for part in identity) == key]
                    if len(matches) > 1:
                        raise ValueError("An existing evidence record has an ambiguous identity; no changes were applied.")
                    if matches:
                        records[matches[0]] = copy.deepcopy(item)
                    else:
                        records.append(copy.deepcopy(item))
        elif action == "append":
            item = copy.deepcopy(op["section"])
            if not isinstance(item, dict):
                raise ValueError("An appended section must be an object.")
            item.setdefault("id", str(uuid.uuid4()))
            for child in sections_in(item):
                child.setdefault("id", str(uuid.uuid4()))
            children(op.get("parent_section_id")).append(item)
        elif action in {"replace", "remove", "move"}:
            siblings, index, target = locate(op.get("section_id"))
            if action == "replace":
                item = copy.deepcopy(op["section"])
                if not isinstance(item, dict):
                    raise ValueError("A replacement section must be an object.")
                item["id"] = target["id"]
                # Replacing prose does not delete unmentioned descendants or exhibits.
                preserve_children = not any(key in item for key in ("sections", "children"))
                for key in ("sections", "children", "embeds"):
                    if key in target and key not in item and (key == "embeds" or preserve_children):
                        item[key] = copy.deepcopy(target[key])
                for child in sections_in(item):
                    child.setdefault("id", str(uuid.uuid4()))
                siblings[index] = item
            elif action == "remove":
                siblings.pop(index)
            else:
                parent_id = op.get("target_parent_section_id", op.get("parent_section_id"))
                target_parent_specified = "target_parent_section_id" in op or "parent_section_id" in op
                subtree_ids = {target["id"], *(s["id"] for s in sections_in(target))}
                if target_parent_specified and parent_id in subtree_ids:
                    raise ValueError("A section cannot move inside itself or its descendants; no changes were applied.")
                destination_list = children(parent_id) if target_parent_specified else siblings
                destination = op.get("index")
                max_index = len(destination_list) - (1 if destination_list is siblings else 0)
                if isinstance(destination, bool) or not isinstance(destination, int) or not 0 <= destination <= max_index:
                    raise ValueError("The destination section index is out of range.")
                siblings.pop(index)
                destination_list.insert(destination, target)
        else:
            raise ValueError("Use append, replace, remove or move for a section edit.")
        check_ids()
    data["embedded_artifacts"] = [e for s in sections_in(data) for e in s.get("embeds", [])]
    return revise_artifact(previous, data, expected_revision=expected_revision, revision_note=revision_note)


def detect_dependencies(artifact: dict, artifact_store: dict) -> dict:
    """Compare pinned exhibits with accessible saved revisions, without changing a pin."""
    latest = {}
    for record in artifact_store.values():
        meta = record.get("metadata", {})
        family = meta.get("deliverable_id", record["id"])
        if family not in latest or int(meta.get("revision", 1)) > int(latest[family].get("metadata", {}).get("revision", 1)):
            latest[family] = record
    embeds = []
    def walk(value, path="data"):
        if isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}.{index}")
        elif isinstance(value, dict):
            for index, embed in enumerate(value.get("embeds", []) or []):
                if isinstance(embed, dict) and embed.get("artifact_id"):
                    embeds.append((embed, f"{path}.embeds.{index}"))
            for key, child in value.items():
                if key not in {"embeds", "embedded_artifacts", "metadata", "claim_bindings", "coverage"}:
                    walk(child, f"{path}.{key}")
    walk(artifact.get("data", {}))
    if not embeds:
        embeds = [(embed, f"data.embedded_artifacts.{index}") for index, embed in enumerate(artifact.get("data", {}).get("embedded_artifacts", []))
                  if isinstance(embed, dict) and embed.get("artifact_id")]
    # Copied datasets and computed values are also pinned inputs. A changed source
    # must flag downstream work even when it is not displayed as an embedded exhibit.
    active_inputs = {}
    for receipt in artifact.get('metadata', {}).get('input_receipts', []):
        target = receipt.get('target_path')
        if receipt.get('purpose') == 'saved_input_copy':
            active_inputs[target] = []
        active_inputs.setdefault(target, []).append(receipt)
    copied = {}
    for receipts in active_inputs.values():
        for receipt in receipts:
            for dependency in [receipt, *(receipt.get('artifact_dependencies') or [])]:
                if dependency.get('artifact_id'):
                    copied[dependency['artifact_id']] = dependency
    for binding in artifact.get('metadata', {}).get('claim_evidence', {}).get('bindings', []):
        for dependency in (binding.get('calculation', {}).get('input_sources') or {}).values():
            if dependency.get('artifact_id'):
                copied[dependency['artifact_id']] = dependency
    family_id = artifact.get('metadata', {}).get('deliverable_id', artifact['id'])
    decisions = artifact.get('data', {}).get('source_dependency_reviews', {})
    for identity in copied:
        original = artifact_store.get(identity, {})
        if original.get('metadata', {}).get('deliverable_id', identity) == family_id:
            continue  # Revising a deliverable from its own previous version is not a stale external input.
        decision = decisions.get(identity, {}) if isinstance(decisions, dict) else {}
        embeds.append(({'artifact_id': identity, 'dependency_kind': 'copied_input',
                       'dependency_review': decision.get('dependency_review') if isinstance(decision, dict) else None},
                      f'data.source_dependency_reviews.{identity}'))
    items, issues = [], []
    for embed, path in embeds:
        source_id = embed["artifact_id"]
        original = artifact_store.get(source_id)
        pinned_meta = original.get("metadata", {}) if original else embed.get("metadata", {})
        family = pinned_meta.get("deliverable_id", source_id)
        pinned_revision = int(pinned_meta.get("revision", 1))
        newest = latest.get(family)
        item = {"artifact_id": source_id, "title": embed.get("title") or (original or {}).get("title") or "Embedded exhibit",
                "location": path, "deliverable_id": family, "pinned_revision": pinned_revision,
                "latest_artifact_id": newest["id"] if newest else None,
                "latest_revision": int(newest.get("metadata", {}).get("revision", 1)) if newest else None,
                "status": "current"}
        if embed.get('dependency_kind'):
            item['dependency_kind'] = embed['dependency_kind']
        if original is None:
            item["status"] = "source_unavailable"
            issues.append(f"{item['title']}: the pinned source revision is unavailable; review the saved exhibit before completion.")
        elif newest and item["latest_revision"] > pinned_revision:
            decision = embed.get("dependency_review") or {}
            if (isinstance(decision, dict) and decision.get("decision") == "retain_pinned"
                    and decision.get("latest_artifact_id") == newest["id"] and str(decision.get("reason") or "").strip()):
                item["status"] = "retained_after_review"
                item["review"] = copy.deepcopy(decision)
            else:
                item["status"] = "newer_revision_available"
                issues.append(f"{item['title']}: revision {pinned_revision} is used, but revision {item['latest_revision']} is now available. Review the change and revise the deliverable or explicitly retain the pinned revision with a reason.")
        items.append(item)
    return {"status": "review_needed" if issues else "current", "items": items, "issues": issues,
            "scope": "Checks accessible saved artifact families. Existing embedded data and revision pins remain unchanged."}


def dependency_metadata(artifact: dict, artifact_store: dict) -> dict:
    """Return a fresh view of review status; do not mutate an immutable artifact."""
    meta = copy.deepcopy(artifact.get("metadata", {}))
    prior_issues = (meta.get("dependency_review") or {}).get("issues", [])
    review = detect_dependencies(artifact, artifact_store)
    meta["dependency_review"] = review
    if "validation" not in meta:
        meta["validation"] = validate_artifact(artifact["type"], artifact.get("data", {}), meta.get("required_items", []))
    validation = meta["validation"]
    fresh = (validation if validation.get('check_version') == ARTIFACT_CHECK_VERSION
             and validation.get('data_sha256') == _validation_payload_hash(artifact.get('data', {})) else
             validate_artifact(artifact['type'], artifact.get('data', {}), meta.get('required_items', [])))
    validation['check_version'] = fresh['check_version']
    validation['data_sha256'] = fresh['data_sha256']
    located = {record.get('item') for record in (meta.get('claim_evidence') or {}).get('coverage', [])
               if record.get('status') == 'content_located'}
    fresh_issues = [issue for issue in fresh['issues'] if issue not in {f'Required coverage is missing: {item}' for item in located}]
    validation['issues'] = list(dict.fromkeys([*validation.get('issues', []), *fresh_issues]))
    validation["issues"] = [issue for issue in validation.get("issues", []) if issue not in prior_issues] + review["issues"]
    validation.setdefault("checks", {})["pinned_dependencies"] = len(review["items"])
    validation["dependency_review"] = review["status"]
    validation["status"] = "needs_revision" if validation["issues"] else "structural_checks_passed"
    return meta


class _StaticHTML(HTMLParser):
    """Keep custom layouts but never accept executable or navigable source markup."""
    tags = set("div span p section article header footer main aside nav h1 h2 h3 h4 h5 h6 table thead tbody tfoot tr th td caption colgroup col ul ol li dl dt dd blockquote pre code b strong i em u s small sup sub br hr a img figure figcaption details summary style".split())
    void = {"br", "hr", "img", "col"}
    forbidden = {"script", "iframe", "object", "embed", "template", "svg", "math", "textarea", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = []
        self.styles = None

    @staticmethod
    def css(value):
        # External resources, escaped identifiers and legacy executable CSS are unnecessary.
        return "" if re.search(r"url\s*\(|@|\\\\|expression\s*\(|behavior\s*:|-moz-binding", value, re.I) else value.replace("<", "").replace(">", "")

    def handle_starttag(self, tag, attrs):
        if self.blocked:
            if tag in self.forbidden:
                self.blocked.append(tag)
            return
        if tag in self.forbidden:
            self.blocked.append(tag)
            return
        if tag not in self.tags:
            return
        if tag == "style":
            self.styles = []
            return
        safe = []
        for key, value in attrs:
            value = value or ""
            if key in {"id", "class", "title", "aria-label", "role", "colspan", "rowspan", "scope", "alt", "width", "height"}:
                safe.append((key, value))
            elif key == "style":
                safe.append((key, self.css(value)))
            elif tag == "a" and key == "href" and re.fullmatch(r"#[\w-]+", value):
                safe.append((key, value))
            elif tag == "img" and key == "src" and re.fullmatch(r"data:image/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+", value):
                safe.append((key, value))
        self.parts.append("<" + tag + "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in safe) + ">")

    def handle_endtag(self, tag):
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
            return
        if tag == "style" and self.styles is not None:
            self.parts.append("<style>" + self.css("".join(self.styles)) + "</style>")
            self.styles = None
        elif tag in self.tags and tag not in self.void:
            self.parts.append("</" + tag + ">")

    def handle_data(self, data):
        if self.blocked:
            return
        if self.styles is not None:
            self.styles.append(data)
        else:
            self.parts.append(html.escape(data))


def interactive_document(source: str) -> str:
    """Static custom layout; trusted host controls supply declared interactions separately.

    No model-authored scripts execute. An iframe must also use sandbox="". Sanitization
    prevents refresh/navigation even when this standalone document is downloaded.
    """
    parser = _StaticHTML()
    parser.feed(source)
    parser.close()
    policy = ("default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
              "img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; "
              "object-src 'none'; base-uri 'none'; form-action 'none'")
    return ('<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
            '<meta name="referrer" content="no-referrer"></head><body>' + "".join(parser.parts) + '</body></html>')
