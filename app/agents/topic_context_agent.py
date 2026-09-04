from app.models import Topic
from app.storage.topic_store import TopicStore


class TopicContextAgent:
    """Replaces the real-estate version's ContextAgent -- there's no RAG
    step here. A workshop Topic's structured fields (modules, methodology,
    outcomes, ...) already are the complete context a content agent needs,
    so this just reads the one JSON record, no embeddings/vector store.
    """

    def __init__(self, topic_store: TopicStore):
        self._topic_store = topic_store

    def get_context(self, *, topic_id: str) -> Topic:
        return self._topic_store.get(topic_id)
