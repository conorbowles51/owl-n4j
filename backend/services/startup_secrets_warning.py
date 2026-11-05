"""A server not marked production still says, on every start, which secrets it would be refused for."""
from __future__ import annotations

import logging
import os

import secret_check

log = logging.getLogger(__name__)


def warn_when_not_enforced(environment=os.environ) -> list[str]:
    found = [] if secret_check.is_production(environment) else secret_check.problems(environment)
    if found:
        log.warning("Sign-in secrets are not safe for a real server: %s. Set them and LOUPE_ENV=production.",
                    "; ".join(found))
    return found
