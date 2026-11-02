"""
Neo4j Service — backward-compatible re-export.

The actual implementation has been split into focused domain services
under services/neo4j/. This module re-exports the facade so that all
existing imports continue to work:

    from services.neo4j_service import neo4j_service
    from services.neo4j_service import parse_json_field
"""

# Re-export the facade and helpers so existing imports keep working
from services.neo4j import neo4j_service  # noqa: F401
from services.neo4j.driver import parse_json_field, safe_float  # noqa: F401
