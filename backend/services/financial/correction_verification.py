"""Shared verification consequences for correction preview and recording."""
from services.financial.documents import read_source_shape, combine_period_outcomes
from services.financial.proof_class import SourceShape, assign_proof_class, admits_automatically
from postgres.models.enums import ProofClass


def correction_verification(document, rows, statuses, *, native_rechecked=False):
    """Compute the class and reservations without modifying any stored object."""
    shape = read_source_shape(document)
    if any(row.proof_class != document.proof_class for row in rows):
        raise ValueError("Document and row proof classes disagree.")
    reservations = (document.metadata_ or {}).get("admissibility_reservations", [])
    if not isinstance(reservations, list) or any(not isinstance(reason, str) for reason in reservations):
        raise ValueError("Source admissibility reservations are malformed.")
    reservations = list(reservations)
    additions = []
    pending = "Corrected ledger reading: native control totals require revalidation."
    conditional = "Corrected ledger reading: native controls recalculated; source interpretation still requires review."
    if native_rechecked:
        reservations = [r for r in reservations if r != pending]
        additions.append(conditional)
    elif shape is SourceShape.native_with_control_totals:
        reservations = [r for r in reservations if r != conditional]
        additions.append(pending)
    if any(row.running_balance_minor is not None for row in rows):
        additions.append("Corrected ledger reading: printed running-balance chain requires revalidation.")
    for reason in additions:
        if reason not in reservations:
            reservations.append(reason)
    outcome = combine_period_outcomes(statuses)
    earned = assign_proof_class(shape, outcome)
    graded = ProofClass.p3 if reservations and admits_automatically(earned) else earned
    return {"can_record": True, "current_proof_class": document.proof_class,
            "proposed_proof_class": graded.value, "reservations": reservations,
            "included_in_default_totals": admits_automatically(graded),
            "scope": "all rows in this source document", "reason": None}
