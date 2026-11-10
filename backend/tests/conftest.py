import os

# A test never walks the live corpus: shared-source linking (services/shared_source.py) is off unless a test names
# its own roots.
os.environ.setdefault('SHARED_SOURCE_ROOTS', '')
