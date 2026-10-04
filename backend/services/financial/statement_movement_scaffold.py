"""Switch for the unvalidated Scotiabank and Monex movement-table readers.

Both readers were written against layouts the benchmark corpus invented
(modelled on the zero-activity readers, not on a real statement with
movements). They are scaffolds: off unless explicitly switched on, so the
existing fail-closed behaviour (a movement table refuses the statement) stays
in force everywhere by default. Even when on, a section is admitted only when
its rows close against every printed control: opening and closing balance,
printed credit and debit totals and the running balance on each row.
Switch on only after the layout has been checked against a real statement.
"""
import os

MOVEMENT_SCAFFOLD_FLAG = 'LOUPE_FINANCIAL_MX_MOVEMENT_SCAFFOLD'


def movement_scaffold_enabled(environ=None):
    """Off unless explicitly switched on: Neil decides activation."""
    value = (os.environ if environ is None else environ).get(MOVEMENT_SCAFFOLD_FLAG, '')
    return value.strip().lower() in ('1', 'true', 'yes', 'on')
