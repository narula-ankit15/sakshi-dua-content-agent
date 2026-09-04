import json
import zipfile
from pathlib import Path

import pytest

from app.ingest import topic_ingest


class FakeGeminiClient:
    def __init__(self, api_key, model):
        pass

    def generate_json(self, *, system: str, prompt: str) -> dict:
        return {
            "topic_name": "Communicate with Impact",
            "tagline": "Say less, land more.",
            "hook_description": "A hands-on workshop for teams whose ideas keep getting lost in delivery.",
            "modules": [{"module_number": 1, "title": "Structuring Your Message", "bullets": ["The framework"]}],
            "methodology": ["Role Plays"],
            "outcomes": ["Structure any message in under 60 seconds"],
            "closing_line": "Communication is the multiplier.",
            "positioning_tags": ["Customised", "Experiential"],
        }


def _write_png(path: Path):
    # Minimal-but-valid 1x1 PNG so PIL.Image.open works during ingestion.
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\xff\x00\x00"
    idat = zlib.compress(raw, 9)
    path.write_bytes(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def _build_zip(tmp_path, doc_text="Module 1: Structuring Your Message\n- The framework") -> Path:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "curriculum.txt").write_text(doc_text)
    _write_png(src_dir / "photo1.png")
    _write_png(src_dir / "photo2.png")

    zip_path = tmp_path / "comm-impact.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in src_dir.iterdir():
            zf.write(f, arcname=f.name)
    return zip_path


def test_split_zip_contents_separates_docs_from_photos(tmp_path):
    zip_path = _build_zip(tmp_path)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)

    docs, photos = topic_ingest.split_zip_contents(extracted)

    assert [d.name for d in docs] == ["curriculum.txt"]
    assert {p.name for p in photos} == {"photo1.png", "photo2.png"}


def test_split_zip_contents_returns_every_doc_when_multiple_present(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "deck.txt").write_text("Deep session transcript")
    (src_dir / "brochure.txt").write_text("Curated brochure copy")
    zip_path = tmp_path / "multi.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in src_dir.iterdir():
            zf.write(f, arcname=f.name)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)

    docs, _ = topic_ingest.split_zip_contents(extracted)

    assert {d.name for d in docs} == {"deck.txt", "brochure.txt"}


def test_split_zip_contents_ignores_macos_zip_junk(tmp_path):
    # A zip built on macOS carries a __MACOSX/ mirror dir plus a
    # "._filename" AppleDouble resource-fork stub per real file -- neither
    # is real content and both must be excluded, or a ~200-byte stub gets
    # "ingested" as if it were a real photo.
    extracted = tmp_path / "extracted"
    real_dir = extracted / "conflict managementworkshop"
    real_dir.mkdir(parents=True)
    (real_dir / "Conflict Management.pdf").write_bytes(b"%PDF-fake")
    _write_png(real_dir / "IMG_9936.png")
    junk_dir = extracted / "__MACOSX" / "conflict managementworkshop"
    junk_dir.mkdir(parents=True)
    (junk_dir / "._Conflict Management.pdf").write_bytes(b"resource-fork-stub")
    (extracted / "__MACOSX" / "._conflict managementworkshop").write_bytes(b"resource-fork-stub")
    (real_dir / "._IMG_9936.jpg").write_bytes(b"resource-fork-stub")

    docs, photos = topic_ingest.split_zip_contents(extracted)

    assert [d.name for d in docs] == ["Conflict Management.pdf"]
    assert len(photos) == 1


def test_split_zip_contents_raises_when_no_doc_present(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    _write_png(extracted / "photo1.png")

    with pytest.raises(ValueError, match="No source doc"):
        topic_ingest.split_zip_contents(extracted)


def test_extract_doc_text_reads_plain_text(tmp_path):
    doc_path = tmp_path / "notes.txt"
    doc_path.write_text("Some workshop notes")

    assert topic_ingest.extract_doc_text(doc_path) == "Some workshop notes"


def test_extract_doc_text_reads_docx(tmp_path):
    doc_path = tmp_path / "brochure.docx"
    with zipfile.ZipFile(doc_path, "w") as zf:
        zf.writestr(
            "word/document.xml",
            "<w:document><w:body><w:p><w:r><w:t>Communicate With Impact.</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>A curated brochure.</w:t></w:r></w:p></w:body></w:document>",
        )

    text = topic_ingest.extract_doc_text(doc_path)

    assert "Communicate With Impact." in text
    assert "A curated brochure." in text


def test_ingest_topic_writes_topic_json_and_photo_bank(tmp_path, monkeypatch):
    monkeypatch.setattr(topic_ingest, "GeminiClient", FakeGeminiClient)

    class FakeSettings:
        gemini_api_key = "fake-key"
        gemini_generation_model = "fake-model"
        topic_data_path = str(tmp_path / "topics")
        asset_bank_path = str(tmp_path / "assets")
        api_public_base_url = "http://127.0.0.1:8123"

    monkeypatch.setattr(topic_ingest, "get_settings", lambda: FakeSettings())

    zip_path = _build_zip(tmp_path)
    topic_ingest.ingest_topic("comm-impact", zip_path)

    topic_json = json.loads((tmp_path / "topics" / "comm-impact" / "topic.json").read_text())
    assert topic_json["topic_name"] == "Communicate with Impact"
    assert topic_json["source_doc_ref"] == "curriculum.txt"
    assert len(topic_json["photo_asset_ids"]) == 2

    metadata = json.loads((tmp_path / "assets" / "comm-impact" / "metadata.json").read_text())
    assert len(metadata) == 2
    assert all(r["topic_id"] == "comm-impact" for r in metadata)
    assert all(r["url"].startswith("http://127.0.0.1:8123/asset-files/comm-impact/photos/") for r in metadata)


def test_ingest_topic_topic_name_override_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(topic_ingest, "GeminiClient", FakeGeminiClient)

    class FakeSettings:
        gemini_api_key = "fake-key"
        gemini_generation_model = "fake-model"
        topic_data_path = str(tmp_path / "topics")
        asset_bank_path = str(tmp_path / "assets")
        api_public_base_url = "http://127.0.0.1:8123"

    monkeypatch.setattr(topic_ingest, "get_settings", lambda: FakeSettings())

    zip_path = _build_zip(tmp_path)
    topic_ingest.ingest_topic("comm-impact", zip_path, topic_name_override="Custom Name")

    topic_json = json.loads((tmp_path / "topics" / "comm-impact" / "topic.json").read_text())
    assert topic_json["topic_name"] == "Custom Name"
