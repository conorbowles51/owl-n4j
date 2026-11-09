"""A WeasyPrint URL fetcher that loads nothing, for reports whose HTML is self-contained.

WeasyPrint 70 takes a ``URLFetcher``: a plain function that refuses a URL there makes the whole PDF fail with
``AttributeError: 'function' object has no attribute '_fail_on_errors'`` instead of a skipped resource (measured
9 Nov on the live venv, weasyprint 70.0, with one <img> in the page). A refusal from this fetcher is logged by
WeasyPrint and the resource is left out, as before the upgrade.
"""
from __future__ import annotations


def deny_all(message: str):
    """A fetcher that refuses every URL with ``message``."""
    from weasyprint.urls import URLFetcher

    class DenyAll(URLFetcher):
        def fetch(self, url, headers=None):
            raise ValueError(message)

    return DenyAll()
