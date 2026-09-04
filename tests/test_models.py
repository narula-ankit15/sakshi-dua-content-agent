import pytest
from pydantic import ValidationError

from app.models import AudienceTone, BrochureBrief, CampaignBrief, CampaignRequest, Channel, Purpose


def _campaign_brief(**overrides) -> CampaignBrief:
    defaults = dict(purpose=Purpose.PROMO_SALE, key_message="msg", cta_text="cta", audience_tone=AudienceTone.CONSUMERS_PREMIUM)
    defaults.update(overrides)
    return CampaignBrief(**defaults)


def test_campaign_request_requires_at_least_one_channel_brief():
    with pytest.raises(ValidationError, match="At least one of email_brief, whatsapp_brief, or brochure_brief"):
        CampaignRequest(topic_id="t", campaign_id="c", campaign_brief=_campaign_brief())


def test_campaign_request_channels_property_includes_brochure():
    request = CampaignRequest(
        topic_id="t", campaign_id="c", campaign_brief=_campaign_brief(), brochure_brief=BrochureBrief()
    )
    assert request.channels == [Channel.BROCHURE]


def test_campaign_brief_requires_description_when_purpose_is_other():
    with pytest.raises(ValidationError, match="purpose_other_description is required"):
        _campaign_brief(purpose=Purpose.OTHER)


def test_campaign_brief_allows_other_with_description():
    brief = _campaign_brief(purpose=Purpose.OTHER, purpose_other_description="Custom purpose")
    assert brief.purpose_other_description == "Custom purpose"
