"""Read-only source scope for recovery work that can still advance."""
from uuid import UUID

from sqlalchemy import or_, select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_recovery import FinancialRecoveryRun as Run, FinancialRecoveryItem as Item


# These are the advancing item states used by deployment_recovery. A paused
# campaign and terminal items have no queued work until explicitly resumed.
ACTIVE_RECOVERY_ITEM_STATUSES = ('pending', 'waiting', 'reading')


def active_recovery_file_ids(session, *, case_id, file_ids=None):
    """Return case-owned originals and retained targets of advancing items.

    Only scalar IDs are read, never source bodies or the full result payload.
    A target reference is accepted only when that evidence belongs to this case.
    Callers expand verified reading families according to their existing rules.
    """
    selected = set(file_ids) if file_ids is not None else None
    if selected == set():
        return set()
    reading_id = Item.result['reading_file_id'].as_string()
    statement = select(Item.file_id, reading_id).join(Run, Item.run_id == Run.id).join(
        EvidenceFile, EvidenceFile.id == Item.file_id).where(
        Run.case_id == case_id, EvidenceFile.case_id == case_id,
        Run.status == 'running', Item.status.in_(ACTIVE_RECOVERY_ITEM_STATUSES))
    if selected is not None:
        statement = statement.where(or_(Item.file_id.in_(selected),
            reading_id.in_([str(identifier) for identifier in selected])))
    originals, targets = set(), set()
    for source_id, target_id in session.execute(statement):
        originals.add(source_id)
        try:
            if target_id:
                targets.add(UUID(target_id))
        except (TypeError, ValueError, AttributeError):
            continue
    if targets:
        originals.update(session.scalars(select(EvidenceFile.id).where(
            EvidenceFile.case_id == case_id, EvidenceFile.id.in_(targets))))
    return originals if selected is None else originals & selected
