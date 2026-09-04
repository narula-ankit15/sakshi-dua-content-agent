from app.agents.compliance_agent import ComplianceAgent
from app.models import BrochureContent, BrochureDraft, EmailDraft, TopicModule, WhatsAppDraft
from app.models.brief import Channel


def _brochure_draft(sample_topic, *, closing_line=None, overflowed=False, html_extra=""):
    content = BrochureContent(
        hero_title=sample_topic.topic_name,
        hero_tagline=sample_topic.tagline,
        hero_description=sample_topic.hook_description,
        hook_lines=["Teams lose deals from how ideas get said, not the ideas themselves."],
        modules=[TopicModule(**m.model_dump()) for m in sample_topic.modules],
        methodology=sample_topic.methodology,
        outcomes=sample_topic.outcomes,
        closing_line=closing_line or sample_topic.closing_line,
        positioning_tags=sample_topic.positioning_tags,
    )
    return BrochureDraft(
        content=content,
        html=f"<html>{html_extra}Sakshi Dua &middot; sakshi@example.com</html>",
        pdf_base64="",
        png_base64="",
        overflowed=overflowed,
    )


def test_unverifiable_outcome_claim_blocks_when_not_backed_by_topic_outcomes(sample_topic):
    draft = WhatsAppDraft(message_variants=["This workshop guarantees you a promotion!"], cta_variants=["Reserve"])
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.WHATSAPP, topic=sample_topic)

    assert result.approved is False
    assert any(i.code == "unverifiable_outcome_claim" for i in result.issues)


def test_unverifiable_outcome_claim_allowed_when_backed_by_topic_outcomes():
    from app.models import Topic

    topic = Topic(
        topic_id="t",
        topic_name="T",
        tagline="tag",
        hook_description="hook",
        outcomes=["You will definitely leave with a repeatable feedback script"],
        closing_line="closing",
    )
    draft = WhatsAppDraft(
        message_variants=["You will definitely leave with a repeatable feedback script."], cta_variants=["Reserve"]
    )
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.WHATSAPP, topic=topic)

    assert not any(i.code == "unverifiable_outcome_claim" for i in result.issues)


def test_unresolved_personalization_token_blocks_approval(sample_topic):
    draft = WhatsAppDraft(message_variants=["Hi {{unknown_token}}, join us!"], cta_variants=["Reserve"])
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.WHATSAPP, topic=sample_topic)

    assert result.approved is False
    assert any(i.code == "unresolved_personalization_token" for i in result.issues)


def test_invalid_html_blocks_approval(sample_topic):
    draft = EmailDraft(subject_lines=["Hi"], html_body="<p>Join us <strong>now</p>")
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.EMAIL, topic=sample_topic)

    assert result.approved is False
    assert any(i.code == "invalid_html" for i in result.issues)


def test_self_closed_br_tag_is_not_flagged_as_invalid_html(sample_topic):
    draft = EmailDraft(subject_lines=["Hi"], html_body="<p>Join us<br/>this weekend</p>")
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.EMAIL, topic=sample_topic)

    assert result.approved is True
    assert not any(i.code == "invalid_html" for i in result.issues)


def test_char_limit_exceeded_blocks_approval(sample_topic):
    draft = WhatsAppDraft(message_variants=["Join us! " * 50], cta_variants=["Reserve"])
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.WHATSAPP, topic=sample_topic)

    assert result.approved is False
    assert any(i.code == "char_limit_exceeded" for i in result.issues)


def test_char_limit_check_flags_only_the_offending_variant(sample_topic):
    draft = WhatsAppDraft(
        message_variants=["Join us!", "Join us! " * 50],
        cta_variants=["Reserve", "Reserve"],
    )
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.WHATSAPP, topic=sample_topic)

    assert result.approved is False
    issues = [i for i in result.issues if i.code == "char_limit_exceeded"]
    assert len(issues) == 1
    assert "Variant 2" in issues[0].message


def test_clean_draft_is_approved_with_no_issues(sample_topic):
    draft = WhatsAppDraft(message_variants=["Structure any message in under 60 seconds."], cta_variants=["Reserve"])
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.WHATSAPP, topic=sample_topic)

    assert result.approved is True
    assert result.issues == []
    assert result.corrected_draft is None


def test_brochure_missing_trainer_identity_is_a_warning_not_blocking(sample_topic):
    draft = _brochure_draft(sample_topic)
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.BROCHURE, topic=sample_topic, trainer_name="", trainer_contact="")

    assert result.approved is True
    assert any(i.code == "trainer_identity_not_configured" for i in result.issues)


def test_brochure_trainer_name_present_passes_brand_check(sample_topic):
    draft = _brochure_draft(sample_topic)
    agent = ComplianceAgent()

    result = agent.review(
        draft=draft, channel=Channel.BROCHURE, topic=sample_topic, trainer_name="Sakshi Dua", trainer_contact=""
    )

    assert not any(i.code == "missing_trainer_name" for i in result.issues)


def test_brochure_content_overflow_blocks_approval(sample_topic):
    draft = _brochure_draft(sample_topic, overflowed=True)
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.BROCHURE, topic=sample_topic, trainer_name="Sakshi Dua")

    assert result.approved is False
    assert any(i.code == "content_overflow" for i in result.issues)


def test_brochure_missing_positioning_tags_is_a_warning(sample_topic):
    draft = _brochure_draft(sample_topic)
    draft.content.positioning_tags = []
    agent = ComplianceAgent()

    result = agent.review(draft=draft, channel=Channel.BROCHURE, topic=sample_topic, trainer_name="Sakshi Dua")

    assert result.approved is True
    assert any(i.code == "missing_positioning_tags" for i in result.issues)
