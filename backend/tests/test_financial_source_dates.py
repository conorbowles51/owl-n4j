import unittest
from services.financial.source_dates import assess_date_text


class SourceDateTests(unittest.TestCase):
    def read(self, raw, origin="digital_text_layer"):
        return assess_date_text(raw, origin)

    def test_ambiguous_order_keeps_both_dates(self):
        result = self.read("01/02/2026")
        self.assertEqual(result["status"], "ambiguous_order")
        self.assertEqual({p["iso_date"] for p in result["proposals"]}, {"2026-02-01", "2026-01-02"})
        self.assertTrue(result["requires_source_review"])

    def test_calendar_rules_do_not_choose_a_locale(self):
        for raw, expected in (("13/02/2026", "2026-02-13"), ("02/13/2026", "2026-02-13"), ("02/02/2026", "2026-02-02")):
            with self.subTest(raw=raw):
                result = self.read(raw)
                self.assertEqual(result["status"], "unambiguous_format")
                self.assertEqual({p["iso_date"] for p in result["proposals"]}, {expected})

    def test_iso_and_leap_calendar_validation(self):
        self.assertEqual(self.read("2024-02-29")["proposals"][0]["iso_date"], "2024-02-29")
        for raw in ("2026-02-29", "31/04/2026", "00/00/2026", "2026-13-01", "01/01/0000"):
            with self.subTest(raw=raw):
                self.assertEqual(self.read(raw)["status"], "invalid_calendar_date")
                self.assertEqual(self.read(raw)["proposals"], [])

    def test_missing_year_never_uses_clock_or_source_neighbours(self):
        for raw in ("01/02", "29/02"):
            result = self.read(raw)
            self.assertEqual(result["status"], "missing_year")
            self.assertTrue(result["proposals"])
            self.assertTrue(all("iso_date" not in p for p in result["proposals"]))
        self.assertEqual(self.read("31/04")["status"], "invalid_calendar_date")

    def test_two_digit_year_does_not_assume_century(self):
        result = self.read("01/02/26")
        self.assertEqual(result["status"], "ambiguous_century")
        self.assertTrue(all("iso_date" not in p for p in result["proposals"]))

    def test_unsupported_ocr_and_formats_are_preserved_without_repairs(self):
        for raw in ("O1/02/2026", "January 2026", "", "01/02-2026", "2026/02/01", "20260201", "١/٢/٢٠٢٦"):
            with self.subTest(raw=raw):
                result = self.read(raw)
                self.assertEqual(result["raw"], raw)
                self.assertEqual(result["status"], "unsupported")
                self.assertEqual(result["proposals"], [])

    def test_recognised_and_unknown_glyphs_never_become_verified_dates(self):
        for origin in ("recognised_glyphs", "unknown", "digital_text_layer"):
            result = self.read(" 2026-02-01 ", origin)
            self.assertEqual(result["origin"], origin)
            self.assertEqual(result["raw"], " 2026-02-01 ")
            self.assertTrue(result["requires_source_review"])
            self.assertNotIn("selected_date", result)

    def test_explicit_english_month_names_and_abbreviations(self):
        for raw, expected in (("7 September 2026", "2026-09-07"), ("September 7, 2026", "2026-09-07"),
                              ("SEP 07 2026", "2026-09-07"), ("7 sept 2026", "2026-09-07"),
                              ("29 Feb 2024", "2024-02-29")):
            with self.subTest(raw=raw):
                result = self.read(raw, "recognised_glyphs")
                self.assertEqual(result['status'], 'unambiguous_format')
                self.assertEqual(result['proposals'][0]['iso_date'], expected)
                self.assertTrue(result['requires_source_review'])
                self.assertEqual(result['raw'], raw)

    def test_named_dates_do_not_infer_year_century_or_repair_tokens(self):
        for raw, status in (("29 February", "missing_year"), ("Feb 29, 24", "ambiguous_century"),
                            ("29 February 2026", "invalid_calendar_date"), ("31 Apr", "invalid_calendar_date"),
                            ("1 January 0000", "invalid_calendar_date")):
            with self.subTest(raw=raw):
                result = self.read(raw)
                self.assertEqual(result['status'], status)
                self.assertTrue(all('iso_date' not in p for p in result['proposals']))
        for raw in ("7 Septembcr 2026", "7 septembre 2026", "7th September 2026", "Sep O7 2026",
                    "September 2026", "Sep 7,", "Sep 7 2026 extra", "7/Sept/2026"):
            with self.subTest(raw=raw):
                result = self.read(raw)
                self.assertEqual(result['status'], 'unsupported')
                self.assertEqual(result['raw'], raw)
