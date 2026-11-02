"""02-U8: identifiers and phone numbers (02 sections 8.2 and 8.3). Synthetic values only."""
from __future__ import annotations

import phonenumbers

from services.phone import identifiers as I
from services.phone import numbers


def key(raw, **kw):
    r = I.classify(raw, **kw)
    return r.identity_key if r else None


def test_the_library_is_the_pinned_version():
    assert phonenumbers.__version__ == numbers.PINNED


def test_four_written_forms_of_one_number_give_one_key():  # PN-5
    forms = ["+1 (202) 555-0143", "+12025550143", "1-202-555-0143", "(202) 555-0143"]
    keys = {key(f, region="US") for f in forms}
    assert len(keys) == 1 and next(iter(keys)).split(":")[0] in ("phone", "other")


def test_a_whatsapp_id_and_its_number_give_one_identity():
    assert key("12025550143@s.whatsapp.net") == key("+12025550143")
    assert key("12025550143@C.US") == key("+12025550143")


def test_group_ids_never_become_persons():
    r = I.classify("120363000000000000@g.us")
    assert r.kind == "other" and r.subkind == "group" and r.identity_key == "other:whatsapp_group:120363000000000000@g.us"


def test_short_codes_emails_and_app_users():
    assert key("72975") == "other:short_code:72975"
    assert key("Mailto:A.B@Example.COM") == "email:a.b@example.com"
    assert key("@SomeUser", context={"app": "Instagram", "category": "Username"}) == "app:instagram:username:someuser"
    assert key("4471x", context={"app": "Facebook Messenger"}) == "app:facebook-messenger:id:4471x"
    assert I.classify("Synthetic Name", context={"name_only": True}) is None


def test_pn_rules_on_a_number_valid_in_the_library():
    # +1 202-456-1111 is a published, valid US number shape in libphonenumber's metadata (no case material).
    r = I.classify("+1 202 456 1111")
    assert r.kind == "phone" and r.identity_key == "phone:+12024561111" and r.region_basis == "explicit_plus"  # PN-1
    assert r.value_display == "+1 202-456-1111"  # PN-4: INTERNATIONAL format
    bare = I.classify("202 456 1111", region="US")
    assert bare.identity_key == r.identity_key and bare.region_basis == "assumed_default"  # PN-2
    decided = I.classify("202 456 1111", region="US", region_basis="decided")
    assert decided.region_basis == "decided"


def test_an_invalid_number_never_gets_a_phone_key():  # PN-3
    r = I.classify("+1 000 000 0000")
    assert r.kind == "other" and r.identity_key == "other:digits:10000000000"
