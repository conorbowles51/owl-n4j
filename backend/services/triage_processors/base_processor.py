"""
Base Processor

Abstract base class for all triage file processors.
Processors take files as input and produce structured artifacts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ProcessingResult:
    """Result from processing a single file."""

    def __init__(
        self,
        source_path: str,
        artifact_type: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.source_path = source_path
        self.artifact_type = artifact_type
        self.content = content
        self.metadata = metadata or {}
        self.error = error

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_path": self.source_path,
            "artifact_type": self.artifact_type,
            "content": self.content,
            "metadata": self.metadata,
            "error": self.error,
        }


class BaseTriageProcessor(ABC):
    """Abstract base class for triage processors."""

    name: str = ""
    display_name: str = ""
    description: str = ""
    input_types: List[str] = []  # file categories or extensions this processor handles
    output_types: List[str] = []  # artifact types this processor produces
    requires_llm: bool = False
    config_schema: Dict[str, Any] = {}

    @abstractmethod
    def process_file(
        self,
        file_path: str,
        file_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> List[ProcessingResult]:
        """
        Process a single file and return a list of artifacts.

        Args:
            file_path: Absolute path to the file
            file_info: Dict with file metadata (sha256, category, mime_type, etc.)
            config: Processor configuration from stage settings

        Returns:
            List of ProcessingResult objects
        """
        ...

    def process_batch(
        self,
        files: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> List[ProcessingResult]:
        """
        Process a batch of files. Override for efficiency.

        Args:
            files: List of dicts with 'file_path' and 'file_info'
            config: Processor configuration

        Returns:
            List of ProcessingResult objects
        """
        results = []
        for file_data in files:
            try:
                result = self.process_file(
                    file_path=file_data["file_path"],
                    file_info=file_data.get("file_info", {}),
                    config=config,
                )
                results.extend(result)
            except Exception as e:
                results.append(ProcessingResult(
                    source_path=file_data["file_path"],
                    artifact_type="error",
                    error=str(e),
                ))
        return results

    def get_info(self) -> Dict[str, Any]:
        """Return processor info for the registry."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "input_types": self.input_types,
            "output_types": self.output_types,
            "requires_llm": self.requires_llm,
            "config_schema": self.config_schema,
        }
