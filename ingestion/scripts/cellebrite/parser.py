"""
Streaming XML parser for Cellebrite UFED phone extraction reports.

Uses xml.etree.ElementTree.iterparse to process 100+ MB XML files
in a single pass with constant memory. Each <model> element is fully
accumulated, converted to a ParsedModel dataclass, and then cleared
from memory.

The parser yields ParsedModel instances in batches for efficient
downstream processing.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Callable, Iterator, List, Dict

from .models import (
    CellebriteReport,
    CaseInfo,
    DeviceInfo,
    ExtractionInfo,
    TaggedFile,
    ParsedModel,
)

NS = "http://pa.cellebrite.com/report/2.0"
NS_BRACKET = f"{{{NS}}}"

# Model types we care about for graph ingestion
SUPPORTED_MODEL_TYPES = {
    # Core entities (Phase 1)
    "Contact",
    "Call",
    "Chat",
    "InstantMessage",
    "Email",
    "Location",
    "UserAccount",
    "SearchedItem",
    "VisitedPage",
    "CalendarEntry",
    "WirelessNetwork",
    "RecognizedDevice",
    "Password",
    "WebBookmark",
    "Autofill",
    "SIMData",
    "User",
    # Phase 4 — device / radio / app events
    "PoweringEvent",
    "DeviceEvent",
    "UserEvent",
    "ScreenEvent",
    "ApplicationUsage",
    "AppUsage",
    "CellTower",
    "Cell",
    "CellLocation",
    # Phase 5 — media / helper models (dispatched to ignore or inline handlers)
    "Attachment",
    "ContactPhoto",
    "ProfilePicture",
    "KeyValueModel",
    "Party",
}

# Model types we intentionally skip (too granular / low investigative value)
SKIPPED_MODEL_TYPES = {
    "NetworkUsage",
}


def _strip_ns(tag: str) -> str:
    """Strip the Cellebrite namespace from an XML tag."""
    if tag.startswith(NS_BRACKET):
        return tag[len(NS_BRACKET):]
    return tag


def _ns(tag: str) -> str:
    """Add the Cellebrite namespace to a tag name."""
    return f"{NS_BRACKET}{tag}"


class CellebriteXMLParser:
    """
    Streaming parser for Cellebrite UFED XML reports.

    Usage:
        parser = CellebriteXMLParser(xml_path, log_callback)
        report = parser.parse_header()  # Parse metadata
        tagged_files = parser.parse_tagged_files()  # Parse file index
        for batch in parser.stream_models(batch_size=200):
            process_batch(batch)
    """

    def __init__(
        self,
        xml_path: Path,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.xml_path = xml_path
        self.log_callback = log_callback
        self._total_models = 0
        self._parsed_models = 0

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    # ------------------------------------------------------------------
    # Phase 1: Parse header, case info, device info, extractions
    # ------------------------------------------------------------------

    def parse_header(self) -> CellebriteReport:
        """
        Parse the report header in a single pass through the first ~5% of the XML.

        Extracts: project attributes, sourceExtractions, caseInformation,
        and metadata (device info). Stops at <taggedFiles> to avoid
        parsing the bulk of the file.

        Identity-bearing items (IMEI, manufacturer, device model) are
        attributed to the *device extraction* — the one whose type is
        Physical / FileSystem / Legacy / AdvancedLogical. SIM-card and
        Report/Logical extractions are not treated as the device, so a
        SIM's "Model = SIM" doesn't get mistaken for the phone's model
        and an accessory's IMEI doesn't overwrite the device's IMEI.
        """
        report = CellebriteReport()

        # Manufacturer / device-name candidates collected during the pass.
        # Lower priority numbers win. We pick the best at the end.
        # Each entry: (priority, source, value, extraction_id)
        manufacturer_candidates: List[tuple] = []
        device_model_candidates: List[tuple] = []

        for event, elem in ET.iterparse(str(self.xml_path), events=["start", "end"]):
            tag = _strip_ns(elem.tag)

            # --- Project root attributes ---
            if event == "start" and tag == "project":
                report.project_id = elem.get("id", "")
                report.report_name = elem.get("name", "")
                report.report_version = elem.get("reportVersion", "")
                report.extraction_type = elem.get("extractionType", "")
                report.node_count = int(elem.get("NodeCount", "0"))
                report.model_count = int(elem.get("ModelCount", "0"))
                self._total_models = report.model_count
                self._log(
                    f"Report: {report.report_name}, "
                    f"version {report.report_version}, "
                    f"{report.node_count} nodes, "
                    f"{report.model_count} models"
                )

            # --- Source Extractions ---
            elif event == "end" and tag == "extractionInfo":
                ext = ExtractionInfo(
                    extraction_id=elem.get("id", ""),
                    name=elem.get("name", ""),
                    extraction_type=elem.get("type", ""),
                    device_name=elem.get("deviceName", ""),
                    full_name=elem.get("fullName", ""),
                    index=elem.get("index", ""),
                )
                report.extractions.append(ext)
                elem.clear()

            # --- Case Information ---
            elif event == "end" and tag == "field":
                parent_tag = ""
                # Check if we're inside caseInformation by field attributes
                field_type = elem.get("fieldType", "")
                if field_type:
                    text = (elem.text or "").strip()
                    mapping = {
                        "ExaminerName": "examiner",
                        "Location": "location",
                        "CaseNumber": "case_number",
                        "CaseName": "case_name",
                        "EvidenceNumber": "evidence_number",
                        "Department": "department",
                        "Organization": "organization",
                        "Investigator": "investigator",
                        "CrimeType": "crime_type",
                    }
                    attr = mapping.get(field_type)
                    if attr and text:
                        setattr(report.case_info, attr, text)
                    elem.clear()

            # --- Metadata / Device Info ---
            elif event == "end" and tag == "item":
                name = elem.get("name", "")
                source_extraction = elem.get("sourceExtraction", "")
                is_device = self._is_device_extraction(report, source_extraction)
                # CDATA content
                text = (elem.text or "").strip()
                if not text:
                    elem.clear()
                    continue

                # IMEI: only the device extraction's IMEI is canonical.
                # Other IMEIs (accessories, paired devices) are kept on
                # accessory_imeis for diagnostics.
                if name == "IMEI":
                    if is_device and not report.device_info.imei:
                        report.device_info.imei = text
                    elif not is_device and text not in report.device_info.accessory_imeis:
                        report.device_info.accessory_imeis.append(text)
                elif name == "IMSI" and is_device and not report.device_info.imsi:
                    report.device_info.imsi = text
                elif name == "ICCID":
                    if text not in report.device_info.iccid:
                        report.device_info.iccid.append(text)
                elif name == "MSISDN":
                    if text not in report.device_info.msisdn:
                        report.device_info.msisdn.append(text)
                elif name == "DeviceInfoAndroidID" and not report.device_info.android_id:
                    report.device_info.android_id = text
                # Manufacturer candidates — lower priority number wins.
                # SIM-card values ("SIM Card") are excluded because they
                # belong to a SIM extraction, not the device.
                elif name == "DeviceInfoSelectedManufacturer" and is_device:
                    manufacturer_candidates.append((1, "selected_manufacturer", text, source_extraction))
                elif name == "Manufacturer" and is_device and text.lower() != "sim card":
                    manufacturer_candidates.append((2, "manufacturer", text, source_extraction))
                elif name == "DeviceInfoBrand" and is_device:
                    manufacturer_candidates.append((3, "brand", text, source_extraction))
                elif name == "Vendor" and is_device and text.lower() != "sim card":
                    manufacturer_candidates.append((4, "vendor", text, source_extraction))
                # Device-model candidates — lower priority number wins.
                # The "SIM" literal is excluded because it appears on SIM
                # extractions and is not the phone's model.
                elif name == "DeviceInfoSelectedDeviceName" and is_device and text.upper() != "SIM":
                    device_model_candidates.append((1, "selected_device_name", text, source_extraction))
                elif name == "DeviceInfoDeviceModel" and is_device:
                    device_model_candidates.append((2, "device_model", text, source_extraction))
                elif name == "Model" and is_device and text.upper() != "SIM":
                    device_model_candidates.append((3, "model", text, source_extraction))
                elif name == "DeviceInfoBluetoothDeviceName":
                    report.device_info.bluetooth_name = text
                    # Bluetooth name is the lowest-priority device-name
                    # candidate; kept so we never regress on reports that
                    # ONLY have Bluetooth metadata.
                    device_model_candidates.append((9, "bluetooth_name", text, source_extraction))
                elif name == "DeviceInfoBluetoothDeviceAddress":
                    report.device_info.bluetooth_mac = text
                elif name == "Mac Address":
                    report.device_info.mac_address = text
                elif name == "DeviceInfoOSType":
                    report.device_info.os_type = text
                elif name == "DeviceInfoCarrierName" and not report.device_info.carrier:
                    report.device_info.carrier = text
                elif name == "Factory number":
                    report.device_info.factory_number = text
                elif name == "Phone Activation Time":
                    report.device_info.phone_activation = text
                elif name == "Bluetooth MAC Address" and not report.device_info.bluetooth_mac:
                    report.device_info.bluetooth_mac = text

                elem.clear()

            # --- Stop at taggedFiles (we'll parse that separately) ---
            elif event == "start" and tag == "taggedFiles":
                break

            # Memory management: clear completed top-level sections
            elif event == "end" and tag in (
                "sourceExtractions",
                "caseInformation",
                "metadata",
                "images",
                "HashSetsInfo",
                "MalwareScanner",
            ):
                elem.clear()

        # Resolve manufacturer + device model from collected candidates.
        # Lowest priority number wins; ties broken by insertion order
        # (which equals XML order, so the first occurrence wins).
        manufacturer_candidates.sort(key=lambda t: t[0])
        device_model_candidates.sort(key=lambda t: t[0])

        if manufacturer_candidates:
            report.device_info.manufacturer = manufacturer_candidates[0][2]
        if device_model_candidates:
            report.device_info.device_model = device_model_candidates[0][2]

        # Persist every candidate (manufacturer + model) so the override
        # popover can offer the investigator a switcher.
        for _, source, value, extraction_id in device_model_candidates:
            report.device_info.device_name_candidates.append({
                "source": source,
                "value": value,
                "extraction_id": extraction_id,
            })
        for _, source, value, extraction_id in manufacturer_candidates:
            report.device_info.device_name_candidates.append({
                "source": source,
                "value": value,
                "extraction_id": extraction_id,
            })

        self._log(
            f"Case: {report.case_info.case_number} - "
            f"{report.case_info.case_name} ({report.case_info.crime_type})"
        )
        self._log(
            f"Device: "
            f"{(report.device_info.manufacturer + ' ') if report.device_info.manufacturer else ''}"
            f"{report.device_info.device_model or 'Unknown'}, "
            f"IMEI: {report.device_info.imei or 'N/A'}, "
            f"Phone(s): {', '.join(report.device_info.msisdn) or 'N/A'}"
        )

        return report

    # ------------------------------------------------------------------
    # Extraction classification helpers
    # ------------------------------------------------------------------

    # Cellebrite extraction "type" values that represent the actual
    # device (vs SIM cards, attached reports, etc.). Anything not in
    # this set — SIM, Logical, Report — is treated as non-device, so
    # its IMEIs / model strings can't be mistaken for the phone's.
    _DEVICE_EXTRACTION_TYPES = {
        "Physical",
        "FileSystem",
        "AdvancedLogical",
        "Legacy",
        "FullFileSystem",
    }

    def _is_device_extraction(self, report: CellebriteReport, extraction_id: str) -> bool:
        """
        Return True if `extraction_id` belongs to the device (phone)
        rather than a SIM card or attached logical report.

        Treats a missing or empty extraction_id as the device extraction
        ONLY when the report has no explicit extractions to disambiguate;
        otherwise, missing source means we can't safely attribute the
        item to the device.
        """
        if not report.extractions:
            return True
        if not extraction_id:
            return False
        for ext in report.extractions:
            if ext.extraction_id == extraction_id:
                return ext.extraction_type in self._DEVICE_EXTRACTION_TYPES
        # Unknown extraction id — be conservative and skip.
        return False

    # ------------------------------------------------------------------
    # Phase 2: Parse tagged files (file index)
    # ------------------------------------------------------------------

    def parse_tagged_files(self) -> List[TaggedFile]:
        """
        Parse all <file> elements from <taggedFiles> section.

        Returns a list of TaggedFile objects mapping UUIDs to local paths.
        """
        tagged_files: List[TaggedFile] = []
        in_tagged_files = False

        for event, elem in ET.iterparse(str(self.xml_path), events=["start", "end"]):
            tag = _strip_ns(elem.tag)

            if event == "start" and tag == "taggedFiles":
                in_tagged_files = True
                continue

            if event == "end" and tag == "taggedFiles":
                elem.clear()
                break

            if not in_tagged_files:
                if event == "end":
                    elem.clear()
                continue

            if event == "end" and tag == "file":
                tf = TaggedFile(
                    file_id=elem.get("id", ""),
                    original_path=elem.get("path", ""),
                    size=int(elem.get("size", "0")) if elem.get("size") else None,
                    deleted=elem.get("deleted", "Intact"),
                    extraction_id=elem.get("extractionId", ""),
                )

                # Extract Local Path, hashes, tags from nested metadata
                for meta_section in elem.findall(_ns("metadata")):
                    for item in meta_section.findall(_ns("item")):
                        item_name = item.get("name", "")
                        item_text = (item.text or "").strip()
                        if item_name == "Local Path":
                            tf.local_path = item_text
                        elif item_name == "MD5":
                            tf.md5 = item_text if item_text else None
                        elif item_name == "SHA256":
                            tf.sha256 = item_text if item_text else None
                        elif item_name == "Tags":
                            tf.tags = item_text if item_text else None

                if tf.local_path:  # Only include files with a local path
                    tagged_files.append(tf)

                elem.clear()

        self._log(f"Parsed {len(tagged_files)} tagged files")
        return tagged_files

    # ------------------------------------------------------------------
    # Phase 3: Stream decoded data models
    # ------------------------------------------------------------------

    def stream_models(self, batch_size: int = 200) -> Iterator[List[ParsedModel]]:
        """
        Stream parsed models from <decodedData> in batches.

        Yields lists of ParsedModel (up to batch_size per yield).
        Skips unsupported/low-value model types.
        Clears each element from memory after parsing.

        Uses model nesting depth to distinguish top-level models
        (direct children of <modelType>) from nested models inside
        <modelField> / <multiModelField>, which must be preserved
        for recursive parsing by _parse_model_element.
        """
        batch: List[ParsedModel] = []
        in_decoded_data = False
        current_model_type_section = None
        models_parsed = 0
        model_depth = 0  # Track nesting depth of <model> elements

        for event, elem in ET.iterparse(str(self.xml_path), events=["start", "end"]):
            tag = _strip_ns(elem.tag)

            # Track when we enter decodedData
            if event == "start" and tag == "decodedData":
                in_decoded_data = True
                continue

            if event == "end" and tag == "decodedData":
                in_decoded_data = False
                elem.clear()
                continue

            if not in_decoded_data:
                if event == "end":
                    elem.clear()
                continue

            # Track which model type section we're in
            if event == "start" and tag == "modelType":
                current_model_type_section = elem.get("type", "")
                continue

            if event == "end" and tag == "modelType":
                current_model_type_section = None
                elem.clear()
                continue

            # Track model nesting depth
            if event == "start" and tag == "model":
                model_depth += 1
                continue

            # Only process top-level models (depth == 1).
            # Nested models (depth > 1) inside modelField/multiModelField
            # are left intact for _parse_model_element to handle recursively.
            if event == "end" and tag == "model":
                model_depth -= 1

                if model_depth > 0:
                    # Nested model — leave intact for parent's recursive parsing
                    continue

                model_type = elem.get("type", "")

                # Only process top-level models in supported types
                if model_type in SKIPPED_MODEL_TYPES:
                    elem.clear()
                    continue

                if model_type in SUPPORTED_MODEL_TYPES:
                    parsed = self._parse_model_element(elem)
                    if parsed:
                        batch.append(parsed)
                        models_parsed += 1

                        if models_parsed % 500 == 0:
                            self._log(
                                f"Parsed {models_parsed}/{self._total_models} models "
                                f"({100 * models_parsed / max(self._total_models, 1):.1f}%)"
                            )

                        if len(batch) >= batch_size:
                            yield batch
                            batch = []

                elem.clear()

        # Yield remaining batch
        if batch:
            yield batch

        self._parsed_models = models_parsed
        self._log(f"Completed: {models_parsed} models parsed")

    def _parse_model_element(self, elem) -> Optional[ParsedModel]:
        """
        Parse a single <model> element into a ParsedModel dataclass.

        Handles fields, modelField, multiModelField, and jumptargets.
        """
        model = ParsedModel(
            model_type=elem.get("type", ""),
            model_id=elem.get("id", ""),
            deleted_state=elem.get("deleted_state", "Intact"),
            decoding_confidence=elem.get("decoding_confidence", ""),
            extraction_id=elem.get("extractionId", ""),
            source_index=elem.get("source_index", ""),
        )

        for child in elem:
            child_tag = _strip_ns(child.tag)

            if child_tag == "field":
                name = child.get("name", "")
                value_elem = child.find(_ns("value"))
                if value_elem is not None and value_elem.text:
                    model.fields[name] = value_elem.text.strip()
                # If <empty/>, field stays absent (None via get_field)

            elif child_tag == "modelField":
                name = child.get("name", "")
                inner_model = child.find(_ns("model"))
                if inner_model is not None:
                    parsed_inner = self._parse_model_element(inner_model)
                    if parsed_inner:
                        model.model_fields[name] = parsed_inner

            elif child_tag == "multiModelField":
                name = child.get("name", "")
                inner_models = []
                for inner in child.findall(_ns("model")):
                    parsed_inner = self._parse_model_element(inner)
                    if parsed_inner:
                        inner_models.append(parsed_inner)
                model.multi_model_fields[name] = inner_models

            elif child_tag == "jumptargets":
                for target_id_elem in child.findall(f".//{_ns('targetid')}"):
                    tid = (target_id_elem.text or "").strip()
                    if tid:
                        is_model = target_id_elem.get("ismodel", "false").lower() == "true"
                        model.jump_targets.append(tid)
                        model.jump_target_is_model.append(is_model)

        return model

    @property
    def total_models(self) -> int:
        return self._total_models

    @property
    def parsed_models(self) -> int:
        return self._parsed_models
