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
# On a card statement (balance owed) a payment or refund is printed with a minus ("- $246.92": Capital One, fdaf956c),
# and the images give it so with direction credit: on a liability the minus marks what reduces the amount owed, so it
# agrees with the credit. Only on a liability statement; a minus on a credit of any other account is refused as
# before. Every proof applies (the balance to the cent decides). Off: such a row is unreadable.
SIGNED_CARD_CREDITS = _switch('LOUPE_FINANCIAL_VISION_SIGNED_CARD_CREDITS')
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
# The first statement of a card that prints only the last 4 digits (Neil, 2026-10-28, LAST4-APPROVED: fdaf956c's 51
# Capital One statements print only "ending in 8160" / "ending in 2602", so rule 1 can never confirm them). With no
# saved statement of the account, a card (liability) statement's header is accepted when the page images and the text
# reading of the same file both read the number masked with the same visible digits (at least 4), the same holder and
# the same bank, the currency is printed, the file's text layer prints no longer number ending in those digits (that
# is rule 1's route), and the case holds no account with those last digits at that bank. Every other proof is
# unchanged. One card is created by one statement only: the earliest of its held statements still to be judged
# (last4_turn); the others wait for it and then follow through the saved account (masked number, holder and bank), so
# a differently printed holder is never merged into it. Recorded with the basis 'page_image_last4_header_matches_text'.
# Off: such a statement stays held as before.
LAST4_FIRST_STATEMENT = _switch('LOUPE_FINANCIAL_VISION_LAST4_FIRST_STATEMENT')
LAST4_BASIS = 'page_image_last4_header_matches_text'
LAST4_NOTE = (' The first statement of this card in the case: the last 4 digits of its number, its holder and bank on '
              'the page images agree with the text of the same file, which prints no longer number for it.')
# The full number printed beside a masked one (coordinator, 2026-10-28: each Capital One statement page 1 prints the
# card's complete number only in its payment coupon's machine-readable line, "1 5178059984428160 09 ...", so LAST4,
# which needs the file to print no longer number, refuses them and rule 1 needs both readings of the full number).
# A card's first statement whose header prints only the last digits is accepted when, besides every LAST4 check but
# that one, the page images read the complete number (full_account_number) and it is, digit for digit, the ONE longer
# number ending in those digits the file's text prints: rule 1's evidence (the full number read alike from the page
# images and the text of the same file), with LAST4's order (one statement creates the card; the rest follow through
# the saved account; another holder is never merged). Off: such a statement stays held as before.
FULL_NUMBER_FROM_IMAGES = _switch('LOUPE_FINANCIAL_VISION_FULL_NUMBER_FROM_IMAGES')
FULL_NUMBER_NOTE = (' The first statement of this card in the case: its full number (%s), printed on its payment '
                    'coupon, is read alike from the page images and the text, as are its holder and bank.')
# A period's summary page read with it (coordinator, 2026-10-28: each of fdaf956c's 52 Capital One periods was read
# from its "Page 2 of N" onwards; the file page before, printing "Page 1 of N" with the previous and new balance, the
# holder and address, is on no statement's table pages, so no opening or closing balance could be read and 6 holders
# were read from the text only). The summary pages the text reading finds before the period (summary_pages: its text
# numbering leads back to "Page 1 of N" over pages of no other statement) are read with the period from its page
# images, and its printed balances may be cited from them. Every proof is unchanged. Off: the period's table pages
# only, as before.
SUMMARY_PAGES = _switch('LOUPE_FINANCIAL_VISION_SUMMARY_PAGES')
# Stored with each outcome read under SUMMARY_PAGES: an outcome stored before it is looked at again once (pending),
# read anew only when its period now has more pages, else just marked.
PAGES_RULE = 1 if SUMMARY_PAGES else 0
# Read with its summary page, a period also has the summary's reverse side: a page the reader marks as not a statement
# page, printing a form number ("002") the reader takes for a page number without a count. Where the period's pages
# print a count ("Page 2 of 4"), a number without one on a page that is not a statement page is not that numbering: the
# page is unnumbered (it may stand only in a gap, as any unnumbered page). Off: it is a page number, as before ("two
# pages of this period print the same page number").
FORM_NUMBERS = _switch('LOUPE_FINANCIAL_VISION_FORM_NUMBERS')
# A card statement lists each purchase by its transaction date, which can fall a few days before the billing cycle it
# is posted in (fdaf956c Capital One "Jun 9 | Jun 12 | U-HAUL" on the statement for Jun 10 to Jul 10, 2023; the text
# reading of the same file dates it Jun 9 too). On any card (liability) statement, not only one whose period is its
# closing date and days, a row dated up to POSTING_DAYS before the start is a posting of this cycle. Off: only there.
CARD_POSTING = _switch('LOUPE_FINANCIAL_VISION_CARD_POSTING')
PROOF_VERSION = 1
for _switched in (SPLIT_SPELLINGS, SECTION_NUMBER, PRINTED_COUNTS, QUIET_PRINTED, CLABE_ACCOUNT, SECTION_BY_TEXT,
                  SIGNED_DEBITS, DATES_FROM_IMAGE, OPENING_FROM_PREVIOUS, IMAGE_TOTALS, CLOSING_DAYS, TEXT_MISREADS,
                  FIRST_STATEMENT, ROW_DATES, PRINTED_ORDER, LAST4_FIRST_STATEMENT, FORM_NUMBERS, CARD_POSTING,
                  SIGNED_CARD_CREDITS, FULL_NUMBER_FROM_IMAGES):
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
# A claim outlives the longest chain reading, so no other worker takes up a statement still being read; a claim left
# by a stopped worker expires after it. The chain itself stops starting readers that could not finish inside
# CHAIN_SECONDS (reader_worst_seconds: each request is bounded by the clock), which leaves the claim a margin.
CLAIM_SECONDS = 150 * 60
CHAIN_SECONDS = CLAIM_SECONDS - 15 * 60
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
    # The override was set for OpenAI's vision model; DeepSeek models are always priced at DeepSeek's own price.
    override = (os.environ.get('LOUPE_FINANCIAL_VISION_PRICE_IN'), os.environ.get('LOUPE_FINANCIAL_VISION_PRICE_OUT'))
    if all(override) and not str(model_id).startswith('deepseek'):
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
                                                           'total_fees', 'total_interest', 'full_account_number'],
                properties=dict(_SECTION['properties'], rows={'type': 'array', 'items': _DOC_ROW},
                                full_account_number={'type': 'string'},
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
PROMPT_VERSION = 'statement-pages-v4'
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
- full_account_number: only when account_number is printed masked or as its last digits only, and the complete number of this same account is printed elsewhere on these pages (e.g. in a payment coupon's account box, or as the run of digits in the coupon's machine-readable line that ends in the same last digits): that complete number, digits only, exactly as printed. Otherwise empty. Never build, complete or guess a number.
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


def page_instructions(pages, strips):
    """(instruction text, PROMPT_VERSION) for reading a statement's page images: the ONE builder of that text, used
    for every provider and every path (Neil, 2026-10-28). Providers differ only in transport (OpenAI's enforced
    response format; the schema after this text for DeepSeek) and in strips per page."""
    return PROMPT + PAGES_NOTE.format(pages=pages, count=strips), PROMPT_VERSION


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
                section['full_account_number'] = str(account.get('full_account_number') or '')
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


def row_amount(row, exponent, liability=False):
    """The row's positive amount in minor units, or None; '-15.89' only on a debit (SIGNED_DEBITS), or on a credit of
    a card statement (``liability``, SIGNED_CARD_CREDITS)."""
    amount = row.get('amount')
    signed = (SIGNED_DEBITS and row.get('direction') == 'debit') or (
        SIGNED_CARD_CREDITS and liability and row.get('direction') == 'credit')
    if signed and str(amount or '').strip().startswith('-'):
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
    """The image reading does not prove; ``str`` is the plain reason recorded for the investigator. ``card`` (a
    card_key) names the account it waits on: no statement of it is confirmed in the case yet, so it is judged again
    once the case holds that card's account (due_again)."""

    def __init__(self, message='', card=None):
        super().__init__(message)
        self.card = card


class WaitsForCard(NotProved):
    """(LAST4_FIRST_STATEMENT) Not judged now: another statement of the same card goes first (last4_turn). Stored
    with ``waiting`` and judged again in a later pass or round (due_again); never a final outcome."""


# ---------------------------------------------------------------------------
# Combining pages into account sections
# ---------------------------------------------------------------------------

_HEADER = ('institution', 'holder', 'account_number', 'currency', 'period_start', 'period_end', 'full_account_number')


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
    if FORM_NUMBERS and any(page.get('printed_page_total') for _, page in pages):
        pages = [(physical, dict(page, printed_page_number=None) if page.get('printed_page_number')
                  and not page.get('printed_page_total') and page.get('is_statement_page') is False else page)
                 for physical, page in pages]
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


def is_card(proposal, liability=None):
    """A card (liability) statement: its balance is what is owed, or the reader detected a credit card."""
    metadata = proposal.get('metadata') or {}
    if liability is None:
        liability = metadata.get('balance_convention') == 'liability_owed'
    return bool(liability) or metadata.get('account_type') == 'credit_card'


def card_key(institution, digits):
    """The card an account-confirmation refusal waits on: its visible last digits at its bank."""
    from services.financial import field_proposals as fp
    return '%s|%s' % (_digits(digits)[-4:], ' '.join(sorted(fp.institution_key(institution))))


def _one_line(text):
    return ' '.join(str(text or '').split())


def _names(values):
    """Distinct printed names, in the order first seen, joined for a sentence."""
    from services.financial import field_proposals as fp
    seen, names = set(), []
    for value in values:
        key = fp.holder_key(value)
        if key and key not in seen:
            seen.add(key)
            names.append(_one_line(value))
    return ' and '.join(names)


def _account_words(account_text, liability, proposal):
    """('card'|'account', 'ending 8160'|'1234567890') for a sentence about the statement's account."""
    from services.financial import field_proposals as fp
    digits, masked = fp.account_identity(account_text)
    kind = 'card' if is_card(proposal, liability) else 'account'
    return kind, ('ending %s' % digits[-4:] if masked else digits)


def _at_bank(known, institution):
    """A saved account at the statement's bank (or one recording no bank, which could be it)."""
    from services.financial import field_proposals as fp
    banks = known.values('institution') or ([known.institution] if known.institution else [])
    return not banks or not institution or any(fp.same_institution(institution, b) for b in banks)


def masked_only_reason(account_text, liability, proposal, check):
    """The plain reason a statement printing only the last digits of its number is held, and what to do."""
    kind, ending = _account_words(account_text, liability, proposal)
    return ('The bank prints only the last 4 digits of this %s (%s) and no statement of it is confirmed in this case '
            'yet. Confirm one statement of this %s and the rest can follow. It was not accepted as the first statement '
            'of this %s because %s.' % (kind, ending, kind, kind, check))


def longer_number_reason(account_text, longer, liability, proposal):
    """The statement's header prints only the last digits, and the file's text prints a longer number ending in them
    (fdaf956c: Capital One's payment coupon line): the first statement of the card is not confirmed from the last digits
    (LAST4 applies only where no longer number is printed), and the page images do not read the longer one."""
    kind, ending = _account_words(account_text, liability, proposal)
    return ('The statement prints only the last 4 digits of this %s (%s) as its account, and no statement of it is '
            'confirmed in this case yet. The file also prints a longer number ending in the same digits (%s), which the '
            'page images do not read as this %s\'s number, so this statement is not accepted as the first of this %s. '
            'Confirm one statement of this %s and the rest can follow.' % (kind, ending, ', '.join(longer[:3]), kind, kind,
                                                                           kind))


def holder_differs_reason(account_text, saved_holders, holder, liability, proposal):
    kind, ending = _account_words(account_text, liability, proposal)
    return ('This %s (%s) is saved for %s; this statement prints %s. Confirm whether they are the same account.'
            % (kind, ending, _names(saved_holders), _one_line(holder)))


def choose_account_reason(account_text, accounts, institution, liability, proposal):
    """More than one saved account could be this statement's, or one with the same digits at another bank."""
    from services.financial import field_proposals as fp
    kind, ending = _account_words(account_text, liability, proposal)
    named = '; '.join('%s at %s' % (k.account or k.digits, _names(k.values('institution') or [k.institution]) or 'a bank not recorded')
                      for k in accounts) or 'another account'
    if len(accounts) == 1 and not _at_bank(accounts[0], institution):
        return ('An account with the same number is saved in this case: %s. This statement (%s %s) prints %s. Confirm '
                'which account it belongs to.' % (named, kind, ending, _one_line(institution) or 'no bank'))
    return ('More than one account saved in this case could be this %s (%s): %s. Choose which account this statement '
            'belongs to.' % (kind, ending, named) if len(accounts) > 1 else
            'Another account saved in this case has the same digits as this %s (%s): %s. Choose whether this '
            'statement belongs to it.' % (kind, ending, named))


def _not_both(field, rule, header, same):
    """Plain words for a header field the page images and the text do not both read alike, else ''."""
    words = {'account_number': 'its number', 'holder': 'the account holder', 'institution': 'the bank'}[field]
    if not (rule[field] and header[field]):
        return '%s is not read from both the page images and the text' % words
    if not same(rule[field], header[field]):
        return '%s read from the page images (%s) differs from the one read from the text (%s)' % (
            words, _one_line(header[field]), _one_line(rule[field]))
    return ''


_TRAILING_DIGITS = re.compile(r'^[^\d]*\d+$')


def _last4_check(proposal, rule, header, liability):
    """(LAST4_FIRST_STATEMENT) The first check a masked first statement fails, in plain words; '' when all pass."""
    from services.financial import field_proposals as fp
    if not LAST4_FIRST_STATEMENT:
        return 'accepting the first statement of such a card from its page images is switched off'
    if not is_card(proposal, liability):
        return 'it is not a card statement; only the first statement of a card can be accepted this way'
    missing = _not_both('account_number', rule, header, lambda a, b: True)
    if missing:
        return missing
    numbers = [fp.account_identity(rule['account_number']), fp.account_identity(header['account_number'])]
    if not all(masked for _, masked in numbers):
        return ('the %s reads a longer number, so both must read the full number'
                % ('text' if not numbers[0][1] else 'page images'))
    if min(len(digits) for digits, _ in numbers) < 4:
        return 'fewer than 4 digits of its number are read'
    if not all(_TRAILING_DIGITS.match(re.sub(r'\s', '', str(n))) for n in (rule['account_number'], header['account_number'])):
        # "517805******8160": its visible digits are not one run at the end, so they do not name it by its last
        # digits; matched by them, it would be another account than one saved with its full number.
        return 'its number shows digits before the masked part; only a number printed by its last digits alone can be accepted this way'
    if numbers[0][0] != numbers[1][0]:
        return 'the digits read from the page images (%s) differ from those read from the text (%s)' % (
            numbers[1][0], numbers[0][0])
    for field, same in (('holder', fp.same_holder), ('institution', fp.same_institution)):
        failed = _not_both(field, rule, header, same)
        if failed:
            return failed
    if not (rule['currency'] or header['currency']):
        return 'the currency is not printed'
    return ''


def first_statement_basis(proposal, rule, header, account_text, institution, holder, liability, knowledge):
    """The basis on which a statement whose account no saved statement confirms is its account's first statement
    (FIRST_STATEMENT: the full number; LAST4_FIRST_STATEMENT: a card printing only its last digits); NotProved with
    the plain reason (what is missing and what a person can do) otherwise."""
    from services.financial import field_proposals as fp
    identity = fp.account_identity(account_text)
    digits, masked = identity
    accounts = getattr(knowledge, 'accounts', []) or []
    same_digits = [k for k in accounts if fp.account_match(identity, (k.digits, k.masked))]
    # A full number: no saved account carries it at any bank (rule 1). Last digits only: none at this bank.
    clash = [k for k in same_digits if _at_bank(k, institution)] if masked else same_digits
    if clash:
        holders = [h for k in clash for h in k.values('holder')]
        if (holder and holders and all(_at_bank(k, institution) for k in clash)
                and not any(fp.same_holder(holder, h) for h in holders)):
            raise NotProved(holder_differs_reason(account_text, holders, holder, liability, proposal))
        raise NotProved(choose_account_reason(account_text, clash, institution, liability, proposal))
    if not masked:
        if first_statement_header(rule, header):
            return FIRST_STATEMENT_BASIS
        why = next((w for w in (_not_both(f, rule, header, same) for f, same in (
            ('account_number', lambda a, b: _digits(a) == _digits(b) and not fp.account_identity(a)[1]
             and not fp.account_identity(b)[1]), ('holder', fp.same_holder), ('institution', fp.same_institution)))
            if w), 'accepting the first statement of an account from its page images is switched off')
        if why.startswith('its number read') or why.startswith('its number is'):
            why = why.replace('its number', 'the full number', 1)
        raise NotProved('No statement of account %s is confirmed in this case yet, and this one was not accepted as '
                        'its first because %s. Confirm one statement of this account and the rest can follow.'
                        % (digits, why))
    check = _last4_check(proposal, rule, header, liability)
    if check:
        raise NotProved(masked_only_reason(account_text, liability, proposal, check), card=card_key(institution, digits))
    return LAST4_BASIS


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
    if CARD_POSTING and TEXT_MISREADS and liability and start and earliest is None:
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
    found = candidates
    if matched == {'ambiguous'}:
        candidates, matched = one_account_spelled_apart(candidates, account_text, institution_printed, holder_printed)
    basis = None
    if not candidates and not matched & {'ambiguous'}:
        # No saved account confirms it: the first statement of its account (rule 1 or LAST4), or held with the reason.
        basis = first_statement_basis(proposal, rule, header, account_text, institution_printed, holder_printed,
                                      liability, knowledge)
    elif not candidates or 'ambiguous' in matched or 'account' not in matched:
        raise NotProved(choose_account_reason(account_text, candidates or found, institution_printed, liability, proposal))
    first_statement = basis is not None
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
    if holder and saved_holders and not any(fp.same_holder(holder, h) for h in saved_holders):
        raise NotProved(holder_differs_reason(account_text, saved_holders, holder, liability, proposal))
    if not holder:
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
    # A summary page (SUMMARY_PAGES) is read for the period's balances and header only: its account summary lines
    # ("Payments - $x", "Transactions + $x") are no payments, so a row cited there holds the statement.
    from services.financial.summary_pages import statement_summary_pages
    summary_only = set(statement_summary_pages(proposal)) - set(statement_pages(proposal)) if SUMMARY_PAGES else set()
    for index, row in enumerate(section['rows']):
        if row.get('page') in summary_only:
            raise NotProved('A payment was read from page %s, the summary page of this period, which lists no payments.'
                            % row['page'])
        amount = row_amount(row, exponent, liability)
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
                **(dict(account_basis=basis) if basis else {}),
                # The complete number the page images read beside a masked one (FULL_NUMBER_FROM_IMAGES).
                **(dict(full_account_number=_digits(header.get('full_account_number'))) if basis == LAST4_BASIS
                   and _digits(header.get('full_account_number')) else {}),
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
    from services.financial.summary_pages import balance_pages
    # Its pages and its summary page before them, where a card prints its previous and new balance (summary_pages).
    cited = balance_pages(proposal)
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
        if page not in cited:
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


def _render(path, pages, reader):
    """The pages in this reader's strips (a reader without its own strips: the default)."""
    return render_pages(path, pages) if reader.strips is None else render_pages(path, pages, strips=reader.strips)


# Each provider's request settings (in code, never .env). DeepSeek (benchmarked 2026-10-28): max thinking, 6 strips a
# page (it gives each image a fixed token budget, so narrower strips keep the print legible), a long read (a long
# statement takes up to ~25 minutes), 2 retries of a dropped connection or a server error. OpenAI: as before.
PROVIDER_NAMES = {'deepseek': 'DeepSeek', 'openai': 'OpenAI'}
READER_SETTINGS = {
    'deepseek': dict(strips=6, timeout=1500, max_output_tokens=DEEPSEEK_RESERVE_OUTPUT_TOKENS, retries=2),
    'openai': dict(strips=STRIPS, timeout=PAGE_TIMEOUT_SECONDS, max_output_tokens=16000, retries=0),
}
RETRY_PAUSE_SECONDS = 5
# The OpenAI client tries a request up to 3 times (its own 2 retries); its timeout applies to connecting and to
# reading each, and it may pause up to a minute between tries.
OPENAI_CLIENT_TRIES = 3
OPENAI_RETRY_PAUSE_SECONDS = 60
CONNECT_SECONDS = 10


def reader_worst_seconds(reader):
    """The longest one reader's request can take: every try at its full allowance, with the pauses between."""
    settings = READER_SETTINGS.get(reader.provider)
    if settings is None:
        return 0
    from services.llm_service import LLMExecutionContext
    tries = settings['retries'] + 1
    pauses = sum(RETRY_PAUSE_SECONDS * (n + 1) for n in range(settings['retries']))
    if reader.provider == 'openai':
        return tries * OPENAI_CLIENT_TRIES * 2 * settings['timeout'] + tries * (OPENAI_CLIENT_TRIES - 1) * \
            OPENAI_RETRY_PAUSE_SECONDS + pauses
    # DeepSeek: the clock deadline is checked as each piece arrives, and a silent connection is dropped after
    # DEEPSEEK_READ_GAP_SECONDS, so one try ends by timeout + gap.
    return tries * (settings['timeout'] + LLMExecutionContext.DEEPSEEK_READ_GAP_SECONDS + CONNECT_SECONDS) + pauses


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
            keyed = keyed_page_reader(provider, model_id, api_key, context=f'case {str(case_id)[:8]}', warn=False)
            reader.read, reader.unavailable = keyed.read, keyed.unavailable
    if reader.unavailable:
        log.warning('Page-image reader %s %s not used for case %s: %s', provider, model_id, str(case_id)[:8],
                    reader.unavailable)
    return reader


def keyed_page_reader(provider, model_id, api_key, *, context='', warn=True):
    """PageReader for ``provider``/``model_id`` with a key in hand (provider_page_reader; benchmarks). Checked before
    any page is rendered or sent: never to a model that does not take images (ai_model_capabilities)."""
    from services.ai_model_capabilities import ModelCannotReadImages, require_images
    settings = READER_SETTINGS.get(provider) or {}
    reader = PageReader(provider=provider, model=model_id, read=None, unavailable='',
                        strips=settings.get('strips', STRIPS),
                        max_output_tokens=settings.get('max_output_tokens', RESERVE_OUTPUT_TOKENS))
    if not settings:
        reader.unavailable = f'page-image reading is not available for {provider}'
    else:
        try:
            require_images(provider, model_id, api_key=api_key, context=context)
            reader.read = document_request(model_id, api_key, provider)
        except ModelCannotReadImages as error:
            reader.unavailable = str(error)
    if warn and reader.unavailable:
        log.warning('Page-image reader %s %s not used (%s): %s', provider, model_id, context, reader.unavailable)
    return reader


def chain_page_reader(db, case_id):
    """The readers of the workload's chain, in order (ai_model_policy.get_workload_chain): DeepSeek first, OpenAI the
    failsafe by default. A reader that cannot be used now is kept with its reason; the chain starts at the next."""
    from services.ai_model_policy import deepseek_only, get_workload_chain
    only = deepseek_only(db, WORKLOAD)
    readers = []
    for entry in get_workload_chain(db, WORKLOAD):
        if only and entry['provider'] != 'deepseek':
            # "DeepSeek only" is ON: this reader is not built and nothing is sent to it; the reason shows on the
            # outcome ("OpenAI failover is switched off").
            readers.append(PageReader(provider=entry['provider'], model=entry['model_id'], read=None,
                                      unavailable=f'{provider_name(entry["provider"])} failover is switched off',
                                      switched_off=True, strips=None, max_output_tokens=RESERVE_OUTPUT_TOKENS))
            continue
        readers.append(provider_page_reader(db, case_id, entry['provider'], entry['model_id']))
    return readers


def switched_off(db, provider):
    """Why ``provider`` is not sent page images now ("DeepSeek only" is ON and it is not DeepSeek), else ''.

    Scope (fin-deepseek, 2026-10-28): the switch decides who reads NOW. While ON nothing is sent to another provider,
    and no reading by it decides a new outcome of the chain or a new replacement of a saved statement. Evidence
    already accepted before the switch (stored proved readings behind ready/imported statements, their printed
    counts, offers a person already holds, the learning loop's record of proved readings) stays as it was: undoing it
    would un-settle statements that are already settled (Rule 0, no regression)."""
    from services.ai_model_policy import deepseek_only
    if provider != 'deepseek' and deepseek_only(db, WORKLOAD):
        return f'{provider_name(provider)} failover is switched off'
    return ''


def reading_provider(record):
    """Who read a stored outcome's deciding reading: its provider; a reading stored before the chain was OpenAI's."""
    return (record or {}).get('provider') or 'openai'


def _single(db, case_id, provider, model_id):
    why = switched_off(db, provider)
    if why:
        raise RuntimeError(why)
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


def workload_page_reader(db, case_id):
    """(model_id, read) of the first reader of the workload's chain that can be used now (chain_page_reader: the
    "DeepSeek only" switch, keys and the image check apply); raises with every reason when none can."""
    readers = chain_page_reader(db, case_id)
    for reader in readers:
        if not reader.unavailable:
            return reader.model, reader.read
    raise RuntimeError('; '.join(f'{provider_name(r.provider)} {r.model}: {r.unavailable}' for r in readers))


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
    # A reader switched off (DeepSeek only) is not part of it: switching OpenAI failover back on reads held
    # statements again, with the failsafe.
    return ' > '.join(f'{r.provider}/{r.model}' for r in readers
                      if not getattr(r, 'switched_off', False)) + f' ({PROMPT_VERSION})'


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
        prompt, _ = page_instructions(len(pages), strips)
        for attempt in range(settings['retries'] + 1):
            context = LLMExecutionContext(provider, model_id, api_key=api_key)
            try:
                text = context.call_vision_json(prompt, images, image_labels=labels, schema=DOCUMENT_SCHEMA,
                                                schema_name='statement_document', timeout=settings['timeout'],
                                                max_output_tokens=settings['max_output_tokens'])
                break
            except Exception as error:  # noqa: BLE001 - retried only when the connection or server failed
                if attempt >= settings['retries'] or not _retryable(error):
                    # What the provider reported it used (an answer cut short is billed), for the caller to count.
                    error.usage = dict(context.last_usage or {})
                    raise
                log.warning('Page-image request to %s failed (%s: %s); trying again (%s of %s)', provider,
                            type(error).__name__, str(error)[:200], attempt + 1, settings['retries'])
                time.sleep(RETRY_PAUSE_SECONDS * (attempt + 1))
        try:
            document = json.loads(text)
        except ValueError as error:
            unreadable = UnreadableAnswer('the answer was not valid JSON')
            unreadable.usage = dict(context.last_usage or {})
            raise unreadable from error
        if not isinstance(document, dict):
            unreadable = UnreadableAnswer('the answer was not a JSON object')
            unreadable.usage = dict(context.last_usage or {})
            raise unreadable
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


def period_pages(proposal):
    """The pages read from page images for this held period: statement_pages, and its summary pages before it that
    the text reading found (SUMMARY_PAGES, summary_pages)."""
    from services.financial.summary_pages import statement_summary_pages
    pages = statement_pages(proposal)
    if not SUMMARY_PAGES or not pages:
        return pages
    return sorted(set(pages) | set(statement_summary_pages(proposal)))


def rejudgeable(record, revision=None, model_id=None, pages=None, due=False):
    """A stored not-proved outcome judged under older proof rules, whose stored page reading is judged
    again under the current ones (no new request). With ``revision``: only for the same reading of
    the file, the same model and the same pages the stored page reading covers. ``due``: one judged under these
    rules that is due again all the same (due_again: it waits on another statement of its card, or the card it
    waited on is now saved)."""
    if not (REJUDGE and record and record.get('version') == VERSION and isinstance(record.get('raw'), dict)
            and ((record.get('proof') or 1) < PROOF_VERSION or due)):
        return False
    status = record.get('status')
    if status != 'not_proved' and not (status == 'reading' and record.get('rejudging') and not _being_read(record)):
        return False
    if revision is not None and (record.get('revision') != revision
                                 or _without_prompt(_reader_of(record)) != _without_prompt(model_id)
                                 or list(record.get('pages') or []) != list(pages or [])):
        return False
    return True


_PROMPT_SUFFIX = re.compile(r' \(statement-pages-[^)]*\)$')


def _without_prompt(reader_id):
    """A chain id without its instructions' version: a stored page reading is judged again under new proof rules
    whatever instructions it was read with (a new prompt reads only what is read anew, never re-judging)."""
    return _PROMPT_SUFFIX.sub('', str(reader_id or ''))


def _judged(stored, **extra):
    """A stored not-proved outcome (or an abandoned re-judge claim of one) marked judged under these rules."""
    record = {k: v for k, v in stored.items() if k not in ('rejudging', 'claim_id', 'waiting')}
    return dict(record, status='not_proved', proof=PROOF_VERSION, **extra)


def _stored(file, key):
    return ((file.metadata_ or {}).get(METADATA_KEY) or {}).get(key or '')


def _being_read(stored):
    if not stored or stored.get('status') != 'reading':
        return False
    started = datetime.fromisoformat(stored['at'])
    return (datetime.now(timezone.utc) - started).total_seconds() < CLAIM_SECONDS


def _store(db, file_id, key, record, claim=None, rejudge=None, owner=None, unchanged=None):
    """Store the record under the file's lock. With ``claim=(revision, model)``: False, storing
    nothing, when the statement is being read, was read or was given up (checked under the lock).
    With ``rejudge=(revision, model, pages)``: False, storing nothing, unless the stored outcome is
    still one to judge again from its stored page reading (rejudgeable). With ``owner``: False, storing
    nothing, unless the stored record is this worker's re-judge claim or still rejudgeable. With ``unchanged``: False,
    storing nothing, unless the stored record is still that one."""
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
    if unchanged is not None and previous != unchanged:
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


def reserve_usd(model_id, images, max_output_tokens=None):
    """The most a request with these images can cost (counted before it is sent). Not given, the output reserved is
    the provider's cap: a DeepSeek request may answer up to DEEPSEEK_RESERVE_OUTPUT_TOKENS (its thinking counts)."""
    if max_output_tokens is None:
        max_output_tokens = DEEPSEEK_RESERVE_OUTPUT_TOKENS if str(model_id).startswith('deepseek') \
            else RESERVE_OUTPUT_TOKENS
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
    first = message.split(' ', 1)[0]
    # Lower-cased to run on in a sentence, unless the first word is a name or an acronym (DeepSeek, OpenAI, PDF).
    keep = first[1:] != first[1:].lower() or message[:2] == message[:2].upper()
    return message if keep else message[:1].lower() + message[1:]


def _attempt_words(attempt):
    name = provider_name(attempt.get('provider'))
    status, message = attempt.get('status'), _clause(attempt.get('message'))
    if status == 'not_proved':
        return f'{name} could not prove it: {message}'
    if status == 'failed':
        return f'{name} could not read it: {message}'
    if status == 'stale':
        return f'{name} read it while the statement changed'
    if status == 'switched_off':
        return f'{name} failover is switched off'
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
    if 'deferred' in statuses and 'failed' not in statuses:
        # A reader was not started for lack of time: not a final outcome; read again in a later round.
        record.update(status='unavailable', message='The page images are read again later; the statement stays held. '
                                                    + details)
    elif 'failed' in statuses:
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


def _current(record, revision, model_id, pages=None):
    """A final outcome of this reading of the file by this reader; with ``pages``, of these same pages (a period read
    now with more pages, SUMMARY_PAGES, is read anew)."""
    return (record and record.get('version') == VERSION and record.get('revision') == revision
            and _reader_of(record) == model_id and record.get('status') in FINAL
            and (pages is None or list(record.get('pages') or []) == list(pages)))


def read_item(factory, item_id, resolve_path, *, page_reader=None, knowledge_for=None, apply=True, force=False,
              numbers_of=None):
    """Read one held statement from its page images (_read_item) and record the outcome, whatever it is (_decided):
    a journal line, the statement's outcome history and, a skip, its queue note. Measuring records nothing.
    ``numbers_of(path)``: the numbers the file's text prints (printed_numbers; injectable for tests)."""
    record = _read_item(factory, item_id, resolve_path, page_reader=page_reader, knowledge_for=knowledge_for,
                        apply=apply, force=force, numbers_of=numbers_of)
    if apply and not force:
        _decided(factory, item_id, record)
    return record


def _read_item(factory, item_id, resolve_path, *, page_reader=None, knowledge_for=None, apply=True, force=False,
               numbers_of=None):
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
            pages = period_pages(proposal)
            if not pages:
                return dict(record, reason='no_pages')
            if len(pages) > MAX_PAGES:
                record.update(status='not_proved', message=f'This period has {len(pages)} pages; page images are read for periods up to {MAX_PAGES} pages.')
                return _finish(factory, item_id, file_id, key, dict(record, revision=proposal['revision'], pages=pages,
                                                                    pages_rule=PAGES_RULE), apply)
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
            due = not force and due_again(stored, lambda: knowledge_for(db, case_id))
            again = not force and rejudgeable(stored, proposal['revision'], model_id, pages, due=due)
            same_pages = list((stored or {}).get('pages') or []) == list(pages)
            if not again and not force and rejudgeable(stored):
                # Judged again only from the same stored page reading; never requested anew for it. Marked
                # judged under these rules, so it is not offered again (as before re-judging existed). A period
                # now read with more pages (SUMMARY_PAGES) is not marked as looked at: it is read anew next time.
                if apply:
                    # Under the file's lock, only while it is still that outcome (rejudgeable, any reading).
                    _store(db, file_id, key, _judged(stored, **({'pages_rule': PAGES_RULE} if same_pages else
                                                              {'read_anew_at': datetime.now(timezone.utc).isoformat()})),
                           rejudge=(None, None, None))
                    db.commit()
                else:
                    db.rollback()
                return dict(stored, reason='already_read')
            if _current(stored, proposal['revision'], model_id, pages) and not force and not again:
                if apply and (stored.get('pages_rule') or 0) != PAGES_RULE:
                    # Its pages are still the ones read (SUMMARY_PAGES adds none): marked looked at, nothing read.
                    _store(db, file_id, key, dict(stored, pages_rule=PAGES_RULE), unchanged=stored)
                    db.commit()
                return dict(stored, reason='already_read')
            if _being_read(stored) and not force:
                return dict(record, reason='being_read')
            record.update(revision=proposal['revision'], model=model_id, reader=model_id, pages=pages, pages_rule=PAGES_RULE,
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
                                  rejudge=(proposal['revision'], model_id, pages, due)):
                        db.rollback()
                        return dict(record, reason='being_read')
                    db.commit()
                else:
                    db.rollback()
            elif apply:
                # The claim, checked again under the file's lock (another worker may hold it).
                if not _store(db, file_id, key, dict(record, status='reading'), claim=(proposal['revision'], model_id, pages)):
                    db.rollback()
                    return dict(record, reason='being_read')
                db.commit()
            else:
                db.rollback()
        # A reader not used now (switched off by "DeepSeek only", no key, cannot read images) is never judged from a
        # reading it stored earlier either: only the readers in use decide.
        not_used = {(r.provider, r.model) for r in readers if r.unavailable and r.provider}
        if again:
            # The page readings already stored, judged under the current proof rules: no request, no cost.
            candidates = [(reader, raw) for reader, raw in stored_attempts(stored)
                          if (reader.provider, reader.model) not in not_used]
            # The readers not used now still show why ("OpenAI failover is switched off").
            candidates += [(reader, None) for reader in readers if reader.unavailable and reader.provider]
        else:
            # A reading of an earlier try of this same reading of the file (the chain stopped at a failed request)
            # is judged again rather than requested again.
            reuse = _reusable(stored, record['revision'], pages)
            candidates = [(reader, None if reader.unavailable else reuse.get(_attempt_key(reader))) for reader in readers]
        attempts, accepted, waiting = [], None, None
        spent_now, seconds, page_costs = 0.0, 0.0, {}
        chain_started = time.monotonic()
        for reader, raw in candidates:
            attempt = dict(provider=reader.provider, model=reader.model,
                           prompt_version=getattr(reader, 'prompt_version', None) or (PROMPT_VERSION if reader.provider else None))
            if raw is None and reader.unavailable:
                attempts.append(dict(attempt, status='switched_off' if getattr(reader, 'switched_off', False)
                                     else 'unavailable', message=reader.unavailable))
                continue
            if raw is None and time.monotonic() - chain_started + reader_worst_seconds(reader) > CHAIN_SECONDS:
                # It could outlast the claim: not started now; the statement is read again in a later round.
                attempts.append(dict(attempt, status='deferred',
                                     message='not enough time was left to read it in this round'))
                continue
            if raw is None:
                # Outside any lock or transaction: render (in this reader's strips) and read.
                images = _render(path, pages, reader)
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
                    failed = dict(attempt, status='failed', error=type(error).__name__,
                                  message=failure_words(error), seconds=took)
                    usage = getattr(error, 'usage', None) or {}
                    if usage.get('completion_tokens'):
                        # An answer cut short or unreadable is billed: its cost is counted (the reservation stays).
                        cost = cost_usd(reader.model, usage)
                        spent_now += cost
                        failed.update(cost_usd=round(cost, 6), prompt_tokens=usage.get('prompt_tokens'),
                                      completion_tokens=usage.get('completion_tokens'))
                        for number, _ in images:
                            share = page_costs.setdefault(number, dict(page=number, prompt_tokens=0,
                                                                       completion_tokens=0, cost_usd=0.0))
                            share['prompt_tokens'] += round((usage.get('prompt_tokens') or 0) / len(images))
                            share['completion_tokens'] += round((usage.get('completion_tokens') or 0) / len(images))
                            share['cost_usd'] = round(share['cost_usd'] + cost / len(images), 6)
                    attempts.append(failed)
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
                    if reading.get('account_basis') == LAST4_BASIS:
                        # The first statement of a card printing only its last digits: its file's text and its turn.
                        full = last4_turn(db, case_id, item_id, reading, path, numbers_of=numbers_of)
                        reading['full_number_confirmed'] = full
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
                    attempts.append(dict(attempt, status='not_proved', message=str(reason),
                                         **({'account_wait': reason.card} if reason.card else {})))
                    if isinstance(reason, WaitsForCard):
                        # Not this statement's turn: judged again later, once the card's earlier statement is.
                        waiting = reason
                        break
                except Exception as error:  # noqa: BLE001 - this reading could not be judged: the next one reads
                    db.rollback()
                    if reader.provider is None:
                        raise
                    log.exception('Judging the page-image reading by %s %s failed', reader.provider, reader.model)
                    attempts.append(dict(attempt, status='failed', error=type(error).__name__,
                                         message=f'its reading could not be checked ({type(error).__name__})'))
        record = _outcome(record, attempts, accepted, spent_now, seconds, page_costs, again)
        if accepted is None:
            if waiting is not None:
                # Not final (waiting, due_again): judged again from the stored reading, in a later pass or round.
                record.update(status='not_proved', message=str(waiting), waiting=True)
                return dict(_finish(factory, item_id, file_id, key, record, apply), reason='waits_for_card')
            wait = next((a['account_wait'] for a in attempts if a.get('account_wait')), None)
            if wait:
                record['account_wait'] = wait  # judged again once the card's first statement is accepted
            return _finish(factory, item_id, file_id, key, record, apply)
        if accepted.get('basis') == 'dates_from_page_images':
            record['basis'] = 'dates_from_page_images'
        else:
            if reading.get('account_basis'):
                # The first statement of its account (FIRST_STATEMENT, LAST4_FIRST_STATEMENT): what admitted its
                # header, recorded with it.
                full = reading.get('full_number_confirmed')
                record.update(account_basis=reading['account_basis'], message=record['message'] + (
                    FULL_NUMBER_NOTE % full if full else
                    LAST4_NOTE if reading['account_basis'] == LAST4_BASIS else FIRST_STATEMENT_NOTE))
                if reading['account_basis'] == LAST4_BASIS:
                    record['card'] = last4_card(reading)
                    if full:
                        record['card']['full_number'] = full
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
    if saved and reading.get('account_basis') == LAST4_BASIS:
        # A saved statement's account is in the case already: a card is never created from its replacement.
        raise NotProved(masked_only_reason(reading['account_number'], None, proposal,
                                           'a saved statement is never the first statement of a card'))
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


# ---------------------------------------------------------------------------
# The first statement of a card printing only its last digits (LAST4_FIRST_STATEMENT): whose turn it is
# ---------------------------------------------------------------------------

# Statements whose status settles nothing more about their card: imported ones are in its saved account (checked
# through the case's accounts), the others are not statements of it any more.
SETTLED_STATUSES = ('imported', 'removed', 'superseded_reading', 'duplicate_ignored', 'skipped')
# A run of digits; digits joined by hyphens; or a card number printed in groups (13 to 19 digits in groups of 3 to 7,
# separated by spaces, non-breaking spaces, dots or hyphens, a line break included: 4-4-4-4, Amex 4-6-5).
_LONGER = re.compile(r'(?<![\d-])(?:\d{3,7}(?:[\s\u00a0.\-]{1,3}\d{3,7}){2,5}|\d+(?:-\d+)+|\d{6,})(?![\d-])')
_CARD_GROUPS = re.compile(r'\d{3,7}(?:[\s\u00a0.\-]{1,3}\d{3,7}){2,5}')
_printed_cache = {}
_printed_lock = threading.Lock()


def printed_numbers(path):
    """Every number of at least 6 digits (a full account number, as field_proposals.FULL_ACCOUNT_DIGITS) the file's
    text layer prints, digits only: a run of digits, digits joined by hyphens, or a card number printed in groups
    (_LONGER). Cached per file (path, size, time)."""
    import fitz
    stat = os.stat(str(path))
    key = (str(path), stat.st_size, stat.st_mtime)
    with _printed_lock:
        if key in _printed_cache:
            return _printed_cache[key]
    found = set()
    with fitz.open(str(path)) as document:
        for page in document:
            text = page.get_text() or ''
            for match in _LONGER.finditer(text):
                digits = _digits(match.group(0))
                if _CARD_GROUPS.fullmatch(match.group(0)) and not 13 <= len(digits) <= 19:
                    # Groups that do not make a card number as a whole: each run of 6 digits or more on its own, and
                    # every run of neighbouring groups that makes 13 to 19 digits ("Ref 1234 5178 0512 3456 8160").
                    groups = re.findall(r'\d+', match.group(0))
                    found.update(g for g in groups if len(g) >= 6)
                    for first in range(len(groups)):
                        for last in range(first + 2, len(groups)):
                            joined = ''.join(groups[first:last + 1])
                            if 13 <= len(joined) <= 19:
                                found.add(joined)
                    continue
                if len(digits) >= 6:
                    found.add(digits)
    with _printed_lock:
        _printed_cache.clear()  # one file at a time is enough: a round reads one file's statements together
        _printed_cache[key] = found
    return found


def _same_card(digits, institution, account, bank):
    from services.financial import field_proposals as fp
    if not fp.account_match((digits, True), fp.account_identity(account)):
        return False
    return not bank or not institution or fp.same_institution(institution, bank)


def card_turn(db, case_id, item_id, card):
    """(LAST4_FIRST_STATEMENT) NotProved when the case already records an account with the card's last digits at its
    bank; WaitsForCard while another statement of the card goes first: an earlier held one still to be judged (or
    itself waiting), or one saved and not yet imported. An earlier one held after its reading was accepted (its save
    or import refused) is decided: it waits for a person, and this one is not held for it. ``card``: dict(digits, institution, holder, period_start) of the reading."""
    from services.financial import field_proposals as fp
    from postgres.models.financial import FinancialAccount as Account
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
                                                          FinancialImportBatchItem as Item)
    digits, institution = card['digits'], card['institution']
    ending = digits[-4:]
    for account in db.scalars(select(Account).where(Account.case_id == case_id)):
        if _same_card(digits, institution, account.identifier_as_printed or account.identifier_normalised or '',
                      account.institution_name):
            if account.holder_name and card.get('holder') and not fp.same_holder(card['holder'], account.holder_name):
                raise NotProved('This card (ending %s) is saved for %s; this statement prints %s. Confirm whether they '
                                'are the same account.' % (ending, _one_line(account.holder_name), _one_line(card['holder'])))
            raise NotProved('An account with the same last digits (%s at %s) is already recorded in this case. Choose '
                            'whether this statement belongs to it.' % (account.identifier_as_printed or ending,
                                                                       account.institution_name or 'a bank not recorded'))
    ours = (card.get('period_start') or '', str(item_id))
    others = db.execute(select(Item.id, Item.status, Item.statement_key, Item.file_id, Item.summary)
                        .join(Batch, Batch.id == Item.batch_id)
                        .where(Batch.case_id == case_id, Batch.status != 'removed', Item.id != item_id,
                               Item.status.notin_(SETTLED_STATUSES))).all()
    metadata = {}
    for other_id, status, key, file_id, summary in sorted(others, key=lambda r: ((r[4] or {}).get('period_start') or '', str(r[0]))):
        summary = summary or {}
        if not _same_card(digits, institution, summary.get('account') or '', summary.get('institution')):
            continue
        when = summary.get('period_start') or ''
        period = ' to '.join(v for v in (when, summary.get('period_end') or '') if v) or 'a period not read'
        if status != 'attention':
            raise WaitsForCard('Another statement of this card (ending %s, %s) is accepted and waits to be imported; '
                               'this one follows it once it is.' % (ending, period))
        if file_id not in metadata:
            metadata[file_id] = db.scalar(select(EvidenceFile.metadata_).where(EvidenceFile.id == file_id)) or {}
        stored = (metadata[file_id].get(METADATA_KEY) or {}).get(key or '')
        if stored and stored.get('status') == 'proved':
            # Its reading was accepted (saved as System) and it is held again: it can still be imported into this
            # card's account later (by the automatic save or a person's retry), and the import joins on bank and last
            # digits alone. So another holder is never let through beside it; the same holder is the same account.
            theirs = ((stored.get('card') or {}).get('holder') or (stored.get('text_reading') or {}).get('holder')
                      or summary.get('holder') or '')
            if not (theirs and card.get('holder') and fp.same_holder(theirs, card['holder'])):
                raise NotProved('Another statement of this card (ending %s, %s) was accepted for %s and waits for a '
                                'person; this statement prints %s. Confirm whether they are the same account.' % (
                                    ending, period, _one_line(theirs) or 'a holder not read',
                                    _one_line(card.get('holder')) or 'no holder'))
            continue
        if (when, str(other_id)) >= ours:
            continue
        if stored and (rejudgeable(stored) or _being_read(stored) or _fresh_wait(stored) or _to_read_anew(stored)):
            raise WaitsForCard('An earlier statement of this card (ending %s, %s) is checked first: a card is '
                               'confirmed from its earliest statement. This one follows it.' % (ending, period))


# A wait is refreshed each time its statement is judged again (every round or pass while it waits); one not judged
# for this long (its batch paused, its file removed or queued to be prepared again) no longer holds the others back.
WAIT_FRESH_SECONDS = 2 * 3600
READ_ANEW_HOLD_SECONDS = 24 * 3600


def _to_read_anew(stored):
    """A not-proved outcome listed to be read anew with more pages (SUMMARY_PAGES: marked, not yet read): still to be
    judged, so a later statement of its card does not go before it. Marking costs nothing and is done for a whole
    backlog at once, while reading takes minutes each (fdaf956c's 52 took about 1.5 hours), so the hold lasts
    READ_ANEW_HOLD_SECONDS from the mark: long enough for any backlog, and one never read (its batch paused, its file
    removed) stops holding the others after it."""
    if not (stored.get('status') == 'not_proved' and (stored.get('pages_rule') or 0) != PAGES_RULE
            and stored.get('read_anew_at')):
        return False
    try:
        started = datetime.fromisoformat(stored['read_anew_at'])
        return (datetime.now(timezone.utc) - started).total_seconds() < READ_ANEW_HOLD_SECONDS
    except (TypeError, ValueError):
        return False


def _fresh_wait(stored):
    if not (stored.get('status') == 'not_proved' and stored.get('waiting')):
        return False
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(stored['at'])).total_seconds() < WAIT_FRESH_SECONDS
    except (KeyError, TypeError, ValueError):
        return False


def last4_turn(db, case_id, item_id, reading, path, numbers_of=None):
    """(LAST4_FIRST_STATEMENT) The checks a card's first statement needs beyond its own pages: the file's text layer
    prints no longer number ending in its digits (rule 1 is that number's route), and it is the card's turn
    (card_turn). NotProved with the plain reason, or WaitsForCard."""
    proposal = dict(metadata=dict(balance_convention='liability_owed'))
    digits = _digits(reading['account_number'])
    try:
        numbers = (numbers_of or printed_numbers)(path)
    except Exception as error:  # noqa: BLE001 - fail closed: the text layer could not be checked
        raise NotProved(masked_only_reason(reading['account_number'], True, proposal,
                                           'the text of its file could not be checked (%s)' % type(error).__name__))
    longer = sorted(n for n in numbers if len(n) > len(digits) and n.endswith(digits))
    full = None
    if longer:
        full = full_number_confirmed(reading, longer)
        if not full:
            raise NotProved(longer_number_reason(reading['account_number'], longer, True, proposal),
                            card=card_key(reading['institution'], digits))
    card_turn(db, case_id, item_id, last4_card(reading))
    return full


def full_number_confirmed(reading, longer):
    """(FULL_NUMBER_FROM_IMAGES) The card's complete number when the page images read it (full_account_number), it
    is a card number (13 to 19 digits, Luhn check digit) and it is the one longer number ending in its last digits the
    file's text prints, digit for digit; else None."""
    full = _digits(reading.get('full_account_number'))
    if not (FULL_NUMBER_FROM_IMAGES and full and 13 <= len(full) <= 19 and _luhn(full) and len(longer) == 1
            and full == longer[0] and full.endswith(_digits(reading['account_number']))):
        return None
    return full


def _luhn(digits):
    """A card number's check digit holds (ISO/IEC 7812)."""
    total = 0
    for index, digit in enumerate(reversed(digits)):
        value = int(digit) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def last4_card(reading):
    return dict(digits=_digits(reading['account_number']), institution=reading['institution'],
                holder=reading['holder'], period_start=reading['period_start'])


def _lock_card(db, case_id, card):
    """Serialise the first statement of one card across workers (the lock ends with the transaction): keyed on the
    case and the last 4 digits only, so two spellings of one bank share it."""
    if db.get_bind().dialect.name != 'postgresql':
        return
    from sqlalchemy import text
    db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
               dict(key='financial-last4|%s|%s' % (case_id, _digits(card['digits'])[-4:])))


def card_known(knowledge, card):
    """A saved account of the case (knowledge) carries the card a refusal waited on (card_key): its last digits at
    its bank, as first_statement_basis finds a clash."""
    from services.financial import field_proposals as fp
    last4, _, bank = str(card or '').partition('|')
    if not last4:
        return False
    return any(fp.account_match((last4, True), (k.digits, k.masked)) and _at_bank(k, bank)
               for k in getattr(knowledge, 'accounts', []) or [])


def due_again(stored, knowledge):
    """(LAST4_FIRST_STATEMENT) A not-proved outcome judged under these rules that is judged again from its stored
    reading all the same: it waited on another statement of its card (WaitsForCard, never final), or it was refused
    only because no statement of its card was confirmed yet and the case now holds the card's account (accepted by
    this rule, or confirmed by a person). ``knowledge``: a callable giving the case's knowledge, called only then."""
    if not (stored and stored.get('status') == 'not_proved'):
        return False
    if stored.get('waiting'):
        return True
    return bool(stored.get('account_wait')) and card_known(knowledge(), stored['account_wait'])


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
        card = record.get('card') if record.get('account_basis') == LAST4_BASIS else None
        if card:
            # A card's first statement: its turn is checked again under the card's lock, held until this save
            # commits, so two workers never both create one card.
            _lock_card(db, case_id, card)
            try:
                card_turn(db, case_id, item_id, card)
            except NotProved as reason:
                db.rollback()
                waits = isinstance(reason, WaitsForCard)
                held = {k: v for k, v in record.items() if k not in ('account_basis', 'card')}
                held.update(status='not_proved', message=str(reason), **({'waiting': True} if waits else {}))
                done = _finish(factory, item_id, file_id, key, held, True)
                return dict(done, reason='waits_for_card') if waits else done
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
            # Only readers in use decide, from a stored reading too (not switched off, not unavailable).
            not_used = {(r.provider, r.model) for r in readers if r.unavailable and r.provider}
            candidates = [(reader, raw) for reader, raw in candidates
                          if raw is None or ((reader.provider, reader.model) not in not_used
                                             and not switched_off(db, reader.provider or 'openai'))]
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
        chain_started = time.monotonic()
        for reader, raw in candidates:
            attempt = dict(provider=reader.provider, model=reader.model,
                           prompt_version=getattr(reader, 'prompt_version', None) or (PROMPT_VERSION if reader.provider else None))
            if raw is None and reader.unavailable:
                attempts.append(dict(attempt, status='switched_off' if getattr(reader, 'switched_off', False)
                                     else 'unavailable', message=reader.unavailable))
                continue
            if raw is None and time.monotonic() - chain_started + reader_worst_seconds(reader) > CHAIN_SECONDS:
                attempts.append(dict(attempt, status='deferred',
                                     message='not enough time was left to read it in this round'))
                continue
            if raw is None:
                images = _render(path, pages, reader)
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
                    failed = dict(attempt, status='failed', error=type(error).__name__,
                                  message=failure_words(error), seconds=round(time.monotonic() - started, 1))
                    usage = getattr(error, 'usage', None) or {}
                    if usage.get('completion_tokens'):
                        cost = cost_usd(reader.model, usage)  # billed though it failed (the reservation stays)
                        spent_now += cost
                        failed['cost_usd'] = round(cost, 6)
                        for number, _ in images:
                            share = page_costs.setdefault(number, dict(page=number, prompt_tokens=0,
                                                                       completion_tokens=0, cost_usd=0.0))
                            share['cost_usd'] = round(share['cost_usd'] + cost / len(images), 6)
                    attempts.append(failed)
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
    if switched_off(db, reading_provider(stored)):
        # "DeepSeek only" is ON: a reading by another provider decides nothing.
        return None, 'image_reader_switched_off'
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
    from services.financial.field_proposals import case_knowledge
    cases, knowledge = dict(db.execute(select(Batch.id, Batch.case_id).where(Batch.id.in_(list(marked)))).all()), {}

    def knowledge_of(batch_id):
        case_id = cases[batch_id]
        if case_id not in knowledge:
            knowledge[case_id] = case_knowledge(db, case_id)
        return knowledge[case_id]
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
        due = stored and stored.get('version') == VERSION and due_again(stored, lambda: knowledge_of(batch_id))
        looked_at = not (stored and stored.get('status') == 'not_proved' and (stored.get('pages_rule') or 0) != PAGES_RULE)
        if stored and stored.get('version') == VERSION and not rejudgeable(stored, due=due) and looked_at and (stored.get('status') in FINAL or (
                stored.get('status') == 'failed' and (stored.get('failures') or 0) >= MAX_FAILURES)):
            # Read once per reading of the file (a new reading is a new file, with its own statements).
            continue
        found.append(item_id)
        if len(found) >= limit:
            break
    return found


_skip_until = {}
WAIT_SKIP_SECONDS = 600
PENDING_LIMIT = 2000
# Statements read at once by a round (each a request of minutes to DeepSeek; small: the host is short of memory).
READ_CONCURRENCY = 3


def sweep(factory, resolve_path, *, budget_seconds=SWEEP_SECONDS, concurrency=None):
    """Background round: read held statements from their page images, up to READ_CONCURRENCY at once (a DeepSeek
    reading takes minutes; each statement's claim keeps any two workers from reading the same one). No new reading
    starts once the round's time is used; those started are finished. Never raises."""
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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

    later, progressed = [], [False]

    def tally(item_id, outcome):
        reason = outcome.get('reason')
        if reason == 'waits_for_card':
            # Another statement of its card goes first: tried again after it, in this round's next pass.
            later.append(item_id)
            return
        progressed[0] = True
        if reason in ('already_read', 'being_read'):
            _skip_until[item_id] = now + 600
            return
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

    def one(item_id):
        try:
            return read_item(factory, item_id, resolve_path)
        except Exception:  # noqa: BLE001 - one statement's failure never stops the round
            log.exception('Page-image reading of item %s failed', str(item_id)[:8])
            return dict(status='skipped', reason='error')

    queue, running, stop = list(ids), {}, False
    workers = max(1, int(concurrency or READ_CONCURRENCY))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='page-images') as pool:
        while queue or running or later:
            while queue and not stop and len(running) < workers \
                    and time.monotonic() - started < budget_seconds:
                item_id = queue.pop(0)
                running[pool.submit(one, item_id)] = item_id
            if not running and later and progressed[0] and not stop and time.monotonic() - started < budget_seconds:
                # A pass in which a statement was decided: those waiting on another statement of their card follow.
                queue, later[:], progressed[0] = list(later), [], False
                continue
            if not running:
                break
            done, _ = wait(list(running), return_when=FIRST_COMPLETED)
            for future in done:
                item_id = running.pop(future)
                outcome = future.result()
                tally(item_id, outcome)
                if outcome.get('status') == 'unavailable':
                    stop = True  # no key / provider: nothing else this round can be read either
            if stop or time.monotonic() - started >= budget_seconds:
                queue = []
    for item_id in later:
        # Still waiting at the round's end, nothing ahead of it decided: looked at again in a while, not every round.
        _skip_until[item_id] = now + WAIT_SKIP_SECONDS
    if skipped:
        report['skipped'] = skipped
    if report['read'] or skipped:
        # Every round that decided anything (each statement's own line is logged by read_item).
        log.info('Page-image reading round: %s', report)
    return report
