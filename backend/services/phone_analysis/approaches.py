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


BUILT = ["money_signals", "message_reconciliation", "deletion_timeline", "relationships", "awareness", "device_users",
         "reparse_comparison", "typed_words", "intent", "common_contacts",
         "contact_matrix", "number_switching",
         "extraction_comparison", "other_devices", "plans"]

# The screen titles, for words outside the screens (a kept result's label).
TITLES = {
    "money_signals": "Money on the phones",
    "message_reconciliation": "Messages across phones",
    "deletion_timeline": "Deleted and hidden",
    "relationships": "Relationships over time",
    "awareness": "Reading, replies and group roles",
    "device_users": "Who used which phone",
    "reparse_comparison": "Read again by an independent tool",
    "typed_words": "Typed words",
    "intent": "Searches and pages",
    "common_contacts": "Common contacts",
    "contact_matrix": "Who contacts whom",
    "number_switching": "Possible number changes",
    "extraction_comparison": "Two extractions of one phone",
    "other_devices": "Devices and accounts across phones",
    "plans": "Plans and check-ins against location",
}
