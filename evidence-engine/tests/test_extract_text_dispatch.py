from pathlib import Path

import pytest

from app.pipeline.extract_text import extract_text


@pytest.mark.asyncio
async def test_unknown_binary_extension_is_not_silently_ingested_as_text(
    tmp_path: Path,
) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"\x00\xff\x10binary")

    with pytest.raises(ValueError, match=r"Unsupported file type: \.bin"):
        await extract_text(str(source), source.name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("legacy.doc", "Legacy .doc files are not supported"),
        ("legacy.xls", "Legacy .xls files are not supported"),
    ],
)
async def test_legacy_office_formats_fail_with_conversion_guidance(
    tmp_path: Path,
    name: str,
    message: str,
) -> None:
    source = tmp_path / name
    source.write_bytes(b"legacy office data")

    with pytest.raises(ValueError, match=message):
        await extract_text(str(source), source.name)


@pytest.mark.asyncio
async def test_explicit_plain_text_format_remains_supported(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("Known fact and reference 104.", encoding="utf-8")

    result = await extract_text(str(source), source.name)

    assert result.text == "Known fact and reference 104."
    assert result.metadata["file_type"] == "text"


@pytest.mark.asyncio
async def test_eml_extracts_headers_and_body_without_attachment_payload(
    tmp_path: Path,
) -> None:
    source = tmp_path / "message.eml"
    source.write_text(
        "From: alice@example.com\n"
        "To: bob@example.com\n"
        "Subject: Payment reference P-104\n"
        "Date: Tue, 21 Jul 2026 10:00:00 +0000\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "Please review payment reference P-104.\n",
        encoding="utf-8",
    )

    result = await extract_text(str(source), source.name)

    assert "From: alice@example.com" in result.text
    assert "Subject: Payment reference P-104" in result.text
    assert "Please review payment reference P-104." in result.text
    assert result.metadata["file_type"] == "eml"
