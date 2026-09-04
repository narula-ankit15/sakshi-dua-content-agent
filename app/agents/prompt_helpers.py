from app.models import CampaignBrief, Purpose, Topic


def humanize(value: str) -> str:
    return value.replace("_", " ").title()


def topic_content_dict(topic: Topic) -> dict:
    """topic.photo_asset_ids/source_doc_ref/topic_id are asset-store/ingestion
    bookkeeping, not content -- a content agent that sees photo_asset_ids in
    TOPIC CONTENT could reference an asset_id from there instead of from the
    CANDIDATE ASSETS block it's actually supposed to use, defeating the
    text_only/image_required=False guidance that CANDIDATE ASSETS is built to
    enforce. Excluded here so the only sanctioned channel for asset ids is
    CANDIDATE ASSETS.
    """
    return topic.model_dump(exclude={"photo_asset_ids", "source_doc_ref", "topic_id"}, exclude_none=True)


def campaign_context_block(campaign_brief: CampaignBrief) -> str:
    """Fields shared by every channel (purpose, key message, audience/tone).
    CTA text is deliberately excluded here -- each channel agent decides how
    (or whether) to surface `cta_text`, since that's channel-specific.
    """
    purpose_label = humanize(campaign_brief.purpose.value)
    if campaign_brief.purpose == Purpose.OTHER and campaign_brief.purpose_other_description:
        purpose_label = f"{purpose_label} - {campaign_brief.purpose_other_description}"
    return (
        f"CAMPAIGN PURPOSE: {purpose_label}\n"
        f"KEY MESSAGE: {campaign_brief.key_message}\n"
        f"AUDIENCE / TONE: {humanize(campaign_brief.audience_tone.value)}\n"
    )
