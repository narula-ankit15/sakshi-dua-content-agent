from app.agents.asset_agent import AI_GENERATED_HERO_TAG, AssetAgent
from app.models import Asset, AssetQuery


class FakeAssetStore:
    def __init__(self, assets: list[Asset]):
        self._assets = assets
        self.last_saved_generated = None

    def list_for_topic(self, topic_id: str) -> list[Asset]:
        return [a for a in self._assets if a.topic_id == topic_id]

    def save_generated_asset(self, topic_id: str, image_bytes: bytes, tags: list[str]) -> Asset:
        self.last_saved_generated = (topic_id, image_bytes, tags)
        asset = Asset(asset_id="generated-1", topic_id=topic_id, url="https://cdn/generated-1.png", kind="image", tags=tags)
        self._assets.append(asset)
        return asset


def _asset(asset_id: str, tags: list[str]) -> Asset:
    return Asset(asset_id=asset_id, topic_id="comm-impact", url="https://cdn/x.jpg", kind="image", tags=tags)


def test_search_without_query_returns_up_to_limit():
    assets = [_asset("a1", ["role play"]), _asset("a2", ["group"]), _asset("a3", ["feedback"])]
    agent = AssetAgent(FakeAssetStore(assets))

    results = agent.search(AssetQuery(topic_id="comm-impact", limit=2))

    assert len(results) == 2


def test_search_ranks_by_tag_overlap():
    assets = [
        _asset("roleplay-group", ["role play", "group"]),
        _asset("feedback-solo", ["feedback", "solo"]),
        _asset("unrelated", ["parking", "lobby"]),
    ]
    agent = AssetAgent(FakeAssetStore(assets))

    results = agent.search(AssetQuery(topic_id="comm-impact", semantic_query="role play group", limit=5))

    assert [r.asset_id for r in results] == ["roleplay-group"]
    assert results[0].score == 1.0


def test_search_falls_back_to_other_assets_when_nothing_matches():
    # A content agent told to pick an image needs *some* real candidates --
    # an empty list makes it invent an asset_id instead of choosing for real.
    assets = [_asset("a1", ["parking"]), _asset("a2", ["lobby"])]
    agent = AssetAgent(FakeAssetStore(assets))

    results = agent.search(AssetQuery(topic_id="comm-impact", semantic_query="role play", limit=5))

    assert {r.asset_id for r in results} == {"a1", "a2"}


def test_search_excludes_zero_score_matches_when_something_did_match():
    assets = [_asset("roleplay", ["role play"]), _asset("unrelated", ["parking"])]
    agent = AssetAgent(FakeAssetStore(assets))

    results = agent.search(AssetQuery(topic_id="comm-impact", semantic_query="role play", limit=5))

    assert [r.asset_id for r in results] == ["roleplay"]


def test_get_by_ids_preserves_caller_order_not_store_order():
    assets = [_asset("a1", []), _asset("a2", []), _asset("a3", [])]
    agent = AssetAgent(FakeAssetStore(assets))

    results = agent.get_by_ids("comm-impact", ["a3", "a1"])

    assert [r.asset_id for r in results] == ["a3", "a1"]


def test_get_by_ids_skips_unknown_ids():
    assets = [_asset("a1", [])]
    agent = AssetAgent(FakeAssetStore(assets))

    results = agent.get_by_ids("comm-impact", ["a1", "does-not-exist"])

    assert [r.asset_id for r in results] == ["a1"]


def test_search_excludes_ai_generated_hero_images_from_candidates():
    # A previous campaign's generated hero image lives in the same
    # metadata.json as real photos -- it must never resurface as "a
    # workshop photo" candidate for a later campaign's gallery/hero search.
    assets = [
        _asset("real-photo", ["group"]),
        _asset("stray-hero", ["group", AI_GENERATED_HERO_TAG]),
    ]
    agent = AssetAgent(FakeAssetStore(assets))

    results = agent.search(AssetQuery(topic_id="comm-impact", semantic_query="group", limit=5))

    assert [r.asset_id for r in results] == ["real-photo"]


def test_search_without_query_also_excludes_ai_generated_hero_images():
    assets = [_asset("real-photo", []), _asset("stray-hero", [AI_GENERATED_HERO_TAG])]
    agent = AssetAgent(FakeAssetStore(assets))

    results = agent.search(AssetQuery(topic_id="comm-impact", limit=5))

    assert [r.asset_id for r in results] == ["real-photo"]


def test_save_generated_delegates_to_store_and_returns_asset():
    store = FakeAssetStore([])
    agent = AssetAgent(store)

    asset = agent.save_generated("comm-impact", b"png-bytes", tags=["ai_generated_hero"])

    assert asset.asset_id == "generated-1"
    assert asset.tags == ["ai_generated_hero"]
    assert store.last_saved_generated == ("comm-impact", b"png-bytes", ["ai_generated_hero"])
