"""Pronouns and role words point at someone without naming them ('She', 'The Court', 'Lic'). Measured on the live
graphs, 25 Nov 2026: of 1,314 alias suggestions in the Similar entities scan, 83 matched on such a word."""
from services.reference_words import drop_pronouns, is_pronoun, is_reference_word, reference_key


def test_pronouns_and_role_words_are_reference_words():
    for text in ['She', 'him', 'The Court', 'THE COURT', 'Lic', 'Licenciado', 'Plaintiff', 'Mother', 'Unknown Victim',
                 "Victim's Mother", '[Unknown]', 'Tu primo', 'su esposa', 'First Party', 'law enforcement']:
        assert is_reference_word(text), text
    assert reference_key('The Court') == reference_key('COURT') == 'court'


def test_names_are_not_reference_words():
    for text in ['Ana Ruiz Vega', "Ana Ruiz's mother", 'Suspect 4', 'Juror No. 313', 'Licenciado Ortega',
                 'Montgomery County Police', 'Baby Trucha', 'Don', 'US', 'IT', '']:
        assert not is_reference_word(text), text


def test_only_bare_pronouns_are_dropped_from_aliases():
    assert is_pronoun('She') and is_pronoun('he') and not is_pronoun('US') and not is_pronoun('Mother')
    assert drop_pronouns(['Ana', 'She', 'Mommy', 'US', 'we']) == ['Ana', 'Mommy', 'US']
