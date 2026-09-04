from typing import Optional

from pydantic import BaseModel, Field


class TopicModule(BaseModel):
    """One numbered module in a workshop's curriculum breakdown."""

    module_number: int
    title: str
    bullets: list[str] = Field(default_factory=list)


class Topic(BaseModel):
    """Structured content for one workshop topic. Deliberately not split into
    "facts" + "retrieved chunks" the way the real-estate version was -- a
    workshop topic's module breakdown, methodology, and outcomes ARE the
    complete context a content agent needs, so there's no separate retrieval
    step (no RAG, no vector store). A content agent reproduces modules,
    methodology, outcomes, and positioning_tags exactly as given here; only
    the hero/hook/closing copy is generated per-campaign.
    """

    topic_id: str
    topic_name: str
    tagline: str
    hook_description: str
    modules: list[TopicModule] = Field(default_factory=list)
    methodology: list[str] = Field(default_factory=list, description="e.g. ['Role Plays', 'Simulations']")
    outcomes: list[str] = Field(default_factory=list, description="what participants can do after")
    closing_line: str
    positioning_tags: list[str] = Field(default_factory=list, description="e.g. ['Customised', 'Experiential']")
    source_doc_ref: Optional[str] = None
    photo_asset_ids: list[str] = Field(default_factory=list)


class TopicSummary(BaseModel):
    """Lightweight id + display name, for populating a topic picker without
    pulling in the full Topic (modules, outcomes, etc.)."""

    topic_id: str
    topic_name: str
