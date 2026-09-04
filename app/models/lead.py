from datetime import datetime

from pydantic import BaseModel, Field, computed_field


class Lead(BaseModel):
    """A prospective client's contact details -- tracked independently of
    any topic/campaign, since a trainer's lead list spans whichever
    workshops they end up pitching, not just one.
    """

    id: str
    name: str
    phone: str = ""
    email: str = ""
    organization: str = ""
    remarks: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1)
    phone: str = ""
    email: str = ""
    organization: str = ""
    remarks: str = ""


class LeadImportResult(BaseModel):
    imported: int
    skipped: list[dict] = Field(default_factory=list, description="[{row: int, reason: str}]")


class LeadImportBatch(BaseModel):
    """One CSV upload's record -- kept so the Leads page can show an
    upload history, not just the leads it produced.
    """

    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    filename: str
    imported_count: int
    skipped: list[dict] = Field(default_factory=list, description="[{row: int, reason: str}]")

    @computed_field
    @property
    def total_rows(self) -> int:
        return self.imported_count + len(self.skipped)

    @computed_field
    @property
    def failed_count(self) -> int:
        return len(self.skipped)

    @computed_field
    @property
    def status(self) -> str:
        return "error" if self.skipped else "success"
