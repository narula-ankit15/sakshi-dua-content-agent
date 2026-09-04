import base64
from typing import Any, Optional, Union

import shortuuid

from app.models import BrochureDraft, Channel, ContentLibraryEntry, ContentStatus, EmailDraft, WhatsAppDraft
from app.storage.brochure_file_store import BrochureFileStore
from app.storage.content_library_store import ContentLibraryStore


class ContentLibraryAgent:
    def __init__(self, store: ContentLibraryStore, brochure_file_store: Optional[BrochureFileStore] = None):
        self._store = store
        self._brochure_file_store = brochure_file_store

    def _content_json(
        self, content: Union[EmailDraft, WhatsAppDraft, BrochureDraft], topic_id: str, creative_id: str
    ) -> dict[str, Any]:
        content_json = content.model_dump(mode="json")
        if isinstance(content, BrochureDraft) and self._brochure_file_store is not None:
            # A brochure's PDF/PNG bytes were only ever the ephemeral preview
            # payload -- persisting means writing real files and swapping
            # the base64 blobs for the URLs pointing at them, not storing
            # binary bytes as SQLite TEXT. Re-persisting under the same
            # creative_id (the update() path) overwrites the same files in
            # place, so the URLs stay stable across an edit.
            urls = self._brochure_file_store.persist(
                topic_id,
                creative_id,
                pdf_bytes=base64.b64decode(content.pdf_base64),
                png_bytes=base64.b64decode(content.png_base64),
            )
            content_json.pop("pdf_base64", None)
            content_json.pop("png_base64", None)
            content_json.update(urls)
        return content_json

    def save(
        self,
        *,
        topic_id: str,
        campaign_id: str,
        channel: Channel,
        variant_label: str,
        content: Union[EmailDraft, WhatsAppDraft, BrochureDraft],
        asset_ids: list[str],
        status: ContentStatus = ContentStatus.APPROVED,
        template_name: str = "Untitled Template",
        content_tag: str = "",
        request_json: Optional[dict[str, Any]] = None,
    ) -> str:
        # {topic_id}-{channel}-{campaign_id}-{shortuuid} keeps IDs
        # human-scannable in the campaign-setup dropdown, per the doc's ID scheme.
        creative_id = f"{topic_id}-{channel.value}-{campaign_id}-{shortuuid.ShortUUID().random(length=6)}"
        entry = ContentLibraryEntry(
            creative_id=creative_id,
            topic_id=topic_id,
            campaign_id=campaign_id,
            channel=channel,
            variant_label=variant_label,
            template_name=template_name,
            template_id=self._store.generate_template_id(channel),
            content_tag=content_tag,
            content_json=self._content_json(content, topic_id, creative_id),
            asset_ids=asset_ids,
            status=status,
            request_json=request_json,
        )
        self._store.save(entry)
        return creative_id

    def update(
        self,
        creative_id: str,
        *,
        content: Union[EmailDraft, WhatsAppDraft, BrochureDraft],
        asset_ids: list[str],
        status: ContentStatus,
        template_name: Optional[str] = None,
        content_tag: Optional[str] = None,
        request_json: Optional[dict[str, Any]] = None,
    ) -> Optional[ContentLibraryEntry]:
        """Overwrites an existing entry's content in place -- same
        creative_id/template_id/created_at, so a saved draft can be reopened
        and edited rather than only ever revised-then-saved-once. None
        returned (not raised) when creative_id doesn't exist, matching
        rename()'s convention so the API layer can turn it into a 404.
        """
        existing = self._store.get(creative_id)
        if existing is None:
            return None
        entry = ContentLibraryEntry(
            creative_id=creative_id,
            topic_id=existing.topic_id,
            campaign_id=existing.campaign_id,
            channel=existing.channel,
            variant_label=existing.variant_label,
            template_name=template_name if template_name is not None else existing.template_name,
            template_id=existing.template_id,
            content_tag=content_tag if content_tag is not None else existing.content_tag,
            content_json=self._content_json(content, existing.topic_id, creative_id),
            asset_ids=asset_ids,
            status=status,
            created_at=existing.created_at,
            request_json=request_json if request_json is not None else existing.request_json,
        )
        self._store.save(entry)
        return entry

    def duplicate(self, creative_id: str) -> Optional[ContentLibraryEntry]:
        """Clones a saved entry under a brand-new creative_id/template_id,
        always as a draft -- the point is a safe-to-edit starting point, not
        a second copy of something already approved and sent.
        """
        existing = self._store.get(creative_id)
        if existing is None:
            return None
        new_id = f"{existing.topic_id}-{existing.channel.value}-{existing.campaign_id}-{shortuuid.ShortUUID().random(length=6)}"
        entry = ContentLibraryEntry(
            creative_id=new_id,
            topic_id=existing.topic_id,
            campaign_id=existing.campaign_id,
            channel=existing.channel,
            variant_label=existing.variant_label,
            template_name=f"{existing.template_name} (Copy)",
            template_id=self._store.generate_template_id(existing.channel),
            content_tag=existing.content_tag,
            content_json=existing.content_json,
            asset_ids=existing.asset_ids,
            status=ContentStatus.DRAFT,
            request_json=existing.request_json,
        )
        self._store.save(entry)
        return entry

    def delete(self, creative_id: str) -> bool:
        return self._store.delete(creative_id)

    def rename(self, creative_id: str, template_name: str) -> Optional[ContentLibraryEntry]:
        return self._store.rename_template_name(creative_id, template_name)
