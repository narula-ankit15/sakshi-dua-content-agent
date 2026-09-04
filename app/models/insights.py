from pydantic import BaseModel


class WordCount(BaseModel):
    word: str
    count: int


class TagCount(BaseModel):
    tag: str
    count: int


class CtaCount(BaseModel):
    cta: str
    count: int


class EmailInsights(BaseModel):
    """Composition analytics derived from what's actually saved in the
    content library -- there is no send/open/click tracking anywhere in this
    system, so these describe what kind of subject lines have been produced,
    not how any of them performed.
    """

    count: int
    avg_subject_words: float
    avg_subject_chars: float
    emoji_usage_rate: float
    top_words: list[WordCount]
    image_usage_rate: float
    top_asset_tags: list[TagCount]
    content_tag_distribution: dict[str, int]


class WhatsAppInsights(BaseModel):
    count: int
    avg_message_words: float
    avg_message_chars: float
    top_cta_phrases: list[CtaCount]
    image_usage_rate: float
    top_asset_tags: list[TagCount]
    content_tag_distribution: dict[str, int]


class TopicInsights(BaseModel):
    topic_id: str
    email: EmailInsights
    whatsapp: WhatsAppInsights
