import operator
from typing import Annotated, Dict, List, Optional, TypedDict, Union

from langgraph.graph import END, START, StateGraph

from app.agents.asset_agent import AI_GENERATED_HERO_TAG, AssetAgent
from app.agents.brochure_agent import BrochureContentAgent
from app.agents.compliance_agent import ComplianceAgent
from app.agents.email_agent import EmailContentAgent
from app.agents.hero_image_agent import HeroImageAgent
from app.agents.library_agent import ContentLibraryAgent
from app.agents.topic_context_agent import TopicContextAgent
from app.agents.usage_tracking_client import ImageGenerationLimitExceeded
from app.agents.whatsapp_agent import WhatsAppContentAgent
from app.models import (
    Asset,
    AssetQuery,
    BrochureBrief,
    BrochureDraft,
    CampaignBrief,
    CampaignRequest,
    Channel,
    ComplianceIssue,
    EMAIL_LAYOUT_SPECS,
    EmailBrief,
    EmailDraft,
    EmailImagery,
    HeroImageSource,
    Topic,
    WhatsAppBrief,
    WhatsAppDraft,
)


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


class OrchestratorState(TypedDict):
    request: CampaignRequest
    topic: Optional[Topic]
    candidate_assets: List[Asset]
    email_draft: Optional[EmailDraft]
    whatsapp_draft: Optional[WhatsAppDraft]
    brochure_draft: Optional[BrochureDraft]
    email_approved: Optional[bool]
    whatsapp_approved: Optional[bool]
    brochure_approved: Optional[bool]
    # All three channel branches can write these in the same run, so they
    # need a merge reducer -- plain TypedDict fields default to "last write
    # wins," which would silently drop a channel's creative_id/status note.
    creative_ids: Annotated[Dict[str, str], _merge_dicts]
    status_notes: Annotated[List[str], operator.add]


class OrchestratorResult(TypedDict):
    creative_ids: Dict[str, str]
    status_notes: List[str]


class DraftReview(TypedDict):
    draft: Union[EmailDraft, WhatsAppDraft, BrochureDraft]
    approved: bool
    issues: List[ComplianceIssue]


class Orchestrator:
    """Fans out to the TopicContext and Asset agents in parallel, fans back
    into whichever content agents the request actually asked for (implied by
    which of email_brief/whatsapp_brief/brochure_brief is present, not a
    separate channel list), routes each draft through Compliance/QA, and
    only hands approved drafts to the Library agent. A rejected draft shows
    up as a status note carrying the blocking issue codes, not a creative
    ID -- callers can tell "channel was skipped" apart from "channel failed
    compliance" by reading the notes.
    """

    def __init__(
        self,
        context_agent: TopicContextAgent,
        asset_agent: AssetAgent,
        email_agent: EmailContentAgent,
        whatsapp_agent: WhatsAppContentAgent,
        brochure_agent: BrochureContentAgent,
        compliance_agent: ComplianceAgent,
        library_agent: ContentLibraryAgent,
        hero_image_agent: HeroImageAgent,
        trainer_name: str = "",
        trainer_contact: str = "",
    ):
        self._context_agent = context_agent
        self._asset_agent = asset_agent
        self._email_agent = email_agent
        self._whatsapp_agent = whatsapp_agent
        self._brochure_agent = brochure_agent
        self._compliance_agent = compliance_agent
        self._library_agent = library_agent
        self._hero_image_agent = hero_image_agent
        self._trainer_name = trainer_name
        self._trainer_contact = trainer_contact
        self._graph = self._build_graph()

    def run(self, request: CampaignRequest) -> OrchestratorResult:
        # request.channels being non-empty is already enforced by
        # CampaignRequest's own validator at parse time.
        initial_state: OrchestratorState = {
            "request": request,
            "topic": None,
            "candidate_assets": [],
            "email_draft": None,
            "whatsapp_draft": None,
            "brochure_draft": None,
            "email_approved": None,
            "whatsapp_approved": None,
            "brochure_approved": None,
            "creative_ids": {},
            "status_notes": [],
        }
        final_state = self._graph.invoke(initial_state)
        return {"creative_ids": final_state["creative_ids"], "status_notes": final_state["status_notes"]}

    def generate_drafts(self, request: CampaignRequest) -> Dict[str, DraftReview]:
        """Generates and compliance-checks drafts for every requested
        channel but does NOT save anything -- this is the "review before
        you save" step. Saving is a separate, explicit call
        (ContentLibraryAgent.save), so nothing lands in the library until
        the caller says so.
        """
        topic = self._context_agent.get_context(topic_id=request.topic_id)

        result: Dict[str, DraftReview] = {}
        if request.email_brief is not None:
            hero_asset, item_assets = self._resolve_email_images(
                request.topic_id, topic, request.campaign_brief, request.email_brief
            )
            draft = self._email_agent.generate(
                campaign_brief=request.campaign_brief,
                email_brief=request.email_brief,
                topic=topic,
                hero_asset=hero_asset,
                item_assets=item_assets,
            )
            result["email"] = self._review(draft, Channel.EMAIL, topic)
        if request.whatsapp_brief is not None:
            draft = self._whatsapp_agent.generate(
                campaign_brief=request.campaign_brief,
                whatsapp_brief=request.whatsapp_brief,
                topic=topic,
                candidate_assets=self._whatsapp_candidate_assets(
                    request.topic_id, request.campaign_brief, request.whatsapp_brief
                ),
            )
            result["whatsapp"] = self._review(draft, Channel.WHATSAPP, topic)
        if request.brochure_brief is not None:
            draft = self._brochure_agent.generate(
                campaign_brief=request.campaign_brief,
                topic=topic,
                layout=request.brochure_brief.layout,
                candidate_assets=self._brochure_candidate_assets(
                    request.topic_id, request.campaign_brief, request.brochure_brief
                ),
            )
            result["brochure"] = self._review(draft, Channel.BROCHURE, topic)
        return result

    def _email_candidate_assets(self, topic_id: str, campaign_brief: CampaignBrief, email_brief: EmailBrief):
        # A user-picked image list takes priority over tag-matching -- fetch
        # exactly those assets, in the order picked, so the agent can't
        # substitute a different one. Falls back to the usual semantic
        # search when nothing was explicitly picked. Limit matches however
        # many image slots the chosen layout actually has (see
        # EMAIL_LAYOUT_SPECS) -- Welcome Grid needs more candidates than
        # Minimal Announcement does.
        if email_brief.selected_asset_ids:
            return self._asset_agent.get_by_ids(topic_id, email_brief.selected_asset_ids)
        limit = EMAIL_LAYOUT_SPECS[email_brief.layout].max_images
        return self._asset_agent.search(
            AssetQuery(topic_id=topic_id, semantic_query=campaign_brief.key_message, limit=limit)
        )

    def _resolve_email_images(
        self, topic_id: str, topic: Topic, campaign_brief: CampaignBrief, email_brief: EmailBrief
    ) -> tuple[Optional[Asset], List[Asset]]:
        spec = EMAIL_LAYOUT_SPECS[email_brief.layout]
        if email_brief.imagery != EmailImagery.USE_ASSET_BANK:
            return None, []
        candidates = self._email_candidate_assets(topic_id, campaign_brief, email_brief)
        if not spec.hero_required:
            # Minimal Announcement has no hero slot at all -- every
            # candidate is an equal-weight item image instead.
            return None, candidates[: spec.item_count]
        if email_brief.hero_image_source == HeroImageSource.AI_GENERATED:
            # A paid image-gen call is opt-in (see HeroImageSource) -- real
            # workshop photos are candid phone shots, not polished enough to
            # be the email's large lead visual, so when the user does ask
            # for AI generation the hero is a fresh illustration, never one
            # of the real candidate_assets, which stay available for items.
            hero = self._generate_hero_asset(topic_id, topic, campaign_brief)
            return hero, candidates[: spec.item_count]
        # SELECTED_PHOTO (the default, no image-gen call): the first
        # candidate -- whatever the user picked, or the top auto-search
        # result -- is the hero directly. This is also how a *previously*
        # AI-generated image gets reused for free instead of regenerated.
        if not candidates:
            return None, []
        return candidates[0], candidates[1 : 1 + spec.item_count]

    def _generate_hero_asset(self, topic_id: str, topic: Topic, campaign_brief: CampaignBrief) -> Optional[Asset]:
        try:
            image_bytes = self._hero_image_agent.generate(topic=topic, campaign_brief=campaign_brief)
        except ImageGenerationLimitExceeded:
            # The user explicitly asked for AI generation -- hitting the
            # daily cap should be a clear, visible failure they can act on
            # (try tomorrow, or pick an existing photo), not a silent
            # fallback to a heroless email.
            raise
        except Exception:
            # Any other failure is a call to an external paid API that can
            # fail for reasons outside anyone's control (network, content
            # policy) -- degrade gracefully to an email without a hero image
            # rather than failing the whole generate/revise request over a
            # decorative visual.
            return None
        return self._asset_agent.save_generated(topic_id, image_bytes, tags=[AI_GENERATED_HERO_TAG])

    def _whatsapp_candidate_assets(self, topic_id: str, campaign_brief: CampaignBrief, whatsapp_brief: WhatsAppBrief):
        # Same override-over-search idea as _email_candidate_assets, just for
        # a single asset_id instead of a list.
        if whatsapp_brief.selected_asset_id:
            return self._asset_agent.get_by_ids(topic_id, [whatsapp_brief.selected_asset_id])
        return self._asset_agent.search(
            AssetQuery(topic_id=topic_id, semantic_query=campaign_brief.key_message, limit=5)
        )

    def _brochure_candidate_assets(self, topic_id: str, campaign_brief: CampaignBrief, brochure_brief: BrochureBrief):
        # Same override-over-search idea as _email_candidate_assets -- a
        # user-picked photo list (first = hero, rest = gallery) takes
        # priority over tag-matching. Falls back to a slightly higher search
        # limit than email/WhatsApp since a brochure can use several photos
        # across sections.
        if brochure_brief.selected_asset_ids:
            return self._asset_agent.get_by_ids(topic_id, brochure_brief.selected_asset_ids)
        return self._asset_agent.search(
            AssetQuery(topic_id=topic_id, semantic_query=campaign_brief.key_message, limit=6)
        )

    def revise_email(
        self,
        *,
        topic_id: str,
        campaign_brief: CampaignBrief,
        email_brief: EmailBrief,
        current_draft: EmailDraft,
        instruction: str,
    ) -> DraftReview:
        topic = self._context_agent.get_context(topic_id=topic_id)
        spec = EMAIL_LAYOUT_SPECS[email_brief.layout]
        # Reuse exactly the same images across a revision rather than paying
        # for a fresh generation (or re-resolving/re-searching) on every
        # small copy tweak -- current_draft.referenced_asset_ids (assembled
        # by EmailContentAgent as [hero?, *items]) is the source of truth
        # for which ones those were, regardless of how they were originally
        # chosen.
        referenced = (
            self._asset_agent.get_by_ids(topic_id, current_draft.referenced_asset_ids)
            if current_draft.referenced_asset_ids
            else []
        )
        if spec.hero_required:
            hero_asset = referenced[0] if referenced else None
            item_assets = referenced[1 : 1 + spec.item_count]
        else:
            hero_asset = None
            item_assets = referenced[: spec.item_count]
        draft = self._email_agent.revise(
            campaign_brief=campaign_brief,
            email_brief=email_brief,
            topic=topic,
            current_draft=current_draft,
            instruction=instruction,
            hero_asset=hero_asset,
            item_assets=item_assets,
        )
        return self._review(draft, Channel.EMAIL, topic)

    def generate_more_subject_lines(
        self, *, topic_id: str, campaign_brief: CampaignBrief, existing_subject_lines: List[str]
    ) -> List[str]:
        topic = self._context_agent.get_context(topic_id=topic_id)
        return self._email_agent.generate_more_subject_lines(
            campaign_brief=campaign_brief, topic=topic, existing_subject_lines=existing_subject_lines
        )

    def revise_whatsapp(
        self,
        *,
        topic_id: str,
        campaign_brief: CampaignBrief,
        whatsapp_brief: WhatsAppBrief,
        current_draft: WhatsAppDraft,
        instruction: str,
    ) -> DraftReview:
        topic = self._context_agent.get_context(topic_id=topic_id)
        candidate_assets = self._whatsapp_candidate_assets(topic_id, campaign_brief, whatsapp_brief)
        draft = self._whatsapp_agent.revise(
            campaign_brief=campaign_brief,
            whatsapp_brief=whatsapp_brief,
            topic=topic,
            current_draft=current_draft,
            instruction=instruction,
            candidate_assets=candidate_assets,
        )
        return self._review(draft, Channel.WHATSAPP, topic)

    def revise_brochure(
        self,
        *,
        topic_id: str,
        campaign_brief: CampaignBrief,
        brochure_brief: BrochureBrief,
        current_draft: BrochureDraft,
        instruction: str,
    ) -> DraftReview:
        topic = self._context_agent.get_context(topic_id=topic_id)
        candidate_assets = self._brochure_candidate_assets(topic_id, campaign_brief, brochure_brief)
        draft = self._brochure_agent.revise(
            campaign_brief=campaign_brief,
            topic=topic,
            current_draft=current_draft,
            instruction=instruction,
            layout=brochure_brief.layout,
            candidate_assets=candidate_assets,
        )
        return self._review(draft, Channel.BROCHURE, topic)

    def _review(self, draft, channel: Channel, topic: Topic) -> DraftReview:
        result = self._compliance_agent.review(
            draft=draft,
            channel=channel,
            topic=topic,
            trainer_name=self._trainer_name,
            trainer_contact=self._trainer_contact,
        )
        return {
            "draft": result.corrected_draft if result.corrected_draft is not None else draft,
            "approved": result.approved,
            "issues": result.issues,
        }

    def _build_graph(self):
        graph = StateGraph(OrchestratorState)

        graph.add_node("topic", self._run_topic)
        graph.add_node("assets", self._run_assets)
        graph.add_node("join", lambda state: {})
        graph.add_node("email_content", self._run_email_content)
        graph.add_node("email_compliance", self._run_email_compliance)
        graph.add_node("email_library", self._run_email_library)
        graph.add_node("whatsapp_content", self._run_whatsapp_content)
        graph.add_node("whatsapp_compliance", self._run_whatsapp_compliance)
        graph.add_node("whatsapp_library", self._run_whatsapp_library)
        graph.add_node("brochure_content", self._run_brochure_content)
        graph.add_node("brochure_compliance", self._run_brochure_compliance)
        graph.add_node("brochure_library", self._run_brochure_library)

        graph.add_edge(START, "topic")
        graph.add_edge(START, "assets")
        graph.add_edge("topic", "join")
        graph.add_edge("assets", "join")

        graph.add_conditional_edges(
            "join", self._route_channels, ["email_content", "whatsapp_content", "brochure_content"]
        )

        graph.add_edge("email_content", "email_compliance")
        graph.add_edge("email_compliance", "email_library")
        graph.add_edge("email_library", END)

        graph.add_edge("whatsapp_content", "whatsapp_compliance")
        graph.add_edge("whatsapp_compliance", "whatsapp_library")
        graph.add_edge("whatsapp_library", END)

        graph.add_edge("brochure_content", "brochure_compliance")
        graph.add_edge("brochure_compliance", "brochure_library")
        graph.add_edge("brochure_library", END)

        return graph.compile()

    @staticmethod
    def _route_channels(state: OrchestratorState) -> List[str]:
        request = state["request"]
        next_nodes = []
        if request.email_brief is not None:
            next_nodes.append("email_content")
        if request.whatsapp_brief is not None:
            next_nodes.append("whatsapp_content")
        if request.brochure_brief is not None:
            next_nodes.append("brochure_content")
        return next_nodes

    def _run_topic(self, state: OrchestratorState) -> dict:
        request = state["request"]
        topic = self._context_agent.get_context(topic_id=request.topic_id)
        return {"topic": topic}

    def _run_assets(self, state: OrchestratorState) -> dict:
        request = state["request"]
        assets = self._asset_agent.search(
            AssetQuery(topic_id=request.topic_id, semantic_query=request.campaign_brief.key_message, limit=6)
        )
        return {"candidate_assets": assets}

    def _run_email_content(self, state: OrchestratorState) -> dict:
        request = state["request"]
        topic = state["topic"]
        hero_asset, item_assets = self._resolve_email_images(
            request.topic_id, topic, request.campaign_brief, request.email_brief
        )
        draft = self._email_agent.generate(
            campaign_brief=request.campaign_brief,
            email_brief=request.email_brief,
            topic=topic,
            hero_asset=hero_asset,
            item_assets=item_assets,
        )
        return {"email_draft": draft}

    def _run_email_compliance(self, state: OrchestratorState) -> dict:
        result = self._compliance_agent.review(
            draft=state["email_draft"], channel=Channel.EMAIL, topic=state["topic"]
        )
        update: dict = {"status_notes": [self._format_note("email", result)], "email_approved": result.approved}
        if result.corrected_draft is not None:
            update["email_draft"] = result.corrected_draft
        return update

    def _run_email_library(self, state: OrchestratorState) -> dict:
        if not state["email_approved"]:
            return {}
        request, draft = state["request"], state["email_draft"]
        creative_id = self._library_agent.save(
            topic_id=request.topic_id,
            campaign_id=request.campaign_id,
            channel=Channel.EMAIL,
            variant_label="primary",
            content=draft,
            asset_ids=draft.referenced_asset_ids,
        )
        return {"creative_ids": {"email": creative_id}, "status_notes": [f"email: saved as {creative_id}"]}

    def _run_whatsapp_content(self, state: OrchestratorState) -> dict:
        request = state["request"]
        draft = self._whatsapp_agent.generate(
            campaign_brief=request.campaign_brief,
            whatsapp_brief=request.whatsapp_brief,
            topic=state["topic"],
            candidate_assets=state["candidate_assets"],
        )
        return {"whatsapp_draft": draft}

    def _run_whatsapp_compliance(self, state: OrchestratorState) -> dict:
        result = self._compliance_agent.review(
            draft=state["whatsapp_draft"], channel=Channel.WHATSAPP, topic=state["topic"]
        )
        update: dict = {
            "status_notes": [self._format_note("whatsapp", result)],
            "whatsapp_approved": result.approved,
        }
        if result.corrected_draft is not None:
            update["whatsapp_draft"] = result.corrected_draft
        return update

    def _run_whatsapp_library(self, state: OrchestratorState) -> dict:
        if not state["whatsapp_approved"]:
            return {}
        request, draft = state["request"], state["whatsapp_draft"]
        asset_ids = [draft.image_asset_id] if draft.image_asset_id else []
        creative_id = self._library_agent.save(
            topic_id=request.topic_id,
            campaign_id=request.campaign_id,
            channel=Channel.WHATSAPP,
            variant_label="primary",
            content=draft,
            asset_ids=asset_ids,
        )
        return {"creative_ids": {"whatsapp": creative_id}, "status_notes": [f"whatsapp: saved as {creative_id}"]}

    def _run_brochure_content(self, state: OrchestratorState) -> dict:
        request = state["request"]
        draft = self._brochure_agent.generate(
            campaign_brief=request.campaign_brief,
            topic=state["topic"],
            layout=request.brochure_brief.layout,
            candidate_assets=state["candidate_assets"],
        )
        return {"brochure_draft": draft}

    def _run_brochure_compliance(self, state: OrchestratorState) -> dict:
        result = self._compliance_agent.review(
            draft=state["brochure_draft"],
            channel=Channel.BROCHURE,
            topic=state["topic"],
            trainer_name=self._trainer_name,
            trainer_contact=self._trainer_contact,
        )
        update: dict = {
            "status_notes": [self._format_note("brochure", result)],
            "brochure_approved": result.approved,
        }
        if result.corrected_draft is not None:
            update["brochure_draft"] = result.corrected_draft
        return update

    def _run_brochure_library(self, state: OrchestratorState) -> dict:
        if not state["brochure_approved"]:
            return {}
        request, draft = state["request"], state["brochure_draft"]
        creative_id = self._library_agent.save(
            topic_id=request.topic_id,
            campaign_id=request.campaign_id,
            channel=Channel.BROCHURE,
            variant_label="primary",
            content=draft,
            asset_ids=draft.referenced_asset_ids,
        )
        return {"creative_ids": {"brochure": creative_id}, "status_notes": [f"brochure: saved as {creative_id}"]}

    @staticmethod
    def _format_note(channel: str, result) -> str:
        note = f"{channel}: {'approved' if result.approved else 'REJECTED'}"
        if result.issues:
            note += " - " + "; ".join(f"{i.severity.value}:{i.code}" for i in result.issues)
        return note
