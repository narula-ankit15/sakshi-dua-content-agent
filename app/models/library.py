from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.brief import Channel


class ContentStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class ContentTag(str, Enum):
    """Broad content-category label, independent of CampaignBrief.purpose --
    purpose drives what the copy says, this drives how the piece gets
    organized/filtered in the library (e.g. by a compliance or ops team
    that cares about service vs. marketing communications)."""

    SERVICE = "service"
    PROMOTIONAL_COMMUNICATION = "promotional_communication"


class ContentLibraryEntry(BaseModel):
    """Mirrors the `content_library` table row-for-row. `content_json` holds
    the actual EmailDraft/WhatsAppDraft payload as a dict rather than a
    typed union so the store doesn't need a schema migration every time a
    channel's draft shape changes.
    """

    creative_id: str
    topic_id: str
    campaign_id: str
    channel: Channel
    variant_label: str = Field(..., description="e.g. 'subject_a', 'primary'")
    template_name: str = Field(default="Untitled Template", description="user-facing name shown on the library card")
    template_id: str = Field(
        default="", description="short human-friendly id, e.g. 'E4821' (email) / 'WA9207' (whatsapp)"
    )
    content_tag: str = Field(default="", description="ContentTag value, e.g. 'service' / 'promotional_communication'")
    content_json: dict[str, Any]
    asset_ids: list[str] = Field(default_factory=list)
    status: ContentStatus = ContentStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # The CampaignRequest-shaped payload (topic_id/campaign_brief/channel
    # brief) that produced content_json -- None for entries saved before
    # this field existed. Letting a saved draft be edited later (rather
    # than only revised-then-saved-once) means reopening the same form it
    # was generated from, which needs these original inputs back.
    request_json: Optional[dict[str, Any]] = None
    # Not a real column -- computed and attached by the API layer (from
    # EmailSendStore) so the library grid can show "sent" counts without a
    # per-card follow-up request. Always 0 for non-email channels.
    sent_count: int = 0
