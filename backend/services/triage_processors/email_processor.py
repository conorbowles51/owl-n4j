"""
Email Processor

Parses email files to extract sender, recipient, subject, date, body:
- EML files (RFC 822)
- MSG files (via extract_msg if available)
"""

from __future__ import annotations

import email
import email.policy
import logging
from typing import Any, Dict, List

from services.triage_processors.base_processor import BaseTriageProcessor, ProcessingResult

logger = logging.getLogger(__name__)


class EmailProcessor(BaseTriageProcessor):
    name = "email_parser"
    display_name = "Email Parser"
    description = "Extract sender, recipient, subject, date, and body from email files (EML, MSG)"
    input_types = ["emails"]
    output_types = ["email_metadata", "email_body"]
    requires_llm = False
    config_schema = {
        "extract_body": {"type": "boolean", "default": True, "description": "Extract email body text"},
        "max_body_chars": {"type": "integer", "default": 50000, "description": "Max body characters"},
    }

    def process_file(
        self,
        file_path: str,
        file_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> List[ProcessingResult]:
        ext = file_info.get("extension", "").lower()
        extract_body = config.get("extract_body", True)
        max_body = config.get("max_body_chars", 50000)

        try:
            if ext == ".eml":
                return self._parse_eml(file_path, extract_body, max_body)
            elif ext == ".msg":
                return self._parse_msg(file_path, extract_body, max_body)
            else:
                # Try EML format as fallback
                return self._parse_eml(file_path, extract_body, max_body)
        except Exception as e:
            return [ProcessingResult(
                source_path=file_path,
                artifact_type="email_metadata",
                error=str(e),
            )]

    def _parse_eml(self, path: str, extract_body: bool, max_body: int) -> List[ProcessingResult]:
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=email.policy.default)

        metadata = {
            "from": str(msg.get("From", "")),
            "to": str(msg.get("To", "")),
            "cc": str(msg.get("Cc", "")),
            "subject": str(msg.get("Subject", "")),
            "date": str(msg.get("Date", "")),
            "message_id": str(msg.get("Message-ID", "")),
            "has_attachments": any(
                part.get_content_disposition() == "attachment"
                for part in msg.walk()
            ),
        }

        # Count attachments
        attachments = []
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                attachments.append({
                    "filename": part.get_filename() or "unnamed",
                    "content_type": part.get_content_type(),
                })
        metadata["attachments"] = attachments
        metadata["attachment_count"] = len(attachments)

        results = [ProcessingResult(
            source_path=path,
            artifact_type="email_metadata",
            content=f"From: {metadata['from']} | To: {metadata['to']} | Subject: {metadata['subject']}",
            metadata=metadata,
        )]

        # Extract body
        if extract_body:
            body = self._get_body(msg)
            if body:
                body = body[:max_body]
                results.append(ProcessingResult(
                    source_path=path,
                    artifact_type="email_body",
                    content=body,
                    metadata={"char_count": len(body)},
                ))

        return results

    def _get_body(self, msg) -> str:
        """Extract text body from email message."""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    try:
                        return part.get_content()
                    except Exception:
                        pass
                elif ct == "text/html":
                    try:
                        return part.get_content()
                    except Exception:
                        pass
        else:
            try:
                return msg.get_content()
            except Exception:
                pass
        return ""

    def _parse_msg(self, path: str, extract_body: bool, max_body: int) -> List[ProcessingResult]:
        try:
            import extract_msg
        except ImportError:
            return [ProcessingResult(
                source_path=path,
                artifact_type="email_metadata",
                error="extract_msg not installed (required for .msg files)",
            )]

        msg = extract_msg.Message(path)
        metadata = {
            "from": msg.sender or "",
            "to": msg.to or "",
            "cc": msg.cc or "",
            "subject": msg.subject or "",
            "date": str(msg.date) if msg.date else "",
            "has_attachments": len(msg.attachments) > 0,
            "attachment_count": len(msg.attachments),
            "attachments": [
                {"filename": a.longFilename or a.shortFilename or "unnamed"}
                for a in msg.attachments
            ],
        }

        results = [ProcessingResult(
            source_path=path,
            artifact_type="email_metadata",
            content=f"From: {metadata['from']} | To: {metadata['to']} | Subject: {metadata['subject']}",
            metadata=metadata,
        )]

        if extract_body and msg.body:
            body = msg.body[:max_body]
            results.append(ProcessingResult(
                source_path=path,
                artifact_type="email_body",
                content=body,
                metadata={"char_count": len(body)},
            ))

        msg.close()
        return results
