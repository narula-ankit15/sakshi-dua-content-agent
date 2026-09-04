"""One-time-per-topic ingestion: a zip of {source doc(s), photos from past
runs} -> a structured data/topics/{topic_id}/topic.json plus a populated
data/assets/{topic_id}/ photo bank.

No chunking/embeddings/vector store here (unlike the real-estate brochure
indexer this replaces) -- a workshop topic's structured fields (modules,
methodology, outcomes, ...) already ARE the complete context a content agent
needs, so this is a single structured-extraction LLM call, not a RAG index.

Run any time a topic's source doc/photos change:

    python -m app.ingest.topic_ingest --topic-id comm-impact --zip-path data/incoming/comm-impact.zip
"""

import argparse
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader

from app.agents.llm_client import GeminiClient
from app.config import get_settings
from app.models import Asset

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DOC_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

SYSTEM_PROMPT = """You extract structured workshop-topic content from a trainer's source document(s) -- typically a
slide-deck/curriculum transcript (long, detailed, session-by-session) and sometimes also a short marketing
brochure or one-pager the trainer already wrote (concise, curated, audience-facing). When both are given, prefer
the brochure's framing for tagline/hook/closing/positioning (it's already written for an audience), and use the
fuller deck for module/methodology depth.
Rules:
- Use ONLY information present in the source document(s). Never invent module titles, outcomes, or
  methodology that aren't grounded in the text -- if the documents are thin on a section, keep that
  section short rather than padding it with generic filler.
- modules must be numbered starting at 1, in the order they appear in the source material.
- Return strictly the JSON schema described in the prompt, nothing else.
"""

RESPONSE_SCHEMA_HINT = """Respond with JSON matching exactly:
{
  "topic_name": "...",
  "tagline": "...",
  "hook_description": "...",
  "modules": [{"module_number": 1, "title": "...", "bullets": ["...", "..."]}],
  "methodology": ["...", "..."],
  "outcomes": ["...", "..."],
  "closing_line": "...",
  "positioning_tags": ["...", "..."]
}
"""

_DOCX_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _extract_docx_text(doc_path: Path) -> str:
    # A .docx is a zip of XML parts -- pulling document.xml and stripping
    # tags is enough for plain paragraph/heading text (which is all this
    # extraction needs) without adding a python-docx dependency.
    with zipfile.ZipFile(doc_path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    text = _DOCX_TAG_RE.sub(" ", xml)
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_doc_text(doc_path: Path) -> str:
    suffix = doc_path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(doc_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        return _extract_docx_text(doc_path)
    return doc_path.read_text(errors="ignore")


def _is_junk_path(path: Path) -> bool:
    # macOS zips these in alongside real content: a top-level __MACOSX/
    # mirror directory, and one AppleDouble "._filename" resource-fork
    # stub per real file -- both need excluding, or a 200-byte stub JPEG
    # ends up "ingested" as a real photo.
    return "__MACOSX" in path.parts or path.name.startswith("._")


def split_zip_contents(extracted_dir: Path) -> tuple[list[Path], list[Path]]:
    photos: list[Path] = []
    docs: list[Path] = []
    for path in sorted(extracted_dir.rglob("*")):
        if not path.is_file() or _is_junk_path(path):
            continue
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            photos.append(path)
        elif suffix in DOC_EXTENSIONS:
            docs.append(path)
    if not docs:
        raise ValueError(
            f"No source doc (.pdf/.docx/.txt/.md) found in the zip -- found {len(photos)} photo(s) only"
        )
    return docs, photos


def ingest_topic(topic_id: str, zip_path: Path, topic_name_override: str = "") -> None:
    settings = get_settings()
    llm = GeminiClient(settings.gemini_api_key, settings.gemini_generation_model)

    with tempfile.TemporaryDirectory() as tmp:
        extracted_dir = Path(tmp)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extracted_dir)

        doc_paths, photo_paths = split_zip_contents(extracted_dir)
        doc_blocks = []
        for doc_path in doc_paths:
            text = extract_doc_text(doc_path)
            if not text.strip():
                print(f"WARNING: no extractable text in {doc_path.name} (scanned image? needs OCR) -- skipping")
                continue
            doc_blocks.append(f"=== SOURCE DOCUMENT: {doc_path.name} ===\n{text}")
        if not doc_blocks:
            raise ValueError(f"No extractable text in any of: {[d.name for d in doc_paths]}")

        prompt = "\n\n".join(doc_blocks) + f"\n\n{RESPONSE_SCHEMA_HINT}"
        raw = llm.generate_json(system=SYSTEM_PROMPT, prompt=prompt)

        photo_asset_ids = _copy_photos(topic_id, photo_paths, settings.asset_bank_path, settings.api_public_base_url)

        topic_dir = Path(settings.topic_data_path) / topic_id
        topic_dir.mkdir(parents=True, exist_ok=True)
        topic_json = {
            "topic_id": topic_id,
            "topic_name": topic_name_override or raw["topic_name"],
            "tagline": raw["tagline"],
            "hook_description": raw["hook_description"],
            "modules": raw["modules"],
            "methodology": raw["methodology"],
            "outcomes": raw["outcomes"],
            "closing_line": raw["closing_line"],
            "positioning_tags": raw["positioning_tags"],
            "source_doc_ref": ", ".join(d.name for d in doc_paths),
            "photo_asset_ids": photo_asset_ids,
        }
        (topic_dir / "topic.json").write_text(json.dumps(topic_json, indent=2))
        print(f"Wrote {topic_dir / 'topic.json'} ({len(raw['modules'])} modules, {len(photo_asset_ids)} photos)")


def _copy_photos(topic_id: str, photo_paths: list[Path], asset_bank_path: str, public_url_base: str) -> list[str]:
    if not photo_paths:
        return []
    topic_asset_dir = Path(asset_bank_path) / topic_id
    photos_dir = topic_asset_dir / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = topic_asset_dir / "metadata.json"
    records = json.loads(metadata_path.read_text()) if metadata_path.exists() else []
    existing_ids = {r["asset_id"] for r in records}

    for i, photo_path in enumerate(photo_paths, start=1):
        asset_id = f"{topic_id}-photo-{i:02d}"
        if asset_id in existing_ids:
            continue
        dest = photos_dir / f"{asset_id}{photo_path.suffix.lower()}"
        shutil.copy(photo_path, dest)

        from PIL import Image

        with Image.open(dest) as im:
            width, height = im.size

        asset = Asset(
            asset_id=asset_id,
            topic_id=topic_id,
            url=f"{public_url_base.rstrip('/')}/asset-files/{topic_id}/photos/{dest.name}",
            kind="image",
            tags=[photo_path.stem.replace("_", " ").replace("-", " ")],
            width=width,
            height=height,
        )
        records.append(json.loads(asset.model_dump_json()))

    metadata_path.write_text(json.dumps(records, indent=2))
    # photo_asset_ids on the Topic record is the topic's whole photo bank
    # (existing + newly-added this run), not just what changed in this call.
    return [r["asset_id"] for r in records]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic-id", required=True)
    parser.add_argument("--zip-path", required=True, help="Zip containing source doc(s) + photos for this topic")
    parser.add_argument("--topic-name", default="", help="Override the LLM-extracted topic_name")
    args = parser.parse_args()

    load_dotenv()
    ingest_topic(args.topic_id, Path(args.zip_path), args.topic_name)


if __name__ == "__main__":
    main()
