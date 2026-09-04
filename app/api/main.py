import base64
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agents.asset_agent import AssetAgent
from app.agents.brochure_agent import BrochureContentAgent
from app.agents.compliance_agent import ComplianceAgent
from app.agents.email_agent import EmailContentAgent
from app.agents.email_sender import EmailSenderRegistry, SenderIdentity
from app.agents.hero_image_agent import HeroImageAgent
from app.agents.image_text_agent import ImageOverlayTextAgent
from app.agents.insights_agent import InsightsAgent
from app.agents.lead_import import LeadCsvError, parse_leads_csv
from app.agents.library_agent import ContentLibraryAgent
from app.agents.llm_client import GeminiClient, GeminiImageClient
from app.agents.orchestrator import Orchestrator
from app.agents.topic_context_agent import TopicContextAgent
from app.agents.usage_tracking_client import (
    ImageGenerationLimitExceeded,
    UsageTrackingImageClient,
    UsageTrackingLLMClient,
)
from app.agents.whatsapp_agent import WhatsAppContentAgent
from app.config import get_settings
from app.models import (
    Asset,
    BrochureBrief,
    BrochureDraft,
    CampaignBrief,
    CampaignRequest,
    Channel,
    ComplianceIssue,
    ContentLibraryEntry,
    ContentStatus,
    ContentTag,
    EmailBrief,
    EmailDraft,
    EmailSendRecord,
    Lead,
    LeadImportBatch,
    LeadImportResult,
    TopicInsights,
    TopicSummary,
    UsageSummary,
    WhatsAppBrief,
    WhatsAppDraft,
)
from app.rendering.brochure_renderer import BrochureRenderer
from app.rendering.email_renderer import EmailRenderer
from app.storage.asset_store import LocalAssetStore
from app.storage.brochure_file_store import BrochureFileStore
from app.storage.content_library_store import ContentLibraryStore
from app.storage.email_send_store import EmailSendStore
from app.storage.lead_import_store import LeadImportStore
from app.storage.lead_store import LeadStore
from app.storage.topic_store import TopicStore
from app.storage.usage_store import IMAGE_GENERATION_PURPOSE, UsageStore

app = FastAPI(title="Workshop Content Agent API")

# Local dev only: the browse UI (Vite on 5174) calls this API directly from
# the browser. Tighten this to a real origin allowlist before deploying anywhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Image-template PNGs rendered by the frontend's image editor get saved to
# disk (see LocalAssetStore.save_generated_asset) and need a real URL the
# browser can load -- this mount is what turns a file on disk into
# GET /asset-files/{topic_id}/generated/{asset_id}.png.
app.mount("/asset-files", StaticFiles(directory=get_settings().asset_bank_path), name="asset-files")

# Persisted brochure PDF/PNG exports (see BrochureFileStore) -- turns a file
# on disk into GET /brochure-files/{topic_id}/{creative_id}.pdf|.png.
Path(get_settings().brochure_files_path).mkdir(parents=True, exist_ok=True)
app.mount("/brochure-files", StaticFiles(directory=get_settings().brochure_files_path), name="brochure-files")

# Fixed brand assets baked into the image (not per-topic content, doesn't
# need the persistent volume) -- currently just the trainer's logo, used in
# the email templates' mark/footer instead of a plain text name.
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static"), name="static")


# Dependencies are built lazily behind @lru_cache (not at import time) so
# the API can start and serve /content-library reads even before
# GEMINI_API_KEY is configured, and so tests can override just the pieces
# that need faking via app.dependency_overrides.


@lru_cache
def get_library_store() -> ContentLibraryStore:
    return ContentLibraryStore(get_settings().content_library_db_path)


@lru_cache
def get_asset_store() -> LocalAssetStore:
    s = get_settings()
    return LocalAssetStore(s.asset_bank_path, public_url_base=s.api_public_base_url)


@lru_cache
def get_brochure_file_store() -> BrochureFileStore:
    s = get_settings()
    return BrochureFileStore(s.brochure_files_path, public_url_base=s.api_public_base_url)


@lru_cache
def get_usage_store() -> UsageStore:
    return UsageStore(get_settings().usage_db_path)


@lru_cache
def get_lead_store() -> LeadStore:
    return LeadStore(get_settings().leads_db_path)


@lru_cache
def get_lead_import_store() -> LeadImportStore:
    return LeadImportStore(get_settings().leads_db_path)


@lru_cache
def get_email_sender_registry() -> EmailSenderRegistry:
    s = get_settings()
    identities = [
        SenderIdentity(id=i.id, display_name=i.display_name, email=i.email, app_password=i.app_password)
        for i in s.resolved_email_senders()
    ]
    return EmailSenderRegistry(identities)


@lru_cache
def get_email_send_store() -> EmailSendStore:
    return EmailSendStore(get_settings().content_library_db_path)


@lru_cache
def get_image_text_agent() -> ImageOverlayTextAgent:
    s = get_settings()
    llm = UsageTrackingLLMClient(
        GeminiClient(s.gemini_api_key, s.gemini_generation_model), get_usage_store(), purpose="image_overlay_text"
    )
    return ImageOverlayTextAgent(llm)


@lru_cache
def get_topic_store() -> TopicStore:
    return TopicStore(get_settings().topic_data_path)


@lru_cache
def get_library_agent() -> ContentLibraryAgent:
    return ContentLibraryAgent(get_library_store(), get_brochure_file_store())


@lru_cache
def get_insights_agent() -> InsightsAgent:
    return InsightsAgent(get_library_store(), get_asset_store())


@lru_cache
def get_brochure_renderer() -> BrochureRenderer:
    s = get_settings()
    return BrochureRenderer(
        trainer_name=s.trainer_name, trainer_contact=s.trainer_contact, asset_bank_path=s.asset_bank_path
    )


@lru_cache
def get_email_renderer() -> EmailRenderer:
    s = get_settings()
    return EmailRenderer(
        trainer_name=s.trainer_name,
        trainer_contact=s.trainer_contact,
        logo_url=f"{s.api_public_base_url.rstrip('/')}/static/logo.png",
    )


@lru_cache
def get_hero_image_agent() -> HeroImageAgent:
    s = get_settings()
    image_client = UsageTrackingImageClient(
        GeminiImageClient(s.gemini_api_key),
        get_usage_store(),
        purpose=IMAGE_GENERATION_PURPOSE,
        daily_limit=s.max_daily_ai_images,
    )
    return HeroImageAgent(image_client)


@lru_cache
def get_orchestrator() -> Orchestrator:
    s = get_settings()
    context_agent = TopicContextAgent(get_topic_store())
    asset_agent = AssetAgent(get_asset_store())
    llm = UsageTrackingLLMClient(
        GeminiClient(s.gemini_api_key, s.gemini_generation_model), get_usage_store(), purpose="content_generation"
    )
    return Orchestrator(
        context_agent,
        asset_agent,
        EmailContentAgent(llm, get_email_renderer()),
        WhatsAppContentAgent(llm),
        BrochureContentAgent(llm, get_brochure_renderer()),
        ComplianceAgent(),
        get_library_agent(),
        get_hero_image_agent(),
        trainer_name=s.trainer_name,
        trainer_contact=s.trainer_contact,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/campaigns/run")
def run_campaign(request: CampaignRequest, orchestrator: Orchestrator = Depends(get_orchestrator)):
    try:
        return orchestrator.run(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImageGenerationLimitExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        # An unhandled exception here would skip CORSMiddleware's error path and
        # the browser would report it as an opaque CORS failure -- surface a real
        # message instead, since this is almost always a transient upstream
        # failure (Gemini rate limit or outage), not a client error.
        raise HTTPException(status_code=502, detail=f"Content generation failed: {e}")


class EmailDraftReview(BaseModel):
    draft: EmailDraft
    approved: bool
    issues: list[ComplianceIssue]


class WhatsAppDraftReview(BaseModel):
    draft: WhatsAppDraft
    approved: bool
    issues: list[ComplianceIssue]


class BrochureDraftReview(BaseModel):
    draft: BrochureDraft
    approved: bool
    issues: list[ComplianceIssue]


class GenerateResponse(BaseModel):
    email: Optional[EmailDraftReview] = None
    whatsapp: Optional[WhatsAppDraftReview] = None
    brochure: Optional[BrochureDraftReview] = None


class ReviseEmailRequest(BaseModel):
    topic_id: str
    campaign_brief: CampaignBrief
    email_brief: EmailBrief
    current_draft: EmailDraft
    instruction: str


class ReviseWhatsAppRequest(BaseModel):
    topic_id: str
    campaign_brief: CampaignBrief
    whatsapp_brief: WhatsAppBrief
    current_draft: WhatsAppDraft
    instruction: str


class ReviseBrochureRequest(BaseModel):
    topic_id: str
    campaign_brief: CampaignBrief
    brochure_brief: BrochureBrief
    current_draft: BrochureDraft
    instruction: str


class MoreSubjectLinesRequest(BaseModel):
    topic_id: str
    campaign_brief: CampaignBrief
    existing_subject_lines: list[str]


class MoreSubjectLinesResponse(BaseModel):
    subject_lines: list[str]


class SaveEmailRequest(BaseModel):
    topic_id: str
    campaign_id: str
    draft: EmailDraft
    template_name: str
    content_tag: ContentTag
    variant_label: str = "primary"
    as_draft: bool = False
    # The CampaignRequest payload that produced `draft` -- stored verbatim
    # so the saved entry can be reopened for editing later (see
    # ContentLibraryEntry.request_json). Optional so older frontend builds
    # don't break; entries saved without it just can't be edited.
    request_json: Optional[dict] = None


class SaveWhatsAppRequest(BaseModel):
    topic_id: str
    campaign_id: str
    draft: WhatsAppDraft
    template_name: str
    content_tag: ContentTag
    variant_label: str = "primary"
    as_draft: bool = False
    request_json: Optional[dict] = None


class SaveBrochureRequest(BaseModel):
    topic_id: str
    campaign_id: str
    draft: BrochureDraft
    template_name: str
    content_tag: ContentTag
    variant_label: str = "primary"
    as_draft: bool = False
    request_json: Optional[dict] = None


class SaveResponse(BaseModel):
    creative_id: str


@app.post("/campaigns/generate", response_model=GenerateResponse)
def generate_campaign(request: CampaignRequest, orchestrator: Orchestrator = Depends(get_orchestrator)):
    """Generates and compliance-checks drafts for every requested channel
    without saving anything -- pairs with /campaigns/revise/* and
    /content-library/* (save) so the caller can review and refine before
    anything lands in the library.
    """
    try:
        result = orchestrator.generate_drafts(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImageGenerationLimitExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Content generation failed: {e}")
    return result


@app.post("/campaigns/revise/email", response_model=EmailDraftReview)
def revise_email(payload: ReviseEmailRequest, orchestrator: Orchestrator = Depends(get_orchestrator)):
    try:
        return orchestrator.revise_email(
            topic_id=payload.topic_id,
            campaign_brief=payload.campaign_brief,
            email_brief=payload.email_brief,
            current_draft=payload.current_draft,
            instruction=payload.instruction,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Revision failed: {e}")


@app.post("/campaigns/generate-more-subject-lines", response_model=MoreSubjectLinesResponse)
def generate_more_subject_lines(
    payload: MoreSubjectLinesRequest, orchestrator: Orchestrator = Depends(get_orchestrator)
):
    try:
        subject_lines = orchestrator.generate_more_subject_lines(
            topic_id=payload.topic_id,
            campaign_brief=payload.campaign_brief,
            existing_subject_lines=payload.existing_subject_lines,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Subject line generation failed: {e}")
    return {"subject_lines": subject_lines}


@app.post("/campaigns/revise/whatsapp", response_model=WhatsAppDraftReview)
def revise_whatsapp(payload: ReviseWhatsAppRequest, orchestrator: Orchestrator = Depends(get_orchestrator)):
    try:
        return orchestrator.revise_whatsapp(
            topic_id=payload.topic_id,
            campaign_brief=payload.campaign_brief,
            whatsapp_brief=payload.whatsapp_brief,
            current_draft=payload.current_draft,
            instruction=payload.instruction,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Revision failed: {e}")


@app.post("/campaigns/revise/brochure", response_model=BrochureDraftReview)
def revise_brochure(payload: ReviseBrochureRequest, orchestrator: Orchestrator = Depends(get_orchestrator)):
    try:
        return orchestrator.revise_brochure(
            topic_id=payload.topic_id,
            campaign_brief=payload.campaign_brief,
            brochure_brief=payload.brochure_brief,
            current_draft=payload.current_draft,
            instruction=payload.instruction,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Revision failed: {e}")


@app.post("/content-library/email", response_model=SaveResponse)
def save_email(payload: SaveEmailRequest, library_agent: ContentLibraryAgent = Depends(get_library_agent)):
    creative_id = library_agent.save(
        topic_id=payload.topic_id,
        campaign_id=payload.campaign_id,
        channel=Channel.EMAIL,
        variant_label=payload.variant_label,
        template_name=payload.template_name,
        content_tag=payload.content_tag.value,
        content=payload.draft,
        asset_ids=payload.draft.referenced_asset_ids,
        status=ContentStatus.DRAFT if payload.as_draft else ContentStatus.APPROVED,
        request_json=payload.request_json,
    )
    return {"creative_id": creative_id}


@app.post("/content-library/whatsapp", response_model=SaveResponse)
def save_whatsapp(payload: SaveWhatsAppRequest, library_agent: ContentLibraryAgent = Depends(get_library_agent)):
    asset_ids = [payload.draft.image_asset_id] if payload.draft.image_asset_id else []
    creative_id = library_agent.save(
        topic_id=payload.topic_id,
        campaign_id=payload.campaign_id,
        channel=Channel.WHATSAPP,
        variant_label=payload.variant_label,
        template_name=payload.template_name,
        content_tag=payload.content_tag.value,
        content=payload.draft,
        asset_ids=asset_ids,
        status=ContentStatus.DRAFT if payload.as_draft else ContentStatus.APPROVED,
        request_json=payload.request_json,
    )
    return {"creative_id": creative_id}


@app.post("/content-library/brochure", response_model=SaveResponse)
def save_brochure(payload: SaveBrochureRequest, library_agent: ContentLibraryAgent = Depends(get_library_agent)):
    creative_id = library_agent.save(
        topic_id=payload.topic_id,
        campaign_id=payload.campaign_id,
        channel=Channel.BROCHURE,
        variant_label=payload.variant_label,
        template_name=payload.template_name,
        content_tag=payload.content_tag.value,
        content=payload.draft,
        asset_ids=payload.draft.referenced_asset_ids,
        status=ContentStatus.DRAFT if payload.as_draft else ContentStatus.APPROVED,
        request_json=payload.request_json,
    )
    return {"creative_id": creative_id}


@app.put("/content-library/email/{creative_id}", response_model=SaveResponse)
def update_email(
    creative_id: str, payload: SaveEmailRequest, library_agent: ContentLibraryAgent = Depends(get_library_agent)
):
    entry = library_agent.update(
        creative_id,
        content=payload.draft,
        asset_ids=payload.draft.referenced_asset_ids,
        status=ContentStatus.DRAFT if payload.as_draft else ContentStatus.APPROVED,
        template_name=payload.template_name,
        content_tag=payload.content_tag.value,
        request_json=payload.request_json,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No content found for creative_id '{creative_id}'")
    return {"creative_id": entry.creative_id}


@app.put("/content-library/whatsapp/{creative_id}", response_model=SaveResponse)
def update_whatsapp(
    creative_id: str, payload: SaveWhatsAppRequest, library_agent: ContentLibraryAgent = Depends(get_library_agent)
):
    asset_ids = [payload.draft.image_asset_id] if payload.draft.image_asset_id else []
    entry = library_agent.update(
        creative_id,
        content=payload.draft,
        asset_ids=asset_ids,
        status=ContentStatus.DRAFT if payload.as_draft else ContentStatus.APPROVED,
        template_name=payload.template_name,
        content_tag=payload.content_tag.value,
        request_json=payload.request_json,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No content found for creative_id '{creative_id}'")
    return {"creative_id": entry.creative_id}


@app.put("/content-library/brochure/{creative_id}", response_model=SaveResponse)
def update_brochure(
    creative_id: str, payload: SaveBrochureRequest, library_agent: ContentLibraryAgent = Depends(get_library_agent)
):
    entry = library_agent.update(
        creative_id,
        content=payload.draft,
        asset_ids=payload.draft.referenced_asset_ids,
        status=ContentStatus.DRAFT if payload.as_draft else ContentStatus.APPROVED,
        template_name=payload.template_name,
        content_tag=payload.content_tag.value,
        request_json=payload.request_json,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No content found for creative_id '{creative_id}'")
    return {"creative_id": entry.creative_id}


@app.post("/content-library/{creative_id}/duplicate", response_model=ContentLibraryEntry)
def duplicate_content(creative_id: str, library_agent: ContentLibraryAgent = Depends(get_library_agent)):
    entry = library_agent.duplicate(creative_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No content found for creative_id '{creative_id}'")
    return entry


@app.get("/content-library/{creative_id}", response_model=ContentLibraryEntry)
def get_content(creative_id: str, store: ContentLibraryStore = Depends(get_library_store)):
    entry = store.get(creative_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No content found for creative_id '{creative_id}'")
    return entry


@app.delete("/content-library/{creative_id}", status_code=204)
def delete_content(creative_id: str, library_agent: ContentLibraryAgent = Depends(get_library_agent)):
    if not library_agent.delete(creative_id):
        raise HTTPException(status_code=404, detail=f"No content found for creative_id '{creative_id}'")


class RenameContentRequest(BaseModel):
    template_name: str


@app.patch("/content-library/{creative_id}", response_model=ContentLibraryEntry)
def rename_content(
    creative_id: str, payload: RenameContentRequest, library_agent: ContentLibraryAgent = Depends(get_library_agent)
):
    entry = library_agent.rename(creative_id, payload.template_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No content found for creative_id '{creative_id}'")
    return entry


@app.get("/content-library/{creative_id}/sends", response_model=list[EmailSendRecord])
def list_email_sends(creative_id: str, store: EmailSendStore = Depends(get_email_send_store)):
    return store.list_for_creative(creative_id)


@app.get("/content-library", response_model=list[ContentLibraryEntry])
def list_content(
    topic_id: list[str] = Query(default=[]),
    channel: Optional[Channel] = None,
    store: ContentLibraryStore = Depends(get_library_store),
    send_store: EmailSendStore = Depends(get_email_send_store),
):
    # No topic_id at all means "no filter" -- Browse Library shows content
    # across every topic until the user selects one or more topic chips.
    entries = store.list_by_topics(topic_id, channel=channel)
    # One extra query for the whole grid (not one per card) to attach how
    # many times each has actually been sent.
    counts = send_store.counts_for_creatives([e.creative_id for e in entries])
    for entry in entries:
        entry.sent_count = counts.get(entry.creative_id, 0)
    return entries


@app.get("/topics", response_model=list[TopicSummary])
def list_topics(topic_store: TopicStore = Depends(get_topic_store)):
    # Populates the topic gate/picker -- only topics with a topic.json (i.e.
    # actually usable for generation) show up here.
    return topic_store.list_topics()


@app.get("/assets", response_model=list[Asset])
def list_assets(topic_id: str, store: LocalAssetStore = Depends(get_asset_store)):
    # Content-library entries only store asset_ids, not resolved URLs -- the
    # browse UI calls this to turn an id into something it can actually render.
    return store.list_for_topic(topic_id)


class CreateLeadRequest(BaseModel):
    name: str = Field(..., min_length=1)
    phone: str = ""
    email: str = ""
    organization: str = ""
    remarks: str = ""


@app.get("/leads", response_model=list[Lead])
def list_leads(search: Optional[str] = None, store: LeadStore = Depends(get_lead_store)):
    return store.list(search=search)


@app.post("/leads", response_model=Lead)
def create_lead(payload: CreateLeadRequest, store: LeadStore = Depends(get_lead_store)):
    return store.create(
        name=payload.name.strip(),
        phone=payload.phone.strip(),
        email=payload.email.strip(),
        organization=payload.organization.strip(),
        remarks=payload.remarks.strip(),
    )


@app.put("/leads/{lead_id}", response_model=Lead)
def update_lead(lead_id: str, payload: CreateLeadRequest, store: LeadStore = Depends(get_lead_store)):
    updated = store.update(
        lead_id,
        name=payload.name.strip(),
        phone=payload.phone.strip(),
        email=payload.email.strip(),
        organization=payload.organization.strip(),
        remarks=payload.remarks.strip(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"No lead found for id '{lead_id}'")
    return updated


@app.delete("/leads/{lead_id}", status_code=204)
def delete_lead(lead_id: str, store: LeadStore = Depends(get_lead_store)):
    if not store.delete(lead_id):
        raise HTTPException(status_code=404, detail=f"No lead found for id '{lead_id}'")


_MAX_CSV_BYTES = 5 * 1024 * 1024


@app.post("/leads/import", response_model=LeadImportResult)
async def import_leads_csv(
    file: UploadFile = File(...),
    store: LeadStore = Depends(get_lead_store),
    import_store: LeadImportStore = Depends(get_lead_import_store),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(raw) > _MAX_CSV_BYTES:
        raise HTTPException(status_code=400, detail="CSV must be under 5MB")
    try:
        text = raw.decode("utf-8-sig")  # -sig strips a BOM Excel/Sheets exports commonly add
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Couldn't read the file as UTF-8 text -- please export as CSV.")
    try:
        rows, skipped = parse_leads_csv(text)
    except LeadCsvError as e:
        raise HTTPException(status_code=400, detail=str(e))
    for row in rows:
        store.create(**row)
    import_store.record(filename=file.filename or "leads.csv", imported_count=len(rows), skipped=skipped)
    return {"imported": len(rows), "skipped": skipped}


@app.get("/leads/import-history", response_model=list[LeadImportBatch])
def list_lead_import_history(limit: int = 20, store: LeadImportStore = Depends(get_lead_import_store)):
    return store.list(limit=limit)


@app.get("/leads/import-history/{batch_id}/report")
def download_lead_import_report(batch_id: str, store: LeadImportStore = Depends(get_lead_import_store)):
    batch = store.get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"No import batch found for id '{batch_id}'")
    lines = ["Row,Reason"]
    for entry in batch.skipped:
        reason = str(entry.get("reason", "")).replace('"', '""')
        lines.append(f'{entry.get("row", "")},"{reason}"')
    csv_text = "\n".join(lines) + "\n"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{batch_id}-errors.csv"'},
    )


@app.get("/leads/import-template")
def download_lead_import_template():
    csv_text = (
        "Name,Phone,Email,Organization,Remarks\n"
        "Asha Rao,9876543210,asha@example.com,Acme Corp,Met at conference\n"
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads-import-template.csv"'},
    )


@app.get("/insights", response_model=TopicInsights)
def get_insights(topic_id: str, agent: InsightsAgent = Depends(get_insights_agent)):
    return agent.compute(topic_id)


@app.get("/usage", response_model=UsageSummary)
def get_usage(store: UsageStore = Depends(get_usage_store)):
    return store.summary(image_generation_daily_limit=get_settings().max_daily_ai_images)


class SetUsageCapRequest(BaseModel):
    daily_cap: Optional[int] = None


@app.put("/usage/cap", response_model=UsageSummary)
def set_usage_cap(payload: SetUsageCapRequest, store: UsageStore = Depends(get_usage_store)):
    store.set_daily_cap(payload.daily_cap)
    return store.summary(image_generation_daily_limit=get_settings().max_daily_ai_images)


# Deliberately not pydantic's EmailStr (would need the extra email-validator
# dependency) -- this is a light sanity check, not the security boundary;
# a malformed address just fails at the real SMTP send instead.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SendEmailRequest(BaseModel):
    # A list (not a comma-separated string) so validation/max-length is a
    # plain pydantic constraint -- the frontend is responsible for splitting
    # a pasted "a@x.com, b@y.com" block into this shape before posting.
    to: list[str] = Field(..., min_length=1, max_length=50)
    subject: str
    html_body: str
    # Which configured identity to send as -- None means "whichever is
    # first," for callers that predate sender selection.
    sender_id: Optional[str] = None
    # Set only when sending a saved library entry -- a send is logged
    # against this creative_id when present, and left unlogged for a
    # not-yet-saved draft preview (nothing to attach the record to).
    creative_id: Optional[str] = None


class SendEmailResult(BaseModel):
    to: str
    sent: bool
    error: Optional[str] = None


class SendEmailResponse(BaseModel):
    results: list[SendEmailResult]


class EmailSenderPublic(BaseModel):
    """Never includes app_password -- this is what the frontend's sender
    picker reads."""

    id: str
    display_name: str
    email: str


@app.get("/email-senders", response_model=list[EmailSenderPublic])
def list_email_senders(registry: EmailSenderRegistry = Depends(get_email_sender_registry)):
    return [
        {"id": i.id, "display_name": i.display_name, "email": i.email} for i in registry.list_identities()
    ]


@app.post("/send-email", response_model=SendEmailResponse)
def send_email(
    payload: SendEmailRequest,
    registry: EmailSenderRegistry = Depends(get_email_sender_registry),
    send_store: EmailSendStore = Depends(get_email_send_store),
):
    if not registry.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Email sending isn't configured yet -- add EMAIL_SENDERS (or GMAIL_ADDRESS/GMAIL_APP_PASSWORD) to .env",
        )
    sender = registry.get(payload.sender_id)
    if sender is None:
        raise HTTPException(status_code=400, detail=f"Unknown sender_id '{payload.sender_id}'")

    # Trim/dedupe (case-insensitively) whatever the frontend split a pasted
    # block into -- a stray blank line or the same address pasted twice
    # shouldn't count against the 50-recipient cap or send twice.
    seen: set[str] = set()
    recipients: list[str] = []
    for raw in payload.to:
        addr = raw.strip()
        key = addr.lower()
        if not addr or key in seen:
            continue
        seen.add(key)
        recipients.append(addr)
    if not recipients:
        raise HTTPException(status_code=400, detail="No recipient addresses given")

    valid = [r for r in recipients if _EMAIL_RE.match(r)]
    invalid = [r for r in recipients if r not in valid]
    if not valid:
        raise HTTPException(status_code=400, detail=f"No valid email addresses in: {', '.join(invalid)}")

    results = [
        SendEmailResult(to=addr, sent=False, error="Doesn't look like a valid email address") for addr in invalid
    ]
    try:
        failures = sender.send(to=valid, subject=payload.subject, html_body=payload.html_body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send email: {e}")
    for addr in valid:
        if addr in failures:
            results.append(SendEmailResult(to=addr, sent=False, error=failures[addr]))
        else:
            results.append(SendEmailResult(to=addr, sent=True))
            if payload.creative_id:
                send_store.record(payload.creative_id, addr)
    return {"results": results}


class SaveGeneratedAssetRequest(BaseModel):
    topic_id: str
    image_base64: str = Field(..., description="PNG bytes, optionally prefixed with a data: URL header")
    tags: list[str] = Field(default_factory=list)


@app.post("/assets/generated", response_model=Asset)
def save_generated_asset(payload: SaveGeneratedAssetRequest, store: LocalAssetStore = Depends(get_asset_store)):
    raw = payload.image_base64.split(",", 1)[-1]  # strip a leading "data:image/png;base64," if present
    try:
        image_bytes = base64.b64decode(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image data: {e}")
    return store.save_generated_asset(payload.topic_id, image_bytes, tags=payload.tags)


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@app.post("/assets/upload", response_model=Asset)
async def upload_asset(
    topic_id: str = Form(...),
    tags: str = Form(""),
    file: UploadFile = File(...),
    store: LocalAssetStore = Depends(get_asset_store),
):
    """Lets a user add their own photo to a topic's asset bank straight
    from the browser -- it lands in the exact same metadata.json as ingested
    and AI-generated images, so it's immediately reusable everywhere a
    picker shows images, not just for the campaign it was uploaded during.
    """
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(image_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 10MB")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        return store.save_uploaded_asset(topic_id, image_bytes, tags=tag_list)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SuggestOverlayTextRequest(BaseModel):
    campaign_brief: CampaignBrief


class SuggestOverlayTextResponse(BaseModel):
    suggestions: list[str]


@app.post("/assets/suggest-overlay-text", response_model=SuggestOverlayTextResponse)
def suggest_overlay_text(
    payload: SuggestOverlayTextRequest, agent: ImageOverlayTextAgent = Depends(get_image_text_agent)
):
    try:
        suggestions = agent.suggest(payload.campaign_brief)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Suggestion failed: {e}")
    return {"suggestions": suggestions}


# Production only: one container serves both the API (every route above)
# and the built frontend, so the browser never needs cross-origin requests.
# Mounted last so it only catches paths no API route already claimed.
# frontend_dist doesn't exist in local dev (the frontend runs on its own
# Vite dev server there instead), so this is a no-op locally.
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend_dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
