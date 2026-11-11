"""Spreadsheet statements (CSV, XLSX, XLS) read into the ledger: services.financial.tabular.

Neil, 11 Nov 2026: build the CSV statement reader, and the same for Excel. The column mapping is guessed, a
person confirms it once per layout, and each row is labelled as read from the file with its sheet and line.
Before this reader, a CSV statement produced no ledger rows at all: ``read_native`` refused it as no format
it knew (the demo case's Penn account, 0 of 5 checks to Travis Kell in the ledger).
"""

from __future__ import annotations

import base64
import io
import unittest
import uuid
import zlib
from datetime import date
from pathlib import Path

from postgres.models.enums import ExtractionLayer, ReconciliationStatus, TransactionDirection
from postgres.models.evidence import EvidenceFile
from services.financial.native import CenturyWindow, NativeFormat, read_native
from services.financial.native_precheck import PrecheckOutcome, parse_bytes, precheck_reading
from services.financial.proof_class import ProofClass
from services.financial import tabular

WINDOW = CenturyWindow(date(2000, 1, 1), date(2030, 12, 31))

# The demo case's Penn's Used Tools export, byte for byte as the demo fixture builds it
# (python3 evidence-engine/tests/phone/fixture_builder.py demo <out>: statements/penn).
DEMO_PENN = b"""SYNTHETIC \xe2\x80\x94 INVENTED FOR TESTING \xe2\x80\x94 NOT EVIDENCE\r
Old Ferrow Savings Bank,PENN'S USED TOOLS LLC,Account 5518-020931\r
Date,Description,Amount,Balance\r
03/19/2024,BENCHYARD MARKETPLACE PAYOUT,1945.00,9365.00\r
03/22/2024,CHECK 1043 TRAVIS KELL,-3400.00,5965.00\r
03/23/2024,BENCHYARD MARKETPLACE PAYOUT,2255.00,8220.00\r
03/27/2024,BENCHYARD MARKETPLACE PAYOUT,2565.00,10785.00\r
04/01/2024,TESSALY PROPERTIES RENT,-2100.00,8685.00\r
04/16/2024,BENCHYARD MARKETPLACE PAYOUT,1924.00,10609.00\r
04/19/2024,CHECK 1051 TRAVIS KELL,-2950.00,7659.00\r
04/20/2024,BENCHYARD MARKETPLACE PAYOUT,2234.00,9893.00\r
04/24/2024,BENCHYARD MARKETPLACE PAYOUT,2544.00,12437.00\r
05/07/2024,BENCHYARD MARKETPLACE PAYOUT,1861.00,14298.00\r
05/08/2024,CARD SALE C RUIZ,95.00,14393.00\r
05/10/2024,CHECK 1066 TRAVIS KELL,-4100.00,10293.00\r
05/11/2024,BENCHYARD MARKETPLACE PAYOUT,2171.00,12464.00\r
05/15/2024,BENCHYARD MARKETPLACE PAYOUT,2481.00,14945.00\r
05/21/2024,BENCHYARD MARKETPLACE PAYOUT,1959.00,16904.00\r
05/22/2024,CARD SALE M RUIZ,240.00,17144.00\r
05/24/2024,CHECK 1072 TRAVIS KELL,-3600.00,13544.00\r
05/25/2024,BENCHYARD MARKETPLACE PAYOUT,2269.00,15813.00\r
05/29/2024,BENCHYARD MARKETPLACE PAYOUT,2579.00,18392.00\r
06/04/2024,BENCHYARD MARKETPLACE PAYOUT,2057.00,20449.00\r
06/07/2024,CHECK 1080 TRAVIS KELL,-3900.00,16549.00\r
06/08/2024,BENCHYARD MARKETPLACE PAYOUT,2367.00,18916.00\r
06/12/2024,BENCHYARD MARKETPLACE PAYOUT,2677.00,21593.00\r
"""

# A Mexican bank's XLS (BIFF8, written with xlwt): merged bank name above the table, an account line,
# Cargo/Abono columns, day-first dates formatted as dates, and a Total line.
XLS_FIXTURE = zlib.decompress(base64.b64decode("".join((
    "eNrtWF1IFFEUPnd+1l1z13XTQgMbhLRMMLMfC3Rb11UMVjcV+iGo2d2hRN2RaQ3yocyfxyDoqehFsIderF76oZJ66yEwigiCQIue"
    "egoKelCnc8/Omm4GLpSQzDfcc+8995xzz51z/2ZeTRfMjN8rmYUMNIAIC6YLHEt4DJMrXfECtpsmL6ZzJybTxn8FlxMD6ZDhsftl"
    "Do8hj/csCHBXeo4U4COmk9APbXpCU9YQjeSDyrgP9UgZ3ESOB4rJKx/RGNGNRO+Q5BOih4hzhWg9ys6wEzDtb6uss2bxMaGM2jzA"
    "7T4gnffEqYEieMFn8aWrLCUrQ8DoVnv/s4ZSKQ8mAAPaoiU0g9fz4RbkAjQ1VYfD1ccRM1CIwZ6A76YC8C29qp8pNn9t+QyQ/2M5"
    "P+cPfCcGMZN/TZAAhsA8TYtkDJeDIfGWDRDWz3f3dWuJpH5uDkZ59Cn5ABrVRExX4poSMQa0qKp0BpAZHEBR9aCyq2Z37Z69+/bX"
    "HZABmrXYWRX39aCeiGn9SR1ZQdU4w/NAVE/wvFPtjetuzCOhVqUjFGxtbG1qzwOIBFrala5Ax+FQVwDFuvSk2sv7T+043mU7jptW"
    "Yh7SOORTuYDWoxeHPHf76+twNOI/RZwhOmVSZ9E2PnQw4TLXQGUPtZBRXAgAlaSxk+gwWd1C5RKihSiDeXmkyCo0j5DMKLWWYz+1"
    "hDf+iiXl7Vge+3LkYenYJ/8OLE+2zA4WTr7zj0MZno1x1OfPCFSxKnbjOscjfzpn1r71gWjxb3uYU/BavpvWgZsP8xQzwPfBMQUe"
    "GnuB9Uikw4i3XIeRDrOsiitYFUmC95uqcaviYk0g6+maiDV5sSZhzWFZljIsXxRyieeDwSmB5CWyzKPyFLkS2TI28759FWCNQF7B"
    "ikxWhi0rMlnhsU+1cf8q3jKrxj3a2ucmW9wzKWOsDtJ2WT44FrVTnojw2XpjQLoNgg/u8xeDJ8kv5IINGzZs2LBhw8Z6AL/18KuO"
    "SDef1L3ZYd2i+X+deUwL9m+SdYsO0PFJ4kdlCBKYG3Ahq/mzCWSWtsVWqZP+X8hxFHs3oAei5EdP1vMXv6jY0vGsWtH795ZQtv0v"
    "ZOPnP+7/Jz4QAqA="
))))


def read(data: bytes, name: str, **kwargs):
    kwargs.setdefault("window", WINDOW)
    return read_native(data, file_name=name, **kwargs)


def lines(reading):
    return [(r.reading.transaction_date, r.reading.direction, r.reading.amount_minor, r.reading.description)
            for r in reading.rows]


class DemoStatementTests(unittest.TestCase):
    def test_the_demo_penn_csv_reaches_the_ledger_rows_with_its_lines(self):
        reading = read(DEMO_PENN, "penn-used-tools-old-ferrow-2024.csv", default_currency="USD")
        reading.check_partition()
        self.assertIs(reading.format, NativeFormat.tabular)
        self.assertEqual((reading.row_count, reading.parsed_row_count), (23, 23))
        checks = [r for r in reading.rows if (r.reading.description or "").startswith("CHECK 10")]
        self.assertEqual(len(checks), 5)
        self.assertTrue(all(r.reading.direction is TransactionDirection.debit for r in checks))
        self.assertEqual(checks[0].reading.amount_minor, 340000)
        self.assertEqual(checks[0].source, {"read_from": "file", "file_kind": "csv", "line": 5,
                                            "file": "penn-used-tools-old-ferrow-2024.csv"})
        sale = next(r for r in reading.rows if r.reading.description == "CARD SALE M RUIZ")
        self.assertEqual((sale.reading.direction, sale.reading.amount_minor), (TransactionDirection.credit, 24000))
        # The balance column proves every row, so the export enters at p1 like any totals-free bank export.
        self.assertIs(reading.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(reading.proof_class, ProofClass.p1)
        self.assertIs(reading.extraction_layer, ExtractionLayer.native)
        self.assertEqual(reading.admissibility_reservations, ())
        self.assertEqual({r.account_key for r in reading.rows}, {"5518-020931"})
        self.assertEqual(reading.document.banner_institution, "Old Ferrow Savings Bank")

    def test_the_precheck_shows_the_guessed_mapping_and_its_note(self):
        parse = parse_bytes(DEMO_PENN, window=WINDOW, file_id="f", file_name="penn.csv", default_currency="USD")
        result = precheck_reading(parse.reading, window=WINDOW, distinguisher="a" * 64, file_id="f")
        self.assertIs(result.outcome, PrecheckOutcome.readable)
        layout = result.as_dict()["layouts"][0]
        self.assertEqual(layout["headings"], ["Date", "Description", "Amount", "Balance"])
        self.assertEqual(layout["header_line"], 3)
        self.assertEqual(layout["source"], "guessed")
        self.assertEqual({k: v for k, v in layout["columns"].items() if v is not None},
                         {"date": 0, "description": 1, "amount": 2, "balance": 3})
        self.assertTrue(any("guess" in note for note in result.reader_notes))

    def test_a_byte_format_with_a_csv_name_is_still_that_format(self):
        bai2 = b"01,SENDER,RECEIVER,240115,0800,1,80,,2/\n"
        self.assertEqual(tabular.tabular_kind("x.csv"), "csv")
        from services.financial.native import sniff
        self.assertEqual([f.value for f in sniff(bai2)], ["bai2"])

    def test_a_file_with_no_currency_is_refused_with_the_reason(self):
        parse = parse_bytes(DEMO_PENN, window=WINDOW, file_id="f", file_name="penn.csv")
        self.assertIs(parse.outcome, PrecheckOutcome.unreadable)
        self.assertIn("prints no currency", parse.reason)


class LayoutTrapTests(unittest.TestCase):
    def test_header_block_two_money_columns_parentheses_symbols_totals_and_day_first(self):
        data = b'''Export generated 2024-05-01
Account Number: ****4421
"Date","Description","Debit","Credit","Balance"
14/03/2024,"COFFEE",  "$4.50", ,"1,000.00"
15/03/2024,"PAYROLL",,"$2,500.00","3,500.00"
16/03/2024,"RENT","(1,200.00)",,"2,300.00"
,"Total","1,204.50","2,500.00",
'''
        reading = read(data, "a.csv", default_currency="USD")
        self.assertEqual(lines(reading), [
            (date(2024, 3, 14), TransactionDirection.debit, 450, "COFFEE"),
            (date(2024, 3, 15), TransactionDirection.credit, 250000, "PAYROLL"),
            (date(2024, 3, 16), TransactionDirection.debit, 120000, "RENT"),
        ])
        self.assertEqual([u.reason for u in reading.unmapped], ["line 7: a totals or balance line, not a payment"])
        self.assertIs(reading.reconciliation_status, ReconciliationStatus.balanced)
        self.assertEqual(reading.document.layouts[0]["date_order_source"], "file")
        self.assertEqual({r.account_key for r in reading.rows}, {"****4421"})

    def test_dates_that_could_be_either_order_are_listed_unsure_never_dropped(self):
        data = b"Date,Description,Amount\n03/04/2024,A,-1.00\n05/06/2024,B,2.00\n"
        reading = read(data, "b.csv", default_currency="USD")
        self.assertEqual(reading.row_count, 0)
        self.assertEqual(reading.parsed_row_count, 2)
        self.assertTrue(all("unsure" in u.reason and "day-first or month-first" in u.reason
                            for u in reading.unmapped))
        layout = dict(reading.document.layouts[0], date_order="day_first")
        confirmed = read(data, "b.csv", default_currency="USD", layouts=[layout])
        self.assertEqual([r.reading.transaction_date for r in confirmed.rows], [date(2024, 4, 3), date(2024, 6, 5)])
        self.assertEqual(confirmed.document.layouts[0]["source"], "confirmed")

    def test_a_confirmed_sign_turns_a_card_export_the_right_way(self):
        data = b"Date,Description,Amount\n2024-01-02,SHOP,25.00\n2024-01-03,PAYMENT,-100.00\n"
        guessed = read(data, "card.csv", default_currency="USD")
        self.assertEqual([r.reading.direction for r in guessed.rows],
                         [TransactionDirection.credit, TransactionDirection.debit])
        layout = dict(guessed.document.layouts[0], amount_sign="negative_is_in")
        flipped = read(data, "card.csv", default_currency="USD", layouts=[layout])
        self.assertEqual([r.reading.direction for r in flipped.rows],
                         [TransactionDirection.debit, TransactionDirection.credit])

    def test_balances_that_do_not_follow_make_the_file_unbalanced_and_say_where(self):
        data = b"Date,Description,Amount,Balance\n2024-01-01,A,10.00,110.00\n2024-01-02,B,-5.00,99.00\n"
        reading = read(data, "c.csv", default_currency="USD")
        self.assertIs(reading.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(reading.proof_class, ProofClass.p3)
        self.assertTrue(any("line 3" in note for note in reading.document.notes))

    def test_newest_first_exports_balance_too(self):
        data = b"Date,Description,Amount,Balance\n2024-01-02,B,-5.00,105.00\n2024-01-01,A,10.00,110.00\n"
        self.assertIs(read(data, "d.csv", default_currency="USD").reconciliation_status,
                      ReconciliationStatus.balanced)

    def test_a_merged_cell_workbook_with_two_statement_sheets(self):
        import openpyxl
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "March"
        sheet.append(["Banco Ejemplo SA"])
        sheet.merge_cells("A1:D1")
        sheet.append(["Fecha", "Concepto", "Cargo", "Abono", "Saldo"])
        sheet.append([date(2024, 3, 1), "SPEI ENVIADO", 100.0, None, 900.0])
        sheet.append([None, "continued", None, None, None])
        sheet.append([date(2024, 3, 2), "DEPOSITO", None, 250.5, 1150.5])
        sheet.append(["Saldo final", None, None, None, 1150.5])
        sheet.cell(7, 1, date(2024, 3, 3))
        sheet.merge_cells("A7:A8")  # one date merged down over two movements
        sheet.cell(7, 2, "FEE")
        sheet.cell(7, 3, 1.5)
        sheet.cell(7, 5, 1149.0)
        sheet.cell(8, 2, "FEE TAX")
        sheet.cell(8, 3, 0.5)
        sheet.cell(8, 5, 1148.5)
        april = book.create_sheet("April")
        april.append(["Fecha", "Concepto", "Cargo", "Abono", "Saldo"])
        april.append([date(2024, 4, 1), "X", 10, None, 1138.5])
        book.create_sheet("Notes").append(["just notes"])
        buffer = io.BytesIO()
        book.save(buffer)
        reading = read(buffer.getvalue(), "mx.xlsx", default_currency="MXN")
        reading.check_partition()
        self.assertEqual([(r.reading.transaction_date, r.source["sheet"], r.source["line"]) for r in reading.rows], [
            (date(2024, 3, 1), "March", 3), (date(2024, 3, 2), "March", 5), (date(2024, 3, 3), "March", 7),
            (date(2024, 3, 3), "March", 8), (date(2024, 4, 1), "April", 2)])
        self.assertEqual(reading.document.banner_institution, "Banco Ejemplo SA")
        self.assertEqual(reading.document.sheets_without_table, ["Notes"])
        # Two statement sheets and no account number: each sheet is its own unnamed account.
        self.assertEqual({r.account_key for r in reading.rows}, {"sheet March", "sheet April"})
        self.assertEqual(len(reading.unmapped), 2)

    def test_an_xls_workbook_reads_dates_merged_banner_and_totals(self):
        reading = read(XLS_FIXTURE, "movimientos.xls", default_currency="MXN")
        self.assertEqual(lines(reading), [
            (date(2023, 2, 1), TransactionDirection.credit, 150000, "SPEI RECIBIDO"),
            (date(2023, 2, 3), TransactionDirection.debit, 30025, "PAGO TARJETA"),
        ])
        self.assertEqual([r.source["sheet"] for r in reading.rows], ["Movimientos", "Movimientos"])
        self.assertEqual({r.account_key for r in reading.rows}, {"0123456789"})
        self.assertEqual(reading.document.banner_institution, "Banco de Prueba SA")
        self.assertIs(reading.reconciliation_status, ReconciliationStatus.balanced)
        self.assertTrue(any("totals" in u.reason for u in reading.unmapped))

    def test_a_file_with_no_statement_table_is_not_read(self):
        with self.assertRaises(tabular.TabularError):
            read(b"Name,Phone\nA,1\n", "contacts.csv", default_currency="USD")


class PaymentAppTests(unittest.TestCase):
    def test_venmo_statement(self):
        data = b''',ID,Datetime,Type,Status,Note,From,To,Amount (total),Amount (tip),Amount (fee),Funding Source,Destination,Beginning Balance,Ending Balance
Account Statement - (@Jane-Doe) ,,,,,,,,,,,,,,
,,,,,,,,,,,,,$0.00,
,111,2024-03-01T10:00:00,Payment,Complete,lunch,Jane Doe,Bob Smith,- $15.00,,0,Venmo balance,,,
,112,2024-03-02T10:00:00,Payment,Complete,rent,Ann Lee,Jane Doe,+ $500.00,,0,,Venmo balance,,
,113,2024-03-03T10:00:00,Charge,Pending,x,Ann Lee,Jane Doe,+ $5.00,,0,,Venmo balance,,
'''
        reading = read(data, "venmo.csv", default_currency="USD")
        self.assertEqual([(r.reading.direction, r.reading.amount_minor, r.reading.counterparty_raw)
                          for r in reading.rows],
                         [(TransactionDirection.debit, 1500, "Bob Smith"),
                          (TransactionDirection.credit, 50000, "Ann Lee")])
        self.assertIn("status is 'Pending': not money that moved", reading.unmapped[-1].reason)

    def test_cash_app_statement_and_an_unknown_status_is_unsure(self):
        data = b'''Transaction ID,Date,Transaction Type,Currency,Amount,Fee,Net Amount,Asset Type,Asset Price,Asset Amount,Status,Notes,Name of sender/receiver,Account
abc,2024-04-01 10:22:01 EDT,Cash Card Debit,USD,-$20.00,$0,-$20.00,,,,CARD CHARGED,Store,Shell,Visa Debit 1234
abd,2024-04-02 10:22:01 EDT,P2P,USD,$50.00,$0,$50.00,,,,PAYMENT DEPOSITED,,K Travis,Visa Debit 1234
abe,2024-04-03 10:22:01 EDT,P2P,USD,$9.00,$0,$9.00,,,,ODD STATE,,K Travis,Visa Debit 1234
'''
        reading = read(data, "cash_app_report.csv")
        self.assertEqual([(r.reading.direction, r.reading.amount_minor, r.reading.counterparty_raw,
                           r.reading.currency) for r in reading.rows],
                         [(TransactionDirection.debit, 2000, "Shell", "USD"),
                          (TransactionDirection.credit, 5000, "K Travis", "USD")])
        self.assertIn("unsure", reading.unmapped[0].reason)
        # The funding card under Cash App's "Account" heading is not this account.
        self.assertEqual({r.account_key for r in reading.rows}, {None})

    def test_paypal_activity_uses_net(self):
        data = b'''"Date","Time","TimeZone","Name","Type","Status","Currency","Gross","Fee","Net","From Email Address","To Email Address","Transaction ID"
"01/05/2024","10:00:00","PST","Acme","Express Checkout Payment","Completed","USD","-30.00","0.00","-30.00","me@x","acme@x","1"
"01/16/2024","10:00:00","PST","Bob","Mobile Payment","Completed","USD","100.00","-3.20","96.80","bob@x","me@x","2"
'''
        reading = read(data, "paypal.csv")
        self.assertEqual([(r.reading.direction, r.reading.amount_minor, r.reading.counterparty_raw)
                          for r in reading.rows],
                         [(TransactionDirection.debit, 3000, "Acme"), (TransactionDirection.credit, 9680, "Bob")])

    def test_an_ach_search_export_takes_its_side_from_the_transaction_code(self):
        data = (b"TraceNumber,ProcessedDate,SecCode,TranCode,Status,Amount,BankAccountLast4\n"
                b"122402,10/3/2024,WEB,27,Processed,2.00,6133\n"
                b"122403,10/14/2024,WEB,22,Processed,5.00,6133\n")
        reading = read(data, "AchSearchResults.csv", default_currency="USD")
        self.assertEqual([(r.reading.direction, r.reading.amount_minor, r.reading.bank_reference)
                          for r in reading.rows],
                         [(TransactionDirection.debit, 200, "122402"), (TransactionDirection.credit, 500, "122403")])
        self.assertEqual({r.account_key for r in reading.rows}, {"6133"})


class AmountAndDateTests(unittest.TestCase):
    def test_amounts(self):
        cases = {"$1,234.50": "1234.50", "(12.00)": "-12.00", "12.00-": "-12.00", "1.234,56": "1234.56",
                 "12,50": "12.50", "USD 7": "7.00", "45.10 CR": "45.10", "45.10 DR": "-45.10", 3.1: "3.10",
                 "− 4": "-4.00"}
        for text, expected in cases.items():
            with self.subTest(text=text):
                value, problem = tabular.parse_amount(text)
                self.assertIsNone(problem)
                self.assertEqual(str(value), expected)
        self.assertIsNotNone(tabular.parse_amount("12.345")[1])
        self.assertIsNotNone(tabular.parse_amount("1,23,4")[1])
        self.assertEqual(tabular.parse_amount(""), (None, None))

    def test_dates(self):
        self.assertEqual(tabular.parse_date("Mar 5, 2024", None, WINDOW)[0], date(2024, 3, 5))
        self.assertEqual(tabular.parse_date("05-Mar-2024", None, WINDOW)[0], date(2024, 3, 5))
        self.assertEqual(tabular.parse_date("2024/03/05 10:22", None, WINDOW)[0], date(2024, 3, 5))
        self.assertEqual(tabular.parse_date("3/5/24", "month_first", WINDOW)[0], date(2024, 3, 5))
        self.assertEqual(tabular.parse_date(45356, None, WINDOW)[0], date(2024, 3, 5))
        self.assertIsNone(tabular.parse_date("31/02/2024", None, WINDOW)[0])


from tests.test_financial_native_ingest_file import IngestFileTestCase  # noqa: E402


class StoreAndReuseTests(IngestFileTestCase):
    """Stored through the production ingest path: rows labelled with their line, the mapping confirmed."""

    def spreadsheet(self, data: bytes, name: str) -> EvidenceFile:
        self._files += 1
        stored = f"sheet-{self._files}-{name}"
        record = EvidenceFile(id=uuid.uuid4(), case_id=self.case.id, original_filename=name,
                              stored_path=f"/evidence/{stored}", sha256=f"{self._files:02d}" * 32)
        self.db.add(record)
        self.db.commit()
        (Path(self._directory) / stored).write_bytes(data)
        return record

    def test_storing_labels_rows_and_confirms_the_layout_for_the_next_file(self):
        from services.financial.native_precheck import confirmed_layouts, precheck_case_file

        first = self.spreadsheet(DEMO_PENN, "penn-used-tools-old-ferrow-2024.csv")
        result = self.ingest(first, default_currency="USD")
        self.assertEqual(result.outcome.value, "stored", result.reason)
        self.assertEqual(result.transactions_stored, 23)
        rows = self.transactions()
        self.assertEqual(len(rows), 23)
        labels = sorted(r.metadata_[tabular.ROW_SOURCE_METADATA_KEY]["line"] for r in rows)
        self.assertEqual(labels, list(range(4, 27)))
        document = self.documents()[0]
        self.assertEqual(document.document_type, "tabular")
        self.assertEqual(document.extraction_layer, int(ExtractionLayer.native))
        layout = document.metadata_[tabular.TABULAR_LAYOUTS_METADATA_KEY][0]
        self.assertEqual(layout["source"], "confirmed")
        self.assertEqual(layout["confirmed_by"]["email"], "investigator@example.test")

        # A second export with the same headings is read with the confirmed mapping, sign flipped by the person.
        with self.fresh() as session:
            saved = confirmed_layouts(session, self.case.id)
        self.assertEqual(len(saved), 1)
        second_bytes = DEMO_PENN.replace(b"5518-020931", b"5518-777777")
        second = self.spreadsheet(second_bytes, "penn-2025.csv")
        shown = precheck_case_file(self.db, case_id=self.case.id, file_id=second.id,
                                   resolve_path=self.resolve_path, window=WINDOW, default_currency="USD")
        self.assertEqual(shown.layouts[0]["source"], "confirmed")
        self.assertEqual(shown.layouts[0]["confirmed_by"]["email"], "investigator@example.test")
        self.assertIsNone(shown.already_in_ledger)
        self.assertTrue(shown.would_ingest)

        # Reading the stored file again says the ledger holds it, and offers no write (the writer would refuse).
        again = precheck_case_file(self.db, case_id=self.case.id, file_id=first.id,
                                   resolve_path=self.resolve_path, window=WINDOW, default_currency="USD")
        self.assertEqual(again.already_in_ledger["document_id"], str(document.id))
        self.assertFalse(again.would_ingest)
        self.assertFalse(again.as_dict()["would_ingest"])
        self.assertEqual(again.row_count, 23)
        refused = self.ingest(first, default_currency="USD")
        self.assertEqual(refused.outcome.value, "already_ingested")

        # A confirmer sent with the request is ignored: an unchanged mapping keeps the stored confirmation, a
        # changed one is the storing person's.
        from services.financial.native_precheck import _layouts_for
        spoofed = dict(shown.layouts[0], confirmed_by={"user_id": None, "name": "Someone Else", "email": "x@y"})
        kept = _layouts_for(self.db, self.case.id, "penn-2025.csv", [spoofed])[0]
        self.assertEqual(kept["confirmed_by"]["email"], "investigator@example.test")
        changed = dict(spoofed, amount_sign="negative_is_in")
        fresh = _layouts_for(self.db, self.case.id, "penn-2025.csv", [changed])[0]
        self.assertNotIn("confirmed_by", fresh)
        result = self.ingest(second, default_currency="USD", layouts=[changed])
        self.assertEqual(result.outcome.value, "stored", result.reason)
        with self.fresh() as session:
            from sqlalchemy import select
            from postgres.models.financial import FinancialSourceDocument
            documents = list(session.scalars(select(FinancialSourceDocument).where(
                FinancialSourceDocument.evidence_file_id == second.id)))
        stored = documents[0].metadata_[tabular.TABULAR_LAYOUTS_METADATA_KEY][0]
        self.assertEqual(stored["confirmed_by"]["email"], "investigator@example.test")
        self.assertEqual(stored["amount_sign"], "negative_is_in")

    def test_a_correction_reads_the_spreadsheet_again_with_its_stored_mapping(self):
        import hashlib
        from sqlalchemy import select
        from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
        from services.financial.correction_native import correction_native_controls

        record = self.spreadsheet(DEMO_PENN, "penn.csv")
        record.sha256 = hashlib.sha256(DEMO_PENN).hexdigest()
        self.db.commit()
        self.assertEqual(self.ingest(record, default_currency="USD").outcome.value, "stored")
        document = self.db.scalar(select(FinancialSourceDocument))
        rows = list(self.db.scalars(select(FinancialTransaction)))
        target = next(r for r in rows if (r.description or "").startswith("CHECK 1043"))
        answer = correction_native_controls(self.db, document, rows, transaction_id=target.id,
                                            amount_minor=target.amount_minor + 1, direction=target.direction,
                                            resolve_path=self.resolve_path, lock_source=False)
        self.assertTrue(answer["available"], answer.get("reason"))
        # The stored file balances; adding a cent to one check breaks the running balance from there on.
        self.assertEqual(answer["current"]["checks"][0]["result"], {"status": "balanced", "breaks": 0})
        self.assertEqual(answer["proposed"]["checks"][0]["result"]["status"], "unbalanced")


if __name__ == "__main__":
    unittest.main()
