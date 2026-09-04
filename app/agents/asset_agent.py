from app.models import Asset, AssetQuery
from app.storage.asset_store import AssetStore

# Tag HeroImageAgent-generated illustrations are saved with (see
# Orchestrator._generate_hero_asset). These live in the same per-topic
# metadata.json as real workshop photos so asset://{id} placeholders can
# still resolve them, but they must never resurface as a *candidate* photo
# for a gallery/hero search -- otherwise one campaign's generated hero can
# get auto-picked as "a real workshop photo" in a later campaign.
AI_GENERATED_HERO_TAG = "ai_generated_hero"


class AssetAgent:
    """Ranks by tag overlap, not embeddings -- assets typically have a
    handful of hand-curated tags, so keyword matching against them is both
    cheap and, for that vocabulary size, about as accurate as embedding
    every asset would be. If the tag vocabulary grows large and free-form,
    swap `_score` for a semantic ranking without changing the agent's
    input/output contract.
    """

    def __init__(self, asset_store: AssetStore):
        self._asset_store = asset_store

    def search(self, query: AssetQuery) -> list[Asset]:
        candidates = [
            a for a in self._asset_store.list_for_topic(query.topic_id) if AI_GENERATED_HERO_TAG not in a.tags
        ]

        if not query.semantic_query:
            return candidates[: query.limit]

        query_tokens = [t.lower() for t in query.semantic_query.split()]
        scored = [
            candidate.model_copy(update={"score": self._score(candidate, query_tokens)})
            for candidate in candidates
        ]
        scored.sort(key=lambda c: c.score, reverse=True)
        matched = [c for c in scored if c.score > 0]
        # A content agent that's told to pick an image needs *some* real
        # candidates to choose from -- an empty list makes it invent an
        # asset_id instead. Fall back to the project's other assets rather
        # than returning nothing just because no tags matched.
        return (matched or scored)[: query.limit]

    def get_by_ids(self, topic_id: str, asset_ids: list[str]) -> list[Asset]:
        # Preserves the given order (the caller's first id is the intended
        # hero image, etc.) rather than whatever order the store returns.
        by_id = {a.asset_id: a for a in self._asset_store.list_for_topic(topic_id)}
        return [by_id[asset_id] for asset_id in asset_ids if asset_id in by_id]

    def save_generated(self, topic_id: str, image_bytes: bytes, tags: list[str]) -> Asset:
        return self._asset_store.save_generated_asset(topic_id, image_bytes, tags)

    @staticmethod
    def _score(asset: Asset, query_tokens: list[str]) -> float:
        tags = [t.lower() for t in asset.tags]
        matches = sum(1 for token in query_tokens if any(token in tag for tag in tags))
        return matches / len(query_tokens) if query_tokens else 0.0
