import json
import uuid
from pathlib import Path
from typing import Protocol

from app.models import Asset


class AssetStore(Protocol):
    """Abstract over "where do asset records live" so a local folder can be
    swapped for S3 (or a real DAM) later without touching the Asset agent.
    """

    def list_for_topic(self, topic_id: str) -> list[Asset]:
        ...

    def save_generated_asset(self, topic_id: str, image_bytes: bytes, tags: list[str]) -> Asset:
        ...

    def save_uploaded_asset(self, topic_id: str, image_bytes: bytes, tags: list[str]) -> Asset:
        ...


class LocalAssetStore:
    """Reads {base_path}/{topic_id}/metadata.json -- a JSON list of asset
    records sitting next to the actual image/video files. No binaries are
    read here; `url` in each record just points at wherever the file lives.
    """

    def __init__(self, base_path: str, public_url_base: str = ""):
        self._base_path = Path(base_path)
        # Every other asset's `url` is an already-public external link (ibb.co
        # etc); a locally-generated image needs the API's own origin prefixed
        # so the frontend (a different origin/port) can actually load it.
        self._public_url_base = public_url_base.rstrip("/")

    def list_for_topic(self, topic_id: str) -> list[Asset]:
        metadata_path = self._base_path / topic_id / "metadata.json"
        if not metadata_path.exists():
            return []
        records = json.loads(metadata_path.read_text())
        return [Asset.model_validate(r) for r in records]

    def save_generated_asset(self, topic_id: str, image_bytes: bytes, tags: list[str]) -> Asset:
        # Image templates built in the editor are a new kind of asset (a
        # locally-rendered PNG, not an externally-hosted URL) but need to
        # show up in the exact same place -- the topic's asset list -- so
        # they're written into the same metadata.json the rest of the bank
        # reads from, rather than a separate table/endpoint.
        return self._save_image(topic_id, image_bytes, id_prefix="img-template", tags=tags)

    def save_uploaded_asset(self, topic_id: str, image_bytes: bytes, tags: list[str]) -> Asset:
        # A user-uploaded photo -- same mechanics as a generated one (lands
        # in the same metadata.json, immediately reusable everywhere), just
        # a different id prefix so the two sources stay distinguishable.
        return self._save_image(topic_id, image_bytes, id_prefix="upload", tags=tags)

    def _save_image(self, topic_id: str, image_bytes: bytes, id_prefix: str, tags: list[str]) -> Asset:
        import io

        from PIL import Image, UnidentifiedImageError

        # Validate and inspect from the in-memory bytes *before* touching
        # disk -- a corrupt/non-image upload should fail cleanly rather than
        # leaving a stray unreadable file behind.
        try:
            with Image.open(io.BytesIO(image_bytes)) as im:
                width, height = im.size
                fmt = (im.format or "PNG").lower()
        except UnidentifiedImageError as e:
            raise ValueError("File is not a readable image") from e
        ext = "jpg" if fmt == "jpeg" else fmt

        topic_dir = self._base_path / topic_id
        generated_dir = topic_dir / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)

        asset_id = f"{topic_id}-{id_prefix}-{uuid.uuid4().hex[:8]}"
        file_path = generated_dir / f"{asset_id}.{ext}"
        file_path.write_bytes(image_bytes)

        asset = Asset(
            asset_id=asset_id,
            topic_id=topic_id,
            url=f"{self._public_url_base}/asset-files/{topic_id}/generated/{asset_id}.{ext}",
            kind="image",
            tags=tags,
            width=width,
            height=height,
        )

        metadata_path = topic_dir / "metadata.json"
        records = json.loads(metadata_path.read_text()) if metadata_path.exists() else []
        records.append(json.loads(asset.model_dump_json()))
        metadata_path.write_text(json.dumps(records, indent=2))

        return asset
