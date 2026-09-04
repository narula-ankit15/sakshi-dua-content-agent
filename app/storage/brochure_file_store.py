from pathlib import Path
from typing import TypedDict


class BrochureFileUrls(TypedDict):
    pdf_url: str
    png_url: str


class BrochureFileStore:
    """Persisted brochure exports live as plain files on disk, one PDF +
    one PNG per creative_id -- same reasoning as LocalAssetStore: a binary
    artifact shouldn't be crammed into a SQLite TEXT column, it should be a
    file with a URL the content-library entry just points at. Preview
    renders (before save) never touch this store -- they stay base64 in the
    draft response and are discarded if the user doesn't save.
    """

    def __init__(self, base_path: str, public_url_base: str = ""):
        self._base_path = Path(base_path)
        self._public_url_base = public_url_base.rstrip("/")

    def persist(self, topic_id: str, creative_id: str, pdf_bytes: bytes, png_bytes: bytes) -> BrochureFileUrls:
        topic_dir = self._base_path / topic_id
        topic_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = topic_dir / f"{creative_id}.pdf"
        png_path = topic_dir / f"{creative_id}.png"
        pdf_path.write_bytes(pdf_bytes)
        png_path.write_bytes(png_bytes)

        return {
            "pdf_url": f"{self._public_url_base}/brochure-files/{topic_id}/{creative_id}.pdf",
            "png_url": f"{self._public_url_base}/brochure-files/{topic_id}/{creative_id}.png",
        }
