"""
Neo4j batch writer for Cellebrite UFED parsed models.

Maps each Cellebrite model type to Neo4j nodes and relationships.
Uses batch transactions for efficient writes of 16K+ entities.

All nodes get:
  - case_id (mandatory, for case isolation)
  - cellebrite_report_key (for multi-report filtering)
  - cellebrite_id (original UUID from XML)
  - source_type: "cellebrite"
  - deleted_state (Intact/Deleted/Trash)
"""

import json
import re
import uuid
from collections import Counter
from typing import List, Dict, Optional, Set, Callable, Tuple  # noqa: F401

from .models import ParsedModel, Party, CellebriteReport

# We import Neo4jClient at usage time to avoid import-order issues
# when this module is loaded from the ingestion scripts directory.


def _geocode_lat_lon(lat: float, lon: float) -> Optional[Dict]:
    """
    Reverse-geocode a coordinate via the backend's pluggable geocoder.

    Lazy-imported because (a) the ingestion module sometimes runs in
    contexts where backend isn't on PYTHONPATH, and (b) the geocoder
    module touches env vars at import time — keeping the import lazy
    means a typo in env doesn't crash the writer, only this one
    point's enrichment.

    Returns the canonical geocoder shape (see backend/services/geocoder.py)
    or None if the backend module isn't reachable.
    """
    try:
        from services.geocoder import reverse_geocode
    except Exception:
        return None
    try:
        return reverse_geocode(float(lat), float(lon))
    except Exception:
        return None


def _safe_int(v) -> Optional[int]:
    """Best-effort int coercion; returns None on bad input rather than raising."""
    try:
        return int(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


# Search engines whose URL "q=" / "query=" / "search_query=" parameters
# carry the literal search term the user typed. Cellebrite usually does
# NOT emit a separate SearchedItem for these — the only record is the
# VisitedPage URL. Recognising them here surfaces the search behind
# every "they went to google.com/search?q=..." entry.
_SEARCH_HOST_QUERY_PARAMS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("google.",        ("q", "query")),
    ("bing.",          ("q",)),
    ("duckduckgo.",    ("q",)),
    ("yahoo.",         ("p", "q")),
    ("yandex.",        ("text",)),
    ("baidu.",         ("wd", "word")),
    ("youtube.",       ("search_query",)),
    ("twitter.",       ("q",)),
    ("x.com",          ("q",)),
    ("reddit.",        ("q",)),
    ("amazon.",        ("k", "field-keywords")),
    ("ebay.",          ("_nkw",)),
)


def _extract_search_query(url: Optional[str]) -> Optional[str]:
    """If `url` is a known search-engine query URL, return the search term."""
    if not url or "://" not in url:
        return None
    try:
        from urllib.parse import urlparse, parse_qs, unquote_plus
    except ImportError:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    if not host:
        return None
    for host_prefix, params in _SEARCH_HOST_QUERY_PARAMS:
        if host_prefix not in host:
            continue
        try:
            qs = parse_qs(parsed.query, keep_blank_values=False)
        except ValueError:
            return None
        for p in params:
            if p in qs and qs[p]:
                # parse_qs already URL-decodes; trim whitespace; cap length.
                q = qs[p][0].strip()
                if q:
                    return q[:500]
        return None
    return None


def _normalise_phone(raw: Optional[str]) -> Optional[str]:
    """Normalize a phone number for deduplication."""
    if not raw:
        return None
    # Strip everything except digits and leading +
    cleaned = re.sub(r"[^\d+]", "", raw.strip())
    if not cleaned:
        return None
    # Remove leading + for consistency
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    # Remove country code 1 for US numbers if 11 digits
    if len(cleaned) == 11 and cleaned.startswith("1"):
        cleaned = cleaned[1:]
    return cleaned


def _normalise_key(raw: Optional[str]) -> str:
    """Normalize a string to a stable key (mirrors entity_resolution.normalise_key)."""
    if not raw:
        return ""
    key = raw.strip().lower()
    key = re.sub(r"[\s_]+", "-", key)
    key = re.sub(r"[^a-z0-9\-]", "", key)
    key = re.sub(r"-+", "-", key)
    return key.strip("-")


def _generate_person_key(
    identifier: Optional[str] = None,
    name: Optional[str] = None,
    source_app: Optional[str] = None,
) -> Optional[str]:
    """
    Generate a stable key for a person from available identifiers.

    Priority:
    1. Phone number (most stable across apps)
    2. Email address
    3. App-specific ID (platform + ID)
    4. Name (fallback)
    """
    # Try phone number first
    phone = _normalise_phone(identifier)
    if phone and phone.isdigit() and len(phone) >= 7:
        return f"phone-{phone}"

    # Try email
    if identifier and "@" in identifier and "." in identifier:
        return f"email-{identifier.lower().strip()}"

    # Try app-specific ID
    if identifier and source_app:
        app_key = _normalise_key(source_app)
        id_key = _normalise_key(identifier)
        if id_key:
            return f"{app_key}-{id_key}"

    # Fallback to name
    if name:
        key = _normalise_key(name)
        if key:
            return key

    return None


class CellebriteNeo4jWriter:
    """
    Writes Cellebrite parsed models to Neo4j as graph entities.

    Handles person deduplication, phone owner identification, and
    relationship creation between entities.
    """

    def __init__(
        self,
        neo4j_client,
        case_id: str,
        report_key: str,
        report: CellebriteReport,
        log_callback: Optional[Callable[[str], None]] = None,
        attachment_map: Optional[Dict[str, List[str]]] = None,
    ):
        self.db = neo4j_client
        self.case_id = case_id
        self.report_key = report_key
        self.report = report
        self.log_callback = log_callback

        # Mapping of model_id -> [file_id, ...] for attachment persistence.
        # Populated from file_linker.build_model_file_map() and set before write_batch().
        self.attachment_map: Dict[str, List[str]] = attachment_map or {}

        # Track created nodes to avoid duplicate creation
        self._created_person_keys: Set[str] = set()
        self._created_node_keys: Set[str] = set()

        # Counters
        self.contacts_created = 0
        self.calls_created = 0
        self.messages_created = 0
        self.chats_created = 0
        self.emails_created = 0
        self.locations_created = 0
        self.accounts_created = 0
        self.searches_created = 0
        self.pages_created = 0
        self.meetings_created = 0
        self.credentials_created = 0
        self.devices_created = 0
        self.wifi_created = 0
        self.bookmarks_created = 0
        # Phase 6 — device inventory / file provenance / identity
        self.autofill_created = 0
        self.sim_data_created = 0
        self.users_created = 0
        self.installed_apps_created = 0
        self.file_downloads_created = 0
        self.network_usage_created = 0
        self.dictionary_words_created = 0
        self.nodes_total = 0
        self.relationships_total = 0

        # Per-model-type failure counter — populated when a handler
        # raises inside `write_batch`. Exposed via `get_stats()` so the
        # orchestrator can fail the task if too many entities are lost.
        # Pre-2026-05-23 the writer swallowed these silently into a log
        # warning and the task still showed `completed` — users had
        # data missing with no UI indication. Now visible.
        self.write_errors: Counter = Counter()

        # Phone owner identity (populated during first pass)
        self._phone_owner_key: Optional[str] = None
        self._phone_owner_names: Dict[str, int] = {}  # name -> count
        self._phone_owner_identifiers: Set[str] = set()

        # SIMData aggregation — see _write_sim_data / finalise_sim_card.
        # Cellebrite emits SIM properties one per model row; we collect
        # them all then write a single SIMCard node at finalisation.
        self._sim_properties: Dict[str, str] = {}
        self._sim_categories: Dict[str, str] = {}

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    # Centralised timestamp-field-name aliases. Cellebrite uses different
    # field names on different model types for what is conceptually the
    # same fact ("when did this happen"): VisitedPage uses `LastVisited`,
    # Chat uses `LastActivity`, InstalledApplication uses `PurchaseDate`,
    # InstantMessage uses `TimeStamp` + (optionally) `DateDelivered`,
    # UserAccount uses `TimeLastLoggedIn`, etc.
    #
    # Handlers should call `_extract_timestamp(model, prefer=("X","Y"))`
    # instead of hardcoding `model.get_field("TimeStamp")`. The audit
    # script (scripts/audit_cellebrite_coverage.py) flags any handler
    # that hardcodes only `TimeStamp` — that pattern has historically
    # dropped 15,000+ events in a single report.
    _TIMESTAMP_ALIASES = (
        "TimeStamp",
        "Timestamp",
        "LastVisited",
        "LastActivity",
        "LastAccessed",
        "LastConnection",
        "PurchaseDate",
        "TimeCreated",
        "TimeLastLoggedIn",
        "DateDelivered",
        "StartTime",
        "EndTime",
        "StartDate",
        "EndDate",
        "Date",
        "DownloadTime",
    )

    def _extract_timestamp(self, model: ParsedModel,
                           prefer: Optional[tuple] = None) -> Optional[str]:
        """Return the first non-empty timestamp field on `model`.

        `prefer` is an ordered tuple of field names the caller knows are
        canonical for this model type; tried first. Falls back to the
        full `_TIMESTAMP_ALIASES` list. Returns None if nothing matched.
        """
        for name in (prefer or ()):
            v = model.get_field(name)
            if v:
                return v
        for name in self._TIMESTAMP_ALIASES:
            if prefer and name in prefer:
                continue
            v = model.get_field(name)
            if v:
                return v
        return None

    def _base_props(self, model: ParsedModel, key: str, name: str) -> Dict:
        """Build base properties common to all Cellebrite nodes."""
        props = {
            "id": str(uuid.uuid4()),
            "key": key,
            "name": name,
            "case_id": self.case_id,
            "cellebrite_report_key": self.report_key,
            "cellebrite_id": model.model_id,
            "source_type": "cellebrite",
            "deleted_state": model.deleted_state,
        }
        # Cellebrite tags every model with a parser-supplied confidence
        # ("High" / "Medium" / "Low" / numeric). Carry it through so the
        # UI can dim or annotate low-confidence rows. Drop blank values
        # so older nodes that didn't capture this still match cleanly.
        if model.decoding_confidence:
            props["decoding_confidence"] = model.decoding_confidence
        # UserMapping ties an artifact to a specific device user on
        # multi-user devices (e.g. Android profiles). Cellebrite emits
        # this on every model — capturing it here means every node gets
        # the prop without per-handler boilerplate. Used downstream for
        # phone-owner disambiguation when multiple users share a device.
        user_mapping = model.get_field("UserMapping")
        if user_mapping:
            props["user_mapping"] = user_mapping
        return props

    def _attachment_props(self, model: ParsedModel) -> Dict:
        """Build attachment_file_ids / attachment_count for a model, if any."""
        file_ids = self.attachment_map.get(model.model_id, [])
        if not file_ids:
            return {}
        return {
            "attachment_file_ids": list(file_ids),
            "attachment_count": len(file_ids),
        }

    def _message_provenance_props(self, model: ParsedModel) -> Dict:
        """Extract Forwarded/Reply/MessageLabel nested children as flat props.

        Cellebrite nests these as <modelField name="Forwarded"> /
        "ReplyTo" / "Labels" (or multiModelField for the latter). The
        parser already captures the nested ParsedModel; we flatten the
        useful identifiers onto the parent message node so investigative
        views can filter "show me only forwarded messages" or "messages
        labelled X" without joining through a sub-node.
        """
        props: Dict = {}

        # Forwarded: messages that originated elsewhere and were relayed.
        # Cellebrite uses several wrapper names depending on extraction;
        # try them in order.
        for fwd_name in ("Forwarded", "ForwardedFrom", "ForwardedMessageData"):
            fwd = model.model_fields.get(fwd_name)
            if fwd is not None:
                props["is_forwarded"] = True
                orig_sender = (
                    fwd.get_field("OriginalSender")
                    or fwd.get_field("From")
                    or fwd.get_field("Sender")
                )
                orig_ts = (
                    fwd.get_field("OriginalTimeStamp")
                    or fwd.get_field("TimeStamp")
                    or fwd.get_field("Date")
                )
                if orig_sender:
                    props["forwarded_from"] = orig_sender
                if orig_ts:
                    props["forwarded_original_timestamp"] = orig_ts
                break

        # Reply: this message is a reply to another. Store the target
        # message id so the UI can render a "↳ in reply to X" affordance.
        for rep_name in ("ReplyTo", "ReplyMessageData", "InReplyTo"):
            rep = model.model_fields.get(rep_name)
            if rep is not None:
                props["is_reply"] = True
                target = (
                    rep.get_field("MessageId")
                    or rep.get_field("Id")
                    or rep.get_field("OriginalMessageId")
                )
                if target:
                    props["reply_to_message_id"] = target
                snippet = rep.get_field("Body") or rep.get_field("Text")
                if snippet:
                    props["reply_to_snippet"] = snippet[:200]
                break

        # Labels / Tags: applied labels (Starred, Important, custom folders).
        labels: List[str] = []
        for lbl_name in ("Labels", "MessageLabels", "Tags"):
            for lbl in model.multi_model_fields.get(lbl_name, []) or []:
                name = lbl.get_field("Name") or lbl.get_field("Value") or lbl.get_field("Label")
                if name and name not in labels:
                    labels.append(name)
        # Single-child variant
        for lbl_name in ("MessageLabel", "Label"):
            lbl = model.model_fields.get(lbl_name)
            if lbl is not None:
                name = lbl.get_field("Name") or lbl.get_field("Value") or lbl.get_field("Label")
                if name and name not in labels:
                    labels.append(name)
        if labels:
            props["labels"] = labels

        return props

    def _ensure_person(
        self,
        identifier: Optional[str] = None,
        name: Optional[str] = None,
        source_app: Optional[str] = None,
        extra_props: Optional[Dict] = None,
    ) -> Optional[str]:
        """
        Ensure a Person node exists, returning its key.
        Uses MERGE semantics — creates if new, skips if exists.
        """
        key = _generate_person_key(identifier, name, source_app)
        if not key:
            return None

        if key in self._created_person_keys:
            return key

        display_name = name or identifier or key
        props = {
            "id": str(uuid.uuid4()),
            "key": key,
            "name": display_name,
            "case_id": self.case_id,
            "cellebrite_report_key": self.report_key,
            "source_type": "cellebrite",
        }
        if extra_props:
            props.update(extra_props)

        # MERGE for concurrency-safety. ON CREATE bootstraps the full
        # prop set; ON MATCH only patches in the `extra_props` payload
        # (addresses, photo_file_ids, contact_source, etc.) — the core
        # identity fields (key, name, id) are left intact. Necessary
        # because Person nodes can be created first by a message
        # handler (with only identifier+name+source_app) and only
        # later enriched by the Contact handler — without ON MATCH the
        # rich Contact data was being silently dropped.
        match_patch = extra_props or {}
        self.db.run_query(
            """
            MERGE (p:Person {key: $key, case_id: $case_id})
            ON CREATE SET p = $props
            ON MATCH  SET p += $match_patch
            """,
            key=key,
            case_id=self.case_id,
            props=props,
            match_patch=match_patch,
        )

        self._created_person_keys.add(key)
        self.nodes_total += 1
        return key

    def _create_node(self, label: str, key: str, props: Dict) -> str:
        """Create a node with the given label and properties."""
        if key in self._created_node_keys:
            return key

        # Sanitize label
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", label.strip())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        if not sanitized:
            sanitized = "Other"

        self.db.run_query(
            f"CREATE (n:`{sanitized}` $props)",
            props=props,
        )

        self._created_node_keys.add(key)
        self.nodes_total += 1
        return key

    def _create_relationship(self, from_key: str, to_key: str, rel_type: str, extra_props: Optional[Dict] = None):
        """Create a relationship between two nodes."""
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", rel_type.strip())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        if not sanitized:
            sanitized = "RELATED_TO"

        props_str = ", ".join(f"{k}: ${k}" for k in (extra_props or {}).keys())
        set_clause = f", {props_str}" if props_str else ""

        params = {
            "from_key": from_key,
            "to_key": to_key,
            "case_id": self.case_id,
            **(extra_props or {}),
        }

        self.db.run_query(
            f"""
            MATCH (a {{key: $from_key, case_id: $case_id}})
            MATCH (b {{key: $to_key, case_id: $case_id}})
            MERGE (a)-[r:`{sanitized}` {{case_id: $case_id}}]->(b)
            """,
            **params,
        )
        self.relationships_total += 1

    # ------------------------------------------------------------------
    # Phone owner
    # ------------------------------------------------------------------

    def collect_phone_owner_info(self, models: List[ParsedModel]):
        """Scan models for phone owner identity (call before writing)."""
        for model in models:
            self._scan_for_phone_owner(model)

    def _scan_for_phone_owner(self, model: ParsedModel):
        """Check all Party elements for IsPhoneOwner flag."""
        # Check direct modelFields (From/To)
        for field_name in ("From", "To"):
            party = model.get_party(field_name)
            if party and party.is_phone_owner:
                if party.name:
                    self._phone_owner_names[party.name] = (
                        self._phone_owner_names.get(party.name, 0) + 1
                    )
                if party.identifier:
                    self._phone_owner_identifiers.add(party.identifier)

        # Check multiModelField Parties
        for party in model.get_parties("Parties"):
            if party.is_phone_owner:
                if party.name:
                    self._phone_owner_names[party.name] = (
                        self._phone_owner_names.get(party.name, 0) + 1
                    )
                if party.identifier:
                    self._phone_owner_identifiers.add(party.identifier)

        # Check nested messages in Chat models
        for msg in model.multi_model_fields.get("Messages", []):
            self._scan_for_phone_owner(msg)

    def create_phone_owner(self) -> Optional[str]:
        """Create the phone owner Person node from collected identity info."""
        # When an investigator-supplied identifier is in play (report had no
        # extractable number, or an override alias was added), make sure it
        # is part of the owner identity even if the models already yielded a
        # phone-owner party — otherwise the manual identifier would land on
        # the PhoneReport but not on the owner Person node, so it wouldn't
        # show in conversations. See cellebrite-phone-number-required rule.
        if getattr(self.report.device_info, "identifier_is_manual", False):
            for ident in self.report.device_info.msisdn:
                if ident:
                    self._phone_owner_identifiers.add(ident)

        if not self._phone_owner_names and not self._phone_owner_identifiers:
            # Fallback: use device MSISDN
            if self.report.device_info.msisdn:
                phone = self.report.device_info.msisdn[0]
                self._phone_owner_identifiers.add(phone)
            else:
                self._log("WARNING: Could not identify phone owner")
                return None

        # Pick the most frequent name (filter out numeric-only names like WhatsApp IDs)
        best_name = None
        if self._phone_owner_names:
            real_names = {
                n: c for n, c in self._phone_owner_names.items()
                if not n.isdigit() and len(n) > 1
            }
            if real_names:
                best_name = max(real_names, key=real_names.get)
            else:
                best_name = max(self._phone_owner_names, key=self._phone_owner_names.get)

        # Pick best identifier — prefer device MSISDN (known phone numbers),
        # then identifiers that look like phone numbers (7-12 digits),
        # then any identifier
        best_identifier = None
        device_phones = set()
        for msisdn in self.report.device_info.msisdn:
            norm = _normalise_phone(msisdn)
            if norm:
                device_phones.add(norm)

        # First choice: use a device MSISDN found in owner identifiers
        for ident in self._phone_owner_identifiers:
            norm = _normalise_phone(ident)
            if norm and norm in device_phones:
                best_identifier = ident
                break

        # Second choice: any identifier that looks like a real phone number (7-12 digits)
        if not best_identifier:
            for ident in self._phone_owner_identifiers:
                phone = _normalise_phone(ident)
                if phone and phone.isdigit() and 7 <= len(phone) <= 12:
                    best_identifier = ident
                    break

        # Third choice: use device MSISDN directly
        if not best_identifier and self.report.device_info.msisdn:
            best_identifier = self.report.device_info.msisdn[0]

        # Last resort: any identifier
        if not best_identifier and self._phone_owner_identifiers:
            best_identifier = next(iter(self._phone_owner_identifiers))

        key = _generate_person_key(
            identifier=best_identifier,
            name=best_name,
        )
        if not key:
            self._log("WARNING: Could not generate key for phone owner")
            return None

        extra_props = {
            "is_phone_owner": True,
            "phone_numbers": list({
                _normalise_phone(i)
                for i in self._phone_owner_identifiers
                if _normalise_phone(i)
            }),
            "all_identifiers": list(self._phone_owner_identifiers),
        }

        self._ensure_person(
            identifier=best_identifier,
            name=best_name,
            extra_props=extra_props,
        )

        self._phone_owner_key = key
        self._log(f"Phone owner: {best_name or 'Unknown'} (key={key})")
        return key

    def create_phone_report_node(self):
        """Create the central PhoneReport anchor node."""
        ci = self.report.case_info
        di = self.report.device_info

        # device_name_candidates is a list-of-dicts which Neo4j can't
        # store natively, so we JSON-encode it. Empty list → None so
        # the prop is dropped entirely (cleaner than storing "[]").
        candidates_json = (
            json.dumps(di.device_name_candidates)
            if di.device_name_candidates else None
        )
        accessory_imeis = list(di.accessory_imeis) if di.accessory_imeis else None

        props = {
            "id": str(uuid.uuid4()),
            "key": self.report_key,
            "name": self.report.report_name,
            "case_id": self.case_id,
            # The PhoneReport tags ITSELF with its report_key so the
            # standard "wipe everything for this report" filter
            # (case_id + cellebrite_report_key) matches the parent
            # node too. Pre-2026-05-23 only its children carried this
            # prop, leaving the PhoneReport node orphaned after a wipe
            # — which then triggered a false "duplicate phone in this
            # case" 409 on the next ingest. See 2026-05-23 wipe-and-
            # re-ingest sequence in WORKING.md.
            "cellebrite_report_key": self.report_key,
            "source_type": "cellebrite_ufed",
            "report_version": self.report.report_version,
            "extraction_type": self.report.extraction_type,
            "node_count": self.report.node_count,
            "model_count": self.report.model_count,
            # Case info
            "examiner": ci.examiner,
            "case_number": ci.case_number,
            "evidence_number": ci.evidence_number,
            "department": ci.department,
            "organization": ci.organization,
            "crime_type": ci.crime_type,
            # Device info
            "device_model": di.device_model,
            "manufacturer": di.manufacturer,
            "device_name_candidates": candidates_json,
            # Investigator-supplied override; null on first ingest. Set
            # via PATCH /api/cellebrite/reports/{key}.
            "device_name_override": None,
            "imei": di.imei,
            "accessory_imeis": accessory_imeis,
            "os_type": di.os_type,
            "phone_numbers": di.msisdn,
            # True when phone_numbers contains an investigator-supplied
            # identifier (report had no extractable number, or an override
            # alias was added). UI badges this so a manual identity isn't
            # mistaken for an extracted MSISDN.
            "device_identifier_manual": getattr(di, "identifier_is_manual", False),
        }

        # Remove None values
        props = {k: v for k, v in props.items() if v is not None}

        # MERGE on (case_id, key) so a re-ingest of the same report updates
        # the existing node instead of creating a duplicate. Preserve the
        # investigator-supplied device_name_override across re-ingest by
        # excluding it from the ON MATCH update.
        match_props = {k: v for k, v in props.items() if k != "device_name_override"}
        self.db.run_query(
            """
            MERGE (r:PhoneReport {case_id: $case_id, key: $key})
            ON CREATE SET r = $create_props
            ON MATCH SET r += $match_props
            """,
            case_id=self.case_id,
            key=self.report_key,
            create_props=props,
            match_props=match_props,
        )
        # Track the key so the in-memory dedupe in _create_node still works
        # for the rest of the writer run.
        self._created_node_keys.add(self.report_key)
        self.nodes_total += 1
        self._log(f"Upserted PhoneReport node: {self.report_key}")

    def link_phone_owner_to_report(self):
        """Link phone owner to the PhoneReport node."""
        if self._phone_owner_key:
            self._create_relationship(
                self.report_key,
                self._phone_owner_key,
                "BELONGS_TO",
            )

    # ------------------------------------------------------------------
    # Model type handlers
    # ------------------------------------------------------------------

    def write_batch(self, models: List[ParsedModel]):
        """Write a batch of parsed models to Neo4j.

        Per-entity errors are caught and counted (not re-raised) — a
        single malformed model shouldn't tear down the whole ingest.
        The counter is exposed via `get_stats()['write_errors']` and the
        orchestrator decides whether to fail the task based on the
        failure rate.
        """
        for model in models:
            try:
                handler = self._get_handler(model.model_type)
                if handler:
                    handler(model)
            except Exception as e:
                self.write_errors[model.model_type or "unknown"] += 1
                self._log(f"WARNING: Error writing {model.model_type} ({model.model_id[:8]}): {e}")

    def _get_handler(self, model_type: str):
        """Get the handler function for a model type."""
        handlers = {
            "Contact": self._write_contact,
            "Call": self._write_call,
            "Chat": self._write_chat,
            "InstantMessage": self._write_instant_message,
            "Email": self._write_email,
            "Location": self._write_location,
            "UserAccount": self._write_user_account,
            "SearchedItem": self._write_searched_item,
            "VisitedPage": self._write_visited_page,
            "CalendarEntry": self._write_calendar_entry,
            "WirelessNetwork": self._write_wireless_network,
            "RecognizedDevice": self._write_recognized_device,
            "Password": self._write_password,
            "WebBookmark": self._write_web_bookmark,
            # Phase 4: Location & Event types
            "CellTower": self._write_cell_tower,
            "Cell": self._write_cell_tower,
            "CellLocation": self._write_cell_tower,
            "PoweringEvent": self._write_device_event,
            "PowerEvent": self._write_device_event,
            "DeviceEvent": self._write_device_event,
            "UserEvent": self._write_device_event,
            "ScreenEvent": self._write_device_event,
            "ApplicationUsage": self._write_app_session,
            "AppUsage": self._write_app_session,
            # Phase 5: Media helpers
            "Attachment": self._write_attachment,
            "ContactPhoto": self._write_contact_photo,
            "ProfilePicture": self._write_profile_picture,
            # Phase 6: device inventory / identity / downloads
            "Autofill": self._write_autofill,
            "SIMData": self._write_sim_data,
            "User": self._write_user,
            "InstalledApplication": self._write_installed_application,
            "FileDownload": self._write_file_download,
            "NetworkUsage": self._write_network_usage,
            "DictionaryWord": self._write_dictionary_word,
            # Explicit ignores (parser emits them, writer silently skips)
            "KeyValueModel": self._noop,
            "Party": self._noop,
            "UserDictionaryEntry": self._noop,
        }
        return handlers.get(model_type)

    def _noop(self, model: ParsedModel):
        """Explicitly-ignored model types. Do nothing."""
        return None

    def _write_contact(self, model: ParsedModel):
        """Contact -> Person node.

        Walks all nested children Cellebrite hangs off a Contact:
          - Entries (PhoneNumber / EmailAddress / WebAddress / UserID / ProfilePicture)
          - Photos (ContactPhoto with jump_target → file UUID)
          - Addresses (StreetAddress with Street/City/Country/Postal etc.)
          - Organizations (Organization with Name/Title/Department)
        Audit on 2026-05-23 found we were dropping all of Photos (822
        across 3 reports), Addresses (67) and Organizations (2). Now
        flattened onto the Person node.
        """
        name = model.get_field("Name")
        source = model.get_field("Source")
        account = model.get_field("Account")
        contact_type = model.get_field("Type")
        group = model.get_field("Group")

        # Get phone numbers and emails from contact entries
        phone_numbers: List[str] = []
        emails: List[str] = []
        web_addresses: List[str] = []
        user_ids: List[str] = []
        photo_file_ids: List[str] = []
        for entry in model.multi_model_fields.get("Entries", []):
            etype = entry.model_type or ""
            value = entry.get_field("Value") or entry.get_field("Identifier")
            category = entry.get_field("Category") or ""
            if etype == "PhoneNumber" and value:
                phone_numbers.append(value)
            elif etype == "EmailAddress" and value:
                emails.append(value)
            elif etype == "WebAddress" and value:
                web_addresses.append(value)
            elif etype == "UserID" and value:
                user_ids.append(value)
            elif etype == "ProfilePicture":
                # Carry the file UUID via the entry's jump_target — the
                # frontend can render the thumbnail by resolving it
                # through evidence_storage.
                if entry.jump_targets:
                    photo_file_ids.append(entry.jump_targets[0])
            elif value:
                # Generic Entry fallback — categorize on Category name.
                if "mail" in category.lower():
                    emails.append(value)
                else:
                    phone_numbers.append(value)

        # ContactPhoto entries (separate from Entries on some reports)
        for photo in model.multi_model_fields.get("Photos", []):
            if photo.jump_targets:
                photo_file_ids.append(photo.jump_targets[0])

        # StreetAddress entries — flatten to a list of human-readable
        # postal strings + a structured first-address dict so the
        # frontend can render either.
        addresses_text: List[str] = []
        first_addr: Dict[str, Optional[str]] = {}
        for addr in model.multi_model_fields.get("Addresses", []):
            parts = []
            for fld in ("HouseNumber", "Street", "City", "State", "PostalCode", "Country"):
                v = addr.get_field(fld)
                if v:
                    parts.append(v)
            if parts:
                addresses_text.append(", ".join(parts))
            if not first_addr:
                for fld, key in (("Street", "street"), ("HouseNumber", "house_number"),
                                  ("City", "city"), ("State", "state"),
                                  ("PostalCode", "postal_code"), ("Country", "country")):
                    v = addr.get_field(fld)
                    if v:
                        first_addr[f"address_{key}"] = v

        # Organization affiliations.
        organizations: List[str] = []
        org_titles: List[str] = []
        for org in model.multi_model_fields.get("Organizations", []):
            org_name = org.get_field("Name") or org.get_field("OrganizationName")
            if org_name:
                organizations.append(org_name)
            title = org.get_field("Title") or org.get_field("Position")
            if title:
                org_titles.append(title)

        # Generate key from best identifier
        best_id = phone_numbers[0] if phone_numbers else (emails[0] if emails else account)
        key = _generate_person_key(identifier=best_id, name=name, source_app=source)
        if not key:
            return

        extra_props: Dict = {}
        if phone_numbers:
            extra_props["phone_numbers"] = phone_numbers
        if emails:
            extra_props["emails"] = emails
        if web_addresses:
            extra_props["web_addresses"] = web_addresses
        if user_ids:
            extra_props["user_ids"] = user_ids
        if photo_file_ids:
            extra_props["photo_file_ids"] = photo_file_ids
        if addresses_text:
            extra_props["addresses"] = addresses_text
        if first_addr:
            extra_props.update(first_addr)
        if organizations:
            extra_props["organizations"] = organizations
        if org_titles:
            extra_props["org_titles"] = org_titles
        if source:
            extra_props["contact_source"] = source
        if contact_type:
            extra_props["contact_type"] = contact_type
        if group:
            extra_props["contact_group"] = group

        self._ensure_person(identifier=best_id, name=name, source_app=source, extra_props=extra_props)
        self._create_relationship(key, self.report_key, "EXTRACTED_FROM")
        self.contacts_created += 1

    def _write_call(self, model: ParsedModel):
        """Call -> PhoneCall node + Person relationships."""
        source = model.get_field("Source")
        direction = model.get_field("Direction")
        call_type = model.get_field("Type")
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp",))
        duration = model.get_field("Duration")
        video_call = model.get_field("VideoCall")
        # Call.Status carries the call outcome (Missed / Rejected /
        # Established / Voicemail / Unknown). Confirmed dropped on
        # 7,881 of 7,896 Call instances by the 2026-05-23 audit —
        # user feedback explicitly called this out as missing.
        status = model.get_field("Status")
        account = model.get_field("Account")

        # Generate unique key for this call
        call_key = f"call-{model.model_id[:12]}"

        props = self._base_props(model, call_key, f"Call ({direction or ''} {call_type or ''})")
        props.update({
            "direction": direction,
            "call_type": call_type,
            "duration": duration,
            "video_call": video_call == "True" if video_call else False,
            "source_app": source,
            "status": status,
            "account": account,
        })
        if timestamp:
            props["date"] = timestamp[:10]  # YYYY-MM-DD
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None  # HH:MM
            props["timestamp"] = timestamp
        props.update(self._attachment_props(model))
        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("PhoneCall", call_key, props)

        # Link parties
        parties = model.get_parties("Parties")
        for party in parties:
            person_key = self._ensure_person(
                identifier=party.identifier,
                name=party.name,
                source_app=source,
            )
            if person_key:
                if party.role == "From":
                    self._create_relationship(person_key, call_key, "CALLED")
                elif party.role == "To":
                    self._create_relationship(call_key, person_key, "CALLED_TO")

        self.calls_created += 1

    def _write_chat(self, model: ParsedModel):
        """Chat -> Communication node (thread)."""
        source = model.get_field("Source")
        chat_id = model.get_field("Id")
        start_time = model.get_field("StartTime")
        last_activity = model.get_field("LastActivity")
        # Account, Name and Description are useful for group-chat
        # identification; 100% dropped in the 2026-05-23 audit.
        account = model.get_field("Account")
        chat_name = model.get_field("Name")
        chat_description = model.get_field("Description")

        chat_key = f"chat-{model.model_id[:12]}"
        messages = model.multi_model_fields.get("Messages", [])
        participants = model.get_parties("Participants")

        props = self._base_props(
            model, chat_key,
            chat_name or f"Chat ({source or 'Unknown'})",
        )
        props.update({
            "chat_id": chat_id,
            "source_app": source,
            "message_count": len(messages),
            "account": account,
            "chat_name": chat_name,
            "description": chat_description,
            # Coarse "is this a group chat?" heuristic from participant
            # count — Cellebrite doesn't always carry an IsGroup flag
            # but >2 participants almost always means group.
            "is_group": len(participants) > 2 if participants else None,
            "participant_count": len(participants) if participants else None,
        })
        if start_time:
            props["date"] = start_time[:10]
            props["start_time"] = start_time
        if last_activity:
            props["last_activity"] = last_activity

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("Communication", chat_key, props)

        # Link participants
        for party in model.get_parties("Participants"):
            person_key = self._ensure_person(
                identifier=party.identifier,
                name=party.name,
                source_app=source,
            )
            if person_key:
                self._create_relationship(person_key, chat_key, "PARTICIPATED_IN")

        # Write individual messages as separate nodes
        for msg in messages:
            self._write_instant_message(msg, parent_chat_key=chat_key)

        self.chats_created += 1

    def _write_instant_message(self, model: ParsedModel, parent_chat_key: Optional[str] = None):
        """InstantMessage -> Communication node (individual message)."""
        source = model.get_field("Source") or model.get_field("SourceApplication")
        body = model.get_field("Body")
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp",))
        # Status carries the send/delivery state ("Sent" / "Delivered" /
        # "Read" / "Failed" / "Draft"). Identifier is the app-side
        # message ID (e.g. WhatsApp's server message ID). DateDelivered
        # is the moment the recipient device acknowledged receipt —
        # distinct from TimeStamp (when the message was composed/sent).
        # All three were dropped in the 2026-05-23 audit.
        status = model.get_field("Status")
        identifier = model.get_field("Identifier")
        folder = model.get_field("Folder")
        date_delivered = model.get_field("DateDelivered")

        msg_key = f"msg-{model.model_id[:12]}"

        # Truncate very long message bodies for the node name
        short_body = (body[:80] + "...") if body and len(body) > 80 else body

        props = self._base_props(model, msg_key, short_body or f"Message ({source or ''})")
        props.update({
            "body": body,
            "source_app": source,
            "message_type": model.get_field("Type"),
            "status": status,
            "identifier": identifier,
            "folder": folder,
            "date_delivered": date_delivered,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp
        props.update(self._attachment_props(model))
        props.update(self._message_provenance_props(model))
        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("Communication", msg_key, props)

        # Link sender
        from_party = model.get_party("From")
        if from_party:
            person_key = self._ensure_person(
                identifier=from_party.identifier,
                name=from_party.name,
                source_app=source,
            )
            if person_key:
                self._create_relationship(person_key, msg_key, "SENT_MESSAGE")

        # Link to parent chat
        if parent_chat_key:
            self._create_relationship(msg_key, parent_chat_key, "PART_OF")

        self.messages_created += 1

    def _write_email(self, model: ParsedModel):
        """Email -> Email node."""
        source = model.get_field("Source")
        subject = model.get_field("Subject")
        body = model.get_field("Body")
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp",))
        folder = model.get_field("Folder")
        status = model.get_field("Status")
        # Account = which mailbox this email lives in (e.g. "gmail").
        # Important for multi-account devices.
        account = model.get_field("Account")

        email_key = f"email-{model.model_id[:12]}"

        props = self._base_props(model, email_key, subject or f"Email ({source or ''})")
        props.update({
            "subject": subject,
            "body": body[:2000] if body else None,  # Truncate long bodies
            "source_app": source,
            "folder": folder,
            "email_status": status,
            "account": account,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp
        props.update(self._attachment_props(model))
        props.update(self._message_provenance_props(model))

        # Remove None values
        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("Email", email_key, props)

        # Link parties
        for party in model.get_parties("Parties"):
            person_key = self._ensure_person(
                identifier=party.identifier,
                name=party.name,
                source_app=source,
            )
            if person_key:
                if party.role == "From":
                    self._create_relationship(person_key, email_key, "EMAILED")
                elif party.role in ("To", "CC", "BCC"):
                    self._create_relationship(email_key, person_key, "SENT_TO")

        self.emails_created += 1

    def _write_location(self, model: ParsedModel):
        """Location -> Location node."""
        source = model.get_field("Source")
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp",))
        loc_type = model.get_field("Type")
        # Name (e.g. "Home", "Work"), Category ("Frequented" / "Visit" /
        # "Search"), Description — all dropped on 120/148, 120/148 and
        # 5/22 Location rows in the 2026-05-23 audit.
        loc_name = model.get_field("Name")
        category = model.get_field("Category")
        description = model.get_field("Description")

        # Get coordinates from nested Position/Coordinate. Cellebrite
        # also embeds accuracy ("PrecisionInMeters" / "Precision" /
        # "HorizontalAccuracy") and a free-form address inside the same
        # Position model — pull them through so the map renderer can
        # show a halo radius and "place" search has a string to match.
        lat = None
        lon = None
        accuracy_meters = None
        position = model.model_fields.get("Position")
        if position:
            lat_str = position.get_field("Latitude")
            lon_str = position.get_field("Longitude")
            try:
                lat = float(lat_str) if lat_str else None
                lon = float(lon_str) if lon_str else None
            except (ValueError, TypeError):
                pass
            # Accuracy field name varies by extraction format; try the
            # common ones in order. Numeric coercion is best-effort.
            for fld in ("PrecisionInMeters", "Precision", "HorizontalAccuracy"):
                v = position.get_field(fld)
                if v is None:
                    continue
                try:
                    accuracy_meters = float(v)
                    break
                except (TypeError, ValueError):
                    continue

        if lat is None or lon is None:
            return  # Skip locations without coordinates

        # Build a free-form address from PositionAddress sub-fields if
        # present. Order matches typical postal display so the result is
        # human-readable; we keep individual components alongside in case
        # search ever wants to filter by city/country specifically.
        address_str = None
        address_parts: Dict[str, Optional[str]] = {}
        addr_model = model.model_fields.get("PositionAddress")
        if addr_model:
            for fld, key in (
                ("Street", "address_street"),
                ("HouseNumber", "address_house_number"),
                ("City", "address_city"),
                ("State", "address_state"),
                ("PostalCode", "address_postal_code"),
                ("Country", "address_country"),
            ):
                v = addr_model.get_field(fld)
                if v:
                    address_parts[key] = v
            ordered = [
                address_parts.get("address_house_number"),
                address_parts.get("address_street"),
                address_parts.get("address_city"),
                address_parts.get("address_state"),
                address_parts.get("address_postal_code"),
                address_parts.get("address_country"),
            ]
            joined = ", ".join(p for p in ordered if p)
            if joined:
                address_str = joined

        # Confidence: Cellebrite uses both a top-level "Confidence" field
        # (carved locations) and the model-level decoding_confidence
        # already captured in _base_props. We surface the field-level
        # one separately because it's a numeric score for carved data
        # rather than a string label.
        confidence_score = None
        conf_raw = model.get_field("Confidence")
        if conf_raw is not None:
            try:
                confidence_score = float(conf_raw)
            except (TypeError, ValueError):
                # Sometimes "High"/"Medium"/"Low"; keep as string.
                confidence_score = conf_raw

        loc_key = f"loc-{model.model_id[:12]}"

        # Always populate location_type so the table column + `type:`
        # search suggestions agree. Without this fallback, rows whose
        # Cellebrite XML omits PositionType get an empty location_type
        # and the table falls through to the `name` — producing
        # visual variants the suggestion endpoint can't match against.
        # Name is the bare type token (no "Location (...)" wrapper)
        # so node names + the table column read identically.
        effective_type = loc_type or source or "Unknown"
        # Use Cellebrite-supplied display name when present (Home/Work
        # labels etc.); fall back to the type token.
        display_name = loc_name or effective_type

        props = self._base_props(model, loc_key, display_name)
        props.update({
            "latitude": lat,
            "longitude": lon,
            "location_type": effective_type,
            "location_category": category,
            "place_label": loc_name,
            "description": description,
            "source_app": source,
        })
        if accuracy_meters is not None:
            props["accuracy_meters"] = accuracy_meters
        if confidence_score is not None:
            props["confidence_score"] = confidence_score
        if address_str:
            props["address"] = address_str
            # Source marker so reverse-geocoded vs Cellebrite-provided
            # addresses are distinguishable downstream — investigators
            # can audit "was this address from the device or inferred?".
            props["geocode_source"] = "cellebrite"
            props.update({k: v for k, v in address_parts.items() if v})
        else:
            # Cellebrite didn't carry an address — try the configured
            # reverse-geocoder. Default-off (returns geocode_source =
            # "none" if no backend is set), so this is a no-op on
            # deploys that haven't opted in. Wrapped in try/except
            # because ingestion must not fail if the geocoder is
            # misconfigured at runtime.
            try:
                geo = _geocode_lat_lon(lat, lon)
            except Exception:
                geo = None
            if geo:
                # Only stamp non-null fields so we don't pollute the
                # node with "address: null". Always include the source
                # marker so audits work.
                for k in ("address", "place_name", "country", "country_code",
                          "admin1", "admin2", "geocode_source", "geocode_accuracy"):
                    v = geo.get(k)
                    if v is not None:
                        props[k] = v
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp

        self._create_node("Location", loc_key, props)

        # Link to phone owner
        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, loc_key, "WAS_AT")

        self.locations_created += 1

    def _write_user_account(self, model: ParsedModel):
        """UserAccount -> Account node."""
        source = model.get_field("Source")
        name = model.get_field("Name")
        username = model.get_field("Username")
        # ServiceType (e.g. "Facebook" / "WhatsApp" / "Google Drive") +
        # ServiceIdentifier (the per-service unique account ID) +
        # TimeCreated were dropped on 100% / 9% / 6% of UserAccount
        # instances respectively by the 2026-05-23 audit.
        service_type = model.get_field("ServiceType")
        service_identifier = model.get_field("ServiceIdentifier")
        time_created = model.get_field("TimeCreated")
        password = model.get_field("Password")

        acct_key = f"acct-{model.model_id[:12]}"

        # Collect user IDs from entries
        user_ids = []
        for entry in model.multi_model_fields.get("Entries", []):
            val = entry.get_field("Value")
            if val:
                user_ids.append(val)

        display_name = name or username or f"Account ({source or 'Unknown'})"

        props = self._base_props(model, acct_key, display_name)
        props.update({
            "username": username,
            "platform": source,
            "service_type": service_type,
            "service_identifier": service_identifier,
            "time_created": time_created,
            # Account credential — stored only when Cellebrite carved
            # it; not always a real password (sometimes a hash/token).
            # `is_sensitive` flags it for redaction in any export.
            "credential": password,
            "is_sensitive": bool(password),
            "user_ids": user_ids if user_ids else None,
        })
        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("Account", acct_key, props)

        # Link to phone owner
        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, acct_key, "OWNS_ACCOUNT")

        self.accounts_created += 1

    def _write_searched_item(self, model: ParsedModel):
        """SearchedItem -> SearchedItem node."""
        value = model.get_field("Value")
        # SearchedItem timestamps can land on LastVisited/Date as well as
        # TimeStamp; the hardcoded-TimeStamp pattern is exactly what the
        # 2026-05-23 audit flagged for dropping events. Use the alias path.
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp", "Date", "LastVisited"))
        source = model.get_field("Source")
        # Origin = which app/surface the search was issued from (browser
        # vs in-app search). Sparse in our data (~3 non-empty) but the
        # audit flagged it as unread — capture it when present.
        origin = model.get_field("Origin")

        if not value:
            return

        key = f"search-{model.model_id[:12]}"

        props = self._base_props(model, key, value[:100])
        props.update({
            "query": value,
            "source_app": source,
            "origin": origin,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("SearchedItem", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "SEARCHED")

        self.searches_created += 1

    def _write_visited_page(self, model: ParsedModel):
        """VisitedPage -> VisitedPage node.

        Cellebrite uses `LastVisited` as the canonical field name on
        VisitedPage (not `TimeStamp`) — the audit on 2026-05-23 found
        15,995 timestamps had been silently dropped on case 43f1afb1
        because the handler only read `TimeStamp`. `_extract_timestamp`
        now tries `LastVisited` first then falls through.

        Also derives a `search_query` when the URL is a well-known
        search-engine query so investigators can find "what did they
        google" without parsing every browser-history URL by hand.
        """
        url = model.get_field("Url")
        title = model.get_field("Title")
        source = model.get_field("Source")
        timestamp = self._extract_timestamp(model, prefer=("LastVisited", "TimeStamp"))
        visit_count = model.get_field("VisitCount")
        url_cache_file = model.get_field("UrlCacheFile")

        if not url and not title:
            return

        key = f"page-{model.model_id[:12]}"

        props = self._base_props(model, key, title or url[:80] if url else "Visited Page")
        props.update({
            "url": url,
            "title": title,
            "source_app": source,
            "visit_count": _safe_int(visit_count),
            "url_cache_file": url_cache_file,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["timestamp"] = timestamp
            props["last_visited"] = timestamp

        # Detect search-engine queries embedded in the URL. Folds the
        # "browser searches" complaint into VisitedPage rather than
        # requiring a separate SearchedItem (Cellebrite doesn't always
        # emit one — for ~99% of "I googled X" traces the only record
        # is a VisitedPage with q= in the URL).
        search_query = _extract_search_query(url)
        if search_query:
            props["search_query"] = search_query
            props["is_search"] = True

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("VisitedPage", key, props)
        self.pages_created += 1

    def _write_calendar_entry(self, model: ParsedModel):
        """CalendarEntry -> Meeting node."""
        subject = model.get_field("Subject")
        details = model.get_field("Details")
        location = model.get_field("Location")
        start_date = model.get_field("StartDate")
        end_date = model.get_field("EndDate")
        # Source = which calendar app (Google Calendar / Outlook /
        # iCloud), Category = calendar grouping (Work / Personal /
        # Holidays). Both dropped on 100% of CalendarEntry instances
        # by the 2026-05-23 audit.
        source = model.get_field("Source")
        category = model.get_field("Category")
        repeat_rule = model.get_field("RepeatRule")
        repeat_until = model.get_field("RepeatUntil")

        if not subject:
            return

        key = f"cal-{model.model_id[:12]}"

        props = self._base_props(model, key, subject)
        props.update({
            "details": details,
            "location_text": location,
            "source_app": source,
            "category": category,
            "repeat_rule": repeat_rule,
            "repeat_until": repeat_until,
        })
        if start_date:
            props["date"] = start_date[:10]
            props["start_date"] = start_date
        if end_date:
            props["end_date"] = end_date

        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("Meeting", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "ATTENDED")

        self.meetings_created += 1

    def _write_wireless_network(self, model: ParsedModel):
        """WirelessNetwork -> WirelessNetwork node."""
        ssid = model.get_field("SSId") or model.get_field("Name")
        bssid = model.get_field("BSSId")
        # WirelessNetwork has BOTH `TimeStamp` (first/most-recent seen)
        # and `LastConnection` (last time the device actually connected).
        # Audit on 2026-05-23 showed 677/677 instances had Source set
        # but it was dropped; LastConnection was rare (5/677) but
        # important when present.
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp", "LastConnection"))
        last_connection = model.get_field("LastConnection")
        source = model.get_field("Source")
        security_mode = model.get_field("SecurityMode")

        if not ssid and not bssid:
            return

        key = f"wifi-{model.model_id[:12]}"

        props = self._base_props(model, key, ssid or bssid or "Unknown WiFi")
        props.update({
            "ssid": ssid,
            "bssid": bssid,
            "source_app": source,
            "security_mode": security_mode,
            "last_connection": last_connection,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["timestamp"] = timestamp

        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("WirelessNetwork", key, props)
        self.wifi_created += 1

    def _write_recognized_device(self, model: ParsedModel):
        """RecognizedDevice -> Device node."""
        name = model.get_field("Name")
        device_type = model.get_field("Type")
        mac = model.get_field("MACAddress")
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp", "LastConnected", "LastConnection"))
        source = model.get_field("Source")
        # SerialNumber is often populated even when MAC/Name are not —
        # carrying it lets us correlate paired devices across reports.
        serial = model.get_field("SerialNumber")

        if not name and not mac and not serial:
            return

        key = f"dev-{model.model_id[:12]}"

        props = self._base_props(model, key, name or mac or serial or "Unknown Device")
        props.update({
            "device_type": device_type,
            "mac_address": mac,
            "serial_number": serial,
            "source_app": source,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["timestamp"] = timestamp

        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("Device", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "PAIRED_WITH")

        self.devices_created += 1

    def _write_password(self, model: ParsedModel):
        """Password -> Credential node (metadata only, NOT the actual secret).

        Cellebrite's Password model carries quite a bit beyond the bare
        secret. We intentionally drop the `Data` field (the actual
        password/token bytes) but capture every other index — service,
        access group, identifier — so investigators can tell *what*
        the credential is for without ever exposing the secret.
        """
        label = model.get_field("Label")
        cred_type = model.get_field("Type")
        account = model.get_field("Account")
        # `Service` typically holds the URL or app identifier the
        # credential is scoped to. `AccessGroup` is the iOS Keychain
        # access group (or Android keystore alias). `ServiceIdentifier`
        # is a free-form vendor-specific identifier.
        service = model.get_field("Service")
        access_group = model.get_field("AccessGroup")
        service_identifier = model.get_field("ServiceIdentifier")
        source = model.get_field("Source")

        key = f"cred-{model.model_id[:12]}"

        props = self._base_props(model, key, label or f"Credential ({cred_type or 'Unknown'})")
        props.update({
            "label": label,
            "credential_type": cred_type,
            "account_ref": account,
            "service": service,
            "access_group": access_group,
            "service_identifier": service_identifier,
            "source_app": source,
            "is_sensitive": True,
            # NOTE: actual password/token data (`Data` field) is
            # intentionally NOT stored.
        })
        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("Credential", key, props)
        self.credentials_created += 1

    def _write_web_bookmark(self, model: ParsedModel):
        """WebBookmark -> WebBookmark node."""
        url = model.get_field("Url")
        title = model.get_field("Title")
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp", "Date", "LastVisited"))
        source = model.get_field("Source")
        # Path = the bookmark's folder location within the browser's
        # bookmark tree (e.g. "Bookmarks Bar/Work"). Empty in our current
        # data but flagged unread by the 2026-05-23 audit; capture when set.
        path = model.get_field("Path")

        if not url and not title:
            return

        key = f"bkmk-{model.model_id[:12]}"

        props = self._base_props(model, key, title or url[:80] if url else "Bookmark")
        props.update({
            "url": url,
            "source_app": source,
            "bookmark_path": path,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["timestamp"] = timestamp

        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("WebBookmark", key, props)
        self.bookmarks_created += 1

    # ------------------------------------------------------------------
    # Phase 4: Location & Event handlers (CellTower, DeviceEvent, AppSession)
    # ------------------------------------------------------------------

    def _write_cell_tower(self, model: ParsedModel):
        """CellTower -> CellTower node. Approximate location fix from a mobile radio registration."""
        timestamp = model.get_field("TimeStamp")
        source = model.get_field("Source")
        cell_id = model.get_field("CellId") or model.get_field("CID")
        mcc = model.get_field("MCC")
        mnc = model.get_field("MNC")
        lac = model.get_field("LAC")
        tac = model.get_field("TAC")
        rssi = model.get_field("RSSI") or model.get_field("SignalStrength")

        # Coordinates might be top-level or nested in Position/Coordinate
        lat = None
        lon = None
        for field in ("Latitude", "Lat"):
            v = model.get_field(field)
            if v is not None:
                try:
                    lat = float(v)
                    break
                except (TypeError, ValueError):
                    pass
        for field in ("Longitude", "Lon", "Lng"):
            v = model.get_field(field)
            if v is not None:
                try:
                    lon = float(v)
                    break
                except (TypeError, ValueError):
                    pass
        if lat is None or lon is None:
            position = model.model_fields.get("Position") or model.model_fields.get("Coordinate")
            if position:
                try:
                    lat = float(position.get_field("Latitude")) if lat is None else lat
                    lon = float(position.get_field("Longitude")) if lon is None else lon
                except (TypeError, ValueError):
                    pass

        radius = None
        radius_raw = (
            model.get_field("Radius")
            or model.get_field("Precision")
            or model.get_field("PrecisionInMeters")
            or model.get_field("HorizontalAccuracy")
        )
        try:
            radius = float(radius_raw) if radius_raw else None
        except (TypeError, ValueError):
            pass

        # Confidence — same dual-shape as Location (carved cell-towers
        # often carry a numeric Confidence; fall back to string).
        confidence_score = None
        conf_raw = model.get_field("Confidence")
        if conf_raw is not None:
            try:
                confidence_score = float(conf_raw)
            except (TypeError, ValueError):
                confidence_score = conf_raw

        if not cell_id and lat is None and lon is None:
            return  # Not enough data to be useful

        key = f"cell-{model.model_id[:12]}"
        name = f"Cell {cell_id}" if cell_id else "Cell tower"
        props = self._base_props(model, key, name)
        props.update({
            "cell_id": cell_id,
            "mcc": mcc,
            "mnc": mnc,
            "lac": lac,
            "tac": tac,
            "rssi": rssi,
            "latitude": lat,
            "longitude": lon,
            # Keep the historical `radius` name AND surface the field
            # under the same `accuracy_meters` key the Location node uses
            # so the map renderer can apply one consistent halo logic.
            "radius": radius,
            "accuracy_meters": radius,
            "confidence_score": confidence_score,
            "source_app": source,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("CellTower", key, props)

        # Link to phone owner
        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "REGISTERED_TO")

    def _write_device_event(self, model: ParsedModel):
        """
        Generic device event (power, unlock, lock, wake, sleep, reboot).

        Cellebrite emits these under several model type names — DeviceEvent
        / PoweringEvent / PowerEvent / UserEvent / ScreenEvent — and uses
        DIFFERENT field names per type:
          - DeviceEvent: StartTime + EventType + Value
          - PoweringEvent: Element + Event + Description + TimeStamp
          - Older variants: TimeStamp + State + Type + Action + Reason

        The 2026-05-23 audit found we were dropping 100% of DeviceEvent
        fields and 75% of PoweringEvent fields because the handler only
        read the older variant names. Try every alias.
        """
        timestamp = self._extract_timestamp(model, prefer=("TimeStamp", "StartTime"))
        source = model.get_field("Source")
        # State / type — try every field name we've ever seen.
        state = (model.get_field("State") or model.get_field("Type")
                 or model.get_field("Action") or model.get_field("EventType")
                 or model.get_field("Event") or model.get_field("Element"))
        reason = (model.get_field("Reason") or model.get_field("Details")
                  or model.get_field("Description"))
        # `Value` is a free-form payload (e.g. "Charging", "Discharging",
        # battery percentage). DeviceEvent uses this generically.
        value = model.get_field("Value")
        battery = model.get_field("Battery") or model.get_field("BatteryLevel")

        # Infer a coarse event_type from the model type + state.
        mt = (model.model_type or "").lower()
        if "power" in mt:
            event_type = "power"
        elif "user" in mt or "lock" in mt or "unlock" in mt:
            event_type = ("unlock" if state and "unlock" in state.lower() else
                          "lock"   if state and "lock"   in state.lower() else
                          "user")
        else:
            event_type = "device"

        key = f"evt-{model.model_id[:12]}"
        label = f"{event_type.title()} event"
        if state:
            label = f"{event_type.title()} ({state})"
        props = self._base_props(model, key, label)
        props.update({
            "event_type": event_type,
            "state": state,
            "reason": reason,
            "value": value,
            "battery": battery,
            "source_app": source,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("DeviceEvent", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "EXPERIENCED")

    def _write_app_session(self, model: ParsedModel):
        """ApplicationUsage / AppUsage -> AppSession node (foreground app session)."""
        timestamp = model.get_field("TimeStamp") or model.get_field("StartTime")
        start_time = model.get_field("StartTime") or timestamp
        end_time = model.get_field("EndTime")
        app_name = model.get_field("Application") or model.get_field("AppName") or model.get_field("Name")
        package = model.get_field("Package") or model.get_field("BundleId") or model.get_field("Identifier")
        source = model.get_field("Source")

        duration_s = None
        try:
            raw = model.get_field("Duration") or model.get_field("ForegroundTime")
            if raw is not None:
                duration_s = float(raw)
        except (TypeError, ValueError):
            pass

        if not app_name and not package:
            return  # Not useful

        key = f"app-{model.model_id[:12]}"
        label = app_name or package or "App session"
        props = self._base_props(model, key, label)
        props.update({
            "app_name": app_name,
            "app_package": package,
            "start_time": start_time,
            "end_time": end_time,
            "duration_s": duration_s,
            "source_app": source,
        })
        if start_time:
            props["date"] = start_time[:10]
            props["time"] = start_time[11:16] if len(start_time) > 16 else None
            props["timestamp"] = start_time

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("AppSession", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "USED")

    # ------------------------------------------------------------------
    # Phase 5: Media helpers (Attachment, ContactPhoto, ProfilePicture)
    # ------------------------------------------------------------------

    def _write_attachment(self, model: ParsedModel):
        """Attachment -> Attachment node.

        Creates a metadata-only node for each Cellebrite <model type="Attachment">.
        Useful for showing attachment-level provenance in the Files Explorer even
        when the backing file bytes are missing on disk.
        """
        filename = (
            model.get_field("Filename")
            or model.get_field("Name")
            or model.get_field("Title")
        )
        mime_type = model.get_field("ContentType") or model.get_field("MimeType")
        size_raw = model.get_field("Size") or model.get_field("FileSize")
        source = model.get_field("Source")
        url = model.get_field("Url")

        try:
            size = int(size_raw) if size_raw else None
        except (TypeError, ValueError):
            size = None

        # First jump_target is usually the underlying file UUID
        file_id = model.jump_targets[0] if model.jump_targets else None

        key = f"att-{model.model_id[:12]}"
        name = filename or f"Attachment ({source or 'Unknown'})"
        props = self._base_props(model, key, name)
        props.update({
            "filename": filename,
            "mime_type": mime_type,
            "size": size,
            "source_app": source,
            "url": url,
            "file_id": file_id,
        })
        # attachment_count/attachment_file_ids attached to the attachment itself if a
        # single file is referenced (mostly for consistency with Phase 3 backfill).
        if file_id:
            props["attachment_file_ids"] = [file_id]
            props["attachment_count"] = 1

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("Attachment", key, props)

    def _write_contact_photo(self, model: ParsedModel):
        """ContactPhoto -> set photo_file_id on the parent Person (no new node)."""
        file_id = model.jump_targets[0] if model.jump_targets else None
        if not file_id:
            return
        # We don't have a back-pointer from ContactPhoto to its owning Person here;
        # ContactPhoto is typically a child model consumed when a Contact is written.
        # If this handler ever fires on its own (top-level ContactPhoto) we just
        # record the file_id so a later backfill can match it. No-op for now.
        # Recorded as an Autofill-like leaf only if useful to investigator.
        return

    def _write_profile_picture(self, model: ParsedModel):
        """ProfilePicture -> similar to ContactPhoto (set on parent Account)."""
        return

    # ------------------------------------------------------------------
    # Phase 6: Device inventory / identity / file provenance
    # ------------------------------------------------------------------

    def _write_autofill(self, model: ParsedModel):
        """Autofill -> Autofill node.

        Browser/app autofill entries (saved logins, addresses, cards, search
        terms). Investigator-valuable because it surfaces credentials and
        personal data the user kept in browser/app form fillers.

        Cellebrite uses `Key` (the form field name) and `Value` (the
        filled value). LastUsedDate is the most recent use. The 2026-05-23
        audit found Key + LastUsedDate were dropped — fixed here.
        """
        value = (
            model.get_field("Value") or model.get_field("FieldValue")
        )
        # Try Key first (the actual Cellebrite XML attribute), then fall
        # back to the older FieldName / Name aliases for compatibility
        # with older UFED PA versions.
        field_name = (
            model.get_field("Key")
            or model.get_field("FieldName")
            or model.get_field("Name")
        )
        source = model.get_field("Source") or model.get_field("SourceApplication")
        timestamp = self._extract_timestamp(model, prefer=("LastUsedDate", "TimeStamp", "LastUsed"))
        last_used = model.get_field("LastUsedDate") or model.get_field("LastUsed")
        url = model.get_field("Url") or model.get_field("Domain")

        if not value and not field_name:
            return

        key = f"autofill-{model.model_id[:12]}"
        label = field_name or (value[:80] if value else "Autofill")

        props = self._base_props(model, key, label)
        props.update({
            "field_name": field_name,
            "value": value,
            "url": url,
            "source_app": source,
            "last_used": last_used,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["timestamp"] = timestamp

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("Autofill", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "AUTOFILLED")

        self.autofill_created += 1

    def _write_sim_data(self, model: ParsedModel):
        """SIMData -> aggregated SIMCard properties.

        Cellebrite emits SIMData as a stream of `Name=X, Value=Y, Category=Z`
        records — ONE record per SIM property (one for ICCID, one for IMSI,
        one for MSISDN, etc.) — NOT one SIMData per SIM card. The 2026-05-23
        audit showed our previous handler (which read fields like ICCID /
        IMSI / MSISDN directly off the model) captured 0% on 9 instances.

        We collect every (name, value) pair into `_sim_properties`. The
        final `finalise_sim_card()` (called once per ingest by the
        orchestrator) creates a single SIMCard node carrying every
        collected property as a sanitised attribute.
        """
        name = model.get_field("Name")
        value = model.get_field("Value")
        category = model.get_field("Category")
        if not name or not value:
            return

        # Defer node creation until finalise_sim_card() — multiple
        # SIMData rows aggregate into one SIMCard.
        prop_key = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
        if not prop_key:
            return
        # Last-write-wins for repeats; UFEDLib's SIM aggregation does
        # the same. Cellebrite rarely emits duplicates for the same
        # property name within one extraction.
        self._sim_properties[prop_key] = value
        if category:
            self._sim_categories[prop_key] = category
        self.sim_data_created += 1

    def finalise_sim_card(self) -> Optional[str]:
        """Materialise one SIMCard node from the aggregated SIMData rows.

        Must be called once after the writer's main batch loop completes
        — by ingestion.py — so every SIMData row across the report has
        contributed. Returns the SIMCard key, or None if no SIM data
        was seen.
        """
        if not self._sim_properties:
            return None
        key = f"sim-{self.report_key}"
        # The MSISDN-equivalent is the most useful label.
        label = (self._sim_properties.get("msisdn")
                 or self._sim_properties.get("phone_number")
                 or self._sim_properties.get("iccid")
                 or self._sim_properties.get("imsi")
                 or "SIM Card")
        props = {
            "id": str(uuid.uuid4()),
            "key": key,
            "name": label,
            "case_id": self.case_id,
            "cellebrite_report_key": self.report_key,
            "source_type": "cellebrite",
        }
        props.update(self._sim_properties)
        # Drop blanks / Nones.
        props = {k: v for k, v in props.items() if v is not None and v != ""}
        # MERGE so a re-ingest updates instead of duplicating.
        self.db.run_query(
            """
            MERGE (s:SIMCard {key: $key, case_id: $cid})
            ON CREATE SET s = $props
            ON MATCH  SET s += $props
            """,
            key=key, cid=self.case_id, props=props,
        )
        self._created_node_keys.add(key)
        self.nodes_total += 1
        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "USED_SIM")
        self._log(f"SIMCard upserted with {len(self._sim_properties)} properties")
        return key

    def _write_user(self, model: ParsedModel):
        """User -> DeviceUser node.

        OS-level user accounts on the device itself (e.g. Android profiles,
        guest user). Distinct from UserAccount (which is per-app credentials).

        Cellebrite carries Identifier (UID), SerialNumber (system-assigned)
        and TimeLastLoggedIn — all 100% non-empty in audited reports but
        dropped pre-2026-05-23.
        """
        name = model.get_field("Name") or model.get_field("UserName") or model.get_field("FullName")
        user_id = (
            model.get_field("Identifier")
            or model.get_field("UserID")
            or model.get_field("Id")
        )
        user_type = model.get_field("UserType") or model.get_field("Type")
        source = model.get_field("Source")
        serial_number = model.get_field("SerialNumber")
        last_login = self._extract_timestamp(
            model, prefer=("TimeLastLoggedIn", "LastLogin"),
        )

        if not name and not user_id and not serial_number:
            return

        key = f"deviceuser-{model.model_id[:12]}"
        label = name or user_id or serial_number or "Device User"

        props = self._base_props(model, key, label)
        props.update({
            "user_name": name,
            "user_id": user_id,
            "user_type": user_type,
            "source_app": source,
            "serial_number": serial_number,
            "time_last_logged_in": last_login,
        })

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("DeviceUser", key, props)

        self.users_created += 1

    def _write_installed_application(self, model: ParsedModel):
        """InstalledApplication -> InstalledApp node.

        Software inventory of the device — what apps were on it at the time
        of extraction. Commonly requested in digital forensics for both
        evidence-collection (was app X present?) and timeline correlation.
        """
        name = (
            model.get_field("Name")
            or model.get_field("ApplicationName")
            or model.get_field("AppName")
        )
        package = (
            model.get_field("Identifier")
            or model.get_field("Package")
            or model.get_field("BundleId")
            or model.get_field("PackageName")
        )
        version = model.get_field("Version") or model.get_field("VersionName")
        install_date = (
            model.get_field("InstallDate")
            or model.get_field("PurchaseDate")
            or self._extract_timestamp(model, prefer=("PurchaseDate", "InstallDate"))
        )
        publisher = model.get_field("Publisher") or model.get_field("Author")
        # OperationMode (Background / Foreground), IsEmulatable (running
        # via an Android emulator on PC, important for fraud cases),
        # DecodingStatus — all captured by the XML on 100% / 94% / 29%
        # of InstalledApplication rows but were dropped pre-audit.
        operation_mode = model.get_field("OperationMode")
        is_emulatable = model.get_field("IsEmulatable")
        decoding_status = model.get_field("DecodingStatus")

        if not name and not package:
            return

        key = f"app-installed-{model.model_id[:12]}"
        label = name or package

        props = self._base_props(model, key, label)
        props.update({
            "app_name": name,
            "app_package": package,
            "app_version": version,
            "install_date": install_date,
            "publisher": publisher,
            "operation_mode": operation_mode,
            "is_emulatable": is_emulatable == "True" if is_emulatable else None,
            "decoding_status": decoding_status,
        })
        if install_date:
            props["date"] = install_date[:10]
            props["timestamp"] = install_date

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("InstalledApp", key, props)

        # Tie installed app to the phone owner
        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "HAD_INSTALLED")

        self.installed_apps_created += 1

    def _write_file_download(self, model: ParsedModel):
        """FileDownload -> FileDownload node.

        A file the device downloaded (typically via a browser or messaging
        app). Provenance is investigation-relevant: distinguishes user-
        acquired files from pre-installed or sync'd ones.

        Cellebrite carries the full timeline: StartTime (download begun),
        EndTime (completed), LastAccessed (user opened it), TargetPath
        (where it landed on disk), BytesReceived (partial-download
        indicator). All dropped pre-2026-05-23 audit.
        """
        url = model.get_field("Url") or model.get_field("SourceUrl")
        filename = model.get_field("Filename") or model.get_field("Name")
        timestamp = self._extract_timestamp(
            model, prefer=("TimeStamp", "StartTime", "DownloadTime", "Date"),
        )
        start_time = model.get_field("StartTime")
        end_time = model.get_field("EndTime")
        last_accessed = model.get_field("LastAccessed")
        size_raw = model.get_field("Size") or model.get_field("FileSize")
        bytes_received_raw = model.get_field("BytesReceived")
        source = model.get_field("Source") or model.get_field("SourceApplication")
        # FileDownload uses `DownloadState` ("Completed"/"InProgress"/
        # "Failed") on newer reports; older ones use `Status` or `State`.
        status = (
            model.get_field("DownloadState")
            or model.get_field("Status")
            or model.get_field("State")
        )
        target_path = model.get_field("TargetPath")

        if not url and not filename:
            return

        try:
            size = int(size_raw) if size_raw else None
        except (TypeError, ValueError):
            size = None
        try:
            bytes_received = int(bytes_received_raw) if bytes_received_raw else None
        except (TypeError, ValueError):
            bytes_received = None

        key = f"dl-{model.model_id[:12]}"
        label = filename or (url[:80] if url else "Download")

        props = self._base_props(model, key, label)
        props.update({
            "url": url,
            "filename": filename,
            "size": size,
            "bytes_received": bytes_received,
            "download_status": status,
            "source_app": source,
            "target_path": target_path,
            "start_time": start_time,
            "end_time": end_time,
            "last_accessed": last_accessed,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp
        props.update(self._attachment_props(model))

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("FileDownload", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "DOWNLOADED")

        self.file_downloads_created += 1

    def _write_network_usage(self, model: ParsedModel):
        """NetworkUsage -> NetworkUsage node.

        Per-app / per-network data-consumption record over a time window.
        Cellebrite emits one per (app, network, window): bytes sent/received,
        the window (DateStarted → DateEnded), connection type (Cellular /
        WiFi), roaming flag, and foreground/background usage mode. Useful
        timeline data — "this app moved 43 MB over cellular at 18:00 on the
        24th" — and was SKIPPED before 2026-05-23. The owning app/UID lands
        in the AdditionalInfo KeyValueModel children.
        """
        source = model.get_field("Source")
        ssid = model.get_field("SSId") or model.get_field("SSID")
        date_started = model.get_field("DateStarted")
        date_ended = model.get_field("DateEnded")
        bytes_received = _safe_int(model.get_field("NumberOfBytesReceived"))
        bytes_sent = _safe_int(model.get_field("NumberOfBytesSent"))
        is_roaming = model.get_field("IsRoaming")
        usage_mode = model.get_field("UsageMode")
        connection_type = model.get_field("NetworkConnectionType")
        timestamp = self._extract_timestamp(
            model, prefer=("DateStarted", "StartTime", "TimeStamp"),
        )

        # AdditionalInfo carries Key=Value pairs (UID, package name, app
        # bundle id). Fold the app/package identity onto the node so the
        # usage can be attributed to a specific app.
        app_identifier = None
        for kv in model.multi_model_fields.get("AdditionalInfo", []):
            k = (kv.get_field("Key") or "").strip().lower()
            v = kv.get_field("Value")
            if not v:
                continue
            if k in ("package", "packagename", "bundleid", "app", "application", "name"):
                app_identifier = v
                break

        # Skip entirely-empty rows (no bytes and no window) — nothing to show.
        if bytes_received is None and bytes_sent is None and not date_started:
            return

        bytes_total = None
        if bytes_received is not None or bytes_sent is not None:
            bytes_total = (bytes_received or 0) + (bytes_sent or 0)

        key = f"netusage-{model.model_id[:12]}"
        label = app_identifier or ssid or connection_type or "Network Usage"

        props = self._base_props(model, key, label[:100])
        props.update({
            "source_app": source,
            "app_identifier": app_identifier,
            "ssid": ssid,
            "bytes_received": bytes_received,
            "bytes_sent": bytes_sent,
            "bytes_total": bytes_total,
            "is_roaming": is_roaming == "True" if is_roaming else None,
            "usage_mode": usage_mode,
            "connection_type": connection_type,
            "date_started": date_started,
            "date_ended": date_ended,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["timestamp"] = timestamp

        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("NetworkUsage", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "CONSUMED_DATA")

        self.network_usage_created += 1

    def _write_dictionary_word(self, model: ParsedModel):
        """DictionaryWord -> DictionaryWord node.

        A word the device keyboard (e.g. SwiftKey) learned from the owner's
        typing, with how often it was typed (Frequency). Looks like
        autocomplete noise in bulk, but an audit found real values among
        them: typed email addresses, phone-number fragments, money amounts,
        names, and phrase fragments — none of which appear anywhere else in
        the extraction. The owner TYPED these, so they attach to the owner.
        """
        word = model.get_field("Word")
        if not word:
            return
        # Drop keyboard artifacts: empty/whitespace or a single non-word
        # character (e.g. "^", ".", ","). Anything with a letter or digit,
        # or any multi-char token, is kept — that's where the values live.
        stripped = word.strip()
        if not stripped or (len(stripped) == 1 and not stripped.isalnum()):
            return

        frequency = _safe_int(model.get_field("Frequency"))
        source = model.get_field("Source")

        key = f"dword-{model.model_id[:12]}"
        props = self._base_props(model, key, word[:100])
        props.update({
            "word": word,
            "frequency": frequency,
            "source_app": source,
        })
        props = {k: v for k, v in props.items() if v is not None}
        self._create_node("DictionaryWord", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "TYPED")

        self.dictionary_words_created += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return ingestion statistics."""
        return {
            "contacts_created": self.contacts_created,
            "calls_created": self.calls_created,
            "chats_created": self.chats_created,
            "messages_created": self.messages_created,
            "emails_created": self.emails_created,
            "locations_created": self.locations_created,
            "accounts_created": self.accounts_created,
            "searches_created": self.searches_created,
            "visited_pages_created": self.pages_created,
            "meetings_created": self.meetings_created,
            "credentials_created": self.credentials_created,
            "devices_created": self.devices_created,
            "wifi_networks_created": self.wifi_created,
            "bookmarks_created": self.bookmarks_created,
            "autofill_created": self.autofill_created,
            "sim_data_created": self.sim_data_created,
            "users_created": self.users_created,
            "installed_apps_created": self.installed_apps_created,
            "file_downloads_created": self.file_downloads_created,
            "network_usage_created": self.network_usage_created,
            "dictionary_words_created": self.dictionary_words_created,
            "total_nodes": self.nodes_total,
            "total_relationships": self.relationships_total,
            "phone_owner": self._phone_owner_key,
            # Per-type write failure counts. {} on a clean run; non-empty
            # means at least one handler raised. Orchestrator surfaces
            # the total via task.progress.failed and fails the task if
            # the rate exceeds the threshold (see cellebrite_service).
            "write_errors": dict(self.write_errors),
            "write_errors_total": sum(self.write_errors.values()),
        }

    def link_all_to_report(self) -> int:
        """Connect every node tagged with this report_key to the PhoneReport
        via a `CONTAINS` edge.

        Done as a single batched sweep after Step 8 so investigative views
        can filter "everything from this device" with a single hop instead
        of property-based filtering. APOC batching keeps the transaction
        small even on reports with hundreds of thousands of entities (the
        2026-05-12 tx-log corruption was caused by an unbatched 33k-node
        write — see project_cellebrite_ingestion_failures memory).

        Returns the number of relationships created.
        """
        try:
            result = self.db.run_query(
                """
                CALL apoc.periodic.iterate(
                    'MATCH (r:PhoneReport {case_id: $cid, key: $rk}),
                           (n {case_id: $cid, cellebrite_report_key: $rk})
                     WHERE n.key <> $rk
                     RETURN r, n',
                    'MERGE (r)-[rel:CONTAINS {case_id: $cid}]->(n)',
                    {batchSize: 1000, parallel: false,
                     params: {cid: $case_id, rk: $report_key}}
                ) YIELD batches, total, errorMessages
                RETURN batches, total, errorMessages
                """,
                case_id=self.case_id,
                report_key=self.report_key,
            )
            if result:
                row = result[0]
                created = int(row.get("total") or 0)
                self.relationships_total += created
                if row.get("errorMessages"):
                    self._log(f"WARNING: CONTAINS sweep errors: {row['errorMessages']}")
                self._log(f"Linked {created} entities to PhoneReport via CONTAINS")
                return created
        except Exception as e:
            self._log(f"WARNING: CONTAINS sweep failed: {e}")
        return 0
