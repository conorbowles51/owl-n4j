import os

# A test never walks the live corpus: shared-source linking (services/shared_source.py) is off unless a test names
# its own roots.
os.environ.setdefault('SHARED_SOURCE_ROOTS', '')

# The case search's ranking model (services/case_search/rerank.py) is never called from a test: a test that needs
# one passes its own model_call.
os.environ.setdefault('LOUPE_CASE_SEARCH_MODEL', 'off')
