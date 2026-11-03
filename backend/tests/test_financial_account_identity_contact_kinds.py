"""02-U11 (docs/cellebrite/02 section 8.9): financial identifier kinds ``phone_number`` and ``email``.

A payment service that addresses an account by a phone number or an email puts it on the statement as the account
reference. These kinds validate and match by the phone identity normalisation (02 section 8.2), not by ``compact``.
R4 ``financial_identifier`` suggests linking a phone identity to a dossier only when the account's holder party is
linked to that dossier. Synthetic values only.
"""
import uuid

from pydantic import ValidationError

from postgres.base import Base
from postgres.models.case_profile import CaseProfile
from services.financial.account_identity import (IdentityRequest, Identifier, identity_state, matches_identifier,
                                                 save_identity)
from services.financial.account_parties import AccountPartyRequest, account_parties, set_account_party
from services.phone.identity_decisions import financial_identifier_dossiers
from tests.test_financial_duplicates import DuplicateTestCase


class ContactKindTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[CaseProfile.__table__])

    def save(self, identifiers, entity_links=(), lookup=None):
        request = IdentityRequest(account_id=self.account.id, expected_revision=identity_state(self.db, self.case.id)['revision'],
                                  identifiers=identifiers, entity_links=list(entity_links),
                                  basis={'basis': 'investigator_knowledge'}, reason='Reviewed the payment service enrolment')
        return save_identity(self.db, case_id=self.case.id, request=request, actor=self.actor,
                             entity_lookup=lookup or (lambda key, case: {'key': key}))

    def test_phone_and_email_validate_by_the_phone_normalisation(self):
        Identifier(kind='phone_number', value='(202) 555-0143')
        Identifier(kind='phone_number', value='+44 20 7946 0958')
        Identifier(kind='email', value='Payer.Name@Example.TEST')
        for kind, value in (('phone_number', '555-01'), ('phone_number', 'not a number'), ('email', 'nobody'),
                            ('email', 'a@b'), ('phone_number', '202***0143')):
            with self.assertRaises(ValidationError, msg=(kind, value)):
                Identifier(kind=kind, value=value)

    def test_a_number_written_two_ways_is_one_identifier(self):
        with self.assertRaises(ValidationError):
            IdentityRequest(account_id=self.account.id, expected_revision='0' * 64, basis={'basis': 'investigator_knowledge'},
                            reason='x', identifiers=[dict(kind='phone_number', value='(202) 555-0143'),
                                                     dict(kind='phone_number', value='+1 202 555 0143')])

    def test_new_kinds_match_by_normalised_value_and_only_their_own_kind(self):
        self.save([dict(kind='phone_number', value='(202) 555-0143'), dict(kind='email', value='Payer@Example.test')])
        self.assertTrue(matches_identifier(self.account, 'phone_number', '+1 202 555 0143'))
        self.assertTrue(matches_identifier(self.account, 'phone_number', '202.555.0143'))
        self.assertFalse(matches_identifier(self.account, 'phone_number', '+1 202 555 0144'))
        self.assertTrue(matches_identifier(self.account, 'email', 'payer@example.TEST'))
        self.assertFalse(matches_identifier(self.account, 'email', 'other@example.test'))
        # a phone or email reference never matches an account-number lookup, nor the other way round
        self.assertFalse(matches_identifier(self.account, 'account', '2025550143'))
        self.assertFalse(matches_identifier(self.account, 'account_number', '+12025550143'))
        self.assertFalse(matches_identifier(self.account, 'phone_number', self.account.identifier_as_printed or '0'))

    def _dossier(self, key):
        d = CaseProfile(id=uuid.uuid4(), case_id=self.case.id, profile_type='person', display_name='Synthetic Holder',
                        contacts=[], canonical_entity_key=key)
        self.db.add(d)
        self.db.commit()
        return str(d.id)

    def _party(self, role):
        directory = account_parties(self.db, case_id=self.case.id)
        owned = set_account_party(self.db, case_id=self.case.id, request=AccountPartyRequest(
            expected_revision=directory['revision'], account_ids=[self.account.id], new_party_name='Synthetic Holder',
            relationship={'role': role}, reason='Reviewed ownership documents'), actor=self.actor)
        return owned['parties'][0]['id']

    def test_r4_needs_the_holder_party_linked_to_a_dossier(self):
        dossier = self._dossier('entity-holder-1')
        ident = [dict(kind='phone_number', value='(202) 555-0143'), dict(kind='email', value='Payer@Example.test'),
                 dict(kind='account_number', value='ACCT-0001')]
        # no party linked: no suggestion
        self.save(ident)
        self.assertEqual(financial_identifier_dossiers(self.db, self.case.id), [])
        # a controller (not holder) linked to the dossier: still none
        controller = self._party('controller')
        self.save(ident, [{'party_id': controller, 'entity_key': 'entity-holder-1'}])
        self.assertEqual(financial_identifier_dossiers(self.db, self.case.id), [])

    def test_r4_fires_for_a_holder_linked_to_a_dossier(self):
        dossier = self._dossier('entity-holder-1')
        holder = self._party('holder')
        self.save([dict(kind='phone_number', value='(202) 555-0143'), dict(kind='email', value='Payer@Example.test'),
                   dict(kind='account_number', value='ACCT-0001')], [{'party_id': holder, 'entity_key': 'entity-holder-1'}])
        account = str(self.account.id)
        self.assertEqual(financial_identifier_dossiers(self.db, self.case.id),
                         [('email:payer@example.test', dossier, account), ('phone:+12025550143', dossier, account)])
        # another case's dossier with the same entity key is never named
        other = CaseProfile(id=uuid.uuid4(), case_id=self.other_case.id, profile_type='person', display_name='Other',
                            contacts=[], canonical_entity_key='entity-holder-1')
        self.db.add(other)
        self.db.commit()
        self.assertEqual({d for _, d, _ in financial_identifier_dossiers(self.db, self.case.id)}, {dossier})
