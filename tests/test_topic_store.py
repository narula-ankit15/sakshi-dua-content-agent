import json

import pytest

from app.storage.topic_store import TopicStore


def _write_topic(base_path, topic_id, topic_name):
    topic_dir = base_path / topic_id
    topic_dir.mkdir()
    (topic_dir / "topic.json").write_text(
        json.dumps(
            {
                "topic_id": topic_id,
                "topic_name": topic_name,
                "tagline": "Tag",
                "hook_description": "Hook",
                "modules": [],
                "methodology": [],
                "outcomes": [],
                "closing_line": "Closing",
                "positioning_tags": [],
            }
        )
    )


def test_list_topics_returns_only_topics_with_topic_json(tmp_path):
    _write_topic(tmp_path, "comm-impact", "Communicate with Impact")
    _write_topic(tmp_path, "negotiation-101", "Negotiation 101")
    (tmp_path / "empty-scaffold").mkdir()  # no topic.json -- shouldn't show up

    store = TopicStore(str(tmp_path))
    summaries = store.list_topics()

    assert {(s.topic_id, s.topic_name) for s in summaries} == {
        ("comm-impact", "Communicate with Impact"),
        ("negotiation-101", "Negotiation 101"),
    }


def test_list_topics_empty_when_base_path_missing(tmp_path):
    store = TopicStore(str(tmp_path / "does-not-exist"))

    assert store.list_topics() == []


def test_get_still_raises_for_unknown_topic(tmp_path):
    store = TopicStore(str(tmp_path))

    with pytest.raises(FileNotFoundError):
        store.get("does-not-exist")
