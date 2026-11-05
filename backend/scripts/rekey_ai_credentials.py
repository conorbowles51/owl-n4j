"""Move the stored AI provider credentials to the current AI_CREDENTIAL_ENCRYPTION_KEY.

Dry run by default: reads every credential and reports the providers. ``--apply`` rewrites them in one transaction and
records it in the activity trail. Run after the new key and AI_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS are live
(deploy/rotate-secrets.sh does both). Never prints a key.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    apply = parser.parse_args().apply

    from postgres.session import _get_session_local
    from services import activity_trail
    from services.ai_provider_credentials import credential_store

    with _get_session_local()() as db:
        providers = credential_store.rekey_stored(db, apply=apply)
        if apply:
            activity_trail.record("ai_credentials_rekeyed", db=db, commit=True, system=True,
                                  details=dict(providers=providers))
    print(("Rewritten" if apply else "Readable, nothing written") + f": {len(providers)} ({', '.join(providers) or 'none'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
