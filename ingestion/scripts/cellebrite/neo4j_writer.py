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

import re
import uuid
from typing import List, Dict, Optional, Set, Callable, Tuple

from .models import ParsedModel, Party, CellebriteReport

# We import Neo4jClient at usage time to avoid import-order issues
# when this module is loaded from the ingestion scripts directory.


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
        self.nodes_total = 0
        self.relationships_total = 0

        # Phone owner identity (populated during first pass)
        self._phone_owner_key: Optional[str] = None
        self._phone_owner_names: Dict[str, int] = {}  # name -> count
        self._phone_owner_identifiers: Set[str] = set()

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def _base_props(self, model: ParsedModel, key: str, name: str) -> Dict:
        """Build base properties common to all Cellebrite nodes."""
        return {
            "id": str(uuid.uuid4()),
            "key": key,
            "name": name,
            "case_id": self.case_id,
            "cellebrite_report_key": self.report_key,
            "cellebrite_id": model.model_id,
            "source_type": "cellebrite",
            "deleted_state": model.deleted_state,
        }

    def _attachment_props(self, model: ParsedModel) -> Dict:
        """Build attachment_file_ids / attachment_count for a model, if any."""
        file_ids = self.attachment_map.get(model.model_id, [])
        if not file_ids:
            return {}
        return {
            "attachment_file_ids": list(file_ids),
            "attachment_count": len(file_ids),
        }

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

        # Use run_query for MERGE to handle concurrency
        self.db.run_query(
            """
            MERGE (p:Person {key: $key, case_id: $case_id})
            ON CREATE SET p = $props
            """,
            key=key,
            case_id=self.case_id,
            props=props,
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

        props = {
            "id": str(uuid.uuid4()),
            "key": self.report_key,
            "name": self.report.report_name,
            "case_id": self.case_id,
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
            "imei": di.imei,
            "os_type": di.os_type,
            "phone_numbers": di.msisdn,
        }

        # Remove None values
        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("PhoneReport", self.report_key, props)
        self._log(f"Created PhoneReport node: {self.report_key}")

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
        """Write a batch of parsed models to Neo4j."""
        for model in models:
            try:
                handler = self._get_handler(model.model_type)
                if handler:
                    handler(model)
            except Exception as e:
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
        """Contact -> Person node."""
        name = model.get_field("Name")
        source = model.get_field("Source")
        account = model.get_field("Account")

        # Get phone numbers and emails from contact entries
        phone_numbers = []
        emails = []
        for entry in model.multi_model_fields.get("Entries", []):
            category = entry.get_field("Category")
            value = entry.get_field("Value")
            if value:
                if category and "mail" in category.lower():
                    emails.append(value)
                else:
                    phone_numbers.append(value)

        # Generate key from best identifier
        best_id = phone_numbers[0] if phone_numbers else (emails[0] if emails else account)
        key = _generate_person_key(identifier=best_id, name=name, source_app=source)
        if not key:
            return

        extra_props = {}
        if phone_numbers:
            extra_props["phone_numbers"] = phone_numbers
        if emails:
            extra_props["emails"] = emails
        if source:
            extra_props["contact_source"] = source

        self._ensure_person(identifier=best_id, name=name, source_app=source, extra_props=extra_props)
        self._create_relationship(key, self.report_key, "EXTRACTED_FROM")
        self.contacts_created += 1

    def _write_call(self, model: ParsedModel):
        """Call -> PhoneCall node + Person relationships."""
        source = model.get_field("Source")
        direction = model.get_field("Direction")
        call_type = model.get_field("Type")
        timestamp = model.get_field("TimeStamp")
        duration = model.get_field("Duration")
        video_call = model.get_field("VideoCall")

        # Generate unique key for this call
        call_key = f"call-{model.model_id[:12]}"

        props = self._base_props(model, call_key, f"Call ({direction or ''} {call_type or ''})")
        props.update({
            "direction": direction,
            "call_type": call_type,
            "duration": duration,
            "video_call": video_call == "True" if video_call else False,
            "source_app": source,
        })
        if timestamp:
            props["date"] = timestamp[:10]  # YYYY-MM-DD
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None  # HH:MM
            props["timestamp"] = timestamp
        props.update(self._attachment_props(model))

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

        chat_key = f"chat-{model.model_id[:12]}"
        messages = model.multi_model_fields.get("Messages", [])

        props = self._base_props(model, chat_key, f"Chat ({source or 'Unknown'})")
        props.update({
            "chat_id": chat_id,
            "source_app": source,
            "message_count": len(messages),
        })
        if start_time:
            props["date"] = start_time[:10]
            props["start_time"] = start_time
        if last_activity:
            props["last_activity"] = last_activity

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
        timestamp = model.get_field("TimeStamp")

        msg_key = f"msg-{model.model_id[:12]}"

        # Truncate very long message bodies for the node name
        short_body = (body[:80] + "...") if body and len(body) > 80 else body

        props = self._base_props(model, msg_key, short_body or f"Message ({source or ''})")
        props.update({
            "body": body,
            "source_app": source,
            "message_type": model.get_field("Type"),
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp
        props.update(self._attachment_props(model))

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
        timestamp = model.get_field("TimeStamp")
        folder = model.get_field("Folder")
        status = model.get_field("Status")

        email_key = f"email-{model.model_id[:12]}"

        props = self._base_props(model, email_key, subject or f"Email ({source or ''})")
        props.update({
            "subject": subject,
            "body": body[:2000] if body else None,  # Truncate long bodies
            "source_app": source,
            "folder": folder,
            "email_status": status,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp
        props.update(self._attachment_props(model))

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
        timestamp = model.get_field("TimeStamp")
        loc_type = model.get_field("Type")

        # Get coordinates from nested Position/Coordinate
        lat = None
        lon = None
        position = model.model_fields.get("Position")
        if position:
            lat_str = position.get_field("Latitude")
            lon_str = position.get_field("Longitude")
            try:
                lat = float(lat_str) if lat_str else None
                lon = float(lon_str) if lon_str else None
            except (ValueError, TypeError):
                pass

        if lat is None or lon is None:
            return  # Skip locations without coordinates

        loc_key = f"loc-{model.model_id[:12]}"

        props = self._base_props(model, loc_key, f"Location ({loc_type or source or 'Unknown'})")
        props.update({
            "latitude": lat,
            "longitude": lon,
            "location_type": loc_type,
            "source_app": source,
        })
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
        timestamp = model.get_field("TimeStamp")
        source = model.get_field("Source")

        if not value:
            return

        key = f"search-{model.model_id[:12]}"

        props = self._base_props(model, key, value[:100])
        props.update({
            "query": value,
            "source_app": source,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["time"] = timestamp[11:16] if len(timestamp) > 16 else None
            props["timestamp"] = timestamp

        self._create_node("SearchedItem", key, props)

        if self._phone_owner_key:
            self._create_relationship(self._phone_owner_key, key, "SEARCHED")

        self.searches_created += 1

    def _write_visited_page(self, model: ParsedModel):
        """VisitedPage -> VisitedPage node (lightweight, no relationships)."""
        url = model.get_field("Url")
        title = model.get_field("Title")
        timestamp = model.get_field("TimeStamp")
        source = model.get_field("Source")

        if not url and not title:
            return

        key = f"page-{model.model_id[:12]}"

        props = self._base_props(model, key, title or url[:80] if url else "Visited Page")
        props.update({
            "url": url,
            "source_app": source,
        })
        if timestamp:
            props["date"] = timestamp[:10]
            props["timestamp"] = timestamp

        self._create_node("VisitedPage", key, props)
        self.pages_created += 1

    def _write_calendar_entry(self, model: ParsedModel):
        """CalendarEntry -> Meeting node."""
        subject = model.get_field("Subject")
        details = model.get_field("Details")
        location = model.get_field("Location")
        start_date = model.get_field("StartDate")
        end_date = model.get_field("EndDate")

        if not subject:
            return

        key = f"cal-{model.model_id[:12]}"

        props = self._base_props(model, key, subject)
        props.update({
            "details": details,
            "location_text": location,
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
        timestamp = model.get_field("TimeStamp")

        if not ssid and not bssid:
            return

        key = f"wifi-{model.model_id[:12]}"

        props = self._base_props(model, key, ssid or bssid or "Unknown WiFi")
        props.update({
            "ssid": ssid,
            "bssid": bssid,
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
        timestamp = model.get_field("TimeStamp") or model.get_field("LastConnected")

        if not name and not mac:
            return

        key = f"dev-{model.model_id[:12]}"

        props = self._base_props(model, key, name or mac or "Unknown Device")
        props.update({
            "device_type": device_type,
            "mac_address": mac,
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
        """Password -> Credential node (metadata only, NOT the actual secret)."""
        label = model.get_field("Label")
        cred_type = model.get_field("Type")
        account = model.get_field("Account")

        key = f"cred-{model.model_id[:12]}"

        props = self._base_props(model, key, label or f"Credential ({cred_type or 'Unknown'})")
        props.update({
            "label": label,
            "credential_type": cred_type,
            "account_ref": account,
            "is_sensitive": True,
            # NOTE: actual password/token data is intentionally NOT stored
        })
        props = {k: v for k, v in props.items() if v is not None}

        self._create_node("Credential", key, props)
        self.credentials_created += 1

    def _write_web_bookmark(self, model: ParsedModel):
        """WebBookmark -> WebBookmark node."""
        url = model.get_field("Url")
        title = model.get_field("Title")
        timestamp = model.get_field("TimeStamp")
        source = model.get_field("Source")

        if not url and not title:
            return

        key = f"bkmk-{model.model_id[:12]}"

        props = self._base_props(model, key, title or url[:80] if url else "Bookmark")
        props.update({
            "url": url,
            "source_app": source,
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
        radius_raw = model.get_field("Radius") or model.get_field("Precision")
        try:
            radius = float(radius_raw) if radius_raw else None
        except (TypeError, ValueError):
            pass

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
            "radius": radius,
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
        Cellebrite emits these under several model type names depending on extraction.
        Stores them under a single DeviceEvent label with an event_type discriminator.
        """
        timestamp = model.get_field("TimeStamp")
        source = model.get_field("Source")
        state = model.get_field("State") or model.get_field("Type") or model.get_field("Action")
        reason = model.get_field("Reason") or model.get_field("Details")
        battery = model.get_field("Battery") or model.get_field("BatteryLevel")

        # Infer event_type from model type + state
        mt = (model.model_type or "").lower()
        if "power" in mt:
            event_type = "power"
        elif "user" in mt or "lock" in mt or "unlock" in mt:
            event_type = "unlock" if state and "unlock" in state.lower() else \
                         "lock"   if state and "lock"   in state.lower() else \
                         "user"
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
            "total_nodes": self.nodes_total,
            "total_relationships": self.relationships_total,
            "phone_owner": self._phone_owner_key,
        }
