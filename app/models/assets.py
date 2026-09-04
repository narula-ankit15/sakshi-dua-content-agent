from typing import Optional

from pydantic import BaseModel, Field


class AssetQuery(BaseModel):
    topic_id: str
    semantic_query: Optional[str] = Field(default=None, description="e.g. 'role play', 'group workshop'")
    limit: int = 5


class Asset(BaseModel):
    """Metadata only, never a raw binary — content agents reference assets
    by ID and the frontend/CDN resolves `url` to bytes.
    """

    asset_id: str
    topic_id: str
    url: str
    kind: str = Field(..., description="'image' | 'video'")
    tags: list[str] = Field(default_factory=list)
    width: Optional[int] = None
    height: Optional[int] = None
    score: Optional[float] = Field(default=None, description="semantic match score, if a query was used")
