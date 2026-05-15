import unittest

from services.phone_normalise import (
    display_format,
    normalise,
    normalise_all,
    normalise_from_person_key,
)


class PhoneNormaliseTests(unittest.TestCase):
    def test_normalise_accepts_common_us_spellings(self):
        self.assertEqual(normalise("+1 (202) 805-2817"), "+12028052817")
        self.assertEqual(normalise("1-202-805-2817"), "+12028052817")
        self.assertEqual(normalise("2028052817"), "+12028052817")
        self.assertEqual(normalise("(202) 805 2817"), "+12028052817")

    def test_normalise_accepts_explicit_international_e164(self):
        self.assertEqual(normalise("+44 7700 900123"), "+447700900123")

    def test_normalise_rejects_names_app_ids_and_short_codes(self):
        self.assertIsNone(normalise("Alex"))
        self.assertIsNone(normalise("12345"))
        self.assertIsNone(normalise("100014422513889"))
        self.assertIsNone(normalise("46648305393"))
        self.assertIsNone(normalise("12403058399@s.whatsapp.net"))

    def test_normalise_rejects_placeholder_repeating_digits(self):
        self.assertIsNone(normalise("0000000000"))
        self.assertIsNone(normalise("+11111111111"))

    def test_normalise_all_deduplicates_in_input_order(self):
        self.assertEqual(
            normalise_all(
                [
                    "+1 (202) 805-2817",
                    "2028052817",
                    "+44 7700 900123",
                    "Alex",
                ]
            ),
            ["+12028052817", "+447700900123"],
        )

    def test_normalise_from_person_key_uses_phone_keys_only(self):
        self.assertEqual(normalise_from_person_key("phone-2028052817"), "+12028052817")
        self.assertIsNone(normalise_from_person_key("email-alex@example.test"))

    def test_display_format_renders_us_and_generic_numbers(self):
        self.assertEqual(display_format("+12028052817"), "+1 (202) 805-2817")
        self.assertEqual(display_format("+447700900123"), "+44 7700 9001 23")
        self.assertIsNone(display_format(None))


if __name__ == "__main__":
    unittest.main()
