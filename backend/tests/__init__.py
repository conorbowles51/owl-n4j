import os

# Automatic save of fully reconciled statements (services/financial/queue_save.py)
# is ON in production. Tests of the manual save flow expect prepared statements
# to stay ready, so it is off here unless a test switches it on itself
# (tests/test_financial_queue_save.py does). Set in the package, not in a pytest
# conftest, so `unittest discover` (the documented suite command) and pytest
# both import it before any test module reads the switch.
os.environ.setdefault('FINANCIAL_AUTO_SAVE_READY', '0')
