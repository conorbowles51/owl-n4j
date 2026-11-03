"""Every built approach, registered with the framework in one place (the API and the worker both call ``install``)."""
from __future__ import annotations

_done = {"installed": False}


def install() -> None:
    if _done["installed"]:
        return
    from services.phone_analysis import framework
    for name in BUILT:
        module = __import__("services.phone_analysis." + name, fromlist=["CODE"])
        framework.register(module)
    _done["installed"] = True


BUILT = ["money_signals", "deletion_timeline"]
