"""
Triage Advisor

LLM-powered advisory agent that analyzes triage case context
and provides investigation guidance, suggested next steps,
and answers investigator questions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from services.triage.triage_storage import triage_storage

logger = logging.getLogger(__name__)


class TriageAdvisor:
    """Advisory agent for triage cases."""

    def advise(
        self,
        triage_case_id: str,
        question: str,
        model_provider: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Answer an investigator's question using triage case context.

        Args:
            triage_case_id: Case ID
            question: The investigator's question
            model_provider: Optional LLM provider override
            model_id: Optional model ID override

        Returns:
            Dict with 'answer' and 'suggestions' keys
        """
        from services.llm_service import llm_service

        case = triage_storage.get_case(triage_case_id)
        if not case:
            return {"answer": "Triage case not found.", "suggestions": []}

        # Build context from case data
        context = self._build_context(case)

        prompt = f"""You are a digital forensics investigation advisor analyzing a triage case.

## Case Context
{context}

## Investigator's Question
{question}

## Instructions
Provide a clear, actionable answer based on the case data above. Include:
1. Direct answer to the question
2. Any relevant observations from the data
3. Suggested next investigation steps

Return valid JSON:
{{
  "answer": "Your detailed answer here",
  "suggestions": [
    {{"action": "short description", "detail": "explanation", "priority": "high|medium|low"}}
  ]
}}"""

        # Optionally override model
        original_config = None
        if model_provider and model_id:
            original_config = llm_service.get_current_config()
            llm_service.set_config(model_provider, model_id)

        try:
            llm_service.set_cost_tracking_context(
                job_type="ingestion",
                description="triage_advisor_chat",
            )

            response = llm_service.call(
                prompt=prompt,
                temperature=0.3,
                json_mode=True,
                timeout=120,
            )

            try:
                result = llm_service.parse_json_response(response)
                return {
                    "answer": result.get("answer", response),
                    "suggestions": result.get("suggestions", []),
                }
            except (json.JSONDecodeError, ValueError):
                return {"answer": response, "suggestions": []}

        except Exception as e:
            logger.exception(f"Advisor chat failed for case {triage_case_id}")
            return {"answer": f"Error: {e}", "suggestions": []}
        finally:
            llm_service.clear_cost_tracking_context()
            if original_config:
                llm_service.set_config(*original_config)

    def suggest_next_steps(self, triage_case_id: str) -> List[Dict[str, Any]]:
        """
        Auto-suggest next investigation steps based on current case state.
        Uses heuristics first, LLM only if needed.
        """
        case = triage_storage.get_case(triage_case_id)
        if not case:
            return []

        suggestions = []
        stages = case.get("stages", [])
        stage_status = {s["type"]: s.get("status") for s in stages}
        scan_stats = case.get("scan_stats", {})
        profile = case.get("profile")

        # Check stage completion and suggest next steps
        if stage_status.get("scan") == "completed" and stage_status.get("classify") == "pending":
            suggestions.append({
                "action": "Run Classification",
                "detail": f"Scan found {scan_stats.get('total_files', 0):,} files. "
                         f"Run classification to identify known-good files (NSRL) and reduce noise.",
                "priority": "high",
                "stage_type": "classify",
            })

        if stage_status.get("classify") == "completed" and stage_status.get("profile") == "pending":
            suggestions.append({
                "action": "Generate Profile",
                "detail": "Classification complete. Generate a profile to see activity timeline, "
                         "user accounts, and high-value artifacts.",
                "priority": "high",
                "stage_type": "profile",
            })

        # After profile, suggest processing based on artifacts found
        if profile:
            artifacts = profile.get("high_value_artifacts", [])
            artifact_types = {a.get("type") for a in artifacts}

            if "browser_history" in artifact_types or "browser_db" in artifact_types:
                has_browser_stage = any(
                    s.get("config", {}).get("processor_name") == "browser_parser"
                    for s in stages if s.get("type") == "custom"
                )
                if not has_browser_stage:
                    count = sum(1 for a in artifacts if a.get("type") in ("browser_history", "browser_db"))
                    suggestions.append({
                        "action": "Parse Browser Databases",
                        "detail": f"Found {count} browser database(s). "
                                 f"Extract browsing history, downloads, and bookmarks.",
                        "priority": "high",
                        "processor": "browser_parser",
                    })

            if "email_store" in artifact_types:
                has_email_stage = any(
                    s.get("config", {}).get("processor_name") == "email_parser"
                    for s in stages if s.get("type") == "custom"
                )
                if not has_email_stage:
                    count = sum(1 for a in artifacts if a.get("type") == "email_store")
                    suggestions.append({
                        "action": "Parse Email Stores",
                        "detail": f"Found {count} email store(s). "
                                 f"Extract sender, recipient, subject, and body.",
                        "priority": "high",
                        "processor": "email_parser",
                    })

            if "encrypted_container" in artifact_types:
                count = sum(1 for a in artifacts if a.get("type") == "encrypted_container")
                suggestions.append({
                    "action": "Review Encrypted Files",
                    "detail": f"Found {count} encrypted container(s). "
                             f"These may require passwords or keys to access.",
                    "priority": "medium",
                })

            # Suggest document analysis for user files
            doc_count = profile.get("by_category", {}).get("documents", {}).get("count", 0)
            if doc_count > 0:
                has_text_stage = any(
                    s.get("config", {}).get("processor_name") == "text_extractor"
                    for s in stages if s.get("type") == "custom"
                )
                if not has_text_stage:
                    suggestions.append({
                        "action": "Extract Document Text",
                        "detail": f"Found {doc_count:,} document files. "
                                 f"Extract text for search and LLM analysis.",
                        "priority": "medium",
                        "processor": "text_extractor",
                    })

            # Suggest EXIF extraction for images
            img_count = profile.get("by_category", {}).get("images", {}).get("count", 0)
            if img_count > 0:
                has_exif_stage = any(
                    s.get("config", {}).get("processor_name") == "exif_extractor"
                    for s in stages if s.get("type") == "custom"
                )
                if not has_exif_stage:
                    suggestions.append({
                        "action": "Extract Image EXIF Data",
                        "detail": f"Found {img_count:,} image files. "
                                 f"Extract GPS coordinates, camera info, and timestamps.",
                        "priority": "medium",
                        "processor": "exif_extractor",
                    })

            # Extension mismatch alert
            mismatches = profile.get("extension_mismatches", [])
            if mismatches:
                suggestions.append({
                    "action": "Review Extension Mismatches",
                    "detail": f"Found {len(mismatches)} files where the file extension "
                             f"doesn't match the detected file type. This could indicate "
                             f"deliberate file concealment.",
                    "priority": "high",
                })

        return suggestions

    def _build_context(self, case: Dict) -> str:
        """Build a text context summary from case data."""
        parts = []

        parts.append(f"Case: {case.get('name', 'Unknown')}")
        parts.append(f"Source: {case.get('source_path', 'Unknown')}")
        parts.append(f"Status: {case.get('status', 'Unknown')}")

        # Scan stats
        stats = case.get("scan_stats", {})
        if stats.get("total_files"):
            parts.append(f"\nScan Results:")
            parts.append(f"  Total files: {stats['total_files']:,}")
            parts.append(f"  Total size: {stats.get('total_size', 0):,} bytes")
            parts.append(f"  OS detected: {stats.get('os_detected', 'Unknown')}")
            parts.append(f"  Unique hashes: {stats.get('unique_hashes', 0):,}")
            parts.append(f"  Extension mismatches: {stats.get('extension_mismatches', 0):,}")

            by_cat = stats.get("by_category", {})
            if by_cat:
                parts.append(f"  Categories: {', '.join(f'{k}: {v:,}' for k, v in sorted(by_cat.items(), key=lambda x: -x[1]))}")

        # Profile data
        profile = case.get("profile")
        if profile:
            classification = profile.get("classification", {})
            if classification:
                parts.append(f"\nClassification:")
                parts.append(f"  Known good (NSRL): {classification.get('known_good', 0):,}")
                parts.append(f"  Known bad: {classification.get('known_bad', 0):,}")
                parts.append(f"  Suspicious: {classification.get('suspicious', 0):,}")
                parts.append(f"  Unknown: {classification.get('unknown', 0):,}")

            users = profile.get("user_profiles", [])
            if users:
                parts.append(f"\nUser Accounts: {', '.join(u.get('account', '') for u in users[:10])}")

            artifacts = profile.get("high_value_artifacts", [])
            if artifacts:
                parts.append(f"\nHigh-Value Artifacts ({len(artifacts)}):")
                for a in artifacts[:15]:
                    parts.append(f"  - [{a.get('type')}] {a.get('path', 'unknown')}")

        # Stage status
        stages = case.get("stages", [])
        if stages:
            parts.append(f"\nProcessing Stages:")
            for s in stages:
                parts.append(
                    f"  {s.get('order', 0)}. {s.get('name')} ({s.get('type')}) - "
                    f"{s.get('status')} "
                    f"({s.get('files_processed', 0)}/{s.get('files_total', 0)} files)"
                )

        return "\n".join(parts)


# Singleton
triage_advisor = TriageAdvisor()
