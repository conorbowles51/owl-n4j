"""Check declared claims against full saved sources, without asserting global truth.

Bindings are immutable evidence receipts: source identity, source/content hashes,
the exact rendered claim and, for computed values, reproducible input hashes.
An exact quotation proves presence in a source, not that the source is correct.
Coverage excerpts prove content was supplied, not that its analysis is adequate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from services.agent.calculation_workspace import calculate
from services.agent.deliverables import get_path


CLAIM_INSTRUCTIONS = (
    "For sourced statements include data.claim_bindings:[{id,section_id or content_path,claim_text,"
    "source:{result_id or artifact_id,path?},quote?}]. Quotes must occur verbatim in the full source and rendered content. "
    "For calculated claims add numeric:{value_path:'value',rendered_value:'123.00',decimals?:2}; source must be a "
    "calculate_artifact_data result, whose expression and full input references will be recomputed. Declare material numeric "
    "claims in data.numeric_claims:[{section_id or content_path,claim_text,binding_id}]; every declaration needs a numeric binding. "
    "For each required_item add data.coverage:[{item,status:'fulfilled' or 'unresolved',section_id or content_path,"
    "excerpt?,claim_ids?:[],reason?}]. Fulfilled coverage needs an exact rendered excerpt or valid claim IDs in that location. "
    "Monetary totals and immediately numeric total/aggregate/combined statements are also detected automatically and need a numeric binding. "
    "A verbatim reported figure may instead use quote plus reported_figure:true, with the prose explicitly calling it reported/stated/recorded/quoted. "
    "These checks establish reference/quote/calculation consistency only; source truth and analytical completeness need review."
)


def fingerprint(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonical_source_fingerprint(results):
    """Hash source contents once per view batch, excluding unrelated tool outputs."""
    pages = set()
    for value in results.values():
        if isinstance(value, dict) and value.get('evidence_id') and isinstance(value.get('pages'), list):
            for page in value['pages']:
                if isinstance(page, dict):
                    pages.add((str(value['evidence_id']), str(value.get('revision')), str(page.get('page_number')),
                               bool(page.get('text_missing')), str(page.get('text') or '')))
    return fingerprint(sorted(pages))


def validation_signature(artifact, results, artifacts, *, canonical_digest=None):
    """Exact authored and relevant source values, plus the current checker version."""
    references, seen = [], set()
    def visit(reference):
        if not isinstance(reference, dict):
            return
        kind = 'artifact_id' if reference.get('artifact_id') else 'result_id'
        identity = reference.get(kind)
        if not identity or (kind, identity) in seen:
            return
        seen.add((kind, identity))
        value = artifacts.get(identity) if kind == 'artifact_id' else results.get(identity)
        selected = value.get('data') if kind == 'artifact_id' and isinstance(value, dict) else value
        references.append((kind, identity, fingerprint(selected)))
        if kind == 'result_id' and isinstance(value, dict) and isinstance(value.get('input_refs'), dict):
            for child in value['input_refs'].values():
                visit(child)
    for binding in artifact['data'].get('claim_bindings', []) or []:
        if isinstance(binding, dict):
            visit(binding.get('source'))
    meta = artifact.get('metadata', {})
    return fingerprint({'check_version': 2, 'type': artifact['type'], 'data': artifact['data'],
        'required': meta.get('required_items', []), 'references': references,
        'source_presence': [(key, key in results) for key in meta.get('source_result_ids', [])],
        'canonical': canonical_digest if canonical_digest is not None else canonical_source_fingerprint(results)})


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _sections(data):
    for section in data.get("sections", []) or []:
        if isinstance(section, dict):
            yield section
            yield from _sections(section)
            yield from _sections({"sections": section.get("children", [])})


def _rendered(data, declaration):
    """Only visible content can support a claim; validation metadata cannot self-certify."""
    section_id = declaration.get("section_id")
    path = declaration.get("content_path")
    if bool(section_id) == bool(path):
        raise ValueError("Specify exactly one section_id or content_path for the rendered claim.")
    if section_id:
        matches = [s for s in _sections(data) if s.get("id") == section_id]
        if len(matches) != 1:
            raise ValueError("The claimed report section is missing or ambiguous.")
        section = matches[0]
        # Heading alone cannot satisfy a promised subject or a claim.
        content = section.get("content", "")
    else:
        if any(p in {"claim_bindings", "numeric_claims", "coverage", "metadata", "numeric_checks", "required_items", "included_items", "sources"}
               for p in str(path).split(".")):
            raise ValueError("A claim must point to rendered content, not declarations or source metadata.")
        if not re.fullmatch(r"(?:(?:sections\.\d+\.)*(?:sections|slides)\.\d+\.content|(?:rows|locations|nodes|links)\.\d+(?:\.[\w-]+)+|sheets\.\d+\.rows\.\d+(?:\.[\w-]+)+|static_content|description|purpose|scope)", str(path)):
            raise ValueError("content_path must address rendered prose or an explicit data cell.")
        content = get_path(data, str(path))
    rendered = (str(content) if isinstance(content, (int, float, Decimal)) and not isinstance(content, bool)
                else "\n".join(_strings(content)))
    return rendered, {k: declaration[k] for k in ("section_id", "content_path") if declaration.get(k)}


def _source(reference, results, artifacts):
    if not isinstance(reference, dict) or bool(reference.get("result_id")) == bool(reference.get("artifact_id")):
        raise ValueError("A source needs exactly one result_id or artifact_id.")
    if reference.get("path") is not None and not isinstance(reference["path"], str):
        raise ValueError("Source paths must be dot-separated strings.")
    if reference.get("result_id"):
        identity = reference["result_id"]
        if identity not in results:
            raise ValueError("The cited tool result is unavailable: " + str(identity))
        whole = results[identity]
        receipt = {"result_id": identity}
    else:
        identity = reference["artifact_id"]
        if identity not in artifacts:
            raise ValueError("The cited artifact is unavailable: " + str(identity))
        artifact = artifacts[identity]
        whole = artifact["data"]
        receipt = {"artifact_id": identity, "revision": artifact.get("metadata", {}).get("revision", 1)}
    selected = get_path(whole, reference["path"]) if reference.get("path") else whole
    receipt.update(path=reference.get("path"), source_sha256=fingerprint(whole), selected_sha256=fingerprint(selected))
    return whole, selected, receipt


def resolve_source_reference(reference, result_store, artifact_store):
    """Resolve a full saved value and immutable fingerprint receipt for workspace tools."""
    return _source(reference, result_store, artifact_store)


def _recompute(record, results, artifacts):
    if not isinstance(record, dict) or record.get("method") != "bounded_python_expression" or not isinstance(record.get("expression"), str):
        raise ValueError("A numeric claim must reference a deterministic calculation result.")
    assumptions = record.get("assumptions", {})
    refs = record.get("input_refs", {})
    if not isinstance(assumptions, dict) or not isinstance(refs, dict):
        raise ValueError("The calculation has invalid recorded inputs.")
    inputs = copy.deepcopy(assumptions)
    receipts = {}
    for name, ref in refs.items():
        _, selected, receipt = _source(ref, results, artifacts)
        inputs[name] = selected
        receipts[name] = receipt
    recomputed = calculate(record["expression"], inputs)
    if record.get("inputs_sha256") != recomputed["inputs_sha256"] or fingerprint(record.get("value")) != fingerprint(recomputed["value"]):
        raise ValueError("The calculation does not reproduce from its full recorded inputs.")
    return recomputed, {"expression": record["expression"], "inputs_sha256": recomputed["inputs_sha256"],
                        "input_sources": receipts, "assumptions_sha256": fingerprint(assumptions),
                        "result_sha256": fingerprint(recomputed["value"])}


def _number(value):
    if isinstance(value, bool):
        raise ValueError("A boolean cannot support a numeric claim.")
    text = re.sub(r"[$£€,\s]", "", str(value))
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        raise ValueError("Use an explicit numeric rendered_value, with optional currency and grouping.")
    number = Decimal(text)
    if not number.is_finite():
        raise ValueError("A numeric claim must be finite.")
    return number


def _list(data, key, issues):
    value = data.get(key, [])
    if not isinstance(value, list):
        issues.append(key + " must be a list.")
        return []
    return value


_TOTAL_CURRENCY = re.compile(r"\b(?:total|aggregate|combined)\b[^\n.!?]{0,80}?(?P<amount>(?:[$£€]\s*|(?:USD|EUR|GBP)\s+)[+-]?\d[\d,]*(?:\.\d+)?)", re.I)
_TOTAL_NUMBER = re.compile(r"\b(?:total|aggregate|combined)\s*(?:(?:is|was|of|equals)\s*|[:=]\s*)?(?P<amount>[+-]?\d[\d,]*(?:\.\d+)?)", re.I)


def _detected_totals(data):
    locations = []
    for section in _sections(data):
        if section.get("id"):
            locations.append((str(section.get("content") or ""), {"section_id": section["id"]}))
    for key in ("purpose", "scope", "description", "static_content"):
        if isinstance(data.get(key), str):
            locations.append((data[key], {"content_path": key}))
    for index, slide in enumerate(data.get("slides", []) or []):
        if isinstance(slide, dict):
            locations.append((str(slide.get("content") or ""), {"content_path": f"slides.{index}.content"}))
    for prose, location in locations:
        spans = set()
        for pattern in (_TOTAL_CURRENCY, _TOTAL_NUMBER):
            for match in pattern.finditer(prose):
                if match.span() in spans:
                    continue
                spans.add(match.span())
                amount = re.sub(r"^(?:USD|EUR|GBP)\s+", "", match.group("amount"), flags=re.I)
                yield match.group(), amount, location


def validate_claims(data, *, result_store, artifact_store, required_items=(), source_result_ids=()):
    issues, bindings, coverage, cited_sources = [], [], [], []
    valid = {}
    for identity in source_result_ids:
        try:
            _, _, receipt = _source({"result_id": identity}, result_store, artifact_store)
            cited_sources.append(receipt)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            issues.append(str(exc))
    declarations = _list(data, "claim_bindings", issues)
    ids = [x.get("id") for x in declarations if isinstance(x, dict)]
    for declaration in declarations:
        receipt = {"binding": copy.deepcopy(declaration), "status": "invalid"}
        bindings.append(receipt)
        try:
            if not isinstance(declaration, dict):
                raise ValueError("Each claim binding must be an object.")
            key = declaration.get("id")
            if not isinstance(key, str) or not key.strip() or ids.count(key) != 1:
                raise ValueError("Claim binding IDs must be nonempty and unique.")
            rendered, location = _rendered(data, declaration)
            claim = declaration.get("claim_text")
            if not isinstance(claim, str) or not claim.strip() or claim not in rendered:
                raise ValueError("The exact claim_text does not occur in the specified rendered content.")
            whole, selected, source = _source(declaration.get("source"), result_store, artifact_store)
            receipt.update(source=source, location=location, claim_sha256=fingerprint(claim))
            quote = declaration.get("quote")
            if quote is not None:
                if not isinstance(quote, str) or not quote.strip() or not any(quote in text for text in _strings(selected)):
                    raise ValueError("The exact quotation does not occur in the full selected source.")
                if quote not in rendered:
                    raise ValueError("The source quotation is absent from the rendered content.")
                receipt["quote_sha256"] = fingerprint(quote)
            numeric = declaration.get("numeric")
            if numeric is not None:
                if not isinstance(numeric, dict) or not declaration["source"].get("result_id") or declaration["source"].get("path"):
                    raise ValueError("Numeric bindings require an entire calculation result plus numeric.value_path.")
                recomputed, calculation = _recompute(whole, result_store, artifact_store)
                value_path = numeric.get("value_path", "value")
                if not isinstance(value_path, str):
                    raise ValueError("numeric.value_path must be a dot-separated string.")
                expected = _number(get_path(recomputed, value_path))
                rendered_value = str(numeric.get("rendered_value", ""))
                # A substring such as 12 in 123 must not validate a different rendered number.
                if not rendered_value or not re.search(r"(?<![\d.,])" + re.escape(rendered_value) + r"(?!\d|[.,]\d)", claim):
                    raise ValueError("The numeric rendered_value is not a complete token in claim_text.")
                actual = _number(rendered_value)
                decimals = numeric.get("decimals")
                if decimals is not None:
                    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 12:
                        raise ValueError("Numeric rounding needs decimals between 0 and 12.")
                    expected = expected.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
                if actual != expected:
                    raise ValueError(f"Rendered numeric claim {actual} differs from the reproducible result {expected}.")
                receipt.update(calculation=calculation, expected_value=str(expected), rendered_value=rendered_value)
            if quote is None and numeric is None:
                receipt["check"] = "reference_exists_only"
            else:
                receipt["check"] = "quote_or_calculation_consistent"
            receipt["status"] = "checked"
            valid[key] = receipt
        except (ValueError, KeyError, TypeError, IndexError, InvalidOperation, ArithmeticError) as exc:
            receipt["error"] = str(exc)
            issues.append("Claim binding: " + str(exc))

    numeric_claims = _list(data, "numeric_claims", issues)
    for claim in numeric_claims:
        try:
            if not isinstance(claim, dict):
                raise ValueError("Numeric claims must be objects.")
            rendered, location = _rendered(data, claim)
            binding = valid.get(claim.get("binding_id"))
            if not binding or "calculation" not in binding:
                raise ValueError("A declared numeric claim has no valid calculation binding.")
            if not claim.get("claim_text") or claim["claim_text"] not in rendered or claim["claim_text"] != binding["binding"]["claim_text"] or location != binding["location"]:
                raise ValueError("The numeric declaration and bound rendered claim differ.")
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            issues.append(str(exc))

    detected_totals = []
    for text, amount, location in _detected_totals(data):
        matching = []
        for key, receipt in valid.items():
            declaration = receipt["binding"]
            if receipt["location"] != location or text not in declaration["claim_text"]:
                continue
            if "calculation" in receipt and _number(amount) == _number(receipt["expected_value"]):
                matching.append(key)
            elif (declaration.get("reported_figure") is True and receipt.get("quote_sha256")
                  and text in declaration.get("quote", "")
                  and re.search(r"\b(?:reported|stated|recorded|quoted)\b", declaration["claim_text"], re.I)):
                matching.append(key)
        detected_totals.append({"text": text, "location": location, "binding_ids": matching,
                                "status": "checked" if matching else "unbound"})
        if not matching:
            issues.append("A detected total needs a matching calculation binding or explicitly labelled verbatim reported figure: " + text)

    entries = _list(data, "coverage", issues)
    for required in required_items:
        matching = [entry for entry in entries if isinstance(entry, dict) and str(entry.get("item", "")).casefold() == str(required).casefold()]
        record = {"item": required, "status": "unresolved"}
        coverage.append(record)
        try:
            if len(matching) != 1:
                raise ValueError("Exactly one explicit coverage record is required.")
            entry = matching[0]
            record["declaration"] = copy.deepcopy(entry)
            if entry.get("status") != "fulfilled":
                raise ValueError(str(entry.get("reason") or "The requested coverage remains unresolved."))
            rendered, location = _rendered(data, entry)
            excerpt = entry.get("excerpt")
            claim_ids = entry.get("claim_ids", [])
            if not isinstance(claim_ids, list) or not all(isinstance(key, str) for key in claim_ids):
                raise ValueError("Coverage claim_ids must be a list of binding IDs.")
            if not excerpt and not claim_ids:
                raise ValueError("Fulfilled coverage needs a rendered excerpt or checked claim bindings.")
            if excerpt and (not isinstance(excerpt, str) or excerpt not in rendered):
                raise ValueError("The coverage excerpt is absent from the rendered content.")
            if any(key not in valid or valid[key]["location"] != location for key in claim_ids):
                raise ValueError("Coverage cites an invalid, missing or differently located claim binding.")
            record.update(status="content_located", location=location, excerpt_sha256=fingerprint(excerpt) if excerpt else None,
                          claim_ids=claim_ids)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            record["error"] = str(exc)
            issues.append("Required coverage " + str(required) + ": " + str(exc))
    from services.agent.source_grounding import inspect_source_grounding
    grounding = inspect_source_grounding(data, result_store, checked_bindings=bindings)
    issues.extend(grounding['issues'])
    return {"issues": issues, "bindings": bindings, "coverage": coverage, "cited_sources": cited_sources, "detected_totals": detected_totals,
            "source_grounding": grounding,
            "checks": {"declared_bindings": len(declarations), "checked_bindings": len(valid),
                       "declared_numeric_claims": len(numeric_claims), "detected_totals": len(detected_totals), "coverage_located": sum(c["status"] == "content_located" for c in coverage)},
            "scope": "Declared references, exact quotes, reproducible numeric claims, coverage locations and precise details in document-cited sections are checked. Presence does not establish entailment; other undeclared claims, source truth and analytical adequacy are not established."}


def apply_claim_validation(artifact, result_store, artifact_store):
    """Refresh evidence checks for agent or human revisions; never inherit old receipts."""
    from services.agent.deliverables import validate_artifact, dependency_metadata
    meta = artifact["metadata"]
    validation = validate_artifact(artifact["type"], artifact["data"], meta.get("required_items", []))
    evidence = validate_claims(artifact["data"], result_store=result_store, artifact_store=artifact_store,
                               required_items=meta.get("required_items", []), source_result_ids=meta.get("source_result_ids", []))
    located = {record['item'] for record in evidence['coverage'] if record['status'] == 'content_located'}
    validation['issues'] = [issue for issue in validation['issues']
                            if issue not in {f'Required coverage is missing: {item}' for item in located}]
    validation["issues"].extend(evidence["issues"])
    validation["checks"].update(evidence["checks"])
    validation["status"] = "needs_revision" if validation["issues"] else "structural_checks_passed"
    validation["source_review"] = "declared_bindings_checked" if evidence["bindings"] and not evidence["issues"] else "not_established"
    validation["source_truth"] = "not_established"
    validation["claim_check_scope"] = evidence["scope"]
    meta["validation"] = validation
    meta["claim_evidence"] = evidence
    meta['claim_validation_signature'] = validation_signature(artifact, result_store, artifact_store)
    meta.update(dependency_metadata(artifact, artifact_store))
    return artifact
