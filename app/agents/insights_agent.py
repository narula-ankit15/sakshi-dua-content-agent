import re
from collections import Counter

from app.models import (
    Asset,
    Channel,
    ContentLibraryEntry,
    CtaCount,
    EmailInsights,
    TagCount,
    TopicInsights,
    WhatsAppInsights,
    WordCount,
)
from app.storage.asset_store import AssetStore
from app.storage.content_library_store import ContentLibraryStore

# Astral-plane emoji blocks + the misc-symbols/dingbats range most emoji in
# subject lines actually come from (✨ 🎉 etc.) -- not exhaustive, but wide
# enough to catch the emoji this app's own agents are prompted to use.
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
_WORD_RE = re.compile(r"[a-zA-Z]{3,}")
_STOPWORDS = {
    "the", "and", "for", "are", "you", "your", "our", "with", "from", "this",
    "that", "now", "get", "new", "into", "over", "just", "have", "has", "was",
    "not", "all", "can", "will", "its", "it's", "here", "book", "visit",
}


def _avg_words(texts: list[str]) -> float:
    if not texts:
        return 0.0
    return round(sum(len(t.split()) for t in texts) / len(texts), 1)


def _avg_chars(texts: list[str]) -> float:
    if not texts:
        return 0.0
    return round(sum(len(t) for t in texts) / len(texts), 1)


def _emoji_rate(texts: list[str]) -> float:
    if not texts:
        return 0.0
    return round(sum(1 for t in texts if _EMOJI_RE.search(t)) / len(texts), 2)


def _top_words(texts: list[str], top_n: int = 8) -> list[WordCount]:
    counter: Counter = Counter()
    for t in texts:
        for w in _WORD_RE.findall(t.lower()):
            if w not in _STOPWORDS:
                counter[w] += 1
    return [WordCount(word=w, count=c) for w, c in counter.most_common(top_n)]


def _top_ctas(ctas: list[str], top_n: int = 6) -> list[CtaCount]:
    counter = Counter(c.strip() for c in ctas if c and c.strip())
    return [CtaCount(cta=c, count=n) for c, n in counter.most_common(top_n)]


def _image_usage_rate(entries: list[ContentLibraryEntry]) -> float:
    if not entries:
        return 0.0
    return round(sum(1 for e in entries if e.asset_ids) / len(entries), 2)


def _top_asset_tags(entries: list[ContentLibraryEntry], assets_by_id: dict[str, Asset], top_n: int = 6) -> list[TagCount]:
    counter: Counter = Counter()
    for e in entries:
        for asset_id in e.asset_ids:
            asset = assets_by_id.get(asset_id)
            if asset:
                counter.update(asset.tags)
    return [TagCount(tag=t, count=c) for t, c in counter.most_common(top_n)]


def _content_tag_distribution(entries: list[ContentLibraryEntry]) -> dict[str, int]:
    counter = Counter(e.content_tag or "untagged" for e in entries)
    return dict(counter)


class InsightsAgent:
    """Composition analytics computed straight from the content library --
    what kind of content has actually been produced (subject line length,
    words, emoji use, image use, CTA phrasing), not how any of it performed.
    This system doesn't send campaigns or track opens/clicks, so real
    engagement metrics don't exist here; the frontend is responsible for
    never presenting these numbers as performance data.
    """

    def __init__(self, library_store: ContentLibraryStore, asset_store: AssetStore):
        self._library_store = library_store
        self._asset_store = asset_store

    def compute(self, topic_id: str) -> TopicInsights:
        entries = self._library_store.list_by_topic(topic_id)
        email_entries = [e for e in entries if e.channel == Channel.EMAIL]
        whatsapp_entries = [e for e in entries if e.channel == Channel.WHATSAPP]
        assets_by_id = {a.asset_id: a for a in self._asset_store.list_for_topic(topic_id)}

        return TopicInsights(
            topic_id=topic_id,
            email=self._email_insights(email_entries, assets_by_id),
            whatsapp=self._whatsapp_insights(whatsapp_entries, assets_by_id),
        )

    @staticmethod
    def _email_insights(entries: list[ContentLibraryEntry], assets_by_id: dict[str, Asset]) -> EmailInsights:
        subject_lines = [s for e in entries for s in e.content_json.get("subject_lines", [])]
        return EmailInsights(
            count=len(entries),
            avg_subject_words=_avg_words(subject_lines),
            avg_subject_chars=_avg_chars(subject_lines),
            emoji_usage_rate=_emoji_rate(subject_lines),
            top_words=_top_words(subject_lines),
            image_usage_rate=_image_usage_rate(entries),
            top_asset_tags=_top_asset_tags(entries, assets_by_id),
            content_tag_distribution=_content_tag_distribution(entries),
        )

    @staticmethod
    def _whatsapp_insights(entries: list[ContentLibraryEntry], assets_by_id: dict[str, Asset]) -> WhatsAppInsights:
        messages = [m for e in entries for m in e.content_json.get("message_variants", [])]
        ctas = [c for e in entries for c in (e.content_json.get("cta_variants") or [])]
        return WhatsAppInsights(
            count=len(entries),
            avg_message_words=_avg_words(messages),
            avg_message_chars=_avg_chars(messages),
            top_cta_phrases=_top_ctas(ctas),
            image_usage_rate=_image_usage_rate(entries),
            top_asset_tags=_top_asset_tags(entries, assets_by_id),
            content_tag_distribution=_content_tag_distribution(entries),
        )
