import json
from pathlib import Path

from app.models import Topic, TopicSummary


class TopicStore:
    """Structured workshop content (modules, methodology, outcomes, ...)
    lives as one JSON file per topic rather than going through retrieval --
    a content agent needs to reproduce modules/methodology/outcomes exactly,
    so they come from a source of truth, not a similarity search.
    """

    def __init__(self, base_path: str):
        self._base_path = Path(base_path)

    def get(self, topic_id: str) -> Topic:
        topic_path = self._base_path / topic_id / "topic.json"
        if not topic_path.exists():
            raise FileNotFoundError(f"No structured topic content found for '{topic_id}' at {topic_path}")
        return Topic.model_validate(json.loads(topic_path.read_text()))

    def list_topics(self) -> list[TopicSummary]:
        # A topic only counts as usable once it has a topic.json -- a bare
        # directory (e.g. one scaffolded but never filled in) shouldn't show
        # up as a pickable topic.
        if not self._base_path.is_dir():
            return []
        summaries = []
        for entry in sorted(self._base_path.iterdir()):
            topic_path = entry / "topic.json"
            if not topic_path.exists():
                continue
            topic = Topic.model_validate(json.loads(topic_path.read_text()))
            summaries.append(TopicSummary(topic_id=entry.name, topic_name=topic.topic_name))
        return summaries
