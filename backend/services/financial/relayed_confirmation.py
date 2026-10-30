"""Enter a person's confirmation of a correction Claude made, given elsewhere (for example by message), on that
person's instruction: the confirmation is the person's, and it records who entered it and the relay note, so it never
reads as if the person pressed Confirm themselves.

Account corrections only (services.financial.account_details_correction.confirm_account_details). The person must be
a user of the system, named and addressed as the users table has them. The relay note is required. A dry run (the
default) goes through the same path and rolls back; ``--apply`` keeps it. A correction the same person already
confirmed through a relay takes the new instruction beside the first one, which stays as it was. There is no HTTP
route for this: a browser cannot enter a confirmation in someone else's name.

    python -m services.financial.relayed_confirmation --case <uuid> --account <uuid> --correction <id> \\
        --user-id <uuid> --name <name> --email <address> --basis <what was checked> \\
        --relay-note <on whose instruction> [--entered-by <who entered it>] [--via <message>] [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

DEFAULT_ENTERED_BY = 'Claude'


def enter_relayed_confirmation(session, *, case_id, account_id, correction_id, user_id, name, email, basis,
                               relay_note, entered_by=DEFAULT_ENTERED_BY, via=None, apply=False):
    """Confirm one account correction as ``name``'s, entered by ``entered_by`` on their instruction."""
    from postgres.models.user import User
    from services.financial import account_details_correction as adc
    from services.financial.decisions import Actor
    from services.financial.pdf_candidates import PdfMappingError
    if not (relay_note or '').strip():
        raise PdfMappingError('Give the relay note (who entered this and on whose instruction). Nothing was changed.', 422)
    user = session.get(User, uuid.UUID(str(user_id)))
    if user is None or user.email.strip().lower() != email.strip().lower() or user.name.strip() != name.strip():
        raise PdfMappingError('The person is not a user with that name and address. Nothing was changed.', 422)
    actor = Actor(name=user.name, email=user.email, user_id=user.id)
    state = adc.account_details_state(session, case_id=case_id, account_id=account_id)
    request = adc.ConfirmAccountDetailsRequest(expected_revision=state['revision'], correction_id=correction_id,
                                               basis=basis)
    relayed = dict(by=entered_by, note=relay_note, **({'via': via} if via else {}))
    result = adc.confirm_account_details(session, case_id=case_id, account_id=account_id, request=request,
                                         actor=actor, relayed=relayed, commit=apply)
    if not apply:
        session.rollback()
    return dict(applied=apply, account_id=str(account_id), correction_id=correction_id, holder=result['holder'],
                confirmed=result['confirmed'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    for flag in ('--case', '--account', '--correction', '--user-id', '--name', '--email', '--basis', '--relay-note'):
        parser.add_argument(flag, required=True)
    parser.add_argument('--entered-by', default=DEFAULT_ENTERED_BY)
    parser.add_argument('--via')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    from services.financial.pdf_candidates import PdfMappingError
    with _get_session_local()() as session:
        try:
            result = enter_relayed_confirmation(session, case_id=uuid.UUID(args.case), account_id=uuid.UUID(args.account),
                correction_id=args.correction, user_id=args.user_id, name=args.name, email=args.email,
                basis=args.basis, relay_note=args.relay_note, entered_by=args.entered_by, via=args.via,
                apply=args.apply)
        except PdfMappingError as exc:
            json.dump(dict(refused=str(exc), status=exc.status_code, applied=False), sys.stdout, indent=2)
            print()
            return 1
    json.dump(result, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
