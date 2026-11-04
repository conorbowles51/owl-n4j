"""Text-message exports uploaded as documents (FEAT-013): sender, time and conversation kept on every message."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "message_exports", Path(__file__).resolve().parents[1] / "app/pipeline/message_exports.py")
message_exports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(message_exports)
read = message_exports.read_message_export

IOS = """[03/04/2024, 14:05:09] Orla Test: Did the 1,250 go through?
[03/04/2024, 14:06:11] Brian Example: Yes, sent from the Galway account
and the rest tomorrow
[03/04/2024, 14:07:00] Orla Test: ok
‎[04/04/2024, 09:00:00] Brian Example: ‎image omitted
"""
ANDROID = """12/31/23, 9:15 PM - Messages and calls are end-to-end encrypted.
12/31/23, 9:16 PM - Ana: Happy new year
12/31/23, 9:17 PM - Luis: Same to you
1/1/24, 10:02 AM - Ana: Call me about the transfer
"""
SMS = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="4">
  <sms protocol="0" address="+353861234567" date="1709474709000" type="1" body="Money is in" contact_name="Brian Example" />
  <sms protocol="0" address="+353861234567" date="1709474800000" type="2" body="Thanks" contact_name="Brian Example" />
  <sms protocol="0" address="+15551230000" date="1709300000000" type="1" body="Who is this?" contact_name="(Unknown)" />
  <mms date="1709474900000" address="+353861234567" msg_box="1" contact_name="Brian Example"><parts><part ct="application/smil" text="x" /><part ct="text/plain" text="Look at this &#55357;&#56832;" /><part ct="image/jpeg" /></parts></mms>
  <sms protocol="0" address="+15551230000" date="99999999999999999999" type="1" body="Odd date" contact_name="(Unknown)" />
  <call number="+1" />
  <sms protocol="0" address="+15551230000" date="1709300100000" type="2" body="Wrong number" contact_name="(Unknown)" />
</smses>
"""


def test_whatsapp_ios_export_keeps_each_sender_and_printed_time_and_joins_continued_lines():
    text, meta = read(IOS, "WhatsApp Chat - Brian.txt")
    assert meta["format"] == "whatsapp_chat_txt" and meta["messages"] == 4
    assert meta["participants"] == ["Brian Example", "Orla Test"] or set(meta["participants"]) == {"Orla Test", "Brian Example"}
    assert "[03/04/2024 14:05:09] Orla Test: Did the 1,250 go through?" in text
    assert "Yes, sent from the Galway account\n    and the rest tomorrow" in text
    assert "dates exactly as printed" in text  # 03/04 is not turned into March or April


def test_whatsapp_android_export_and_its_notice_line():
    text, meta = read(ANDROID, "_chat.txt")
    assert meta["messages"] == 3 and meta["notices"] == 1
    assert "[1/1/24 10:02 AM] Ana: Call me about the transfer" in text


def test_sms_backup_groups_by_conversation_with_direction_and_utc_time():
    text, meta = read(SMS, "sms-20240304.xml")
    assert meta["format"] == "sms_backup_restore_xml" and meta["messages"] == 6 and meta["conversations"] == 2
    assert meta["not_read"] == {"call": 1}
    assert "Brian Example (+353861234567) to phone owner: Look at this \U0001F600 [1 attachment(s) not read: image/jpeg]" in text
    assert "[time not recorded] +15551230000 to phone owner: Odd date" in text
    assert "Conversation with Brian Example (+353861234567): 3 messages" in text
    assert "[2024-03-03 14:05:09 UTC] Brian Example (+353861234567) to phone owner: Money is in" in text
    assert "Phone owner to +15551230000: Wrong number" in text
    assert "1 call item(s)" in text


def test_ordinary_text_and_xml_are_left_alone():
    assert read("Meeting notes\nOrla said: call Brian\nNothing else.", "notes.txt") is None
    assert read("<invoice><total>3</total></invoice>", "invoice.xml") is None
    assert read(IOS, "chat.pdf") is None


def test_a_plain_log_or_listing_with_dates_is_not_taken_for_a_chat():
    log = ("SURVEILLANCE LOG - Subject J. Doe\nPrepared by Agent K.\n03/04/2024 09:15 Subject: left residence\n"
           "03/04/2024 09:40 Subject: entered car\n03/04/2024 10:05 Subject: arrived bank\n03/04/2024 10:30 Note: lost sight\n")
    assert read(log, "log.txt") is None
    listing = "01/02/2024, 10:30 - Transfer: 500.00\n01/02/2024, 10:31 - Transfer: 20.00\n01/02/2024, 10:32 - Transfer: 1.00\n"
    assert read(listing, "bank.txt") is None  # one "sender" is not a conversation


def test_text_before_the_first_message_is_kept():
    text, _ = read("Exported for case 22-114\n" + IOS, "chat.txt")
    assert "Text before the first message:\nExported for case 22-114" in text
