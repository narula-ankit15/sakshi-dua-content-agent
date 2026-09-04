import pytest

from app.models import (
    Asset,
    AudienceTone,
    CampaignBrief,
    EmailBrief,
    Purpose,
    Topic,
    TopicModule,
    WhatsAppBrief,
)


@pytest.fixture
def sample_campaign_brief() -> CampaignBrief:
    return CampaignBrief(
        purpose=Purpose.PROMO_SALE,
        key_message="drive signups for the Communicate with Impact workshop",
        cta_text="Reserve your seat",
        audience_tone=AudienceTone.CONSUMERS_PREMIUM,
    )


@pytest.fixture
def sample_email_brief() -> EmailBrief:
    return EmailBrief()


@pytest.fixture
def sample_whatsapp_brief() -> WhatsAppBrief:
    return WhatsAppBrief(cta_required=True, image_required=True)


@pytest.fixture
def sample_topic() -> Topic:
    return Topic(
        topic_id="comm-impact",
        topic_name="Communicate with Impact",
        tagline="Say less, land more.",
        hook_description="A hands-on workshop for teams whose ideas keep getting lost in the delivery.",
        modules=[
            TopicModule(module_number=1, title="Structuring Your Message", bullets=["The 3-part framework"]),
            TopicModule(module_number=2, title="Reading the Room", bullets=["Spotting disengagement early"]),
        ],
        methodology=["Role Plays", "Live Feedback Rounds"],
        outcomes=["Structure any message in under 60 seconds of prep", "Read a room and adjust delivery live"],
        closing_line="Communication is the multiplier on everything else your team does well.",
        positioning_tags=["Customised", "Experiential", "Business-focused"],
        source_doc_ref="seed",
        photo_asset_ids=["asset-roleplay-1", "asset-group-1"],
    )


@pytest.fixture
def sample_assets() -> list[Asset]:
    return [
        Asset(asset_id="asset-roleplay-1", topic_id="comm-impact", url="https://cdn/roleplay.jpg", kind="image", tags=["role play"]),
        Asset(asset_id="asset-group-1", topic_id="comm-impact", url="https://cdn/group.jpg", kind="image", tags=["group", "workshop"]),
    ]
