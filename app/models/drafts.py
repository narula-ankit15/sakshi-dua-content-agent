from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field

from app.models.topic import TopicModule


class EmailContentItem(BaseModel):
    """One image-led cell in a column/grid layout -- the image itself is
    resolved by code from real selected/generated assets, not the LLM; this
    is just the short caption copy that goes with it.
    """

    title: str
    text: str
    cta_text: Optional[str] = None  # only used by layouts whose items have their own button (Hero + 3-Column)


class EmailContent(BaseModel):
    """Fills one of the fixed EmailLayout templates (see
    app/rendering/email_renderer.py). Like BrochureContent, the LLM only
    writes copy -- asset URLs are resolved by code, and for
    EmailLayout.WORKSHOP_HIGHLIGHTS specifically, modules/methodology/
    outcomes are copied verbatim from the Topic record rather than written
    by the LLM at all, the same "structured facts reproduced exactly"
    principle the brochure already uses.
    """

    eyebrow: Optional[str] = None
    headline: str
    intro_text: str
    bullet_line: Optional[str] = None  # EmailLayout.EVENT's small detail line only
    items: list[EmailContentItem] = Field(default_factory=list)
    modules: list[TopicModule] = Field(default_factory=list)  # WORKSHOP_HIGHLIGHTS only, verbatim from topic
    methodology: list[str] = Field(default_factory=list)  # WORKSHOP_HIGHLIGHTS only, verbatim from topic
    outcomes: list[str] = Field(default_factory=list)  # WORKSHOP_HIGHLIGHTS only, verbatim from topic
    closing_text: str


class EmailDraft(BaseModel):
    subject_lines: list[str] = Field(..., min_length=1, description="2-3 A/B variants")
    html_body: str
    referenced_asset_ids: list[str] = Field(default_factory=list)
    # The structured copy html_body was rendered from -- None only for
    # drafts saved before this field existed. revise() reads this back to
    # know what it's editing, the same way BrochureDraft.content already
    # works.
    content: Optional[EmailContent] = None


class WhatsAppDraft(BaseModel):
    # Multiple full message variants, same idea as EmailDraft.subject_lines --
    # image_asset_id is shared across all variants, only the message copy
    # and CTA vary per variant.
    message_variants: list[str] = Field(..., min_length=1, description="2+ variants for A/B testing")
    # Parallel to message_variants (same length) when WhatsAppBrief.cta_required
    # is True -- lets up to 2 user-picked CTA options be A/B tested alongside
    # the message copy itself, one CTA per variant. None when cta_required is
    # False -- not every WhatsApp message needs an explicit call to action.
    cta_variants: Optional[list[str]] = None
    image_asset_id: Optional[str] = None


class BrochureContent(BaseModel):
    """Fills the fixed 6-section brochure template. hero_*/hook_lines/
    closing_line are the only fields a content agent generates per-campaign
    -- modules/methodology/outcomes/positioning_tags are always copied
    verbatim from the Topic record, never rephrased by the LLM, the same
    "structured facts are reproduced exactly" principle the real-estate
    version applied to RERA numbers and prices.
    """

    hero_title: str
    hero_tagline: str
    hero_description: str
    hook_lines: list[str] = Field(..., min_length=1, description="2-3 lines: why this workshop")
    modules: list[TopicModule]
    methodology: list[str]
    outcomes: list[str]
    closing_line: str
    positioning_tags: list[str]


class BrochureDraft(BaseModel):
    content: BrochureContent
    html: str
    # base64-encoded bytes, populated fresh on every generate/revise call --
    # this is the ephemeral preview; persisted files are only written to
    # disk at explicit save time (see BrochureFileStore).
    pdf_base64: str
    png_base64: str
    overflowed: bool = Field(default=False, description="True if the content didn't fit the fixed one-page layout")
    referenced_asset_ids: list[str] = Field(default_factory=list)


class IssueSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


class ComplianceIssue(BaseModel):
    code: str = Field(..., description="e.g. 'missing_rera_disclaimer', 'guaranteed_language'")
    message: str
    severity: IssueSeverity


class ComplianceResult(BaseModel):
    """Auto-fixable issues (e.g. an omitted disclaimer line) get folded into
    `corrected_draft` and `approved` stays true; blocking issues (e.g. a
    fabricated possession date) leave `approved=False` for a human to look
    at rather than being silently patched.
    """

    approved: bool
    issues: list[ComplianceIssue] = Field(default_factory=list)
    corrected_draft: Optional[Union[EmailDraft, WhatsAppDraft, BrochureDraft]] = None
