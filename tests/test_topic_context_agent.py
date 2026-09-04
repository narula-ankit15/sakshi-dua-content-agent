import pytest

from app.agents.topic_context_agent import TopicContextAgent
from app.models import Topic


class FakeTopicStore:
    def __init__(self, topic: Topic):
        self._topic = topic

    def get(self, topic_id: str) -> Topic:
        assert topic_id == self._topic.topic_id
        return self._topic


def test_get_context_returns_the_topic_directly(sample_topic):
    agent = TopicContextAgent(FakeTopicStore(sample_topic))

    topic = agent.get_context(topic_id="comm-impact")

    assert topic is sample_topic
    assert topic.topic_name == "Communicate with Impact"
    assert len(topic.modules) == 2


def test_get_context_propagates_missing_topic_error():
    class RaisingStore:
        def get(self, topic_id: str) -> Topic:
            raise FileNotFoundError(f"No topic '{topic_id}'")

    agent = TopicContextAgent(RaisingStore())

    with pytest.raises(FileNotFoundError):
        agent.get_context(topic_id="does-not-exist")
