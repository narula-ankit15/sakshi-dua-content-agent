import io
import json

import pytest
from PIL import Image

from app.storage.asset_store import LocalAssetStore


def _png_bytes(width=40, height=20):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 50, 50)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(width=40, height=20):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(50, 100, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def test_save_generated_asset_writes_file_and_appends_metadata(tmp_path):
    store = LocalAssetStore(str(tmp_path), public_url_base="http://127.0.0.1:8123")

    asset = store.save_generated_asset("comm-impact", _png_bytes(64, 32), tags=["image-template"])

    assert asset.topic_id == "comm-impact"
    assert asset.kind == "image"
    assert asset.tags == ["image-template"]
    assert asset.width == 64
    assert asset.height == 32
    assert asset.url == f"http://127.0.0.1:8123/asset-files/comm-impact/generated/{asset.asset_id}.png"

    file_path = tmp_path / "comm-impact" / "generated" / f"{asset.asset_id}.png"
    assert file_path.exists()

    metadata = json.loads((tmp_path / "comm-impact" / "metadata.json").read_text())
    assert any(r["asset_id"] == asset.asset_id for r in metadata)


def test_save_generated_asset_appends_to_existing_metadata(tmp_path):
    topic_dir = tmp_path / "comm-impact"
    topic_dir.mkdir()
    (topic_dir / "metadata.json").write_text(
        json.dumps([{"asset_id": "existing-1", "topic_id": "comm-impact", "url": "https://cdn/e1.jpg", "kind": "image", "tags": []}])
    )

    store = LocalAssetStore(str(tmp_path))
    store.save_generated_asset("comm-impact", _png_bytes(), tags=[])

    metadata = json.loads((topic_dir / "metadata.json").read_text())
    assert len(metadata) == 2
    assert metadata[0]["asset_id"] == "existing-1"


def test_save_generated_asset_ids_are_unique(tmp_path):
    store = LocalAssetStore(str(tmp_path))
    a1 = store.save_generated_asset("comm-impact", _png_bytes(), tags=[])
    a2 = store.save_generated_asset("comm-impact", _png_bytes(), tags=[])
    assert a1.asset_id != a2.asset_id


def test_save_uploaded_asset_writes_file_with_correct_format_and_metadata(tmp_path):
    store = LocalAssetStore(str(tmp_path), public_url_base="http://127.0.0.1:8123")

    asset = store.save_uploaded_asset("comm-impact", _jpeg_bytes(300, 200), tags=["uploaded"])

    assert asset.topic_id == "comm-impact"
    assert asset.width == 300
    assert asset.height == 200
    assert asset.tags == ["uploaded"]
    assert "-upload-" in asset.asset_id
    assert asset.url == f"http://127.0.0.1:8123/asset-files/comm-impact/generated/{asset.asset_id}.jpg"

    file_path = tmp_path / "comm-impact" / "generated" / f"{asset.asset_id}.jpg"
    assert file_path.exists()

    metadata = json.loads((tmp_path / "comm-impact" / "metadata.json").read_text())
    assert any(r["asset_id"] == asset.asset_id for r in metadata)


def test_save_uploaded_asset_rejects_non_image_bytes_without_writing_a_file(tmp_path):
    store = LocalAssetStore(str(tmp_path))

    with pytest.raises(ValueError):
        store.save_uploaded_asset("comm-impact", b"this is not an image, just plain text", tags=[])

    generated_dir = tmp_path / "comm-impact" / "generated"
    assert not generated_dir.exists() or list(generated_dir.iterdir()) == []


def test_save_uploaded_and_save_generated_asset_ids_dont_collide(tmp_path):
    store = LocalAssetStore(str(tmp_path))
    generated = store.save_generated_asset("comm-impact", _png_bytes(), tags=[])
    uploaded = store.save_uploaded_asset("comm-impact", _jpeg_bytes(), tags=[])

    assert generated.asset_id != uploaded.asset_id
    assert "-img-template-" in generated.asset_id
    assert "-upload-" in uploaded.asset_id
