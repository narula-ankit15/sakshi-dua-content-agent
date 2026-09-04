from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Channel(str, Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    BROCHURE = "brochure"


class Purpose(str, Enum):
    PRODUCT_ANNOUNCEMENT = "product_announcement"
    NEWSLETTER = "newsletter"
    PROMO_SALE = "promo_sale"
    EVENT_INVITE = "event_invite"
    WELCOME_ONBOARDING = "welcome_onboarding"
    TRANSACTIONAL_RECEIPT = "transactional_receipt"
    FOLLOW_UP_NUDGE = "follow_up_nudge"
    PAYMENT_POSSESSION_REMINDER = "payment_possession_reminder"
    OTHER = "other"


class AudienceTone(str, Enum):
    CONSUMERS_CASUAL = "consumers_casual"
    CONSUMERS_PREMIUM = "consumers_premium"
    B2B_PROFESSIONAL = "b2b_professional"
    INTERNAL_TEAM = "internal_team"
    COMMUNITY_NEWSLETTER = "community_newsletter"


class CampaignBrief(BaseModel):
    """Shared across every channel in a campaign. Asked once regardless of
    how many channels are selected, since these describe the campaign
    itself (what it's for, what it says, who it's to) rather than any one
    channel's rendering of it.
    """

    purpose: Purpose
    purpose_other_description: Optional[str] = None
    key_message: str
    cta_text: str
    audience_tone: AudienceTone

    @model_validator(mode="after")
    def _require_description_when_other(self) -> "CampaignBrief":
        if self.purpose == Purpose.OTHER and not (self.purpose_other_description or "").strip():
            raise ValueError("purpose_other_description is required when purpose is 'other'")
        return self


class EmailLength(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class EmailImagery(str, Enum):
    TEXT_ONLY = "text_only"
    PLACEHOLDER_BLOCKS = "placeholder_blocks"
    USE_ASSET_BANK = "use_asset_bank"


class HeroImageSource(str, Enum):
    # A fresh Gemini image-generation call every time -- real money per
    # click, so this is opt-in, not the default.
    AI_GENERATED = "ai_generated"
    # No image-gen call at all -- the first entry in selected_asset_ids (or,
    # if none was picked, the top auto-searched candidate) is used as the
    # hero directly. This also lets a *previously* AI-generated image (it
    # stays in the asset bank once made) be reused as the hero for free.
    SELECTED_PHOTO = "selected_photo"


class EmailLayout(str, Enum):
    """Five fixed, server-rendered email structures (Jinja templates, like
    BrochureLayout) -- the LLM only ever writes the copy that drops into
    whichever one is chosen, never the HTML itself. That's what makes "the
    right number of images, at the right size" an actual guarantee instead
    of a prompt hint the model might not follow (a freeform LLM-built HTML
    table once collapsed a photo row to zero width -- see
    EMAIL_LAYOUT_SPECS for the image requirements this now enforces).
    """

    HERO_THREE_COLUMN = "hero_three_column"
    EVENT = "event"
    MINIMAL_ANNOUNCEMENT = "minimal_announcement"
    WELCOME_GRID = "welcome_grid"
    WORKSHOP_HIGHLIGHTS = "workshop_highlights"


class EmailLayoutSpec(BaseModel):
    """Describes exactly what images a layout needs -- used to size the
    image picker (how many slots, required vs optional) and to tell the LLM
    how many item captions to write.
    """

    label: str
    hero_required: bool
    hero_dimensions_hint: str
    item_count: int
    items_required: bool
    item_dimensions_hint: str

    @property
    def max_images(self) -> int:
        return (1 if self.hero_required else 0) + self.item_count


EMAIL_LAYOUT_SPECS: dict[EmailLayout, EmailLayoutSpec] = {
    EmailLayout.HERO_THREE_COLUMN: EmailLayoutSpec(
        label="Hero + 3-Column",
        hero_required=True,
        hero_dimensions_hint="wide banner, at least 1200×600px",
        item_count=3,
        items_required=True,
        item_dimensions_hint="square, at least 800×800px",
    ),
    EmailLayout.EVENT: EmailLayoutSpec(
        label="Event",
        hero_required=True,
        hero_dimensions_hint="wide banner, at least 1200×600px",
        item_count=3,
        items_required=True,
        item_dimensions_hint="square, at least 800×800px",
    ),
    EmailLayout.MINIMAL_ANNOUNCEMENT: EmailLayoutSpec(
        label="Minimal Announcement",
        hero_required=False,
        hero_dimensions_hint="",
        item_count=2,
        items_required=True,
        item_dimensions_hint="wide, at least 1200×600px",
    ),
    EmailLayout.WELCOME_GRID: EmailLayoutSpec(
        label="Welcome Grid",
        hero_required=True,
        hero_dimensions_hint="wide banner, at least 1200×600px",
        item_count=4,
        items_required=True,
        item_dimensions_hint="square, at least 800×800px",
    ),
    EmailLayout.WORKSHOP_HIGHLIGHTS: EmailLayoutSpec(
        label="Workshop Highlights",
        hero_required=True,
        hero_dimensions_hint="wide banner, at least 1200×600px",
        item_count=3,
        items_required=False,
        item_dimensions_hint="square, at least 600×600px (optional gallery photos)",
    ),
}


class EmailBrief(BaseModel):
    """Email-unique fields only -- anything shared with WhatsApp (key
    message, CTA text, audience/tone) lives on CampaignBrief instead.
    """

    design_system_id: Optional[str] = None
    length: EmailLength = EmailLength.MEDIUM
    imagery: EmailImagery = EmailImagery.USE_ASSET_BANK
    layout: EmailLayout = EmailLayout.WORKSHOP_HIGHLIGHTS
    # Only meaningful when imagery is USE_ASSET_BANK, and only when the
    # chosen layout has a hero slot (see EMAIL_LAYOUT_SPECS). Defaults to
    # not spending a paid image-generation call unless the user explicitly
    # asks for one.
    hero_image_source: HeroImageSource = HeroImageSource.SELECTED_PHOTO
    # User-picked asset_ids, in order. Meaning depends on hero_image_source:
    # SELECTED_PHOTO -- first = hero/main image, rest = smaller supporting
    # images. AI_GENERATED -- all of them are supporting/gallery images (the
    # hero comes from generation instead). Empty means "let the agent choose
    # from CANDIDATE ASSETS" (tag-matching auto-search). Capped at 5, the
    # most any layout (Welcome Grid) needs.
    selected_asset_ids: list[str] = Field(default_factory=list, max_length=5)


class WhatsAppLength(str, Enum):
    SHORT = "short"
    STANDARD = "standard"


class WhatsAppBrief(BaseModel):
    cta_required: bool = True
    image_required: bool = False
    length: WhatsAppLength = WhatsAppLength.STANDARD
    # Optional 2nd CTA option (alongside CampaignBrief.cta_text) -- when set,
    # the two are A/B tested across message_variants, one CTA per variant,
    # instead of every variant sharing a single CTA.
    secondary_cta_text: Optional[str] = None
    # A user-picked image overrides the AI's auto-pick, same idea as
    # EmailBrief.selected_asset_ids -- singular here because WhatsAppDraft
    # only ever carries one image_asset_id.
    selected_asset_id: Optional[str] = None


class BrochureLayout(str, Enum):
    """Four visually distinct one-page templates a brochure can be rendered
    into -- same content sections and word/count caps in every one (so
    BrochureContentAgent's output works unmodified against any of them),
    only the visual treatment differs.
    """

    MODERN_GRADIENT = "modern_gradient"
    CLEAN_MINIMAL = "clean_minimal"
    BOLD_GEOMETRIC = "bold_geometric"
    CLASSIC_SIDEBAR = "classic_sidebar"


class BrochureBrief(BaseModel):
    """Its presence on CampaignRequest means "generate a brochure," same
    convention as EmailBrief/WhatsAppBrief. Every text section besides
    Hero/Hook/Closing is pulled directly from the Topic record, so the only
    things left to configure are which layout to render into and which
    photos to use.
    """

    layout: BrochureLayout = BrochureLayout.MODERN_GRADIENT

    # User-picked asset_ids, in order (first = hero photo, rest = the "from
    # past cohorts" gallery strip) -- same convention as
    # EmailBrief.selected_asset_ids. Empty means "let the agent choose from
    # the topic's photo bank" (the existing tag-search behavior).
    selected_asset_ids: list[str] = Field(default_factory=list, max_length=4)


class CampaignRequest(BaseModel):
    """The Orchestrator's entry point. Which channels run is implied by
    which channel briefs are present -- there's no separate `channels`
    list, since a scenario where e.g. `email_brief` is set but email
    shouldn't run doesn't make sense.
    """

    topic_id: str
    campaign_id: str
    campaign_brief: CampaignBrief
    email_brief: Optional[EmailBrief] = None
    whatsapp_brief: Optional[WhatsAppBrief] = None
    brochure_brief: Optional[BrochureBrief] = None

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "CampaignRequest":
        if self.email_brief is None and self.whatsapp_brief is None and self.brochure_brief is None:
            raise ValueError("At least one of email_brief, whatsapp_brief, or brochure_brief must be provided")
        return self

    @property
    def channels(self) -> list[Channel]:
        result = []
        if self.email_brief is not None:
            result.append(Channel.EMAIL)
        if self.whatsapp_brief is not None:
            result.append(Channel.WHATSAPP)
        if self.brochure_brief is not None:
            result.append(Channel.BROCHURE)
        return result
