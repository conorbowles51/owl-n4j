"""Page-image fallback reader for held bank statements (Neil, 2026-10-24).

A statement the rule readers could not prove stays held. When its file is
prepared again through the normal batch path (a recovery re-read or any new
preparation), this reader looks at the images of that statement's pages with
the AI workload ``financial_vision``, a chain of models tried in order
(DeepSeek's image model first, OpenAI's vision model the failsafe: Neil,
2026-10-28), all given the same instructions (PROMPT, PROMPT_VERSION), and asks
for structured JSON only: the account sections printed on
each page, their header (bank, holder, account, currency, period), opening and
closing balances, printed totals and counts, and every payment row with its
printed running balance.

The reading is accepted only when it proves itself, all of:

* opening balance + every row = closing balance, to the cent;
* every printed running balance agrees with the rows before it;
* printed credit/debit totals and counts agree where printed;
* the period is complete and every row date lies inside it;
* printed page numbering shows no missing page;
* the header agrees with the rule reading wherever that read a value, and the
  account is one the case already has saved statements for, with the same
  holder, bank and currency;
* every payment the rule reading read cleanly appears in the image reading
  with the same amount and direction (the image never drops a payment the text
  shows), and every balance the rule reading read is the same.

It is then recorded as a System review of the statement (``save_review``, the
batch's own save), its rows marked "Read from page image, page N", the rule
reading's rows set aside with that reason (retained, never deleted). The
batch's normal assessment and admission then decide again, and the existing
automatic save saves it only when that finds nothing at all to check. A reading
that does not prove is not applied; the statement stays held exactly as it was,
with the reason recorded beside it.

The chain: the first reader whose reading proves is used. A reader that fails
(error, timeout, an answer that is not JSON) or whose reading does not prove
hands over to the next, and the reason is recorded; readings are never combined
and an unproved one is never accepted. Every outcome records each reader's
provider, model, instructions version, seconds, cost and why it did not settle
it; when none proves, the statement stays held with every reason.

Never: a statement with any investigator work (draft or saved review), a saved
or set-aside statement, a ready one, a document review, a fund statement.
Fails closed: switch off, no key, a provider without page-image support, an
API error, a timeout, a truncated or refused answer, or the case's cost cap
reached all leave the statement held. Each reading is stored on the evidence
file with its model, per-page tokens and cost, so a statement is read from its
images once per reading and model.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import select

from services.financial.journal import journal

# Every outcome is a journal line (journal: INFO lines reach the service journal under uvicorn).
log = journal(__name__)


def _switch(name, default='1'):
    return os.environ.get(name, default).strip().lower() not in ('0', 'false', 'off', 'no', '')


def _number(name, default):
    try:
        return float(os.environ.get(name, '') or default)
    except ValueError:
        return float(default)


ENABLED = _switch('LOUPE_FINANCIAL_VISION_FALLBACK')
# Cases whose page images may be sent to the provider (comma-separated case ids, or '*' for every
# case). A case not listed is never read; unset reads none.
APPROVED_CASES = frozenset(c.strip().lower() for c in os.environ.get('LOUPE_FINANCIAL_VISION_CASES', '').split(',') if c.strip())
EVERY_CASE = '*'


def approved(case_id):
    return EVERY_CASE in APPROVED_CASES or str(case_id).lower() in APPROVED_CASES
# Spend cap per case for one worker run (process lifetime); readings already
# stored are reused and cost nothing again.
CASE_BUDGET_USD = _number('LOUPE_FINANCIAL_VISION_CASE_BUDGET_USD', 30)
MAX_PAGES = int(_number('LOUPE_FINANCIAL_VISION_MAX_PAGES', 30))
PAGE_TIMEOUT_SECONDS = int(_number('LOUPE_FINANCIAL_VISION_TIMEOUT_SECONDS', 180))
IMAGE_WIDTH = int(_number('LOUPE_FINANCIAL_VISION_IMAGE_WIDTH', 1600))
STRIPS = int(_number('LOUPE_FINANCIAL_VISION_STRIPS', 3))
STRIP_OVERLAP = 0.06
SWEEP_SECONDS = _number('LOUPE_FINANCIAL_VISION_SWEEP_SECONDS', 240)
WORKLOAD = 'financial_vision'
VERSION = 'vision-reader-v1'
# The proof rules a stored outcome was judged under. A stored not-proved reading judged under
# older rules is judged again from its stored page reading (no new request), once.
REJUDGE = _switch('LOUPE_FINANCIAL_VISION_REJUDGE')
# One account saved under two account records whose bank is spelled differently ("BBVA" and
# "BBVA MEXICO"): the same full number and every spelling naming the same bank is one account.
SPLIT_SPELLINGS = _switch('LOUPE_FINANCIAL_VISION_SPLIT_SPELLINGS')
# A product section heading printing its own number on the same line as the statement's CLABE ("SERVICIO
# EMPRESARIAL FX KAPITAL 194-99292-001-6  CLABE 128180000000109664", Kapital and Intercam): the page images give
# the heading's number as the account number, the text reading the CLABE. The image number is this statement's
# account when the text reading shows it printed on that one line beside "CLABE <the statement's CLABE>".
# Off: such a reading matches no section and the statement waits for a person (10 BNB2 Kapital statements).
SECTION_NUMBER = _switch('LOUPE_FINANCIAL_VISION_SECTION_NUMBER')
# A file holding only some printed pages of a statement (BNB2 ECO 2023 MN, BBVA 23: the movement pages of a "PAGINA
# n/N" printing) is complete when a page it holds prints the period's deposit and withdrawal counts and totals and
# the payments read match all four: another movement on a missing page would change a printed count. Off: the
# printed page numbering alone holds the reading.
PRINTED_COUNTS = _switch('LOUPE_FINANCIAL_VISION_PRINTED_COUNTS')
# Version 2 is SPLIT_SPELLINGS, 3 SECTION_NUMBER, 4 PRINTED_COUNTS, each on top of the one before; with a switch off
# the rules are the version before it and nothing is judged again for it.
# A section the images show printing 0 deposits and 0 withdrawals, totals 0.00 and 0.00, and one balance at both
# ends (BNB2 ECO 2023 DOLARES, BBVA 23 USD: one page of a "PAGINA n/N" printing) proves the period had no
# movement from its own printed controls, as the text readers' printed zero totals do (printed-zero-totals-v1);
# admission records the basis 'page_image_zero_counts'. Off: such a period waits for a person's confirmation.
QUIET_PRINTED = _switch('LOUPE_FINANCIAL_VISION_QUIET_PRINTED')
# A CLABE names its account in digits 7 to 17 (bank 3, branch 3, account 11, check digit 1). The images give a Monex
# statement's CLABE (112180000030419770) where the text reading has the contract number (3041977): a CLABE whose
# check digit is right names the account its account digits hold, at least 6 digits without leading zeros.
CLABE_ACCOUNT = _switch('LOUPE_FINANCIAL_VISION_CLABE_ACCOUNT')
# Andrews prints one member number over several share sections ("820433320": BASE SHARE SAVINGS, FREE CHECKING),
# its share id ("ID 0040") on some pages only and no currency: the images give every section the member number,
# or the share id, and no currency, while the text reading has "820433320 / Share 0040" in USD. Of the sections the
# number names, the statement's is the one the text reading itself identifies: its read opening and closing balance
# are the section's and every payment it read cleanly is in the section; exactly one section must agree, and a
# section printing no currency stays a candidate when none prints one. One account saved under two bank spellings
# is one account when every record's saved holders include the printed holder (a name the account holder later
# changed is still saved beside it, on that record or one the printed holder is saved on). Off: such a statement matches no section, or two accounts (9 Erica periods).
SECTION_BY_TEXT = _switch('LOUPE_FINANCIAL_VISION_SECTION_BY_TEXT')
# The images give a withdrawal's amount with the minus the statement prints before it ('-15.89', direction debit;
# Andrews prints every withdrawal so), though the reading asks for a positive amount: such an amount is the
# withdrawal's when the minus agrees with its direction. A minus on a credit is refused as before. Off: every
# such row is unreadable (Erica Andrews Dec 2020, 129 withdrawals).
SIGNED_DEBITS = _switch('LOUPE_FINANCIAL_VISION_SIGNED_DEBITS')
# A text reading complete in every amount and running balance, held only for row dates it could not read
# ('12/lll' printed 12/18), takes each such date from the page images: the one image row on the same page with the
# same amount, direction and running balance, dated inside the period and inside the text's own payment order (on
# or after the dated row before it, on or before the one after it). The text reading is then recorded with those
# dates (each citing its page image) and must check out with nothing left; it is used only when the image reading
# does not prove the period itself. Off: such a period waits for a person (Erica Andrews Dec 2020).
DATES_FROM_IMAGE = _switch('LOUPE_FINANCIAL_VISION_DATES_FROM_IMAGE')
DATE_REASON = 'Date read from page image, page {page}; amount and running balance as read from the text.'
# A production missing the statement's summary page (BNB2 ECO Ago 2023 MN: bank pages 2-16 of 20; page 1, which prints
# the opening balance, is not in the file): every movement is read, the deposit and withdrawal counts and totals the
# images show agree with them, and the closing balance is read, so the opening is the closing less the movements. It
# is taken only when a saved statement next to the period confirms it (the previous one closing at it, or the next one
# opening at the closing read; none disagreeing) and the printed running balances chain from it, and is recorded with
# that basis (``_opening_from_previous``). Off: such a period waits for a person (fin-queue3 L8, 2026-10-26).
OPENING_FROM_PREVIOUS = _switch('LOUPE_FINANCIAL_VISION_OPENING_FROM_PREVIOUS')
OPENING_REASON = ('Opening balance not printed in these pages: the closing balance read less the payments read, '
                  'which agree with the printed counts and totals; confirmed by {previous}.')
# The text reading's printed deposit or withdrawal total of a period the images prove is the scan's misreading when the
# images read the same printed total otherwise (BNB2 09 BBVA 23 MXN: text 3,428,314.57, image 3,129,314.57 = the one
# deposit, the ledger and opening + deposits - withdrawals = the printed closing). The proof already checked the
# image's printed total against every payment read, so the recorded review takes it for that total, citing the page
# image, as it takes the image's opening and closing. Off: the text's total stays and holds the period.
IMAGE_TOTALS = _switch('LOUPE_FINANCIAL_VISION_IMAGE_TOTALS')
TOTAL_REASON = 'Printed total read from page image, page {page}; it agrees with the payments read.'
# A card statement prints one date, its statement (billing-cycle closing) date, and the days in its billing cycle
# ('Statement Date: 04/25/22', 'Days in Billing Cycle 31'; Merrick), but no period: the images gave no period and
# the reading could not prove. The images now give that closing date as the period end and the printed days
# (``days_in_period``); the start is the closing date less those days plus one, two printed facts (as the text
# engine's closing-only rule, statement_engine B1), and must agree with the text reading wherever that read a
# start or end. Off: such a statement is 'The statement period could not be read' (Erica Merrick, 42 statements).
CLOSING_DAYS = _switch('LOUPE_FINANCIAL_VISION_CLOSING_DAYS')
MAX_CYCLE_DAYS = 95
# A card statement prints its fee and interest totals ('TOTAL FEES FOR THIS PERIOD 0.00', 'TOTAL INTEREST FOR THIS
# PERIOD 39.59'); payments read from the page images are added rows, which the text controls cannot be compared with,
# so every such statement read from its images stayed held ('Check the printed fee total'). The images now give each
# charge line's kind and the printed fee and interest totals: a printed total must equal the lines of its kind read
# (and the text's reading of the same total wherever that read one), and is then the checked control for those rows
# (statement_admission). A charge line printed as 0.00 moves nothing and is not a payment. Rides on CLOSING_DAYS.
# A damaged text layer reads some payments 'cleanly' but wrongly (Erica Merrick: a payment's trailing minus lost,
# 'MOBILE PAYMENT 150.00' read as a charge; one glyph misread, '15.35' printed 15.85): the image reading, which proves
# the period on its own, was refused as dropping a payment the text shows. Now a text payment is found in the image
# reading when an image row on the same date has its amount in the other direction, or its direction and an amount
# of the same digits but one. Each image row answers one text payment. Off: only the same amount and direction.
TEXT_MISREADS = _switch('LOUPE_FINANCIAL_VISION_TEXT_MISREADS')
# A card statement lists each purchase by its transaction date, which can fall a few days before the billing cycle
# it is posted in ('06/24' on the statement for 06/26 to 07/26/21). On a card statement whose period is its printed
# closing date and days (CLOSING_DAYS), a row dated up to POSTING_DAYS before the start is a posting of this cycle.
# Off: such a row is 'dated outside the statement period'. Rides on TEXT_MISREADS.
POSTING_DAYS = 5
# The first statement of an account (Neil, 2026-10-27, rule 1): no saved statement of the case confirms the account,
# so every reading of it was refused ("This account has no saved statement in the case to confirm the page-image
# reading against"; OPDMD66 Truist: 2 statements) and no first statement could ever be accepted. The header is then
# accepted when the page images and the text reading of the same file agree on all three: the FULL account number
# (both printed in full, no mask, the same digits), the holder (same_holder) and the bank (same_institution); the
# currency must be printed. Every other proof is unchanged (balances to the cent, printed totals and counts, pages,
# period). Recorded with the basis 'page_image_header_matches_text'. Off: such a statement stays held as before.
FIRST_STATEMENT = _switch('LOUPE_FINANCIAL_VISION_FIRST_STATEMENT')
FIRST_STATEMENT_BASIS = 'page_image_header_matches_text'
FIRST_STATEMENT_MIN_DIGITS = 6
FIRST_STATEMENT_NOTE = (' The first statement of this account in the case: its full account number, holder and bank on the '
                        'page images agree with the text of the same file.')
# Row dates the arithmetic cannot check (coordinator, 2026-10-28: OpenAI read Andrews "11/03 ... -20.00" as 11/02 and
# "09/01 08/31 Debit Card -9.00" as 09/02, each the date of the line beside it). Besides lying inside the period, the
# rows of a section must run in date order as printed (forward or reverse, or each block of one direction when the
# statement prints deposits and withdrawals apart), and every payment the text of the file reads cleanly with its date
# must be in the page-image reading with that same date, amount and direction. Any disagreement holds the statement
# with its reason. Off: dates are checked against the period only, as before.
ROW_DATES = _switch('LOUPE_FINANCIAL_VISION_ROW_DATES')
# Pages scanned out of order (coordinator, 2026-10-28: Andrews "statement 820433320 Pt 1" Dec 2020 is file pages
# 38,37,36,35,39,40 printing 1..6): when the printed numbers of the period's pages form one complete run, no number
# twice and none missing, the pages are read in printed order whatever their order in the file. Off: printed numbers
# must rise with the file's pages, as before.
PRINTED_ORDER = _switch('LOUPE_FINANCIAL_VISION_PRINTED_ORDER')
PROOF_VERSION = 1
for _switched in (SPLIT_SPELLINGS, SECTION_NUMBER, PRINTED_COUNTS, QUIET_PRINTED, CLABE_ACCOUNT, SECTION_BY_TEXT,
                  SIGNED_DEBITS, DATES_FROM_IMAGE, OPENING_FROM_PREVIOUS, IMAGE_TOTALS, CLOSING_DAYS, TEXT_MISREADS,
                  FIRST_STATEMENT, ROW_DATES, PRINTED_ORDER):
    # Each switch on top of the one before; with one off, the rules are the version before it.
    if not _switched:
        break
    PROOF_VERSION += 1
METADATA_KEY = 'financial_vision_reading'
# A saved statement period that is incomplete (no dates, or a balance missing: Alex saved 41 Erica Merrick periods with
# their payments only, from a damaged text reading) is read from its page images once (read_saved), stored on the
# file under SAVED_KEY, never applied here: the reader replacement (saved_reading_replacement) judges it like any
# reading and replaces the saved copy, linked and restorable, only when it proves. Off: nothing is read or used.
SAVED_KEY = 'financial_vision_saved_reading'
SAVED_READING = _switch('LOUPE_FINANCIAL_VISION_SAVED_READING')
MARK = 'vision_fallback'
SYSTEM_NAME = 'System'
SYSTEM_EMAIL = 'vision-reader@system.local'
ROW_REASON = 'Read from page image, page {page}.'
REPLACED_REASON = ('Set aside: the reading of the page images of this period reconciles exactly and replaces '
                   'the text reading, which is retained.')
# A claim outlives the longest chain reading (DeepSeek's read allowance with its retries, then OpenAI's), so no
# other worker takes up a statement still being read; a claim left by a stopped worker expires after it.
CLAIM_SECONDS = 90 * 60
# A statement whose request fails this many times (for the same reading) is not requested again.
MAX_FAILURES = 3
# Reserved before each request: an answer cut short, refused or timed out is still billed.
RESERVE_TOKENS_PER_IMAGE = 1600
RESERVE_OUTPUT_TOKENS = 16000
DEEPSEEK_RESERVE_OUTPUT_TOKENS = 64000
GAVE_UP = 'The page images could not be read after several tries; the statement stays held.'
# Statements a person has worked on (Neil, 2026-10-27, rule 2): read from their page images too (the same cost cap).
# A reading that proves is stored as an OFFER beside their work ('offered'), never saved, merged or imported: the queue
# and the statement show it side by side with their saved work, and only their click saves it (accept_offer: their own
# save, save_review, as them, against the work the offer was compared with; their earlier review stays in its history).
# "Keep mine" records the decline ('offer_declined'); their work is never changed. Off: such a statement is not read.
OFFERS = _switch('LOUPE_FINANCIAL_VISION_OFFERS')
OFFER_MESSAGE = 'A reading from the page images checks out.'
# Outcomes not attempted again for the same reading (failed, budget and unavailable are retried later).
FINAL = ('proved', 'not_proved', 'stale', 'offered', 'offer_accepted', 'offer_declined')
# USD per million tokens (input, output). Unknown models use the most expensive line.
# As Loupe's own pricing table (ai_pricing_rates, migration 20260722) for the 5.6 models.
PRICES = {'gpt-4o': (2.50, 10.00), 'gpt-4.1': (2.00, 8.00), 'gpt-5': (1.25, 10.00),
          'gpt-5.6-sol': (5.00, 30.00), 'gpt-5.6-terra': (2.50, 15.00), 'gpt-5.6-luna': (1.00, 6.00),
          # Loupe's pricing table (migration 20260807): deepseek-v4-flash* 0.14 / 0.28, deepseek-v4-pro* 0.435 / 0.87;
          # 'deepseek-flash' is the account's name for V4.1 Flash (GET /models, 2026-10-28), priced as V4 Flash.
          'deepseek-flash': (0.14, 0.28), 'deepseek-v4-flash': (0.14, 0.28), 'deepseek-v4-pro': (0.435, 0.87)}
FALLBACK_PRICE = (5.00, 30.00)

_spend = {}
_spend_lock = threading.Lock()


def price(model_id):
    override = (os.environ.get('LOUPE_FINANCIAL_VISION_PRICE_IN'), os.environ.get('LOUPE_FINANCIAL_VISION_PRICE_OUT'))
    if all(override):
        try:
            return float(override[0]), float(override[1])
        except ValueError:
            pass
    for prefix in sorted(PRICES, key=len, reverse=True):
        if model_id == prefix or model_id.startswith(prefix + '-'):
            return PRICES[prefix]
    return FALLBACK_PRICE


def cost_usd(model_id, usage):
    rate_in, rate_out = price(model_id)
    usage = usage or {}
    return round((usage.get('prompt_tokens') or 0) * rate_in / 1e6 + (usage.get('completion_tokens') or 0) * rate_out / 1e6, 6)


def spent(case_id):
    with _spend_lock:
        return _spend.get(str(case_id), 0.0)


def _add_spend(case_id, amount):
    with _spend_lock:
        _spend[str(case_id)] = _spend.get(str(case_id), 0.0) + amount


def _reserve(case_id, amount):
    """Count ``amount`` against the case's budget; False (nothing counted) when it would pass the budget."""
    with _spend_lock:
        if _spend.get(str(case_id), 0.0) + amount > CASE_BUDGET_USD:
            return False
        _spend[str(case_id)] = _spend.get(str(case_id), 0.0) + amount
        return True


# ---------------------------------------------------------------------------
# The request: one page image -> its account sections, schema-enforced
# ---------------------------------------------------------------------------

def _nullable(kind):
    return {'type': [kind, 'null']}


_ROW = {'type': 'object', 'additionalProperties': False,
        'required': ['date', 'description', 'amount', 'direction', 'balance_after', 'unreadable'],
        'properties': {
            'date': {'type': 'string', 'description': 'YYYY-MM-DD; the posting (operation) date printed for the row.'},
            'description': {'type': 'string'},
            'amount': {'type': 'string', 'description': 'Positive amount as printed, digits with a dot decimal separator, no thousands separators, e.g. 1234.56'},
            'direction': {'type': 'string', 'enum': ['credit', 'debit']},
            'balance_after': _nullable('string'),
            'unreadable': {'type': 'boolean'}}}
_SECTION = {'type': 'object', 'additionalProperties': False,
            'required': ['section_name', 'institution', 'holder', 'account_number', 'currency', 'currency_as_printed', 'period_start',
                         'period_end', 'opening_balance', 'closing_balance', 'total_credits', 'total_debits',
                         'count_credits', 'count_debits', 'rows', 'no_transactions_printed'],
            'properties': {
                'section_name': {'type': 'string', 'description': 'The printed heading of this account or sub-account section (product, share or sub-account name); empty when none.'},
                'institution': {'type': 'string'}, 'holder': {'type': 'string'},
                'account_number': {'type': 'string'},
                'currency': {'type': 'string', 'description': 'ISO 4217 code only if the page prints the currency; else empty.'},
                'currency_as_printed': {'type': 'string'},
                'period_start': {'type': 'string'}, 'period_end': {'type': 'string'},
                'opening_balance': _nullable('string'), 'closing_balance': _nullable('string'),
                'total_credits': _nullable('string'), 'total_debits': _nullable('string'),
                'count_credits': _nullable('integer'), 'count_debits': _nullable('integer'),
                'rows': {'type': 'array', 'items': _ROW},
                'no_transactions_printed': {'type': 'boolean'}}}
PAGE_SCHEMA = {'type': 'object', 'additionalProperties': False,
               'required': ['printed_page_number', 'printed_page_total', 'is_statement_page', 'sections'],
               'properties': {'printed_page_number': _nullable('integer'), 'printed_page_total': _nullable('integer'),
                              'is_statement_page': {'type': 'boolean'},
                              'sections': {'type': 'array', 'items': _SECTION}}}

# One request per statement: every page image, labelled with its page number; each row cites its page.
_DOC_ROW = dict(_ROW, required=_ROW['required'] + ['page', 'charge_kind'],
                properties=dict(_ROW['properties'], page={'type': 'integer'},
                                charge_kind={'type': 'string', 'enum': ['', 'fee', 'interest']}))
_ACCOUNT = dict(_SECTION, required=_SECTION['required'] + ['opening_balance_page', 'closing_balance_page', 'days_in_period',
                                                           'total_fees', 'total_interest'],
                properties=dict(_SECTION['properties'], rows={'type': 'array', 'items': _DOC_ROW},
                                opening_balance_page=_nullable('integer'), closing_balance_page=_nullable('integer'),
                                days_in_period=_nullable('integer'), total_fees=_nullable('string'),
                                total_interest=_nullable('string')))
DOCUMENT_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['pages', 'accounts'],
                   'properties': {
                       'pages': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                                 'required': ['page', 'printed_page_number', 'printed_page_total', 'is_statement_page'],
                                 'properties': {'page': {'type': 'integer'},
                                                'printed_page_number': _nullable('integer'),
                                                'printed_page_total': _nullable('integer'),
                                                'is_statement_page': {'type': 'boolean'}}}},
                       'accounts': {'type': 'array', 'items': _ACCOUNT}}}

# The one set of instructions for reading statement page images, sent to every provider (Neil, 2026-10-28: "when
# sending anything to openai the same advanced instructions you send to deepseek"). OpenAI receives the schema as its
# enforced response format; DeepSeek, which enforces none, receives it after these instructions (llm_service).
# Benchmarked as headless/ds_prompt_v3.txt (20 statements, image-checked answer key). No bank is a rule here: names
# in quotation marks are examples only. Change the text -> change PROMPT_VERSION (stored on every reading).
PROMPT_VERSION = 'statement-pages-v3'
PROMPT = """You are a forensic transcriber. The images are the pages of a bank, credit-union or card account statement. Your transcription goes into a forensic ledger used as evidence, and it is checked afterwards by strict arithmetic: opening balance plus every movement must equal the closing balance to the cent, every printed running balance must agree, and every printed total and count must match. One missed, doubled, mis-dated, mis-signed or mis-read line fails the whole statement. Accuracy matters far more than speed: work slowly, line by line.

These instructions apply to statements from any bank, in any language and layout. The examples in quotation marks show common wording; they are illustrations, not the only forms you will meet.

ABSOLUTE RULES
1. Transcribe only what is printed. Never calculate, infer, correct, round or complete a number, and never invent or drop a line to make figures add up. If the printed figures do not reconcile after careful re-reading, transcribe them as printed: the checker decides.
2. Every movement line printed for an account appears in rows exactly once.
3. If you cannot read a row's date or amount with certainty, still include the row with your best reading and set unreadable: true.
4. Return one JSON object only, no markdown, matching the given JSON Schema.

HOW THE IMAGES ARE GIVEN
- Each image is preceded by a label "Page N" or "Page N, part k of K". N is the page's position in the evidence file. It is NOT the page number printed on the statement, and it may be a large number such as 39 even for the first page of this statement. Wherever the schema asks for "page", give this label number N, never the printed page number.
- The pages may not be given in the statement's own order. Use the printed page numbers ("Page 2 of 6", "2 de 6", "PAGINA 2 / 6") to know the reading order.
- When a page is cut into horizontal strips (part 1 of K is the top), neighbouring strips OVERLAP: the last lines of one strip are repeated at the top of the next. A line seen in two strips is one line. Judge sameness by date, description, amount AND running balance together.

WORK IN THIS ORDER (internally; output only the JSON)
Step 1, survey. For each image note its label N, the printed page number and total, which accounts or sub-accounts it shows, and where each movement table starts and ends. Tables often continue across pages.
Step 2, header facts for each account (rules below).
Step 3, read every movement table line by line in the statement's reading order (printed page order, top to bottom). For each line with an amount in a movement column, record its date, description, amount, direction, running balance and page label.
Step 4, verify with the printed running balances. When the statement prints a running balance on its lines, walk your rows in order: each balance should equal the previous balance plus a credit or minus a debit. Where it does not, you have probably skipped a line, taken a line twice (often across a strip overlap or page break), put an amount in the wrong direction, or misread a digit. Go back to that exact spot in the image and re-read it. Fix only what the image shows; never change a number to make it fit. Two consecutive rows with the same running balance after a non-zero amount are almost always one line read twice.
Step 5, completeness. Re-check every strip once more: every movement line appears once, and no line was taken from a summary box, a totals line or a balance line.

PAGES (pages[])
One entry per image label: page = the label number N; printed_page_number / printed_page_total = exactly what is printed on that page, digit by digit (null when not printed or not certain); is_statement_page = false only for a page with no account information at all (blank, legal terms, advertising, cheque images without balances).

ACCOUNTS (accounts[]): one entry per account or sub-account that has its own opening and closing balance, in printed order.
- section_name: that section's printed heading, verbatim, including any ID printed with it (e.g. "ID 0040 FREE CHECKING", "CUENTA SANTANDER PYME").
- institution: the bank's name as printed.
- holder: the account holder name(s) exactly as printed in the name/address block or "Account holder" line. When several names are printed as joint holders, give all of them, one per line, separated by a newline, in printed order. Read each letter carefully: these are real people's or companies' names, so check easily confused letters (E/B/F, O/D/0, I/l/1, rn/m) against the rest of the name. Never use the bank's name, a street address or a column heading.
- account_number: the identifier of THIS section's account, exactly as printed, keeping masks such as ****1234.
  * When one statement covers several sub-accounts (shares, pockets, currency sub-accounts) under one customer/member number and each section prints its own short ID, give that section's own ID (e.g. "0000", "0040"), not the shared member number. When sections print no ID of their own, give the account number printed for the statement.
  * Prefer the number labelled as the account number ("Account Number", "No. de Cuenta", "Número de cuenta", "Cuenta"). Use an interbank/IBAN/CLABE-type number only when no account number is printed.
  * Never use a statement, page, document, routing/sort-code, branch, client, contract or card number of another product, a phone number, or a Bates/production stamp.
- currency: ISO code only when the statement prints the currency or its name (e.g. "M.N.", "Moneda Nacional", "PESOS" = MXN; "USD", "DÓLARES" = USD; "EUR"). A bare "$" or other symbol alone is not a currency: leave it empty. currency_as_printed: the literal text you used, else empty.
- period_start / period_end (YYYY-MM-DD): the statement period printed for this account. US statements write month/day/year; most others day/month/year: decide from the statement's language and from dates that only make sense one way (a 13 or higher must be a day). A statement that prints only a closing/statement date: period_end = that date, period_start empty. days_in_period: printed number of days, else null.
- opening_balance / closing_balance: the balances printed at the start and at the end of the period (e.g. "Previous Balance", "Beginning Balance", "Saldo Anterior", "Saldo Inicial"; "Ending Balance", "New Balance", "Saldo Final", "Saldo al Corte"), with the page label each is printed on. Negative only when printed negative (minus sign, parentheses, "DR"/"OD", or as the statement marks it).
- total_credits / total_debits and count_credits / count_debits: only when the statement prints a period total or count of money in / money out for this account; else null. Never add them up yourself.
- total_fees / total_interest: only when the statement prints a single line that is explicitly the period total of fees charged, or of interest charged, to the customer (e.g. "Total Fees for this Period", "Total Interest Charged for this Period"). Use null for anything else: commission or tax summaries that may break amounts down differently, interest earned or paid to the customer, year-to-date figures, rates, and any figure whose label you are not certain of.
- no_transactions_printed: true only when the statement explicitly says there were no movements for this account.

ROWS (rows[]): every movement line of the account, in the statement's reading order, across all its pages.
- page: the label number N of the image the line is printed on.
- date (YYYY-MM-DD): the date in the table's own date column, on the same printed line as the amount: the date the bank lists the line under.
  * If the table has two date columns side by side (e.g. "Fecha Oper." / "Fecha Liq.", "Trans. date" / "Post date"), use the leftmost one.
  * Other dates on or under the line (a card purchase date, a cheque date, a date inside the description or on a detail line, e.g. "08/31 0 0000089465 CASH APP") belong to the description. They are not the row's date.
  * If a line has no date of its own because the statement prints the date only once for a group of lines, use the last date printed above it in the date column.
  * Read the date on THE SAME printed line as the amount. Never take it from the line above or below. Dates in a table normally never go backwards; if yours do, re-read that spot.
  * Take the year from the statement period; for a period spanning two years, give each date the year of its month within the period.
- description: the first printed line of the entry, as printed. Detail lines under it belong to the same entry and are never separate rows.
- amount: exactly as printed in the movement column, digits with a dot decimal separator, no thousands separators, no currency symbol. Keep a minus sign when the statement prints one; never add one.
- direction: from where and how the amount is printed, never from arithmetic.
  * Separate money-in and money-out columns: the column the number sits under decides (money in = credit; money out = debit). Line each number up with its column heading.
  * A single amount column: a minus sign, parentheses, "DR" or the statement's own debit marker = debit. Otherwise decide from the line's meaning: deposit, transfer in, refund, interest or dividend paid to the customer = credit; withdrawal, purchase, cheque, fee, transfer out, payment = debit.
- balance_after: the running balance printed on that line, exactly as printed, else null. If two balance columns are printed, use the leftmost one.
- charge_kind: "fee" for a fee or commission charged to the customer, "interest" for interest charged to the customer, otherwise "". Interest earned is "".
- unreadable: true only when you cannot read the date or amount with certainty.
NEVER list as rows: opening, previous, closing or ending balance lines, "balance forward" lines, subtotals, totals, daily-balance tables, summary boxes, year-to-date figures, rate lines, or cheque-image captions.

FORMAT
All amounts use a dot as the decimal separator, no thousands separators, and a minus sign only where printed. Use "" or null for anything not printed. Output exactly one JSON object."""

# After the instructions: how many pages, and in how many strips each is given (strips: render_pages).
PAGES_NOTE = """

This statement has {pages} page(s), each given as {count} overlapping strip(s)."""


def document_pages(document, sent_pages):
    """The document reading as [(page, page json)] in the per-page form ``combine`` takes.

    Each account becomes one section per page it uses, under a name unique to it,
    so ``combine`` gives back exactly one section per account. A row or balance
    citing a page that was not sent raises NotProved.
    """
    sent = list(sent_pages)
    numbering = {entry.get('page'): entry for entry in document.get('pages') or []}
    if any(page not in numbering for page in sent):
        # Every page sent is described (its printed number), or the page-numbering check could not run.
        raise NotProved('The page-image reading does not describe every page that was read.')
    by_page = {page: [] for page in sent}
    for index, account in enumerate(document.get('accounts') or []):
        rows = account.get('rows') or []
        cited = [row.get('page') for row in rows] + [account.get(k) for k in ('opening_balance_page', 'closing_balance_page')
                                                      if account.get(k) is not None]
        if any(page not in by_page for page in cited):
            raise NotProved('The page-image reading cites a page that was not read.')
        used = sorted(set(cited) or {sent[0]}, key=sent.index)
        first, last = used[0], used[-1]
        for page in used:
            section = {key: '' for key in _SECTION['properties'] if _SECTION['properties'][key].get('type') == 'string'}
            section.update({key: None for key in ('opening_balance', 'closing_balance', 'total_credits', 'total_debits',
                                                  'count_credits', 'count_debits')})
            section.update(section_name='ACCOUNT %d' % (index + 1), account_number=account.get('account_number') or '',
                           rows=[{k: v for k, v in row.items() if k != 'page'} for row in rows if row.get('page') == page],
                           no_transactions_printed=bool(account.get('no_transactions_printed')) and page == first)
            if page == first:
                section.update({key: account.get(key) for key in ('institution', 'holder', 'currency', 'currency_as_printed',
                                'period_start', 'period_end', 'total_credits', 'total_debits', 'count_credits', 'count_debits')})
                for key in ('days_in_period', 'total_fees', 'total_interest'):
                    if account.get(key) is not None:
                        section[key] = account[key]
            if page == (account.get('opening_balance_page') or first):
                section['opening_balance'] = account.get('opening_balance')
            if page == (account.get('closing_balance_page') or last):
                section['closing_balance'] = account.get('closing_balance')
            by_page[page].append(section)
    return [(page, dict(printed_page_number=(numbering.get(page) or {}).get('printed_page_number'),
                        printed_page_total=(numbering.get(page) or {}).get('printed_page_total'),
                        is_statement_page=bool((numbering.get(page) or {}).get('is_statement_page', True)),
                        sections=by_page[page])) for page in sent]


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def _iso(value):
    try:
        parsed = date.fromisoformat(str(value or ''))
        return parsed.isoformat() if parsed.isoformat() == value else ''
    except ValueError:
        return ''


_GROUPED = re.compile(r'(-?)\$?\s*(\d{1,3}(?:,\d{3})+)(\.\d+)?')
_CODE = re.compile(r'\s*(?:[A-Z]{3}|M\.N\.|MN|DLLS?)\.?$')


def to_minor(value, exponent, *, signed=False):
    """'1234.56' -> 123456; None for anything not a plain decimal with at most the currency's places.

    Only two unambiguous print forms are normalised: a trailing currency code
    ('0.00 USD') and comma thousands groups of exactly three digits
    ('1,234,567.89'). Anything else (a comma decimal, odd grouping) is refused.
    """
    text = _CODE.sub('', str(value if value is not None else '').strip())
    grouped = _GROUPED.fullmatch(text)
    if grouped:
        text = grouped.group(1) + grouped.group(2).replace(',', '') + (grouped.group(3) or '')
    elif text.startswith('$') or text.startswith('-$'):
        text = text.replace('$', '').strip()
    if not re.fullmatch(r'-?\d{1,16}(\.\d{1,%d})?' % max(exponent, 1), text):
        return None
    if text.startswith('-') and not signed:
        return None
    try:
        amount = Decimal(text) * (Decimal(10) ** exponent)
    except InvalidOperation:
        return None
    return int(amount) if amount == amount.to_integral_value() else None


def row_amount(row, exponent):
    """The row's positive amount in minor units, or None; '-15.89' only on a debit (SIGNED_DEBITS)."""
    amount = row.get('amount')
    if SIGNED_DEBITS and row.get('direction') == 'debit' and str(amount or '').strip().startswith('-'):
        amount = str(amount).strip()[1:]
    return to_minor(amount, exponent)


def _digits(text):
    return re.sub(r'\D', '', str(text or ''))


def _exponent(currency):
    from services.financial.money import get_currency
    try:
        return get_currency(currency).exponent
    except Exception:  # noqa: BLE001 - an unknown code cannot be proved
        return None


class NotProved(Exception):
    """The image reading does not prove; ``str`` is the plain reason recorded for the investigator."""


# ---------------------------------------------------------------------------
# Combining pages into account sections
# ---------------------------------------------------------------------------

_HEADER = ('institution', 'holder', 'account_number', 'currency', 'period_start', 'period_end')


def _continued(merged, account, label, period):
    """The earlier section this one continues, or None for a new section.

    Same account (digits agree) and a compatible period; between sections of one
    account, the same printed section name, or one without a name yet. Without an
    account: the same section name, else the section just before (a continuation).
    """
    def period_ok(m):
        return not all(period) or not all(m['period']) or m['period'] == period
    if account:
        same = [m for m in merged if m['digits'] and (m['digits'].endswith(account) or account.endswith(m['digits']))
                and period_ok(m)]
        if label:
            return next((m for m in reversed(same) if m['label'] == label), None) or \
                next((m for m in reversed(same) if not m['label']), None)
        return same[-1] if same else None
    if label:
        named = next((m for m in reversed(merged) if m['label'] == label), None)
        if named is not None:
            return named
        if merged and merged[-1]['label']:
            return None  # a differently named section starts here
    return merged[-1] if merged else None


def _canonical(value):
    """A printed amount in one comparable form ('65,660.55' == '65660.55'), else its text."""
    minor = to_minor(value, 6, signed=True)
    return str(minor) if minor is not None else ' '.join(str(value).split())


def combine(pages):
    """[(page_number, page_json)] -> merged sections, each with its rows' page numbers.

    A section printing an account number starts (or continues) that account; a
    section without one continues the previous section. Conflicting printed
    values for one account section (two openings, two periods) raise NotProved.
    """
    merged = []
    for page_number, page in pages:
        for section in page.get('sections') or []:
            account = _digits(section.get('account_number'))
            label = ' '.join(str(section.get('section_name') or '').upper().split())
            period = (_iso(section.get('period_start')), _iso(section.get('period_end')))
            target = _continued(merged, account, label, period)
            if target is not None and label and not target['label']:
                target['label'] = label
            if target is None:
                target = dict(digits=account, label=label, period=('', ''), header={k: '' for k in _HEADER}, rows=[], pages=[],
                              values={}, balance_pages={}, no_transactions=False)
                merged.append(target)
            if account and len(account) > len(target['digits']):
                target['digits'] = account
            if all(period):
                if all(target['period']) and target['period'] != period:
                    raise NotProved('The page images print two different periods for one account section.')
                target['period'] = period
            for key in _HEADER:
                value = str(section.get(key) or '').strip()
                if value and not target['header'][key]:
                    target['header'][key] = value
            for key in ('opening_balance', 'closing_balance', 'total_credits', 'total_debits', 'count_credits', 'count_debits',
                        'days_in_period', 'total_fees', 'total_interest'):
                value = section.get(key)
                if value in (None, ''):
                    continue
                value = str(value).strip()
                if key in target['values'] and _canonical(target['values'][key]) != _canonical(value):
                    raise NotProved('The page images print two different values for the %s.' % key.replace('_', ' '))
                target['values'][key] = value
                target['balance_pages'].setdefault(key, page_number)
            target['no_transactions'] = target['no_transactions'] or bool(section.get('no_transactions_printed'))
            for row in section.get('rows') or []:
                target['rows'].append(dict(row, page=page_number))
            if page_number not in target['pages']:
                target['pages'].append(page_number)
    return merged


def check_page_numbering(pages, file_pages=None, printed_order=False):
    """NotProved when the printed numbering shows pages absent from the file.

    The numbering may count the whole printed document while this period uses
    only some of its pages; a page is missing when the file has fewer pages
    than printed, or a printed number is beyond the file. ``printed_order``: pages
    out of the file's order may pass in printed order (PRINTED_ORDER); True is then
    returned and the caller must check the order is the one it reads and saves.
    """
    totals = {page.get('printed_page_total') for _, page in pages if page.get('printed_page_total')}
    numbers = {page.get('printed_page_number') for _, page in pages if page.get('printed_page_number')}
    if len(totals) > 1:
        raise NotProved('The pages print different page counts; the period may combine two printings.')
    if totals:
        total = next(iter(totals))
        if not isinstance(total, int) or total < 1 or total > 500:
            raise NotProved('The printed page count could not be read.')
        count = len(file_pages) if file_pages else len(pages)
        if total > count or any(isinstance(n, int) and n > count for n in numbers):
            missing = sorted(set(range(1, total + 1)) - numbers)
            raise NotProved('The pages print %s pages but the file has %s; pages may be missing (printed pages not read: %s).' % (
                total, count, ', '.join(str(n) for n in missing[:10]) or 'none'))
    return _numbering_has_no_gap(pages, file_pages, next(iter(totals)) if totals else None, printed_order)


def _printed_run(numbers, file_pages, total, period_pages):
    """The printed numbers of the period's pages form one complete run first..last (no number twice, none missing),
    out of file order, and the printed pages before and after the run are at least pages of the file before and
    after the period's pages."""
    if len(numbers) < 2 or numbers == sorted(numbers) or \
            sorted(numbers) != list(range(min(numbers), min(numbers) + len(numbers))):
        return False
    file_pages = file_pages or period_pages
    before = len([p for p in file_pages if p < min(period_pages)])
    after = len([p for p in file_pages if p > max(period_pages)])
    return min(numbers) - 1 <= before and (not total or total - max(numbers) <= after)


def check_text_keeps_printed_order(document, proposal, pages):
    """NotProved when the page images print this period's pages out of the file's order and the text reading of the
    same file does not already keep them (its pages and its payment rows) in that printed order.

    The saved review places the page-image rows beside the text reading's rows, page by page, and the date checks
    follow the text reading's row order: both are in printed order only when the text reading is. Two readings agreeing
    on the order also settles a page number misread into another complete run.
    """
    numbering = {entry.get('page'): entry.get('printed_page_number') for entry in document.get('pages') or []}
    numbers = [numbering.get(page) for page in sorted(pages) if isinstance(numbering.get(page), int) and numbering[page] >= 1]
    if not PRINTED_ORDER or numbers == sorted(numbers):
        return
    order = list(pages)
    rows = [row.get('page_number') for row in proposal.get('rows') or [] if row.get('kind') in ('transaction', 'unresolved')
            and row.get('page_number') in order]
    positions = [order.index(page) for page in rows]
    if printed_order(document, order) != order or positions != sorted(positions):
        raise NotProved('The pages of this period are out of order in the file, and the text of the file does not '
                        'read them in the printed order; the payments could not be put in printed order.')


def printed_order(document, sent_pages):
    """The pages sent, numbered pages put in printed order (each into a place a numbered page held) when PRINTED_ORDER
    is on and their printed numbers form one complete run; else the pages as sent."""
    sent = list(sent_pages)
    numbering = {entry.get('page'): entry.get('printed_page_number') for entry in document.get('pages') or []}
    numbered = [page for page in sent if isinstance(numbering.get(page), int) and numbering[page] >= 1]
    numbers = [numbering[page] for page in numbered]
    if not PRINTED_ORDER or len(set(numbers)) != len(numbers) or \
            sorted(numbers) != list(range(min(numbers or [1]), min(numbers or [1]) + len(numbers))):
        return sent
    in_order = iter(sorted(numbered, key=numbering.get))
    return [next(in_order) if page in numbered else page for page in sent]


def _numbering_has_no_gap(pages, file_pages, total, printed_order=False):
    """NotProved when a printed page number between this period's pages is not one of them.

    With PRINTED_ORDER, pages whose printed numbers form one complete run pass in printed order
    whatever their order in the file (a file scanned in reverse). True when the pages pass only in printed
    order (the caller then checks the text reading keeps that order).
    """
    try:
        _numbering_in_file_order(pages, file_pages, total)
    except NotProved:
        numbers = [page.get('printed_page_number') for _, page in sorted(pages, key=lambda pair: pair[0])
                   if isinstance(page.get('printed_page_number'), int) and page.get('printed_page_number') >= 1]
        if not (printed_order and PRINTED_ORDER) or not _printed_run(numbers, file_pages, total, [p for p, _ in pages]):
            raise
        return True
    return False


def _numbering_in_file_order(pages, file_pages, total):
    """NotProved when a printed page number between this period's pages is not one of them.

    As the text reader's numbering rule: an unnumbered page of the period (cover,
    notice, reverse side) may stand in for a number only where it sits in the gap.
    Before the first and after the last numbered page the printed pages must at
    least be pages of the file (the numbering may count the whole printed document).
    """
    numbered, loose, previous = [], 0, None
    for physical, page in sorted(pages, key=lambda pair: pair[0]):
        number = page.get('printed_page_number')
        if not isinstance(number, int) or number < 1:
            loose += 1
            continue
        if previous is not None and number == previous:
            raise NotProved('Two pages of this period print the same page number (%s); the pages could not be '
                            'put in order.' % number)
        if previous is not None and (number < previous or number - previous - 1 > loose):
            raise NotProved('The printed page numbers of this period skip from page %s to page %s; '
                            'a page may be missing.' % (previous, number))
        numbered.append((physical, number))
        previous, loose = number, 0
    if not numbered:
        return
    file_pages = sorted(file_pages or [p for p, _ in pages])
    (first_physical, first), (last_physical, last) = numbered[0], numbered[-1]
    before = len([p for p in file_pages if p < first_physical])
    after = len([p for p in file_pages if p > last_physical])
    if first - 1 > before or (total and total - last > after):
        raise NotProved('The printed page numbers show pages of this statement that are not in the file; '
                        'a page may be missing.')


# ---------------------------------------------------------------------------
# Proof
# ---------------------------------------------------------------------------

def _movement(row, liability):
    return row['amount_minor'] * (1 if row['direction'] == 'credit' else -1) * (-1 if liability else 1)


def _rule_metadata(proposal):
    metadata = proposal.get('metadata') or {}
    return dict(currency=proposal.get('currency') or '', holder=metadata.get('holder') or '',
                account_number=metadata.get('account_number') or '', institution=metadata.get('institution') or '',
                period_start=metadata.get('period_start') or '', period_end=metadata.get('period_end') or '')


def same_number(a, b):
    """Two printed account references name the same account: equal, a masked suffix, or one embedded in
    the other (a CLABE or contract number carrying the account number), at least 8 digits."""
    from services.financial import field_proposals as fp
    a, b = _digits(a), _digits(b)
    if not a or not b:
        return False
    if fp.account_match(fp.account_identity(a), fp.account_identity(b)) or a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    if CLABE_ACCOUNT and len(shorter.lstrip('0')) >= 6 and _clabe_account(longer).lstrip('0') == shorter.lstrip('0'):
        return True
    return (len(shorter) >= 8 and shorter in longer) or (len(shorter) == 4 and longer.endswith(shorter))


def _clabe_account(digits):
    """The 11 account digits of an 18-digit CLABE whose check digit (weights 3, 7, 1) is right, else ''."""
    if len(digits) != 18 or not digits.isdigit():
        return ''
    check = (10 - sum(int(d) * w % 10 for d, w in zip(digits[:17], (3, 7, 1) * 6)) % 10) % 10
    return digits[6:17] if check == int(digits[17]) else ''


def _heading_numbers(proposal):
    """Numbers printed on a non-payment line of the text reading beside "CLABE <the statement's account>"."""
    account = _digits(_rule_metadata(proposal)['account_number'])
    if not SECTION_NUMBER or len(account) != 18:
        return set()
    numbers = set()
    for row in proposal.get('rows') or []:
        if row.get('kind') == 'transaction':
            continue
        line = ' '.join(str(c.get('expected_text') or '') for c in row.get('source_cells') or [])
        if not re.search(r'\bCLABE\s*' + account + r'\b', line, re.I):
            continue
        others = [n for n in re.findall(r'\d[\d-]*\d', re.sub(r'\bCLABE\s*' + account + r'\b', ' ', line, flags=re.I))
                  if len(_digits(n)) >= 8]
        if len(others) == 1:
            numbers.add(_digits(others[0]))
    return numbers


def same_account(number, proposal):
    """The number read from the page images names the statement's account: the same number, or the
    section heading's own number printed beside the statement's CLABE."""
    account = _rule_metadata(proposal)['account_number']
    return same_number(number, account) or (_digits(number) and _digits(number) in _heading_numbers(proposal))


def _period_end(section):
    return section['period'][1] or _iso(section['header'].get('period_end'))


def closing_days(section):
    """The printed days in the billing cycle of a section printing only its closing date (CLOSING_DAYS), else None."""
    value = str(section['values'].get('days_in_period') if section['values'].get('days_in_period') is not None else '').strip()
    if not value.isdigit() or not 1 <= int(value) <= MAX_CYCLE_DAYS:
        return None
    return int(value)


def choose_section(sections, proposal):
    rule = _rule_metadata(proposal)
    account = _digits(rule['account_number'])
    candidates = [s for s in sections if s['rows'] or s['values']]
    if account and len(account) >= 4:
        numbered = [s for s in candidates if s['digits'] and same_account(s['digits'], proposal)]
        # Sections printing no number (it is printed in the page header only) remain candidates
        # when no section prints this account's number.
        candidates = numbered or [s for s in candidates if not s['digits']]
    if rule['period_end'] and len(candidates) > 1:
        candidates = [s for s in candidates if _period_end(s) == rule['period_end']]
    if rule['currency'] and len(candidates) > 1:
        printed = [s for s in candidates if s['header']['currency'] == rule['currency']]
        if not printed and SECTION_BY_TEXT:
            printed = [s for s in candidates if not s['header']['currency']]
        candidates = printed
    if SECTION_BY_TEXT and len(candidates) > 1:
        agreeing = [s for s in candidates if _identified_by_text(proposal, s)]
        if len(agreeing) == 1:
            candidates = agreeing
    if not candidates:
        raise NotProved('The page images show no account section matching this statement.')
    if len(candidates) > 1:
        raise NotProved('The page images show %s account sections; the statement could not be matched to one.' % len(candidates))
    return candidates[0]


def _identified_by_text(proposal, section):
    """The text reading read both balances, they are this section's, and every payment it read cleanly is in it."""
    from services.financial.review_arithmetic import integer
    exponent = _exponent(proposal.get('currency') or '')
    if exponent is None:
        return False
    balances = {}
    for row in proposal.get('rows') or []:
        if row.get('kind') == 'balance':
            role = ((row.get('fields') or {}).get('description') or '').strip().lower()
            value = integer((row.get('fields') or {}).get('balance'))
            if role in ('opening balance', 'closing balance') and value is not None:
                balances[role.split()[0]] = value
    if set(balances) != {'opening', 'closing'}:
        return False
    for which in ('opening', 'closing'):
        if to_minor(section['values'].get(which + '_balance'), exponent, signed=True) != balances[which]:
            return False
    rows = []
    for row in section['rows']:
        amount = row_amount(row, exponent)
        if amount is None or row.get('direction') not in ('credit', 'debit'):
            return False
        rows.append(dict(amount_minor=amount, direction=row['direction']))
    try:
        _agrees_with_rule_reading(proposal, rows, balances['opening'], balances['closing'])
    except NotProved:
        return False
    return True


def one_account_spelled_apart(candidates, account_text, institution, holder):
    """(candidates, matched) when the saved accounts matching a full printed number are one account
    saved twice under bank spellings that name the same bank, else ([], {'ambiguous'}).

    matching_accounts calls them ambiguous because their bank spellings differ. They are accepted
    as one only when: the switch is on, the bank is printed, the statement's number is printed in
    full, every candidate holds exactly that full number (none masked), every saved bank spelling
    names the same bank as every other and as the printed one, and the holder is printed, every
    candidate records a holder, and the printed holder agrees with every saved one. Anything else
    stays ambiguous (held)."""
    from services.financial import field_proposals as fp
    digits, masked = fp.account_identity(account_text)
    if not (SPLIT_SPELLINGS and candidates and digits and not masked and institution):
        return [], {'ambiguous'}
    if any(k.masked or k.digits != digits for k in candidates):
        return [], {'ambiguous'}
    banks = [i for k in candidates for i in (k.values('institution') or ([k.institution] if k.institution else []))]
    if not all(k.values('institution') or k.institution for k in candidates) or not all(fp.same_institution(a, b) for a in banks + [institution]
                                                for b in banks + [institution]):
        return [], {'ambiguous'}
    if not (holder and all(k.values('holder') for k in candidates)):
        return [], {'ambiguous'}
    if SECTION_BY_TEXT:
        # The printed holder is saved on a record, and every record shares a holder with those records.
        anchors = [k for k in candidates if any(fp.same_holder(holder, h) for h in k.values('holder'))]
        names = [holder] + [h for k in anchors for h in k.values('holder')]
        if not anchors or not all(any(fp.same_holder(h, n) for h in k.values('holder') for n in names) for k in candidates):
            return [], {'ambiguous'}
    elif not all(fp.same_holder(holder, h) for k in candidates for h in k.values('holder')):
        return [], {'ambiguous'}
    return candidates, {'account', 'institution', 'holder'}


def first_statement_header(rule, header):
    """(FIRST_STATEMENT) The page images and the text reading of the same file agree on the full account number,
    the holder and the bank: each read by both, the number printed in full by both (no mask, at least
    FIRST_STATEMENT_MIN_DIGITS digits, the same digits), the holder the same person and the bank the same bank."""
    from services.financial import field_proposals as fp
    if not FIRST_STATEMENT:
        return False
    numbers = [fp.account_identity(rule['account_number']), fp.account_identity(header['account_number'])]
    if any(masked or len(digits or '') < FIRST_STATEMENT_MIN_DIGITS for digits, masked in numbers):
        return False
    if numbers[0][0] != numbers[1][0] or _digits(rule['account_number']) != _digits(header['account_number']):
        return False
    if not (rule['holder'] and header['holder'] and fp.same_holder(rule['holder'], header['holder'])):
        return False
    return bool(rule['institution'] and header['institution']
                and fp.same_institution(rule['institution'], header['institution']))


def prove(proposal, section, knowledge):
    """The proved reading {details, opening, closing, rows, pages} or NotProved with the reason."""
    from services.financial import field_proposals as fp
    rule = _rule_metadata(proposal)
    header = section['header']
    liability = (proposal.get('metadata') or {}).get('balance_convention') == 'liability_owed'
    # Header against the rule reading, wherever that read a value.
    account_text = rule['account_number'] or header['account_number']
    if not _digits(account_text):
        raise NotProved('The account number could not be read from the page images.')
    if rule['account_number'] and header['account_number'] and not same_account(header['account_number'], proposal):
        raise NotProved('The account number read from the page images differs from the one read from the text.')
    for field, same in (('holder', fp.same_holder), ('institution', fp.same_institution)):
        if rule[field] and header[field] and not same(rule[field], header[field]):
            raise NotProved('The %s read from the page images differs from the one read from the text.' % (
                'account holder' if field == 'holder' else 'bank'))
    start, end = section['period']
    if not end:
        end = _period_end(section)
        start = _iso(section['header'].get('period_start'))
    earliest = None
    if not start and end and CLOSING_DAYS:
        days = closing_days(section)
        if days:
            # Only the closing date and the days in the billing cycle are printed: two printed facts (B1); a start
            # the text reading has must be this one (checked below).
            start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
            if TEXT_MISREADS and liability:
                earliest = (date.fromisoformat(start) - timedelta(days=POSTING_DAYS)).isoformat()
    if not start and end and rule['period_start'] and rule['period_end'] == end:
        # Only the end is printed with this section; the start is the text reading's for the same period.
        start = rule['period_start']
    if not (start and end and start <= end):
        raise NotProved('The statement period could not be read from the page images.')
    if (rule['period_start'] and rule['period_start'] != start) or (rule['period_end'] and rule['period_end'] != end):
        raise NotProved('The period read from the page images differs from the one read from the text.')
    # Header against the account's saved statements: the same printed number at the same bank
    # (fail closed when two different accounts could be meant).
    holder_printed = header['holder'] or rule['holder']
    institution_printed = header['institution'] or rule['institution']
    candidates, matched = fp.matching_accounts(dict(account_number=account_text, institution=institution_printed), knowledge)
    if matched == {'ambiguous'}:
        candidates, matched = one_account_spelled_apart(candidates, account_text, institution_printed, holder_printed)
    first_statement = False
    if not candidates and not matched & {'ambiguous'}:
        # Truly the first: no saved account of the case carries this number at all (at any bank, full or masked).
        identity = fp.account_identity(account_text)
        first_statement = first_statement_header(rule, header) and not any(
            fp.account_match(identity, (known.digits, known.masked)) for known in getattr(knowledge, 'accounts', []) or [])
        if not first_statement:
            raise NotProved('This account has no saved statement in the case to confirm the page-image reading against.')
    elif not candidates or 'ambiguous' in matched or 'account' not in matched:
        raise NotProved('This account has no saved statement in the case to confirm the page-image reading against.')
    partial = not first_statement and ('masked' in matched or not rule['account_number'])
    if partial and not holder_printed:
        # Only some digits agree, or only the page images print the number: another account at the
        # bank could end the same way, so the printed holder must also agree (checked below).
        raise NotProved('The account holder is not printed, so the account could not be confirmed from a partial number.')

    def currencies(known):
        return set(known.values('currency')) or ({known.currency} if known.currency else set())
    # One number can hold several currency sub-accounts, each saved as its own account.
    printed = {c for c in (rule['currency'], header['currency']) if c}
    if len(printed) > 1:
        raise NotProved('The currency read from the page images differs from the one read from the text.')
    if first_statement and not printed:
        raise NotProved('The currency is not printed, and this account has no saved statement to take it from.')
    if printed:
        currency = next(iter(printed))
        candidates = [k for k in candidates if currencies(k) == {currency}]
        if not candidates and not first_statement:
            raise NotProved('The currency differs from the saved statements of this account.')
    else:
        known_currencies = set().union(*(currencies(k) for k in candidates))
        if len(known_currencies) != 1:
            raise NotProved('The currency is not printed and the saved statements of this account have more than one.')
        currency = next(iter(known_currencies))
    saved_holders = [h for k in candidates for h in k.values('holder')]
    saved_institutions = [i for k in candidates for i in k.values('institution')] or [k.institution for k in candidates if k.institution]
    holder = holder_printed or (saved_holders[-1] if saved_holders and len({fp.holder_key(h) for h in saved_holders}) == 1 else '')
    institution = institution_printed or (saved_institutions[-1] if saved_institutions else '')
    if partial and not (saved_holders and saved_institutions and institution_printed):
        # A partial number is confirmed only by a printed holder and bank the saved statements also record.
        raise NotProved('The account could not be confirmed from a partial number: the saved statements of this '
                        'account do not record the holder and bank to compare.')
    if not holder or (saved_holders and not any(fp.same_holder(holder, h) for h in saved_holders)):
        raise NotProved('The account holder could not be confirmed against the saved statements of this account.')
    if not institution or (saved_institutions and not all(fp.same_institution(institution, i) for i in saved_institutions)):
        raise NotProved('The bank could not be confirmed against the saved statements of this account.')
    exponent = _exponent(currency)
    if exponent is None:
        raise NotProved('The currency is not supported.')
    # Balances.
    opening = to_minor(section['values'].get('opening_balance'), exponent, signed=True)
    closing = to_minor(section['values'].get('closing_balance'), exponent, signed=True)
    derive_opening = OPENING_FROM_PREVIOUS and opening is None and closing is not None and not liability
    if (opening is None and not derive_opening) or closing is None:
        raise NotProved('The opening or closing balance could not be read from the page images.')
    # Rows.
    rows = []
    for index, row in enumerate(section['rows']):
        amount = row_amount(row, exponent)
        if CLOSING_DAYS and amount == 0 and not row.get('unreadable') and row.get('charge_kind') in ('fee', 'interest'):
            continue  # a charge line printed as 0.00 moves nothing
        when = _iso(row.get('date'))
        if row.get('unreadable') or not amount or not when or row.get('direction') not in ('credit', 'debit') \
                or not str(row.get('description') or '').strip():
            raise NotProved('A payment on page %s could not be read with certainty from the page image.' % row['page'])
        if not (earliest or start) <= when <= end:
            raise NotProved('A payment on page %s is dated outside the statement period.' % row['page'])
        balance = None
        if row.get('balance_after') not in (None, ''):
            balance = to_minor(row['balance_after'], exponent, signed=True)
            if balance is None:
                raise NotProved('A running balance on page %s could not be read.' % row['page'])
        rows.append(dict(index=index, date=when, description=' '.join(str(row['description']).split())[:4000],
                         amount_minor=amount, direction=row['direction'], balance_minor=balance, page=row['page'],
                         charge_kind=row.get('charge_kind') or ''))
    previous_end = None
    if derive_opening:
        opening, previous_end = _opening_from_previous(section, rows, closing, candidates, currency, start, end,
                                                       exponent)
    if not rows and not _printed_quiet(section, opening, closing, exponent):
        raise NotProved('No payments were read from the page images; a period without payments needs its printed confirmation.')
    _not_summary_lines(section, rows, exponent)
    _directions_from_running_balances(rows, opening, closing, liability)
    expected = opening + sum(_movement(r, liability) for r in rows)
    if expected != closing:
        raise NotProved('The page-image reading did not balance: the payments come to %s, the printed closing balance is %s (difference %s).'
                        % (_show(expected, exponent), _show(closing, exponent), _show(expected - closing, exponent)))
    if not _running_ok(rows, opening, liability):
        raise NotProved('A printed running balance does not agree with the payments read before it.')
    for direction in ('credit', 'debit'):
        printed = section['values'].get('total_%ss' % direction)
        if printed is not None:
            total = to_minor(printed, exponent)
            if total is None or total != sum(r['amount_minor'] for r in rows if r['direction'] == direction):
                raise NotProved('The %s read do not add up to the printed total.' % ('credits' if direction == 'credit' else 'charges'))
        count = section['values'].get('count_%ss' % direction)
        if count is not None:
            if not str(count).isdigit() or int(count) != sum(r['direction'] == direction for r in rows):
                raise NotProved('The number of %s read differs from the printed count.' % ('credits' if direction == 'credit' else 'charges'))
    _agrees_with_rule_reading(proposal, rows, opening, closing)
    if ROW_DATES:
        _dates_in_order(rows)
        _dates_agree_with_text(proposal, rows, exponent)
    charges = charge_totals(proposal, section, rows, exponent) if CLOSING_DAYS else {}
    return dict(account_keys=[k.key for k in candidates], currency=currency, holder=holder, institution=institution,
                account_number=account_text, charge_totals=charges,
                **(dict(account_basis=FIRST_STATEMENT_BASIS) if first_statement else {}),
                period_start=start, period_end=end, opening=opening, closing=closing, rows=rows,
                opening_page=section['balance_pages'].get('opening_balance') if previous_end is None else rows[0]['page'],
                closing_page=section['balance_pages'].get('closing_balance'),
                # The printed totals the proof checked against the payments read (IMAGE_TOTALS).
                printed_totals={d: to_minor(section['values']['total_%ss' % d], exponent) for d in ('credit', 'debit')
                                if section['values'].get('total_%ss' % d) is not None},
                **({} if previous_end is None else dict(opening_previous_end=previous_end)))


def _opening_from_previous(section, rows, closing, candidates, currency, start, end, exponent):
    """(OPENING_FROM_PREVIOUS) (opening, previous period end) of an asset account section whose opening balance the
    pages do not print. Every payment is read and the images show both directions' counts and totals, each agreeing
    with the payments; the opening is the closing less the payments. A saved statement of the account in this currency
    next to the period (at most ADJACENT_DAYS apart) must confirm it: the latest before it closing at that opening, or
    the first after it opening at the closing read; none of them may disagree. Returns which one confirmed it.
    NotProved otherwise."""
    from datetime import timedelta
    values = section['values']
    for direction in ('credit', 'debit'):
        total, count = values.get('total_%ss' % direction), values.get('count_%ss' % direction)
        mine = [r for r in rows if r['direction'] == direction]
        if (total is None or count is None or to_minor(total, exponent) != sum(r['amount_minor'] for r in mine)
                or not str(count).isdigit() or int(count) != len(mine)):
            raise NotProved('The opening balance is not printed in these pages, and the printed counts and totals '
                            'that would fix it were not all read in agreement with the payments.')
    if not rows:
        raise NotProved('The opening balance is not printed in these pages.')
    opening = closing - sum(_movement(r, False) for r in rows)
    begins, ends = date.fromisoformat(start), date.fromisoformat(end)
    statements = [s for k in candidates for s in k.statements if (s.currency or '').upper() == currency
                  and s.period_start and s.period_end]
    before = [s for s in statements if s.period_end < start
              and begins - date.fromisoformat(s.period_end) <= timedelta(days=ADJACENT_DAYS)]
    after = [s for s in statements if s.period_start > end
             and date.fromisoformat(s.period_start) - ends <= timedelta(days=ADJACENT_DAYS)]
    last = max((s.period_end for s in before), default=None)
    first = min((s.period_start for s in after), default=None)
    previous = [s.closing_minor for s in before if s.period_end == last and s.closing_minor is not None]
    following = [s.opening_minor for s in after if s.period_start == first and s.opening_minor is not None]
    if any(value != opening for value in previous) or any(value != closing for value in following):
        raise NotProved('The opening balance is not printed in these pages, and the payments read do not lead back '
                        'to the balances of the saved statements next to this period.')
    if not previous and not following:
        raise NotProved('The opening balance is not printed in these pages, and the account has no saved statement '
                        'next to this period to confirm it.')
    return opening, (('the previous saved statement, to ' + last) if previous else
                     ('the next saved statement, from ' + first))


def charge_totals(proposal, section, rows, exponent):
    """{scope: printed total} for each fee/interest total the images print, proved equal to the charge lines of
    its kind read and to the text's reading of that total where the text read it; NotProved otherwise."""
    from services.financial.review_arithmetic import integer
    proved = {}
    for scope, key in (('fee', 'total_fees'), ('interest', 'total_interest')):
        printed = section['values'].get(key)
        if printed in (None, ''):
            continue
        total = to_minor(printed, exponent)
        if total is None:
            raise NotProved('The printed %s total could not be read from the page images.' % scope)
        # A charge is money out; a refunded charge of the kind counts against it.
        lines = sum(r['amount_minor'] * (1 if r['direction'] == 'debit' else -1) for r in rows if r.get('charge_kind') == scope)
        if lines != total:
            raise NotProved('The %s charges read do not add up to the printed %s total.' % (scope, scope))
        for control in proposal['rows']:
            fields = control.get('fields') or {}
            if control.get('kind') == 'statement_total' and fields.get('total_scope') == scope:
                text = integer(fields.get('balance'))
                if text is not None and text != total:
                    raise NotProved('The printed %s total read from the page images differs from the one read from the text.' % scope)
        proved[scope] = total
    return proved


def _printed_quiet(section, opening, closing, exponent):
    """The images print this section's deposit and withdrawal counts as 0, both totals as zero and equal balances."""
    values = section['values']
    return bool(QUIET_PRINTED and opening == closing
                and all(str(values.get('count_%ss' % d)) == '0' and to_minor(values.get('total_%ss' % d), exponent) == 0
                        for d in ('credit', 'debit')))


def printed_controls(proposal, section, reading, request):
    """The period's deposit and withdrawal counts and totals printed on the images, when all four are printed (each
    already proved equal to the payments read), with the balance rows of the review they belong to; else None."""
    values = section['values']
    exponent = _exponent(reading['currency'])
    controls = {}
    for direction in ('credit', 'debit'):
        count, total = values.get('count_%ss' % direction), to_minor(values.get('total_%ss' % direction), exponent)
        if not str(count).isdigit() or total is None:
            return None
        controls['count_%ss' % direction], controls['total_%ss_minor' % direction] = int(str(count)), total
    originals = {row['id']: row for row in proposal['rows']}
    ends = {}
    for row in request['rows']:
        if row['id'] in ('manual:opening-balance', 'manual:closing-balance'):
            ends[row['id'][len('manual:'):].split('-')[0]] = row['id']
        elif originals.get(row['id'], {}).get('kind') == 'balance':
            role = (originals[row['id']]['fields'].get('description') or '').strip().lower()
            if role in ('opening balance', 'closing balance'):
                ends.setdefault(role.split()[0], row['id'])
    return dict(controls, opening_minor=reading['opening'], closing_minor=reading['closing'], currency=reading['currency'],
                period_start=reading['period_start'], period_end=reading['period_end'], balance_rows=ends)


def image_evidence(proposal, controls, charges=None):
    """What a proved page-image reading adds to the statement's reading: its printed controls, its proved fee and
    interest totals (CLOSING_DAYS), and for a quiet period the source proof of no activity
    (statement_admission.source_proves_no_activity checks it against the review's balance rows and period)."""
    extra = dict(image_charge_totals=charges) if charges and CLOSING_DAYS else {}
    if not controls:
        return extra
    extra.update(image_printed_controls=controls)
    quiet = (QUIET_PRINTED and controls['count_credits'] == 0 and controls['count_debits'] == 0
             and controls['total_credits_minor'] == 0 and controls['total_debits_minor'] == 0
             and controls['opening_minor'] == controls['closing_minor'])
    ends = controls.get('balance_rows') or {}
    if quiet and set(ends) == {'opening', 'closing'} and not (proposal.get('no_activity_evidence') or {}).get('verified'):
        extra['no_activity_evidence'] = dict(verified=True, method='page-image-zero-counts-v1', basis='page_image_zero_counts',
            family='page_image', opening_row_id=ends['opening'], closing_row_id=ends['closing'],
            balance_minor=str(controls['opening_minor']), currency=controls['currency'],
            period_start=controls['period_start'], period_end=controls['period_end'])
    return extra


def stored_image_evidence(file, result):
    """image_evidence of the proved page-image reading stored for this same reading of the statement (outside the
    reading revision, like the page gap it settles)."""
    if not (PRINTED_COUNTS or QUIET_PRINTED):
        return {}
    record = _stored(file, result.get('statement_id') or '')
    if not record or record.get('status') != 'proved' or record.get('revision') != result.get('revision'):
        # A saved statement's page reading (read_saved), proved for this same reading.
        record = ((file.metadata_ or {}).get(SAVED_KEY) or {}).get(result.get('statement_id') or '') if SAVED_READING else None
    if not record or record.get('status') != 'proved' or record.get('revision') != result.get('revision'):
        return {}
    return image_evidence(result, record.get('printed_controls'), record.get('charge_totals'))


def _not_summary_lines(section, rows, exponent):
    """A reading whose only rows are the printed period totals has read the summary, not the movements."""
    totals = {direction: to_minor(section['values'].get('total_%ss' % direction), exponent) for direction in ('credit', 'debit')}
    counts = {direction: section['values'].get('count_%ss' % direction) for direction in ('credit', 'debit')}
    by_direction = {direction: [r for r in rows if r['direction'] == direction] for direction in ('credit', 'debit')}
    echoed = [d for d in ('credit', 'debit') if len(by_direction[d]) == 1 and totals[d] is not None
              and by_direction[d][0]['amount_minor'] == totals[d] and str(counts[d]) != '1']
    if echoed and sum(len(v) for v in by_direction.values()) == len(echoed):
        raise NotProved('The page-image reading lists only the printed period totals, not the payments.')


ADJACENT_DAYS = 3


def check_neighbours(db, case_id, reading):
    """The account's saved statements next to this period agree with it; none overlaps it.

    The previous saved period ending at most ADJACENT_DAYS before this start must
    close at this opening; the next one starting at most ADJACENT_DAYS after this end
    must open at this closing (where those balances are recorded). A saved period of
    the same account and currency overlapping this one holds it (a decision).
    """
    from datetime import timedelta
    from postgres.models.financial import (FinancialSourceDocument as Source, FinancialStatementPeriod as Period)
    keys = [UUID(key) for key in reading['account_keys']]
    start, end = date.fromisoformat(reading['period_start']), date.fromisoformat(reading['period_end'])
    rows = db.execute(select(Period.period_start, Period.period_end, Period.opening_balance_minor, Period.closing_balance_minor)
        .join(Source, Source.id == Period.source_document_id)
        .where(Period.case_id == case_id, Period.account_id.in_(keys), Period.currency == reading['currency'],
               Source.status == 'admitted', Source.metadata_['financial_import_removal'].as_string().is_(None))).all()
    for saved_start, saved_end, opening, closing in rows:
        if saved_start and saved_end and saved_start <= end and start <= saved_end:
            raise NotProved('A saved statement of this account already covers part of this period.')
        if saved_end and timedelta(0) < start - saved_end <= timedelta(days=ADJACENT_DAYS) and closing is not None \
                and closing != reading['opening']:
            raise NotProved('The opening balance differs from the closing balance of the previous saved statement.')
        if saved_start and timedelta(0) < saved_start - end <= timedelta(days=ADJACENT_DAYS) and opening is not None \
                and opening != reading['closing']:
            raise NotProved('The closing balance differs from the opening balance of the next saved statement.')


def _show(minor, exponent):
    sign = '-' if minor < 0 else ''
    whole, part = divmod(abs(minor), 10 ** exponent)
    return f'{sign}{whole:,}' + (f'.{part:0{exponent}d}' if exponent else '')


def _directions_from_running_balances(rows, opening, closing, liability):
    """Each payment's direction from the printed running balances, when they settle every one.

    Only when every row prints its balance after, each balance differs from the one before
    (the opening for the first) by exactly the row's amount, and the last is the printed
    closing balance: then the balances, not the column the model put the amount in, say
    whether money came in or went out. Otherwise nothing changes (the checks below decide).
    """
    if not rows or any(r['balance_minor'] is None for r in rows) or rows[-1]['balance_minor'] != closing:
        return 0
    directions, before = [], opening
    for row in rows:
        change = (row['balance_minor'] - before) * (-1 if liability else 1)
        if abs(change) != row['amount_minor']:
            return 0
        directions.append('credit' if change > 0 else 'debit')
        before = row['balance_minor']
    disagree = sum(row['direction'] != direction for row, direction in zip(rows, directions))
    # Only a slip on a few rows: the rows read the same way as the balances confirm the sign
    # convention. Many disagreeing (a card read as an account, or every balance's sign lost)
    # would flip the whole reading; then nothing changes and the checks below hold it.
    if disagree == 0 or disagree > max(1, len(rows) // 10) or len(rows) - disagree < 3:
        return 0
    corrected = 0
    for row, direction in zip(rows, directions):
        if row['direction'] != direction:
            row['direction'], row['direction_from_balance'] = direction, True
            corrected += 1
    return corrected


def _running_ok(rows, opening, liability):
    """Every printed running balance agrees in printed order (or, for a reverse-printed list, in reverse)."""
    if not any(r['balance_minor'] is not None for r in rows):
        return True
    for sequence in (rows, list(reversed(rows))):
        balance, ok = opening, True
        for row in sequence:
            balance += _movement(row, liability)
            if row['balance_minor'] is not None and row['balance_minor'] != balance:
                ok = False
                break
        if ok:
            return True
    return False


def _forward(dates):
    return all(a <= b for a, b in zip(dates, dates[1:]))


def _ordered(dates):
    return _forward(dates) or _forward(dates[::-1])


def _dates_in_order(rows):
    """(ROW_DATES) The rows run in date order as printed: the whole section forward or in reverse, or, when it prints
    each direction in a block of its own (deposits, then withdrawals), each block, all in the same order."""
    if _ordered([r['date'] for r in rows]):
        return
    blocks, seen = [], set()
    for row in rows:
        if not blocks or blocks[-1][0] != row['direction']:
            if row['direction'] in seen:
                break
            seen.add(row['direction'])
            blocks.append((row['direction'], []))
        blocks[-1][1].append(row)
    else:
        for oriented in (lambda d: d, lambda d: d[::-1]):
            if all(_forward(oriented([r['date'] for r in block])) for _, block in blocks):
                return
    page = next(b['page'] for a, b in zip(rows, rows[1:]) if b['date'] < a['date'])
    raise NotProved('The payment dates read from the page images are out of printed order on page %s.' % page)


_BESIDE_DATE = 'Check the additional date printed beside this payment.'


def _dates_agree_with_text(proposal, rows, exponent):
    """(ROW_DATES) Every payment the text of the file reads cleanly, with its date, whose amount and direction the
    page images also read, is in the page-image reading on that same date."""
    from collections import Counter
    from services.financial.review_arithmetic import integer
    available = Counter((r['amount_minor'], r['direction'], r['date']) for r in rows)
    read = {(r['amount_minor'], r['direction']) for r in rows}
    for row in proposal['rows']:
        fields = row.get('fields') or {}
        # A row held only for the second date printed beside it (Andrews "09/01 08/31 Debit Card") has its own date read.
        if row.get('kind') != 'transaction' or row.get('excluded') or not all(str(issue).startswith(_BESIDE_DATE) for issue in row.get('issues') or ()):
            continue
        amount, when = integer(fields.get('amount_minor')), _iso(fields.get('date'))
        if not when or (amount, fields.get('direction')) not in read:
            continue
        key = (amount, fields['direction'], when)
        if available[key]:
            available[key] -= 1
            continue
        raise NotProved('A payment of %s the text of the file dates %s is dated differently in the page-image reading.'
                        % (_show(amount, exponent), when))


def _misread_of(amount, direction, row):
    """Whether a text payment (amount, direction) is a misreading of this image row (TEXT_MISREADS): the same
    amount the other way, or the same way with the same number of digits and exactly one digit different."""
    if amount == row['amount_minor']:
        return direction != row['direction']
    a, b = str(amount), str(row['amount_minor'])
    return direction == row['direction'] and len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1


def _agrees_with_rule_reading(proposal, rows, opening, closing):
    """Every cleanly read text payment is in the image reading; every read text balance is the same."""
    from collections import Counter
    from services.financial.review_arithmetic import integer
    available = Counter((r['amount_minor'], r['direction']) for r in rows)
    misread = []  # text payments not found as read, kept for the misreading rule
    missing = 0
    for row in proposal['rows']:
        fields = row.get('fields') or {}
        if row.get('kind') == 'balance':
            value = integer(fields.get('balance'))
            role = (fields.get('description') or '').strip().lower()
            if value is not None and ((role == 'opening balance' and value != opening) or
                                      (role == 'closing balance' and value != closing)):
                raise NotProved('The %s read from the page images differs from the one read from the text.' % role)
            continue
        if row.get('kind') != 'transaction' or row.get('excluded') or row.get('issues'):
            continue
        amount = integer(fields.get('amount_minor'))
        if amount is None or amount <= 0 or fields.get('direction') not in ('credit', 'debit'):
            continue
        key = (amount, fields['direction'])
        if available[key]:
            available[key] -= 1
        else:
            misread.append((amount, fields['direction'], fields.get('date')))
    if misread and TEXT_MISREADS:
        # Image rows no text payment took as read, by date (TEXT_MISREADS).
        left = []
        for r in rows:
            if available[(r['amount_minor'], r['direction'])]:
                available[(r['amount_minor'], r['direction'])] -= 1
                left.append(r)
        for amount, direction, when in misread:
            match = next((r for r in left if when and r.get('date') == when and _misread_of(amount, direction, r)), None)
            if match is None:
                missing += 1
            else:
                left.remove(match)
    else:
        missing = len(misread)
    if missing:
        raise NotProved('%s payment%s read from the text %s not found in the page-image reading.' % (
            missing, '' if missing == 1 else 's', 'was' if missing == 1 else 'were'))


# ---------------------------------------------------------------------------
# The review the proved reading becomes
# ---------------------------------------------------------------------------

# The Kapital/Intercam reader holds a line whose DIA cell the scan lost with its own wording (fin-queue3 re-run of
# 10 ARRENDO INTERCAM OCT 2022: the image read the day, but the row counted as held for more than its date).
_DATE_ISSUES = ('Check the full date in the PDF.', 'Check the additional date printed beside this payment.',
                'Check the printed day against this statement period.')


def dates_request(proposal, readings):
    """(DATES_FROM_IMAGE) The text reading's review with its unread row dates read from the page images, or NotProved."""
    from services.financial.import_batches import assess, initial_request
    from services.financial.review_arithmetic import integer
    exponent = _exponent(proposal.get('currency') or '')
    rule = _rule_metadata(proposal)
    if exponent is None or not (rule['period_start'] and rule['period_end']):
        raise NotProved('The period of the text reading is not complete.')
    payments = [r for r in proposal['rows'] if not r.get('excluded') and r.get('kind') in ('transaction', 'unresolved')]
    held = [r for r in proposal['rows'] if not r.get('excluded') and r.get('issues')]
    if not held:
        raise NotProved('The text reading holds no row for a date.')
    image_rows = [dict(row, page=page) for page, document in readings for section in document.get('sections') or []
                  for row in section.get('rows') or []]
    dates = {}
    for row in held:
        fields = row.get('fields') or {}
        if row.get('kind') != 'transaction' or fields.get('date') or not all(
                any(issue.startswith(prefix) for prefix in _DATE_ISSUES) for issue in row['issues']):
            raise NotProved('The text reading holds a row for more than its date.')
        amount, balance = integer(fields.get('amount_minor')), integer(fields.get('balance'))
        if not amount or balance is None or fields.get('direction') not in ('credit', 'debit'):
            raise NotProved('A row held for its date has no amount or running balance.')
        same = [r for r in image_rows if r['page'] == row.get('page_number') and not r.get('unreadable')
                and r.get('direction') == fields['direction'] and row_amount(r, exponent) == amount
                and to_minor(r.get('balance_after'), exponent, signed=True) == balance]
        when = _iso(same[0].get('date')) if len(same) == 1 else ''
        if not when or not rule['period_start'] <= when <= rule['period_end']:
            raise NotProved('The page images do not give one date for the payment on page %s.' % row.get('page_number'))
        index = payments.index(row)
        before = [r['fields']['date'] for r in payments[:index] if (r.get('fields') or {}).get('date')]
        after = [r['fields']['date'] for r in payments[index + 1:] if (r.get('fields') or {}).get('date')]
        if (before and when < before[-1]) or (after and when > after[0]):
            raise NotProved('The date read from the page images is outside the printed payment order on page %s.'
                            % row.get('page_number'))
        dates[row['id']] = (when, row.get('page_number'))
    request = initial_request(proposal)
    for entry in request['rows']:
        if entry['id'] in dates:
            entry.update(date=dates[entry['id']][0], reason=DATE_REASON.format(page=dates[entry['id']][1]))
    state, summary = assess(proposal, request)
    if state != 'ready' or summary.get('problems') or summary.get('problem_count'):
        first = next((p.get('message') for p in summary.get('problems') or [] if p.get('message')), '')
        raise NotProved('With the dates from the page images the statement still has a check: ' + (first or state))
    return request


def row_reason(page, by=None):
    """A row's provenance: the page it is read from and, in a chain, which provider read it."""
    reason = ROW_REASON.format(page=page)
    return reason[:-1] + f', by {by}.' if by else reason


def build_request(proposal, reading, by=None):
    """The statement review (as the batch save takes it) recording a proved reading (``by``: the provider)."""
    from services.financial.import_batches import initial_request
    from services.financial.manual_row_placement import allowed_source_positions
    request = initial_request(proposal)
    request.update(currency=reading['currency'], holder=reading['holder'], account_number=reading['account_number'],
                   institution=reading['institution'], period_start=reading['period_start'],
                   period_end=reading['period_end'])
    originals = {row['id']: row for row in proposal['rows']}
    roles = {}
    totals = reading.get('printed_totals') or {} if IMAGE_TOTALS else {}
    for row in request['rows']:
        original = originals[row['id']]
        direction = original['fields'].get('total_direction')
        if original['kind'] == 'statement_total' and direction in totals:
            if str(totals[direction]) != str(row.get('balance_minor')):
                row.update(balance_minor=str(totals[direction]),
                           reason=TOTAL_REASON.format(page=original.get('page_number') or ''))
        if original['kind'] == 'balance':
            role = (original['fields'].get('description') or '').strip().lower()
            if role in ('opening balance', 'closing balance'):
                roles.setdefault(role, []).append(row)
            continue
        if not row['excluded']:
            row.update(excluded=True, reason=REPLACED_REASON)
    pages = proposal.get('statement_page_numbers') or sorted({s['page_number'] for s in proposal.get('sources') or []}) \
        or proposal.get('page_numbers') or []
    for role, value, page in (('opening balance', reading['opening'], reading['opening_page']),
                              ('closing balance', reading['closing'], reading['closing_page'])):
        existing = roles.get(role) or []
        if len(existing) > 1:
            raise NotProved('The text reading has more than one %s for this period.' % role)
        derived = role == 'opening balance' and reading.get('opening_previous_end')
        reason = OPENING_REASON.format(previous=derived) if derived else row_reason(page, by)
        if existing:
            existing[0]['balance_minor'] = str(value)
            if derived:
                existing[0]['reason'] = reason
            continue
        if page not in pages:
            raise NotProved('The %s was read from a page outside this statement.' % role)
        request['rows'].append(dict(id=f'manual:{role.split()[0]}-balance', excluded=True, manual_page=page,
                                    date='', date_unprinted=False, date_values={}, description=role.title(),
                                    counterparty='', amount_minor='0', direction=None, balance_minor=str(value),
                                    reason=reason))
    for row in reading['rows']:
        if row['page'] not in (proposal.get('page_numbers') or []):
            raise NotProved('A payment was read from a page outside this file.')
        entry = dict(id=f'manual:vision-p{row["page"]}-{row["index"]}', excluded=False, manual_page=row['page'],
                     date=row['date'], date_unprinted=False, date_values={}, description=row['description'],
                     counterparty='', amount_minor=str(row['amount_minor']), direction=row['direction'],
                     balance_minor=str(row['balance_minor']) if row['balance_minor'] is not None else None,
                     reason=row_reason(row['page'], by) + (
                         ' In or out from the printed running balance.' if row.get('direction_from_balance') else ''))
        allowed = sorted(allowed_source_positions(originals, row['page'], pages))
        anchor = next((a for a in allowed if a[0] == 'after'), None) or (allowed[0] if allowed else None)
        if anchor:
            # After the last text row of its page (all set aside), so the image rows keep printed order.
            on_page = [r for r in proposal['rows'] if r.get('kind') in ('transaction', 'unresolved') and r.get('page_number') == row['page']]
            if on_page:
                anchor = ('after', on_page[-1]['id'])
            entry['source_order_anchor'] = dict(relation=anchor[0], row_id=anchor[1])
        request['rows'].append(entry)
    return request


# ---------------------------------------------------------------------------
# Reading the images
# ---------------------------------------------------------------------------

def render_pages(path, page_numbers, width=IMAGE_WIDTH, strips=None):
    """[(page, [png, ...])]: each page as ``strips`` overlapping horizontal strips, top to bottom.

    One whole portrait page is shrunk by the model to about 768 pixels wide, too
    small for dense statement print; strips keep the rendered width.
    """
    import fitz
    from services.financial.page_render import render_page_png
    strips = STRIPS if strips is None else strips
    pages = []
    with fitz.open(str(path)) as document:
        for number in page_numbers:
            if strips <= 1:
                pages.append((number, [render_page_png(document, page_number=number, width=width)]))
                continue
            render_page_png(document, page_number=number, width=8)  # validates the page number
            page = document.load_page(number - 1)
            rect = page.rect
            zoom = width / rect.width
            height = rect.height / strips
            overlap = height * STRIP_OVERLAP
            images = []
            for index in range(strips):
                top = max(rect.y0, rect.y0 + index * height - overlap)
                bottom = min(rect.y1, rect.y0 + (index + 1) * height + overlap)
                clip = fitz.Rect(rect.x0, top, rect.x1, bottom)
                images.append(page.get_pixmap(matrix=(zoom, 0.0, 0.0, zoom, 0.0, 0.0), clip=clip).tobytes('png'))
            pages.append((number, images))
    return pages


# Each provider's request settings (in code, never .env). DeepSeek (benchmarked 2026-10-28): max thinking, 6 strips a
# page (it gives each image a fixed token budget, so narrower strips keep the print legible), a long read (a long
# statement takes up to ~25 minutes), 2 retries of a dropped connection or a server error. OpenAI: as before.
PROVIDER_NAMES = {'deepseek': 'DeepSeek', 'openai': 'OpenAI'}
READER_SETTINGS = {
    'deepseek': dict(strips=6, timeout=1500, max_output_tokens=DEEPSEEK_RESERVE_OUTPUT_TOKENS, retries=2),
    'openai': dict(strips=STRIPS, timeout=PAGE_TIMEOUT_SECONDS, max_output_tokens=16000, retries=0),
}
RETRY_PAUSE_SECONDS = 5


class PageReader(SimpleNamespace):
    """One reader of the chain: provider, model, read(pages) -> (document json, usage), strips, max_output_tokens;
    ``unavailable`` (why) instead of ``read`` when it cannot be used now (no key, a model that cannot read images)."""


def provider_name(provider):
    return PROVIDER_NAMES.get(provider or '', provider or '')


def _retryable(error):
    """A dropped connection or a server-side error (5xx, 429): sent again. A read timeout is not (it took the whole
    allowance once already); the next reader of the chain takes over instead."""
    import requests
    if isinstance(error, requests.exceptions.ReadTimeout):
        return False
    if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError)):
        return True
    response = getattr(error, 'response', None)
    status = getattr(response, 'status_code', None)
    return isinstance(error, requests.exceptions.HTTPError) and status is not None and (status >= 500 or status == 429)


def provider_page_reader(db, case_id, provider, model_id):
    """PageReader for ``provider``/``model_id`` with the provider's stored key (ai_provider_credentials). Fails closed:
    no key, or a model that does not take images (ai_model_capabilities), gives an unavailable reader (WARNING)."""
    from services.ai_provider_credentials import get_provider_api_key
    from services.ai_model_capabilities import ModelCannotReadImages, require_images
    settings = READER_SETTINGS.get(provider)
    reader = PageReader(provider=provider, model=model_id, read=None, unavailable='',
                        strips=(settings or {}).get('strips', STRIPS),
                        max_output_tokens=(settings or {}).get('max_output_tokens', RESERVE_OUTPUT_TOKENS))
    if settings is None:
        reader.unavailable = f'page-image reading is not available for {provider}'
    else:
        try:
            api_key = get_provider_api_key(db, provider)
        except Exception as error:  # noqa: BLE001 - no key: not used
            api_key, reader.unavailable = None, f'its key could not be read ({type(error).__name__})'
        if not api_key and not reader.unavailable:
            reader.unavailable = f'no {provider_name(provider)} key is connected'
        if api_key:
            try:
                # Before any page is rendered or sent: never to a model that does not take images.
                require_images(provider, model_id, api_key=api_key, context=f'case {str(case_id)[:8]}')
                reader.read = document_request(model_id, api_key, provider)
            except ModelCannotReadImages as error:
                reader.unavailable = str(error)
    if reader.unavailable:
        log.warning('Page-image reader %s %s not used for case %s: %s', provider, model_id, str(case_id)[:8],
                    reader.unavailable)
    return reader


def chain_page_reader(db, case_id):
    """The readers of the workload's chain, in order (ai_model_policy.get_workload_chain): DeepSeek first, OpenAI the
    failsafe by default. A reader that cannot be used now is kept with its reason; the chain starts at the next."""
    from services.ai_model_policy import get_workload_chain
    return [provider_page_reader(db, case_id, entry['provider'], entry['model_id'])
            for entry in get_workload_chain(db, WORKLOAD)]


def _single(db, case_id, provider, model_id):
    reader = provider_page_reader(db, case_id, provider, model_id)
    if reader.unavailable:
        raise RuntimeError(reader.unavailable)
    return reader.model, reader.read


def openai_page_reader(db, case_id, model_id=None):
    """(model_id, read) for OpenAI alone: the chain's OpenAI model unless given; raises when unavailable."""
    from services.ai_model_policy import get_workload_chain
    model_id = model_id or next((e['model_id'] for e in get_workload_chain(db, WORKLOAD) if e['provider'] == 'openai'),
                                None) or get_openai_vision_default()
    return _single(db, case_id, 'openai', model_id)


def deepseek_page_reader(db, case_id, model_id=None):
    """(model_id, read) for DeepSeek alone: the chain's DeepSeek model unless given; raises when unavailable."""
    from services.ai_model_policy import get_workload_chain
    model_id = model_id or next((e['model_id'] for e in get_workload_chain(db, WORKLOAD) if e['provider'] == 'deepseek'),
                                None) or 'deepseek-flash'
    return _single(db, case_id, 'deepseek', model_id)


def get_openai_vision_default():
    from services.ai_model_policy import FINANCIAL_VISION_OPENAI
    return FINANCIAL_VISION_OPENAI['model_id']


def readers_of(page_reader, db, case_id):
    """[PageReader] from a page reader: the chain's list, or a single (model_id, read) (tests, benchmarks), whose
    provider is not named (its outcomes keep the single-reader wording)."""
    found = page_reader(db, case_id)
    if isinstance(found, tuple):
        model_id, read = found
        return [PageReader(provider=None, model=model_id, read=read, unavailable='', strips=None,
                           max_output_tokens=RESERVE_OUTPUT_TOKENS)]
    return list(found)


def chain_id(readers):
    """What a stored outcome was read by: one unnamed reader keeps its model id (as before the chain); a chain is its
    providers and models in order with the instructions' version, so a new chain or prompt reads again."""
    if len(readers) == 1 and readers[0].provider is None:
        return readers[0].model
    return ' > '.join(f'{r.provider}/{r.model}' for r in readers) + f' ({PROMPT_VERSION})'


def document_request(model_id, api_key, provider='openai'):
    """read([(page, [png, ...])]) -> (document json, usage): one request for the statement's pages, with the shared
    instructions (PROMPT); each provider's own settings (READER_SETTINGS). Raises on any failure."""
    from services.llm_service import LLMExecutionContext
    settings = READER_SETTINGS.get(provider) or READER_SETTINGS['openai']

    def read(pages):
        strips = max(len(images) for _, images in pages)
        labels, images = [], []
        for number, parts in pages:
            for index, image in enumerate(parts):
                labels.append(f'Page {number}' if len(parts) == 1 else f'Page {number}, part {index + 1} of {len(parts)}')
                images.append(image)
        prompt = PROMPT + PAGES_NOTE.format(pages=len(pages), count=strips)
        for attempt in range(settings['retries'] + 1):
            context = LLMExecutionContext(provider, model_id, api_key=api_key)
            try:
                text = context.call_vision_json(prompt, images, image_labels=labels, schema=DOCUMENT_SCHEMA,
                                                schema_name='statement_document', timeout=settings['timeout'],
                                                max_output_tokens=settings['max_output_tokens'])
                break
            except Exception as error:  # noqa: BLE001 - retried only when the connection or server failed
                if attempt >= settings['retries'] or not _retryable(error):
                    raise
                log.warning('Page-image request to %s failed (%s: %s); trying again (%s of %s)', provider,
                            type(error).__name__, str(error)[:200], attempt + 1, settings['retries'])
                time.sleep(RETRY_PAUSE_SECONDS * (attempt + 1))
        try:
            document = json.loads(text)
        except ValueError as error:
            raise UnreadableAnswer('the answer was not valid JSON') from error
        if not isinstance(document, dict):
            raise UnreadableAnswer('the answer was not a JSON object')
        return document, dict(context.last_usage or {})
    return read


class UnreadableAnswer(ValueError):
    """The provider answered, but not with the JSON object asked for."""


def failure_words(error):
    """Why a request failed, in plain words (stored beside the outcome; never the key or the images)."""
    import requests
    if isinstance(error, UnreadableAnswer):
        return str(error)
    if isinstance(error, requests.exceptions.Timeout) or 'timed out' in str(error).lower():
        return 'it did not answer in time'
    if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError)):
        return 'the connection to it failed'
    status = getattr(getattr(error, 'response', None), 'status_code', None) or getattr(error, 'status_code', None)
    text = str(error)
    if status == 429 or 'insufficient_quota' in text or 'no credits' in text.lower():
        return 'it refused the request (rate limit, or no credit left on the account)'
    if 'Connection' in type(error).__name__:
        return 'the connection to it failed'
    if status:
        return f'it answered with an error (HTTP {status})'
    if 'incomplete' in text or 'declined' in text or 'empty' in text:
        return text[:200].rstrip('.')
    return f'the request failed ({type(error).__name__})'


# ---------------------------------------------------------------------------
# One held statement
# ---------------------------------------------------------------------------

def eligible(item, file, proposal):
    """None when the statement may be read from its images, else why not (a code)."""
    from services.financial.statement_progress import review_progress
    if item.status != 'attention':
        return 'not_held'
    if item.review_request or (file is not None and review_progress(file, item.statement_key)):
        return 'investigator_work'
    if proposal.get('saved_review') or proposal.get('previous_saved_review'):
        return 'investigator_work'
    for key, code in (('document_review', 'document'), ('not_payment_statement', 'not_payment'),
                      ('assignment_only', 'assignment'), ('current_import', 'saved'), ('reading_failure', 'reading_failure')):
        if proposal.get(key):
            return code
    if not item.statement_key and len(proposal.get('statement_choices') or []) > 1:
        return 'file_level'
    if (proposal.get('review_recovery') or {}).get('required'):
        return 'recovery_review'
    if (proposal.get('printed_copies') or {}) and not proposal['printed_copies'].get('identical'):
        return 'printed_copies'
    duplicate = proposal.get('duplicate_disposition') or {}
    if duplicate.get('current') and duplicate.get('status') == 'ignored':
        return 'duplicate'
    if ((item.summary or {}).get('duplicate_disposition') or {}).get('status') == 'ignored':
        return 'duplicate'
    return None


def prepared_elsewhere(db, item, proposal):
    """None when the held statement was prepared from the reading the current code makes, else why not.

    The same test reader_release uses for 'unchanged': the item's revision and review model
    are the current ones and the file still splits into the same statements. Otherwise the
    file is due to be prepared again (which carries the investigator's work), and is read
    from its page images after that.
    """
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial.import_batches import REVIEW_MODEL
    summary = item.summary or {}
    if summary.get('revision') != proposal.get('revision') or summary.get('review_model') != REVIEW_MODEL:
        return 'prepared_by_older_reader'
    keys = {choice['id'] for choice in proposal.get('statement_choices') or []}
    if keys:
        items = set(db.scalars(select(Item.statement_key).where(
            Item.batch_id == item.batch_id, Item.file_id == item.file_id,
            Item.status.notin_(('removed', 'superseded_reading')))))
        if keys != {key or '' for key in items}:
            return 'prepared_by_older_reader'
    return None


def statement_pages(proposal):
    pages = proposal.get('statement_page_numbers') or sorted({s['page_number'] for s in proposal.get('sources') or []
                                                             if type(s.get('page_number')) is int})
    if not pages and len(proposal.get('statement_choices') or []) <= 1:
        # The only statement of its file, with no table read: every page of the file is its page.
        pages = list(proposal.get('page_numbers') or [])
    return [p for p in pages if p in (proposal.get('page_numbers') or pages)]


def rejudgeable(record, revision=None, model_id=None, pages=None):
    """A stored not-proved outcome judged under older proof rules, whose stored page reading is judged
    again under the current ones (no new request). With ``revision``: only for the same reading of
    the file, the same model and the same pages the stored page reading covers."""
    if not (REJUDGE and record and record.get('version') == VERSION and isinstance(record.get('raw'), dict)
            and (record.get('proof') or 1) < PROOF_VERSION):
        return False
    status = record.get('status')
    if status != 'not_proved' and not (status == 'reading' and record.get('rejudging') and not _being_read(record)):
        return False
    if revision is not None and (record.get('revision') != revision or _reader_of(record) != model_id
                                 or list(record.get('pages') or []) != list(pages or [])):
        return False
    return True


def _judged(stored, **extra):
    """A stored not-proved outcome (or an abandoned re-judge claim of one) marked judged under these rules."""
    record = {k: v for k, v in stored.items() if k not in ('rejudging', 'claim_id')}
    return dict(record, status='not_proved', proof=PROOF_VERSION, **extra)


def _stored(file, key):
    return ((file.metadata_ or {}).get(METADATA_KEY) or {}).get(key or '')


def _being_read(stored):
    if not stored or stored.get('status') != 'reading':
        return False
    started = datetime.fromisoformat(stored['at'])
    return (datetime.now(timezone.utc) - started).total_seconds() < CLAIM_SECONDS


def _store(db, file_id, key, record, claim=None, rejudge=None, owner=None):
    """Store the record under the file's lock. With ``claim=(revision, model)``: False, storing
    nothing, when the statement is being read, was read or was given up (checked under the lock).
    With ``rejudge=(revision, model, pages)``: False, storing nothing, unless the stored outcome is
    still one to judge again from its stored page reading (rejudgeable). With ``owner``: False, storing
    nothing, unless the stored record is this worker's re-judge claim or still rejudgeable."""
    from postgres.models.evidence import EvidenceFile
    file = db.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id).with_for_update()
                     .execution_options(populate_existing=True))
    if file is None:
        return False
    metadata = deepcopy(file.metadata_ or {})
    readings = metadata.setdefault(METADATA_KEY, {})
    previous = readings.get(key or '')
    if claim and (_being_read(previous) or _current(previous, *claim) or gave_up(previous, claim[0])):
        return False
    if rejudge and not rejudgeable(previous, *rejudge):
        return False
    if owner and not ((previous or {}).get('claim_id') == owner or rejudgeable(previous)):
        return False
    if previous and previous.get('status') not in ('reading',) and previous.get('revision') != record.get('revision'):
        metadata.setdefault(METADATA_KEY + '_history', []).append(previous)
        metadata[METADATA_KEY + '_history'] = metadata[METADATA_KEY + '_history'][-20:]
    readings[key or ''] = record
    file.metadata_ = metadata
    return True


def _note(item, record):
    """The outcome beside the held statement, shown in the queue (summary key survives readiness refreshes)."""
    offer = record.get('offer') if isinstance(record.get('offer'), dict) else None
    item.summary = {**(item.summary or {}), 'vision_reading': dict(
        {k: record.get(k) for k in ('status', 'reason', 'message', 'pages', 'cost_usd', 'model', 'provider', 'at')},
        line=outcome_line(record), **({'offer': {k: offer.get(k) for k in ('id', 'mine', 'offered')}} if offer else {}))}


# ---------------------------------------------------------------------------
# Every outcome, recorded (decision logging, fin-holes A)
# ---------------------------------------------------------------------------

# Each statement's outcomes, newest last, beside METADATA_KEY on its file: one entry per distinct outcome (the same
# outcome again only counts up and moves its last time), the last OUTCOME_HISTORY kept. Nothing is overwritten.
OUTCOMES_KEY = METADATA_KEY + '_outcomes'
OUTCOME_HISTORY = 30
# Why a statement was not read from its page images, in plain words ("Not read from page images: ...").
SKIP_WORDS = {
    'investigator_work': 'you have saved work on it',
    'prepared_by_older_reader': 'it is first being prepared again with the current reader',
    'not_held': 'it is not held',
    'case_not_approved': 'page-image reading is not switched on for this case',
    'file_removed': 'the file is removed from Financial',
    'document': 'it is a document review',
    'not_payment': 'it is set aside as not a payment statement',
    'assignment': 'it is assigned to an account without reading',
    'saved': 'it is already saved',
    'reading_failure': 'the file itself could not be read',
    'file_level': 'its file holds several statements that are not separated yet',
    'recovery_review': 'it waits for its recovery review',
    'printed_copies': 'its file prints differing copies of it',
    'duplicate': 'it was set aside as a copy',
    'no_pages': 'no page of it was found in its file',
    'unavailable': 'the page-image reader is not available just now',
    'failed_repeatedly': 'its page images could not be read after several tries',
    'gone': 'it is no longer in its batch',
}
# Outcomes of the moment (another worker has it, or it was decided before): logged at debug, not recorded.
PASSING = ('already_read', 'being_read')


def outcome_line(record):
    """The outcome in plain words, for the queue and the journal."""
    status, reason, message = record.get('status'), record.get('reason'), str(record.get('message') or '').strip()
    if status == 'proved':
        return 'Read from page images: accepted. ' + (message or 'The period reconciles exactly.')
    if status == 'not_proved':
        return 'Read from page images: not accepted, because ' + (message[:1].lower() + message[1:] if message else 'it did not prove.')
    if status == 'offered':
        return 'Read from page images: ' + (message or OFFER_MESSAGE) + ' It is offered beside your saved work; nothing is changed unless you use it.'
    if status in ('offer_accepted', 'offer_declined'):
        return 'Read from page images: ' + message
    if status == 'failed':
        return 'Not read from page images: ' + (message or 'the reading failed; it is tried again later.')
    if status == 'budget':
        return 'Not read from page images: the reading budget for this case is used for now.'
    if status == 'stale':
        return 'Not read from page images: ' + (message or 'the statement changed while it was read.')
    words = SKIP_WORDS.get(reason) or (reason or 'not read').replace('_', ' ')
    return 'Not read from page images: %s.' % words


def _history_entry(record):
    entry = {k: record.get(k) for k in ('at', 'status', 'reason', 'message', 'model', 'provider', 'prompt_version',
                                        'cost_usd', 'seconds', 'pages', 'revision', 'proof', 'rejudged', 'basis',
                                        'account_basis', 'failover') if record.get(k) not in (None, '', [])}
    entry['line'] = outcome_line(record)
    return entry


def _same_outcome(a, b):
    return all((a or {}).get(k) == (b or {}).get(k) for k in ('status', 'reason', 'message', 'revision', 'model'))


def _record_outcome(db, file_id, key, record):
    """Append the outcome to the statement's history under the file's lock; False when it repeats the last one."""
    from postgres.models.evidence import EvidenceFile
    file = db.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id).with_for_update()
                     .execution_options(populate_existing=True))
    if file is None:
        return False
    metadata = deepcopy(file.metadata_ or {})
    history = list((metadata.get(OUTCOMES_KEY) or {}).get(key or '') or [])
    entry = _history_entry(record)
    if history and _same_outcome(history[-1], entry):
        last = dict(history[-1])
        last.update(times=(last.get('times') or 1) + 1, last_at=entry.get('at'))
        history[-1] = last
        changed = False
    else:
        history.append(dict(entry, times=1))
        changed = True
    metadata.setdefault(OUTCOMES_KEY, {})[key or ''] = history[-OUTCOME_HISTORY:]
    file.metadata_ = metadata
    return changed


def outcomes(file, key):
    """A statement's recorded outcomes, oldest first."""
    return list(((getattr(file, 'metadata_', None) or {}).get(OUTCOMES_KEY) or {}).get(key or '') or [])


def _decided(factory, item_id, record):
    """Every outcome of read_item: a journal line, the statement's outcome history, and (a skip) the queue note."""
    from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
                                                          FinancialImportBatchItem as Item)
    reason = record.get('reason')
    if reason in PASSING:
        log.debug('Page-image reader: item %s %s', str(item_id)[:8], reason)
        return
    try:
        with factory() as db:
            item = db.scalar(select(Item).where(Item.id == item_id).with_for_update())
            batch = db.get(Batch, item.batch_id) if item is not None else None
            where = 'item %s' % str(item_id)[:8]
            if item is not None:
                where = 'case %s file %s statement %s' % (str(batch.case_id)[:8] if batch else '?', str(item.file_id)[:8],
                                                          (item.statement_key or '-')[:8])
            line = outcome_line(record)
            level = logging.WARNING if record.get('status') in ('failed', 'unavailable') else logging.INFO
            log.log(level, 'Page-image reader: %s: %s%s', where, line,
                    ' (%s)' % reason if reason and record.get('status') == 'skipped' else '')
            if item is None:
                db.rollback()
                return
            changed = _record_outcome(db, item.file_id, item.statement_key or '', record)
            shown = (item.summary or {}).get('vision_reading') or {}
            if (record.get('status') == 'skipped' and item.status == 'attention' and reason in SKIP_WORDS
                    and (changed or shown.get('reason') != reason or shown.get('status') != 'skipped')):
                # Why it was not read, beside the held statement (a final outcome is noted by _finish/_save).
                _note(item, record)
            db.commit()
    except Exception:  # noqa: BLE001 - recording never changes the outcome
        log.exception('Recording a page-image reading outcome failed')


def reserve_usd(model_id, images, max_output_tokens=RESERVE_OUTPUT_TOKENS):
    """The most a request with these images can cost (counted before it is sent)."""
    count = sum(len(strips) for _, strips in images)
    return cost_usd(model_id, dict(prompt_tokens=count * RESERVE_TOKENS_PER_IMAGE + 4000,
                                   completion_tokens=max_output_tokens))


# ---------------------------------------------------------------------------
# The reader chain: each reader's attempt, and the outcome they decide
# ---------------------------------------------------------------------------

def _reader_of(record):
    """What a stored outcome was read by (chain_id); outcomes stored before the chain name their model."""
    return (record or {}).get('reader') or (record or {}).get('model')


def _attempt_key(reader):
    return (reader.provider, reader.model, getattr(reader, 'prompt_version', None) or PROMPT_VERSION)


def _attempt_raw(record, attempt):
    if attempt.get('raw') is not None:
        return attempt['raw']
    return record.get('raw') if attempt.get('raw_in_record') else None


def stored_attempts(record):
    """[(PageReader, page reading)] of a stored outcome, in the order they were read (no request needed)."""
    found = []
    for attempt in record.get('attempts') or []:
        raw = _attempt_raw(record, attempt)
        if isinstance(raw, dict):
            found.append((PageReader(provider=attempt.get('provider'), model=attempt.get('model'), read=None,
                                     unavailable='', strips=None, max_output_tokens=RESERVE_OUTPUT_TOKENS,
                                     prompt_version=attempt.get('prompt_version')), raw))
    if not found and isinstance(record.get('raw'), dict):
        found.append((PageReader(provider=record.get('provider'), model=record.get('model'), read=None, unavailable='',
                                 strips=None, max_output_tokens=RESERVE_OUTPUT_TOKENS,
                                 prompt_version=record.get('prompt_version')), record['raw']))
    return found


def _reusable(stored, revision, pages):
    """{attempt key: page reading} of the stored outcome's readings of this same reading of the file and pages."""
    if not stored or stored.get('version') != VERSION or stored.get('revision') != revision \
            or list(stored.get('pages') or []) != list(pages or []) or stored.get('status') == 'reading':
        return {}
    return {(a.get('provider'), a.get('model'), a.get('prompt_version')): _attempt_raw(stored, a)
            for a in stored.get('attempts') or [] if a.get('provider') and isinstance(_attempt_raw(stored, a), dict)}


def _reused_cost(stored, reader):
    key = _attempt_key(reader)
    return next((a.get('cost_usd') for a in (stored or {}).get('attempts') or []
                 if (a.get('provider'), a.get('model'), a.get('prompt_version')) == key), None)


def _clause(message):
    message = str(message or '').strip().rstrip('.')
    return message[:1].lower() + message[1:] if message[:2] != message[:2].upper() else message


def _attempt_words(attempt):
    name = provider_name(attempt.get('provider'))
    status, message = attempt.get('status'), _clause(attempt.get('message'))
    if status == 'not_proved':
        return f'{name} could not prove it: {message}'
    if status == 'failed':
        return f'{name} could not read it: {message}'
    if status == 'stale':
        return f'{name} read it while the statement changed'
    return f'{name} was not used: {message}'


def _outcome(record, attempts, accepted, spent_now, seconds, page_costs, again):
    """The outcome record of the chain's attempts: what each reader did (provider, model, instructions version,
    seconds, cost, why it did not settle it), the reading that decided it, and the outcome in plain words.
    An outcome of one unnamed reader (tests, benchmarks) keeps the wording it had before the chain."""
    record = dict(record)
    named = any(a.get('provider') for a in attempts)
    with_raw = [a for a in attempts if a.get('raw') is not None]
    main = accepted or (with_raw[0] if with_raw else None)
    if main is not None:
        record['raw'] = main['raw']
    if again:
        record['seconds'] = 0
    else:
        costs = sorted(page_costs.values(), key=lambda c: c['page'])
        reused = sum(a.get('cost_usd') or 0 for a in attempts if a.get('reused'))
        record.update(page_costs=costs, cost_usd=round(sum(c['cost_usd'] for c in costs) + reused, 6),
                      spent_usd=round(spent_now, 6), seconds=round(seconds, 1))
    if named:
        shown = main or (attempts[-1] if attempts else {})
        record.update(provider=shown.get('provider'), model=shown.get('model'), prompt_version=shown.get('prompt_version'),
                      attempts=[dict({k: v for k, v in a.items() if k != 'raw'},
                                     **({'raw_in_record': True} if a is main else
                                        {'raw': a['raw']} if a.get('raw') is not None else {}))
                                for a in attempts])
    if record.get('status') == 'stale':
        return record
    before = [a for a in attempts if a is not accepted and a.get('status') != 'proved']
    details = ' '.join(_attempt_words(a) + '.' for a in before) if named else ''
    if accepted is not None:
        by = f' by {provider_name(accepted.get("provider"))}' if named else ''
        if named and before:
            record['failover'] = [{k: a.get(k) for k in ('provider', 'model', 'status', 'message')} for a in before]
            by += ' (' + '; '.join(_attempt_words(a) for a in before) + ')'
        record.update(status='proved', rows=accepted['rows'])
        if accepted.get('basis') == 'dates_from_page_images':
            filled = accepted['rows']
            record['message'] = ('The text reading, with %s date%s read from the page images%s; the period reconciles '
                                 'exactly. (The page-image reading alone did not prove it: %s)' % (
                                     filled, '' if filled == 1 else 's', by, accepted.get('alone')))
        else:
            record['message'] = f'Read from the page images{by}; the period reconciles exactly.'
        return record
    statuses = {a.get('status') for a in attempts}
    if 'failed' in statuses:
        failures_now = (record.get('failures') or 0) + 1
        record.update(status='failed', failures=failures_now,
                      error=next(a.get('error') for a in attempts if a.get('status') == 'failed'),
                      message=(GAVE_UP if failures_now >= MAX_FAILURES else
                               'The page images could not be read just now; the statement stays held.')
                      + (' ' + details if details else ''))
    elif 'budget' in statuses:
        record.update(status='budget', message='Not read from the page images: the reading budget for this case is '
                                               'used for now.' + (' ' + details if details else ''))
    elif not named:
        record.update(status='not_proved', message=next(a['message'] for a in attempts if a.get('status') == 'not_proved'))
    else:
        record.update(status='not_proved', message='No reading of the page images proves it. ' + details)
    return record


def failures(record, revision):
    """Failed requests for this reading; a claim left 'reading' past its time (the worker stopped
    mid-request, after the request was sent) counts as one more."""
    if not record or record.get('version') != VERSION or record.get('revision') != revision:
        return 0
    if record.get('status') == 'failed':
        return record.get('failures') or 0
    if record.get('status') == 'reading' and not _being_read(record):
        return (record.get('failures') or 0) + 1
    return 0


def gave_up(record, revision):
    return failures(record, revision) >= MAX_FAILURES


def _current(record, revision, model_id):
    return (record and record.get('version') == VERSION and record.get('revision') == revision
            and _reader_of(record) == model_id and record.get('status') in FINAL)


def read_item(factory, item_id, resolve_path, *, page_reader=None, knowledge_for=None, apply=True, force=False):
    """Read one held statement from its page images (_read_item) and record the outcome, whatever it is (_decided):
    a journal line, the statement's outcome history and, a skip, its queue note. Measuring records nothing."""
    record = _read_item(factory, item_id, resolve_path, page_reader=page_reader, knowledge_for=knowledge_for,
                        apply=apply, force=force)
    if apply and not force:
        _decided(factory, item_id, record)
    return record


def _read_item(factory, item_id, resolve_path, *, page_reader=None, knowledge_for=None, apply=True, force=False):
    """Read one held statement from its page images. Returns the outcome record. Never raises.

    ``page_reader(db, case_id) -> (model_id, read)`` and ``knowledge_for(db, case_id)``
    are injectable for tests and the truth benchmark. ``apply=False`` measures only:
    nothing is stored or saved. ``force`` reads a statement that is not held (truth
    accuracy sampling only, never with ``apply``).
    """
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
                                                          FinancialImportBatchItem as Item)
    from services.financial.import_batches import assess
    from services.financial.statement_import import read_statement_import
    if force and apply:
        raise ValueError('A forced reading is for measurement only')
    page_reader = page_reader or chain_page_reader
    if knowledge_for is None:
        from services.financial.field_proposals import case_knowledge

        def knowledge_for(db, case_id):
            return case_knowledge(db, case_id)
    record = dict(version=VERSION, proof=PROOF_VERSION, status='skipped', message='', at=datetime.now(timezone.utc).isoformat())
    file_id, key = None, ''
    again, stored, claim_id = False, None, 'none'
    try:
        with factory() as db:
            item = db.get(Item, item_id)
            batch = db.get(Batch, item.batch_id) if item else None
            file = db.get(EvidenceFile, item.file_id) if item else None
            if item is None or batch is None or file is None or batch.status == 'removed':
                return dict(record, reason='gone')
            case_id, file_id, key = batch.case_id, item.file_id, item.statement_key or ''
            if not approved(case_id):  # measuring sends the images too
                return dict(record, reason='case_not_approved')
            entry = next((e for e in batch.files or [] if e.get('file_id') == str(file_id)), {})
            from services.financial.pdf_candidates import PdfMappingError
            from services.financial.file_visibility import financial_file_visibility
            if financial_file_visibility(file)['financial_removed']:
                # Removed from Financial: nothing to read until a person restores it (not a failed reading).
                return dict(record, reason='file_removed')
            try:
                proposal = read_statement_import(db, case_id=case_id, evidence_file_id=file_id,
                                                 currency=entry.get('currency') or None, statement_id=key or None)
            except PdfMappingError as error:
                if 'no longer available' not in str(error):
                    raise
                # The current reading no longer has this period: the file is due to be prepared
                # again, and is read from its page images after that (not a failed reading).
                return dict(record, reason='prepared_by_older_reader')
            why = eligible(item, file, proposal)
            if force and why in ('not_held', 'saved', 'investigator_work'):
                why = None  # accuracy sampling of saved statements only (never applied)
            offer = False
            if why == 'investigator_work' and OFFERS and not force:
                # Their work stays theirs: a reading that proves is only offered to them (_offer), never saved.
                why, offer = None, True
                record['offer'] = True
            if why:
                return dict(record, reason=why)
            if not force:
                why = prepared_elsewhere(db, item, proposal)
                if why:
                    return dict(record, reason=why)
                state, _ = assess(proposal, None)
                if state != 'attention':
                    return dict(record, reason='not_held')
            pages = statement_pages(proposal)
            if not pages:
                return dict(record, reason='no_pages')
            if len(pages) > MAX_PAGES:
                record.update(status='not_proved', message=f'This period has {len(pages)} pages; page images are read for periods up to {MAX_PAGES} pages.')
                return _finish(factory, item_id, file_id, key, dict(record, revision=proposal['revision'], pages=pages), apply)
            try:
                readers = readers_of(page_reader, db, case_id)
            except Exception as error:  # noqa: BLE001 - fail closed
                return dict(record, status='unavailable', reason='unavailable', message=str(error)[:300])
            if not any(not r.unavailable for r in readers):
                # No reader of the chain can be used (no key, no model that reads images): nothing is sent.
                return dict(record, status='unavailable', reason='unavailable', message='; '.join(
                    f'{provider_name(r.provider)} {r.model}: {r.unavailable}' for r in readers)[:300])
            model_id = chain_id(readers)
            stored = _stored(file, key)
            again = not force and rejudgeable(stored, proposal['revision'], model_id, pages)
            if not again and not force and rejudgeable(stored):
                # Judged again only from the same stored page reading; never requested anew for it. Marked
                # judged under these rules, so it is not offered again (as before re-judging existed).
                if apply:
                    # Under the file's lock, only while it is still that outcome (rejudgeable, any reading).
                    _store(db, file_id, key, _judged(stored), rejudge=(None, None, None))
                    db.commit()
                else:
                    db.rollback()
                return dict(stored, reason='already_read')
            if _current(stored, proposal['revision'], model_id) and not force and not again:
                return dict(stored, reason='already_read')
            if _being_read(stored) and not force:
                return dict(record, reason='being_read')
            record.update(revision=proposal['revision'], model=model_id, reader=model_id, pages=pages,
                          text_reading=_rule_metadata(proposal),
                          failures=0 if again else failures(stored, proposal['revision']))
            if record['failures'] >= MAX_FAILURES and not force:
                if stored.get('status') == 'failed':
                    return dict(stored, reason='failed_repeatedly')
                return _finish(factory, item_id, file_id, key, dict(record, status='failed', reason='failed_repeatedly',
                               message=GAVE_UP), apply)
            path = resolve_path(file.stored_path)
            if again:
                record.update(failures=0, cost_usd=stored.get('cost_usd'), page_costs=stored.get('page_costs'),
                              read_at=stored.get('read_at') or stored.get('at'), rejudged=True)
                if apply:
                    # The claim keeps the stored reading (and is checked again under the file's lock).
                    claim_id = str(uuid4())
                    if not _store(db, file_id, key, dict(stored, status='reading', rejudging=True, claim_id=claim_id,
                                  at=datetime.now(timezone.utc).isoformat()),
                                  rejudge=(proposal['revision'], model_id, pages)):
                        db.rollback()
                        return dict(record, reason='being_read')
                    db.commit()
                else:
                    db.rollback()
            elif apply:
                # The claim, checked again under the file's lock (another worker may hold it).
                if not _store(db, file_id, key, dict(record, status='reading'), claim=(proposal['revision'], model_id)):
                    db.rollback()
                    return dict(record, reason='being_read')
                db.commit()
            else:
                db.rollback()
        if again:
            # The page readings already stored, judged under the current proof rules: no request, no cost.
            candidates = stored_attempts(stored)
        else:
            # A reading of an earlier try of this same reading of the file (the chain stopped at a failed request)
            # is judged again rather than requested again.
            reuse = _reusable(stored, record['revision'], pages)
            candidates = [(reader, reuse.get(_attempt_key(reader))) for reader in readers]
        attempts, accepted = [], None
        spent_now, seconds, page_costs = 0.0, 0.0, {}
        for reader, raw in candidates:
            attempt = dict(provider=reader.provider, model=reader.model,
                           prompt_version=getattr(reader, 'prompt_version', None) or (PROMPT_VERSION if reader.provider else None))
            if raw is None and reader.unavailable:
                attempts.append(dict(attempt, status='unavailable', message=reader.unavailable))
                continue
            if raw is None:
                # Outside any lock or transaction: render (in this reader's strips) and read.
                images = render_pages(path, pages, strips=reader.strips)
                reserved = reserve_usd(reader.model, images, reader.max_output_tokens)
                # The most it can cost is counted before the request is sent, and settled after.
                if not _reserve(case_id, reserved):
                    attempts.append(dict(attempt, status='budget',
                                         message='the reading budget for this case is used for now'))
                    break
                started = time.monotonic()
                try:
                    # One request with every page of the period, each image labelled with its page number.
                    raw, usage = reader.read(images)
                except Exception as error:  # noqa: BLE001 - this reader failed: the next one of the chain reads
                    took = round(time.monotonic() - started, 1)
                    seconds += took
                    if reader.provider is None:
                        raise  # a single reader (tests, benchmarks): failed as before
                    log.warning('Page-image reading by %s %s failed for file %s after %ss (%s: %s)%s',
                                reader.provider, reader.model, str(file_id)[:8], took, type(error).__name__,
                                str(error)[:200], '; the next reader takes over' if reader is not candidates[-1][0] else '')
                    attempts.append(dict(attempt, status='failed', error=type(error).__name__,
                                         message=failure_words(error), seconds=took))
                    continue
                took = round(time.monotonic() - started, 1)
                cost = cost_usd(reader.model, usage)
                _add_spend(case_id, cost - reserved)
                spent_now += cost
                seconds += took
                for number, _ in images:
                    share = page_costs.setdefault(number, dict(page=number, prompt_tokens=0, completion_tokens=0, cost_usd=0.0))
                    share['prompt_tokens'] += round((usage.get('prompt_tokens') or 0) / len(images))
                    share['completion_tokens'] += round((usage.get('completion_tokens') or 0) / len(images))
                    share['cost_usd'] = round(share['cost_usd'] + cost / len(images), 6)
                attempt.update(cost_usd=round(cost, 6), seconds=took, prompt_tokens=usage.get('prompt_tokens'),
                               completion_tokens=usage.get('completion_tokens'))
                log.info('Page-image reading: case %s file %s by %s %s, %s pages, %ss, cost $%.4f ($%.4f a page; '
                         '%s tokens in, %s out)', str(case_id)[:8], str(file_id)[:8], reader.provider or 'model',
                         reader.model, len(images), took, cost, cost / len(images), usage.get('prompt_tokens'),
                         usage.get('completion_tokens'))
            else:
                attempt.update(reused=True, cost_usd=_reused_cost(stored, reader), seconds=0)
            attempt['raw'] = raw
            by = provider_name(reader.provider) or None
            with factory() as db:
                item = db.get(Item, item_id)
                proposal = read_statement_import(db, case_id=case_id, evidence_file_id=file_id,
                                                 currency=entry.get('currency') or None, statement_id=key or None)
                if proposal['revision'] != record['revision']:
                    db.rollback()
                    attempts.append(dict(attempt, status='stale'))
                    return _finish(factory, item_id, file_id, key, _outcome(dict(record, status='stale',
                        message='The statement was read again while its page images were read.'),
                        attempts, None, spent_now, seconds, page_costs, again), apply)
                try:
                    reading, request, controls, _ = judge(db, case_id, proposal, raw, pages, knowledge_for(db, case_id),
                                                          saved=force, by=by)
                    accepted = dict(attempt, status='proved', rows=len(reading['rows']))
                    attempts.append(accepted)
                    db.rollback()
                    break
                except NotProved as reason:
                    request = None
                    if DATES_FROM_IMAGE and not force:
                        try:
                            request = dates_request(proposal, document_pages(raw, pages))
                        except NotProved:
                            request = None
                    db.rollback()
                    if request is not None:
                        filled = sum(1 for row in request['rows'] if str(row.get('reason') or '').startswith('Date read from page image'))
                        accepted = dict(attempt, status='proved', basis='dates_from_page_images', rows=filled,
                                        alone=str(reason))
                        attempts.append(accepted)
                        reading, controls = None, None
                        break
                    attempts.append(dict(attempt, status='not_proved', message=str(reason)))
                except Exception as error:  # noqa: BLE001 - this reading could not be judged: the next one reads
                    db.rollback()
                    if reader.provider is None:
                        raise
                    log.exception('Judging the page-image reading by %s %s failed', reader.provider, reader.model)
                    attempts.append(dict(attempt, status='failed', error=type(error).__name__,
                                         message=f'its reading could not be checked ({type(error).__name__})'))
        record = _outcome(record, attempts, accepted, spent_now, seconds, page_costs, again)
        if accepted is None:
            return _finish(factory, item_id, file_id, key, record, apply)
        if accepted.get('basis') == 'dates_from_page_images':
            record['basis'] = 'dates_from_page_images'
        else:
            if reading.get('account_basis'):
                # The first statement of its account (FIRST_STATEMENT): what admitted its header, recorded with it.
                record.update(account_basis=reading['account_basis'], message=record['message'] + FIRST_STATEMENT_NOTE)
            if controls:
                record['printed_controls'] = controls
            if reading.get('charge_totals') and CLOSING_DAYS:
                record['charge_totals'] = reading['charge_totals']
        record['request'] = request
        if not apply:
            return record
        if offer:
            return _offer(factory, item_id, file_id, key, record, request)
        return _save(factory, item_id, case_id, file_id, key, record, request)
    except Exception as error:  # noqa: BLE001 - fail closed: the statement stays held
        log.exception('Page-image reading failed; the statement stays held')
        if again:
            # Judging the stored reading again failed: its earlier outcome stands, marked judged under
            # these rules, with its stored reading (final, so it is never requested anew).
            try:
                if apply and file_id is not None:
                    with factory() as db:
                        _store(db, file_id, key, _judged(stored, rejudge_error=type(error).__name__), owner=claim_id)
                        db.commit()
            except Exception:  # noqa: BLE001
                log.exception('Recording a failed re-judging failed')
            return dict(stored, reason='rejudge_failed', rejudged=True)
        record.update(status='failed', error=type(error).__name__, failures=(record.get('failures') or 0) + 1)
        record['message'] = GAVE_UP if record['failures'] >= MAX_FAILURES else \
            'The page images could not be read just now; the statement stays held.'
        try:
            if apply and file_id is not None:
                return _finish(factory, item_id, file_id, key, record, apply)
        except Exception:  # noqa: BLE001
            log.exception('Recording a failed page-image reading failed')
        return record


def judge(db, case_id, proposal, document, pages, knowledge, *, saved=False, by=None):
    """(reading, request, printed controls, judged proposal) of a page reading that proves this statement; NotProved
    otherwise. ``saved``: a saved statement, judged as if it were not saved yet (no neighbour check: the reader
    replacement weighs its coverage)."""
    from services.financial.import_batches import assess
    readings = document_pages(document, pages)
    page_gap, printed = None, False
    try:
        printed = check_page_numbering(readings, proposal.get('page_numbers'), printed_order=True)
    except NotProved as gap:
        if not PRINTED_COUNTS:
            raise
        # A page gap is settled by the bank's own printed counts and totals of the period's
        # deposits and withdrawals on a page held, as the batch's page gate settles it
        # (import_issues.printed_complete): decided below.
        page_gap = gap
    if printed:
        # The pages pass only in printed order: the text reading must keep that order too, or the saved review
        # would place the payments out of it. Where it does not, the pages are out of order as before this rule:
        # a page gap, read in the text reading's order, that only the printed counts and totals settle.
        try:
            check_text_keeps_printed_order(document, proposal, pages)
        except NotProved as gap:
            if not PRINTED_COUNTS:
                raise
            page_gap = gap
    section = choose_section(combine(readings), proposal)
    if page_gap is not None and not proposal.get('printed_pages_missing') and any(
            section['values'].get(k) is None for k in ('count_credits', 'count_debits', 'total_credits', 'total_debits')):
        # The text reading does not see the gap, so the page gate cannot weigh it: only all four
        # printed on the images (each proved equal to the payments read, in prove) settle it.
        raise page_gap
    reading = prove(proposal, section, knowledge)
    if not saved:
        check_neighbours(db, case_id, reading)
    request = build_request(proposal, reading, by=by)
    controls = printed_controls(proposal, section, reading, request) if (PRINTED_COUNTS or QUIET_PRINTED) else None
    judged = dict(proposal, **image_evidence(proposal, controls, reading.get('charge_totals')))
    state, summary = assess(dict(judged, current_import=None) if saved else judged, request)
    if page_gap is not None and state != 'ready':
        raise page_gap
    if state != 'ready' or summary.get('problems') or summary.get('problem_count'):
        first = next((p.get('message') for p in summary.get('problems') or [] if p.get('message')), '')
        raise NotProved('The page-image reading reconciles, but the statement still has a check: ' + (first or state))
    return reading, request, controls, judged


def _finish(factory, item_id, file_id, key, record, apply):
    if not apply:
        return record
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    with factory() as db:
        _store(db, file_id, key, {k: v for k, v in record.items() if k != 'request'})
        item = db.scalar(select(Item).where(Item.id == item_id).with_for_update())
        shown = record.get('status') not in ('failed', 'reading') or (record.get('failures') or 0) >= MAX_FAILURES
        if item is not None and item.status == 'attention' and shown:
            _note(item, record)
        db.commit()
    return record


def _save(factory, item_id, case_id, file_id, key, record, request):
    """The batch's own review save (System), then the automatic save of what now checks out completely."""
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial.decisions import Actor
    from services.financial.effective_statement_review import batch_review_revision
    from services.financial.import_batches import save_review
    from services.financial.statement_import import StatementReviewDraft
    from services.financial.pdf_candidates import PdfMappingError
    actor = Actor(name=SYSTEM_NAME, email=SYSTEM_EMAIL)
    with factory() as db:
        item = db.get(Item, item_id)
        if item is None or item.status != 'attention' or item.review_request:
            db.rollback()
            return _finish(factory, item_id, file_id, key, dict(record, status='stale',
                message='The statement changed while its page images were read.'), True)
        batch_id = item.batch_id
        try:
            outcome = save_review(db, case_id=case_id, batch_id=batch_id, item_id=item_id,
                                  request=StatementReviewDraft.model_validate(request),
                                  expected_review_revision=batch_review_revision(None, None), actor=actor)
        except PdfMappingError as error:
            db.rollback()
            return _finish(factory, item_id, file_id, key, dict(record, status='not_proved',
                message='The page-image reading could not be recorded: ' + str(error)), True)
        except Exception:
            db.rollback()
            from postgres.models.evidence import EvidenceFile
            from services.financial.statement_progress import review_progress
            with factory() as check:
                file = check.get(EvidenceFile, file_id)
                progress = review_progress(file, key) if file is not None else None
                by = (progress or {}).get('saved_by') or {}
                ours = any(str(row.get('id', '')).startswith('manual:vision-')
                           or str(row.get('reason') or '').startswith('Date read from page image')
                           for row in ((progress or {}).get('request') or {}).get('rows') or [])
                if not (by.get('name') == SYSTEM_NAME and by.get('user_id') == 'None' and ours):
                    raise  # this review was not saved: a failed reading (read_item)
            # The review was saved; what failed came after its commit (the readiness refresh).
            log.exception('Page-image reading: the review is saved; refreshing the statement after it failed')
            outcome = dict(status='saved')
    stored = {k: v for k, v in record.items() if k != 'request'}
    stored['review_status'] = outcome.get('status')
    try:
        with factory() as db:
            _store(db, file_id, key, stored)
            item = db.get(Item, item_id)
            if item is not None:
                _note(item, stored)
            db.commit()
            from services.financial.queue_save import auto_save_prepared
            auto_save_prepared(db, case_id=case_id, batch_id=batch_id, file_id=file_id)
    except Exception:  # noqa: BLE001 - the review is saved (the statement is ready); only this record or the automatic save failed
        log.exception('Recording a saved page-image reading failed; its review is saved')
    log.info('Page-image reading proved statement %s of file %s (%s rows, $%.4f); saved as System review',
             str(item_id)[:8], str(file_id)[:8], record.get('rows'), record.get('cost_usd') or 0)
    return stored


# ---------------------------------------------------------------------------
# An offer beside a person's work (rule 2)
# ---------------------------------------------------------------------------

def _minor_text(value):
    return None if value in (None, '') else str(value)


def offer_values(request):
    """The values a person compares: header, balances, payments read and their totals (minor units as text)."""
    request = request or {}
    rows = [r for r in request.get('rows') or [] if isinstance(r, dict)]
    balances = {}
    for row in rows:
        role = str(row.get('description') or '').strip().lower()
        if row.get('excluded') and role in ('opening balance', 'closing balance') and row.get('balance_minor') not in (None, ''):
            balances.setdefault(role.split()[0], str(row['balance_minor']))
    payments = [r for r in rows if not r.get('excluded') and str(r.get('amount_minor') or '0').strip('0-')]
    total = lambda direction: str(sum(int(r['amount_minor']) for r in payments if r.get('direction') == direction))
    return dict(holder=request.get('holder') or '', account_number=request.get('account_number') or '',
                institution=request.get('institution') or '', currency=request.get('currency') or '',
                period_start=request.get('period_start') or '', period_end=request.get('period_end') or '',
                opening_minor=balances.get('opening'), closing_minor=balances.get('closing'), payments=len(payments),
                credits_minor=total('credit'), debits_minor=total('debit'))


def _their_work(item, file, key):
    """(their current review request, its revision token): the batch draft, else their saved review."""
    from services.financial.effective_statement_review import batch_review_revision
    from services.financial.statement_progress import review_progress
    saved = review_progress(file, key) if file is not None else None
    request = item.review_request or (saved or {}).get('request') or {}
    return request, batch_review_revision(item.review_request, saved)


def _offer(factory, item_id, file_id, key, record, request):
    """Store a proving reading of a statement a person has worked on as an offer beside their work. Nothing of theirs
    is written: their draft, saved review and the statement stay exactly as they are."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    with factory() as db:
        # The file before the item: the order save_review locks them in.
        file = db.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id).with_for_update())
        item = db.scalar(select(Item).where(Item.id == item_id).with_for_update())
        answered = _stored(file, key) if file is not None else None
        if answered and answered.get('status') in ('offer_accepted', 'offer_declined'):
            # The person answered an earlier offer while this reading ran: their answer stands as the record.
            db.rollback()
            return dict(record, status='stale', message='The person answered an earlier offer while this one was read.')
        if item is None or item.status != 'attention':
            db.rollback()
            return _finish(factory, item_id, file_id, key, dict(record, status='stale',
                message='The statement changed while its page images were read.'), True)
        theirs, work_revision = _their_work(item, file, key)
        offered = offer_values(request)
        # The offer's identity: the person's click names the offer they were shown; a different one is refused.
        offer_id = hashlib.sha256(json.dumps([request, work_revision, record.get('at')], sort_keys=True, default=str)
                                  .encode()).hexdigest()[:16]
        stored = dict({k: v for k, v in record.items() if k != 'request'}, status='offered', message=OFFER_MESSAGE,
                      offer=dict(id=offer_id, request=request, work_revision=work_revision, mine=offer_values(theirs),
                                 offered=offered))
        _store(db, file_id, key, stored)
        _note(item, stored)
        db.commit()
    log.info('Page-image reading of statement %s of file %s (a person\'s work) checks out: offered beside their work '
             '(%s rows, $%.4f); nothing saved', str(item_id)[:8], str(file_id)[:8], record.get('rows'), record.get('cost_usd') or 0)
    return stored


def _offer_target(session, case_id, batch_id, item_id, offer_id):
    """(item, file, stored offer) under the batch and file locks, in save_review's order (batch, file, item), so an
    answer is settled against the offer as it stands: still on offer, and the very offer the person was shown."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial.import_batches import batch_for
    from services.financial.pdf_candidates import PdfMappingError
    batch = batch_for(session, case_id, batch_id, True)
    file_id = session.scalar(select(Item.file_id).where(Item.id == item_id, Item.batch_id == batch.id))
    if file_id is None:
        raise PdfMappingError('Statement not found in this batch.', 404)
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id).with_for_update()
                          .execution_options(populate_existing=True))
    item = session.scalar(select(Item).where(Item.id == item_id).with_for_update())
    stored = _stored(file, item.statement_key)
    if not stored or stored.get('status') != 'offered' or not (stored.get('offer') or {}).get('request'):
        raise PdfMappingError('There is no page-image reading on offer for this statement.', 409)
    if not offer_id or stored['offer'].get('id') != offer_id:
        raise PdfMappingError('The reading on offer changed since you opened it. Reopen the statement to see it.', 409)
    return item, file, stored


def _offer_record(session, item, file_id, stored, status, actor, message):
    """Record the person's answer to an offer on the reading record and in the outcome history, under the locks
    _offer_target took (flushed, not committed)."""
    who = dict(name=getattr(actor, 'name', None), email=getattr(actor, 'email', None),
               user_id=str(getattr(actor, 'user_id', '') or ''))
    record = dict(stored, status=status, message=message, decided_by=who, at=datetime.now(timezone.utc).isoformat())
    _store(session, file_id, item.statement_key or '', record)
    session.flush()  # the outcome history reads the file again under its lock
    _record_outcome(session, file_id, item.statement_key or '', record)
    session.flush()  # save_review reads the file again (populate_existing): it must keep this record
    return record, who


def _offer_noted(session, item_id, file_id, record, who):
    """The answer beside the statement, committed, and in the journal."""
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    current = session.scalar(select(Item).where(Item.id == item_id).with_for_update())
    if current is not None:
        _note(current, record)
    session.commit()
    log.info('Page-image offer for statement %s of file %s: %s by %s', str(item_id)[:8], str(file_id)[:8],
             record['status'], who.get('name') or who.get('email'))
    return record


def _offer_decided(session, item, file_id, stored, status, actor, message):
    record, who = _offer_record(session, item, file_id, stored, status, actor, message)
    return _offer_noted(session, item.id, file_id, record, who)


def accept_offer(session, *, case_id, batch_id, item_id, offer_id, actor):
    """'Use this reading': the offered reading saved through the person's own save (save_review, as them), checked
    against the work the offer was compared with, so a change to their work since refuses (409) instead of being
    overwritten, and against the offer they were shown (offer_id). The acceptance is recorded in the same transaction
    as the save (save_review's commit), under the batch and file locks, so a concurrent 'Keep mine' or second click
    finds it settled. Their earlier saved review stays in the file's review history. Returns save_review's result."""
    from services.financial.import_batches import save_review
    from services.financial.statement_import import StatementReviewDraft
    from services.financial.pdf_candidates import PdfMappingError
    item, file, stored = _offer_target(session, case_id, batch_id, item_id, offer_id)
    offer = stored['offer']
    file_id, item_id = file.id, item.id
    record, who = _offer_record(session, item, file_id, stored, 'offer_accepted', actor,
                                'The reading from the page images was used, by your choice; your earlier review is '
                                'kept in its history.')
    try:
        result = save_review(session, case_id=case_id, batch_id=batch_id, item_id=item_id,
                             request=StatementReviewDraft.model_validate(offer['request']),
                             expected_review_revision=offer['work_revision'], actor=actor)
    except PdfMappingError as error:
        session.rollback()  # the acceptance record with it: nothing was saved
        if error.status_code == 409:
            # Their work or the statement changed since the offer was made: the offer, if still on offer, is withdrawn.
            try:
                item, file, stored = _offer_target(session, case_id, batch_id, item_id, offer_id)
            except PdfMappingError:
                session.rollback()
            else:
                _offer_decided(session, item, file_id, stored, 'stale', actor,
                               'The statement or your work on it changed after this reading was offered, so it was '
                               'not used. Nothing was changed.')
        raise
    _offer_noted(session, item_id, file_id, record, who)
    return result


def decline_offer(session, *, case_id, batch_id, item_id, offer_id, actor):
    """'Keep mine': the offer is set aside; their work is not touched."""
    item, file, stored = _offer_target(session, case_id, batch_id, item_id, offer_id)
    _offer_decided(session, item, file.id, stored, 'offer_declined', actor,
                   'You kept your own work; the reading from the page images was set aside.')
    return dict(status='offer_declined')


# ---------------------------------------------------------------------------
# A saved statement (reader replacement of an incomplete saved period)
# ---------------------------------------------------------------------------

def _saved_target(db, document):
    """(case id, file, statement key, currency, proposal) of a saved statement review, or a reason string."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialStatementPeriod
    from services.financial.statement_import import read_statement_import
    metadata = document.metadata_ or {}
    key = metadata.get('statement_import_statement_id') or ''
    file = db.get(EvidenceFile, document.evidence_file_id) if document.evidence_file_id else None
    if not key or file is None:
        return 'no_statement'
    if not approved(document.case_id):
        return 'case_not_approved'
    period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == document.id))
    currency = (period.currency if period is not None else None) or None
    proposal = read_statement_import(db, case_id=document.case_id, evidence_file_id=file.id, currency=currency,
                                     statement_id=key)
    return document.case_id, file, key, currency, proposal


def read_saved(factory, document_id, resolve_path, *, page_reader=None, knowledge_for=None, stored_only=False):
    """Read a saved statement's pages from their images once per reading of the file and model (SAVED_KEY), judge
    the reading as if the statement were not saved yet, and store the outcome (never applied). Returns the record.
    ``stored_only``: judge the stored reading again under the current rules and store that outcome, sending no
    request (STORED_REJUDGE). Never raises; fails closed like read_item."""
    from postgres.models.financial import FinancialSourceDocument
    if knowledge_for is None:
        from services.financial.field_proposals import case_knowledge

        def knowledge_for(db, case_id):
            return case_knowledge(db, case_id)
    page_reader = page_reader or chain_page_reader
    record = dict(version=VERSION, proof=PROOF_VERSION, status='skipped', at=datetime.now(timezone.utc).isoformat())
    if not SAVED_READING:
        return dict(record, reason='disabled')
    try:
        with factory() as db:
            document = db.get(FinancialSourceDocument, UUID(str(document_id)))
            if document is None or document.status != 'admitted':
                return dict(record, reason='not_saved')
            target = _saved_target(db, document)
            if isinstance(target, str):
                return dict(record, reason=target)
            case_id, file, key, currency, proposal = target
            pages = statement_pages(proposal)
            if not pages or len(pages) > MAX_PAGES:
                return dict(record, reason='pages')
            stored = ((file.metadata_ or {}).get(SAVED_KEY) or {}).get(key)
            if stored_only:
                readers, model_id = [], _reader_of(stored)
            else:
                readers = readers_of(page_reader, db, case_id)
                if not any(not r.unavailable for r in readers):
                    return dict(record, status='unavailable', reason='unavailable', message='; '.join(
                        f'{provider_name(r.provider)} {r.model}: {r.unavailable}' for r in readers)[:300])
                model_id = chain_id(readers)
            if (stored and stored.get('version') == VERSION and stored.get('revision') == proposal['revision']
                    and _reader_of(stored) == model_id and list(stored.get('pages') or []) == pages
                    and isinstance(stored.get('raw'), dict)):
                candidates, again = stored_attempts(stored), True
            else:
                candidates, again = [(reader, None) for reader in readers], False
            path = resolve_path(file.stored_path)
            file_id = file.id
            db.rollback()
        record.update(revision=proposal['revision'], model=model_id, reader=model_id, pages=pages,
                      document_id=str(document_id))
        if again:
            record.update(cost_usd=stored.get('cost_usd'), page_costs=stored.get('page_costs'))
        if not candidates and stored_only:
            return dict(record, reason='no_image_reading')
        attempts, accepted, reading, controls = [], None, None, None
        spent_now, seconds, page_costs = 0.0, 0.0, {}
        for reader, raw in candidates:
            attempt = dict(provider=reader.provider, model=reader.model,
                           prompt_version=getattr(reader, 'prompt_version', None) or (PROMPT_VERSION if reader.provider else None))
            if raw is None and reader.unavailable:
                attempts.append(dict(attempt, status='unavailable', message=reader.unavailable))
                continue
            if raw is None:
                images = render_pages(path, pages, strips=reader.strips)
                reserved = reserve_usd(reader.model, images, reader.max_output_tokens)
                if not _reserve(case_id, reserved):
                    attempts.append(dict(attempt, status='budget', message='the reading budget for this case is used for now'))
                    break
                started = time.monotonic()
                try:
                    raw, usage = reader.read(images)
                except Exception as error:  # noqa: BLE001 - the next reader of the chain reads
                    if reader.provider is None:
                        raise
                    log.warning('Page-image reading of saved statement by %s %s failed (%s: %s)', reader.provider,
                                reader.model, type(error).__name__, str(error)[:200])
                    attempts.append(dict(attempt, status='failed', error=type(error).__name__,
                                         message=failure_words(error), seconds=round(time.monotonic() - started, 1)))
                    continue
                took = round(time.monotonic() - started, 1)
                cost = cost_usd(reader.model, usage)
                _add_spend(case_id, cost - reserved)
                spent_now, seconds = spent_now + cost, seconds + took
                for number, _ in images:
                    share = page_costs.setdefault(number, dict(page=number, prompt_tokens=0, completion_tokens=0, cost_usd=0.0))
                    share['cost_usd'] = round(share['cost_usd'] + cost / len(images), 6)
                attempt.update(cost_usd=round(cost, 6), seconds=took)
                log.info('Page-image reading of saved statement: case %s file %s by %s %s, %s pages, cost $%.4f',
                         str(case_id)[:8], str(file_id)[:8], reader.provider or 'model', reader.model, len(pages), cost)
            attempt['raw'] = raw
            with factory() as db:
                try:
                    reading, request, controls, _ = judge(db, case_id, proposal, raw, pages, knowledge_for(db, case_id),
                                                          saved=True, by=provider_name(reader.provider) or None)
                    accepted = dict(attempt, status='proved', rows=len(reading['rows']))
                    attempts.append(accepted)
                    break
                except NotProved as reason:
                    attempts.append(dict(attempt, status='not_proved', message=str(reason)))
                finally:
                    db.rollback()
        record = _outcome(record, attempts, accepted, spent_now, seconds, page_costs, again)
        if again:
            record.pop('seconds', None)
        if record.get('raw') is None:
            return dict(record, reason=record.get('status'))
        if accepted is not None:
            if controls:
                record['printed_controls'] = controls
            if reading.get('charge_totals'):
                record['charge_totals'] = reading['charge_totals']
        with factory() as db:
            from postgres.models.evidence import EvidenceFile
            locked = db.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id).with_for_update()
                               .execution_options(populate_existing=True))
            metadata = deepcopy(locked.metadata_ or {})
            metadata.setdefault(SAVED_KEY, {})[key] = record
            locked.metadata_ = metadata
            db.commit()
        return record
    except Exception as error:  # noqa: BLE001 - fail closed: nothing is replaced
        log.exception('Page-image reading of a saved statement failed')
        return dict(record, status='failed', reason=type(error).__name__, message=str(error)[:300])


def saved_image_request(db, document, statement_id, proposal):
    """(request, judged proposal, reading) from the page reading stored for this saved statement (read_saved), judged
    now under the current rules with no request sent; or (None, reason code). Reads only."""
    from postgres.models.evidence import EvidenceFile
    if not SAVED_READING:
        return None, 'disabled'
    file = db.get(EvidenceFile, document.evidence_file_id)
    stored = (((file.metadata_ or {}).get(SAVED_KEY) or {}).get(statement_id or '') if file is not None else None)
    if not stored or not isinstance(stored.get('raw'), dict) or stored.get('version') != VERSION:
        return None, 'no_image_reading'
    if stored.get('revision') != proposal.get('revision') or list(stored.get('pages') or []) != statement_pages(proposal):
        return None, 'image_reading_stale'
    from services.financial.field_proposals import case_knowledge
    try:
        reading, request, _, judged = judge(db, document.case_id, proposal, stored['raw'], stored['pages'],
                                            case_knowledge(db, document.case_id), saved=True)
    except NotProved:
        return None, 'image_not_proved'
    return (request, judged, reading), None


# ---------------------------------------------------------------------------
# Which statements: held ones of prepared files
# ---------------------------------------------------------------------------

def pending(db, limit=50):
    """Held, untouched statements of prepared files (batch entry ``MARK``, or finished preparing)."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
                                                          FinancialImportBatchItem as Item)
    from services.financial import held_reprepare
    stamp = held_reprepare.preparation_stamp()
    marked = {}
    for batch_id, case_id, files in db.execute(select(Batch.id, Batch.case_id, Batch.files).where(
            Batch.status.notin_(('removed', 'pausing', 'paused')))):
        if not approved(case_id):
            continue
        for entry in files or ():
            # Marked when prepared with this reader on; a file prepared before it was switched on is
            # read too once its preparation is finished ('checked'); read_item reads it only when it
            # was prepared from the reading the current code makes (prepared_elsewhere).
            # Not one queued to be prepared again, nor (unmarked) one the re-preparation has not
            # judged yet (held_reprepare): that re-preparation carries her work and goes first.
            queued = held_reprepare._mark(entry).get('state')
            if not entry.get('file_id') or queued in ('pending', 'handed'):
                continue
            if entry.get(MARK) or (entry.get('status') == 'checked' and not (
                    held_reprepare.ENABLED and held_reprepare.stale(entry, stamp))):
                marked.setdefault(batch_id, set()).add(entry['file_id'])
    if not marked:
        return []
    found = []
    for item_id, batch_id, file_id, key, draft, metadata in db.execute(
            select(Item.id, Item.batch_id, Item.file_id, Item.statement_key, Item.review_request, EvidenceFile.metadata_)
            .join(EvidenceFile, EvidenceFile.id == Item.file_id)
            .where(Item.batch_id.in_(list(marked)), Item.status == 'attention')
            .order_by(Item.updated_at, Item.id)):
        # An untouched draft is stored as JSON null, which SQL "IS NULL" does not match. A statement with a person's
        # draft is listed too: read_item decides it ('investigator_work') and the outcome is recorded beside it.
        if str(file_id) not in marked.get(batch_id, ()):
            continue
        stored = ((metadata or {}).get(METADATA_KEY) or {}).get(key or '')
        if stored and stored.get('version') == VERSION and not rejudgeable(stored) and (stored.get('status') in FINAL or (
                stored.get('status') == 'failed' and (stored.get('failures') or 0) >= MAX_FAILURES)):
            # Read once per reading of the file (a new reading is a new file, with its own statements).
            continue
        found.append(item_id)
        if len(found) >= limit:
            break
    return found


_skip_until = {}
PENDING_LIMIT = 2000


def sweep(factory, resolve_path, *, budget_seconds=SWEEP_SECONDS):
    """Background round: read held statements from their page images, a few per round. Never raises."""
    report = dict(read=0, proved=0, not_proved=0, failed=0, cost_usd=0.0)
    skipped = {}
    if not ENABLED:
        return report
    started = time.monotonic()
    try:
        with factory() as db:
            # A statement not read (not eligible, skipped for now) stores nothing and stays listed:
            # the whole list is taken and those skipped are passed over before any is read, so they
            # never keep the others from their turn.
            ids = pending(db, limit=PENDING_LIMIT)
    except Exception:
        log.exception('Finding statements to read from page images failed; the next round retries')
        return report
    now = time.monotonic()
    ids = [item_id for item_id in ids if _skip_until.get(item_id, 0) <= now]
    for item_id in ids:
        if time.monotonic() - started >= budget_seconds:
            break
        outcome = read_item(factory, item_id, resolve_path)
        reason = outcome.get('reason')
        if reason in ('already_read', 'being_read'):
            _skip_until[item_id] = now + 600
            continue
        if outcome.get('status') in ('proved', 'not_proved', 'failed', 'unavailable', 'stale', 'budget') or reason:
            # Not looked at again by this process for a while unless its reading changes.
            _skip_until[item_id] = now + (3600 if outcome.get('status') in ('failed', 'unavailable', 'budget') else 6 * 3600)
        if outcome.get('status') in ('proved', 'not_proved', 'failed', 'offered'):
            report['read'] += 1
            report[outcome['status']] = report.get(outcome['status'], 0) + 1
            if not outcome.get('rejudged'):
                spent_now = outcome.get('spent_usd')
                report['cost_usd'] = round(report['cost_usd'] + ((outcome.get('cost_usd') if spent_now is None else spent_now) or 0), 6)
        elif reason or outcome.get('status') in ('budget', 'stale', 'unavailable'):
            why = reason or outcome['status']
            skipped[why] = skipped.get(why, 0) + 1
        if outcome.get('status') == 'unavailable':
            break  # no key / provider: nothing else this round can be read either
    if skipped:
        report['skipped'] = skipped
    if report['read'] or skipped:
        # Every round that decided anything (each statement's own line is logged by read_item).
        log.info('Page-image reading round: %s', report)
    return report
