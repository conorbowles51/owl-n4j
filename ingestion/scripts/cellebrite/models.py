"""
Data models for Cellebrite UFED phone report ingestion.

Intermediate Python dataclasses that sit between the raw XML parsing
and the Neo4j graph writing. Designed for memory efficiency — models
are populated incrementally as the streaming parser processes the XML.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class CaseInfo:
    """Case metadata from <caseInformation>."""
    examiner: Optional[str] = None
    case_number: Optional[str] = None
    case_name: Optional[str] = None
    evidence_number: Optional[str] = None
    department: Optional[str] = None
    organization: Optional[str] = None
    investigator: Optional[str] = None
    crime_type: Optional[str] = None
    location: Optional[str] = None


@dataclass
class DeviceInfo:
    """Device metadata from <metadata section="Device Info">."""
    android_id: Optional[str] = None
    imei: Optional[str] = None
    imsi: Optional[str] = None
    iccid: List[str] = field(default_factory=list)
    msisdn: List[str] = field(default_factory=list)  # Phone numbers
    bluetooth_name: Optional[str] = None
    bluetooth_mac: Optional[str] = None
    mac_address: Optional[str] = None
    os_type: Optional[str] = None
    carrier: Optional[str] = None
    factory_number: Optional[str] = None
    phone_activation: Optional[str] = None
    device_model: Optional[str] = None
    # Canonical brand from DeviceInfoSelectedManufacturer / Manufacturer.
    # Composes with device_model into the displayed label.
    manufacturer: Optional[str] = None
    # Every plausible device-name source we saw in the report, in priority
    # order. Each entry is {source, value, extraction_id}. Lets the
    # frontend offer the investigator a switcher between detected names.
    device_name_candidates: List[Dict[str, str]] = field(default_factory=list)
    # IMEIs seen on extractions OTHER than the device extraction (e.g.
    # accessories, paired devices). Kept for diagnostics — not the
    # canonical IMEI of the phone.
    accessory_imeis: List[str] = field(default_factory=list)


@dataclass
class ExtractionInfo:
    """Extraction source from <sourceExtractions>."""
    extraction_id: str = ""
    name: str = ""
    extraction_type: str = ""  # Legacy, Logical, Physical
    device_name: str = ""
    full_name: str = ""
    index: str = ""


@dataclass
class TaggedFile:
    """File reference from <taggedFiles>."""
    file_id: str = ""
    local_path: str = ""  # Relative path within report folder (Windows backslash format)
    original_path: str = ""  # Original device path
    md5: Optional[str] = None
    sha256: Optional[str] = None
    size: Optional[int] = None
    deleted: str = "Intact"
    extraction_id: str = ""
    tags: Optional[str] = None  # e.g., "Image", "Audio", "Archives"
    # EXIF / Cellebrite-parsed file timestamps. Cellebrite emits these
    # as metadata <item> children of <file> when present (typically for
    # images / videos / audio). Stored on the evidence record so the
    # Files tab can filter by date taken / has-geotag without re-
    # parsing the original bytes.
    creation_time: Optional[str] = None  # ISO 8601 — when the file was created on the device
    modify_time: Optional[str] = None    # ISO 8601 — last modification
    access_time: Optional[str] = None    # ISO 8601 — last access
    capture_time: Optional[str] = None   # ISO 8601 — EXIF DateTimeOriginal (camera capture)
    latitude: Optional[float] = None     # Decimal degrees
    longitude: Optional[float] = None    # Decimal degrees
    gps_altitude: Optional[float] = None # Meters (negative below sea level)
    # Camera identity from EXIF — surfaces "what device took this photo".
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    # Image dimensions in pixels.
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    # EXIF Orientation tag — needed to render thumbnails the right way up.
    orientation: Optional[str] = None
    # Software field from EXIF (camera firmware version or editing app).
    exif_software: Optional[str] = None


@dataclass
class Party:
    """Represents a communication participant."""
    identifier: Optional[str] = None
    role: Optional[str] = None  # From, To, CC, BCC
    name: Optional[str] = None
    is_phone_owner: bool = False


@dataclass
class ParsedModel:
    """
    Generic parsed Cellebrite model from <decodedData>.

    Each model has typed fields, optional nested models, and
    jump targets (UUID references to other models/files).
    """
    model_type: str = ""
    model_id: str = ""
    deleted_state: str = "Intact"
    decoding_confidence: str = ""
    extraction_id: str = ""
    source_index: str = ""

    # Scalar fields: name -> value (string, parsed later by writer)
    fields: Dict[str, Any] = field(default_factory=dict)

    # Nested single models: field_name -> ParsedModel
    model_fields: Dict[str, 'ParsedModel'] = field(default_factory=dict)

    # Nested multi-models: field_name -> list of ParsedModel
    multi_model_fields: Dict[str, List['ParsedModel']] = field(default_factory=dict)

    # Jump target UUIDs
    jump_targets: List[str] = field(default_factory=list)

    # Whether each jump target is a model (True) or file (False)
    jump_target_is_model: List[bool] = field(default_factory=list)

    def get_field(self, name: str, default: Any = None) -> Any:
        """Get a field value by name."""
        return self.fields.get(name, default)

    def get_parties(self, field_name: str = "Parties") -> List[Party]:
        """Extract Party objects from a multiModelField."""
        parties = []
        for pm in self.multi_model_fields.get(field_name, []):
            party = Party(
                identifier=pm.get_field("Identifier"),
                role=pm.get_field("Role"),
                name=pm.get_field("Name"),
                is_phone_owner=pm.get_field("IsPhoneOwner", "").lower() == "true"
                if pm.get_field("IsPhoneOwner") else False,
            )
            parties.append(party)
        return parties

    def get_party(self, field_name: str = "From") -> Optional[Party]:
        """Extract a single Party from a modelField."""
        pm = self.model_fields.get(field_name)
        if pm is None:
            return None
        return Party(
            identifier=pm.get_field("Identifier"),
            role=pm.get_field("Role"),
            name=pm.get_field("Name"),
            is_phone_owner=pm.get_field("IsPhoneOwner", "").lower() == "true"
            if pm.get_field("IsPhoneOwner") else False,
        )


@dataclass
class CellebriteReport:
    """Top-level report container aggregating all parsed data."""
    project_id: str = ""
    report_name: str = ""
    report_version: str = ""
    extraction_type: str = ""
    node_count: int = 0
    model_count: int = 0
    case_info: CaseInfo = field(default_factory=CaseInfo)
    device_info: DeviceInfo = field(default_factory=DeviceInfo)
    extractions: List[ExtractionInfo] = field(default_factory=list)
    # file_index is built separately by file_linker, not stored here
