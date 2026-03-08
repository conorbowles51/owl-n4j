"""
Maintenance Service for Vector DB integrity.

Provides audit, repair, purge, and health operations for ChromaDB
to ensure case isolation and prevent cross-case data leakage.

Operations:
  - health()         Quick status check (counts + pass/fail)
  - audit()          Full integrity scan across all collections
  - repair()         Backfill missing case_id metadata
  - purge_orphans()  Remove entries with no valid case association
"""

from typing import Dict, Optional, Callable


class MaintenanceService:
    """Service for maintaining vector database integrity."""

    def health(self) -> Dict:
        """
        Quick health check returning counts per collection and pass/fail status.

        Returns:
            Dict with collection counts, case_id coverage percentages, and status.
        """
        from services.vector_db_service import vector_db_service
        if not vector_db_service:
            return {"status": "unavailable", "reason": "Vector DB not initialized"}

        report = {"status": "healthy", "collections": {}}

        for name in ["documents", "entities", "chunks"]:
            entries = vector_db_service.get_all_metadata(name)
            total = len(entries)
            with_case_id = sum(
                1 for _, meta in entries
                if meta and meta.get("case_id") and meta["case_id"] != ""
            )
            missing = total - with_case_id
            pct = round((with_case_id / total * 100), 1) if total > 0 else 100.0

            report["collections"][name] = {
                "total": total,
                "with_case_id": with_case_id,
                "missing_case_id": missing,
                "coverage_pct": pct,
            }

            # Mark unhealthy if any entries are missing case_id
            if missing > 0:
                report["status"] = "unhealthy"

        return report

    def audit(self, log_callback: Optional[Callable] = None) -> Dict:
        """
        Full integrity audit across all ChromaDB collections.

        Cross-references case_ids against valid Postgres cases to find:
        - Entries with missing/empty case_id
        - Entries with case_ids that don't match any valid case (orphans)
        - Per-case counts

        Args:
            log_callback: Optional callback(level, message) for progress updates.

        Returns:
            Structured audit report dict.
        """
        from services.vector_db_service import vector_db_service
        if not vector_db_service:
            return {"status": "error", "reason": "Vector DB not initialized"}

        def log(level: str, msg: str):
            print(f"[Maintenance] [{level.upper()}] {msg}")
            if log_callback:
                log_callback(level, msg)

        log("info", "Starting vector DB integrity audit...")

        # Get valid case IDs from Postgres
        valid_case_ids = self._get_valid_case_ids()
        log("info", f"Found {len(valid_case_ids)} valid cases in Postgres")

        report = {
            "status": "complete",
            "valid_cases": len(valid_case_ids),
            "collections": {},
        }

        for name in ["documents", "entities", "chunks"]:
            log("info", f"Auditing {name} collection...")
            entries = vector_db_service.get_all_metadata(name)
            total = len(entries)

            missing_case_id = []
            invalid_case_id = []
            case_counts = {}

            for entry_id, meta in entries:
                meta = meta or {}
                case_id = meta.get("case_id", "")

                if not case_id:
                    missing_case_id.append(entry_id)
                elif case_id not in valid_case_ids:
                    invalid_case_id.append({"id": entry_id, "case_id": case_id})
                else:
                    case_counts[case_id] = case_counts.get(case_id, 0) + 1

            valid_count = total - len(missing_case_id) - len(invalid_case_id)

            report["collections"][name] = {
                "total": total,
                "valid": valid_count,
                "missing_case_id": len(missing_case_id),
                "invalid_case_id": len(invalid_case_id),
                "per_case": case_counts,
                "missing_ids_sample": missing_case_id[:20],
                "invalid_ids_sample": invalid_case_id[:20],
            }

            log("info", f"  {name}: {total} total, {valid_count} valid, "
                f"{len(missing_case_id)} missing case_id, {len(invalid_case_id)} invalid case_id")

        # Overall health
        total_issues = sum(
            c["missing_case_id"] + c["invalid_case_id"]
            for c in report["collections"].values()
        )
        report["total_issues"] = total_issues
        report["healthy"] = total_issues == 0

        log("info", f"Audit complete. Total issues: {total_issues}")
        return report

    def repair(self, dry_run: bool = False, log_callback: Optional[Callable] = None) -> Dict:
        """
        Repair missing case_id metadata by running the backfill script.

        This wraps the existing backfill_case_ids script which resolves case_id
        from evidence storage, file paths, and relationship traversal.

        Args:
            dry_run: If True, report what would be fixed without making changes.
            log_callback: Optional callback(level, message) for progress updates.

        Returns:
            Backfill result dict with statistics.
        """
        try:
            from scripts.backfill_case_ids import backfill_case_ids
            return backfill_case_ids(
                dry_run=dry_run,
                include_entities=True,
                include_vector_db=True,
                log_callback=log_callback,
            )
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def purge_orphans(
        self, dry_run: bool = True, log_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Remove vector entries with no valid case association.

        Targets entries where:
        1. case_id is empty/missing (after repair has been attempted), OR
        2. case_id doesn't match any valid Postgres case

        Args:
            dry_run: If True (default), report what would be deleted without acting.
            log_callback: Optional callback(level, message) for progress updates.

        Returns:
            Dict with purge statistics per collection.
        """
        from services.vector_db_service import vector_db_service
        if not vector_db_service:
            return {"status": "error", "reason": "Vector DB not initialized"}

        def log(level: str, msg: str):
            print(f"[Maintenance] [{level.upper()}] {msg}")
            if log_callback:
                log_callback(level, msg)

        mode = "DRY RUN" if dry_run else "LIVE"
        log("info", f"Starting orphan purge ({mode})...")

        valid_case_ids = self._get_valid_case_ids()
        log("info", f"Found {len(valid_case_ids)} valid cases in Postgres")

        report = {"status": "complete", "dry_run": dry_run, "collections": {}}

        for name in ["documents", "entities", "chunks"]:
            entries = vector_db_service.get_all_metadata(name)

            orphan_ids = []
            for entry_id, meta in entries:
                meta = meta or {}
                case_id = meta.get("case_id", "")
                if not case_id or case_id not in valid_case_ids:
                    orphan_ids.append(entry_id)

            deleted = 0
            if orphan_ids and not dry_run:
                deleted = vector_db_service.delete_by_ids(name, orphan_ids)

            report["collections"][name] = {
                "total": len(entries),
                "orphans_found": len(orphan_ids),
                "deleted": deleted if not dry_run else 0,
                "would_delete": len(orphan_ids) if dry_run else 0,
                "orphan_ids_sample": orphan_ids[:20],
            }

            log("info", f"  {name}: {len(orphan_ids)} orphans "
                f"{'would be deleted' if dry_run else f'deleted ({deleted})'}")

        total_orphans = sum(c["orphans_found"] for c in report["collections"].values())
        report["total_orphans"] = total_orphans
        log("info", f"Purge complete. Total orphans: {total_orphans}")

        return report

    def _get_valid_case_ids(self) -> set:
        """
        Get all valid case IDs from the Postgres database.

        Returns:
            Set of case_id strings.
        """
        try:
            from postgres.session import _get_session_local
            from postgres.models.case import Case

            SessionLocal = _get_session_local()
            db = SessionLocal()
            try:
                case_ids = db.query(Case.id).all()
                return {str(cid[0]) for cid in case_ids}
            finally:
                db.close()
        except Exception as e:
            print(f"[Maintenance] Warning: Could not load case IDs from Postgres: {e}")
            return set()


# Singleton instance
maintenance_service = MaintenanceService()
