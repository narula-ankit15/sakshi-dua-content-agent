import re
from html.parser import HTMLParser
from typing import Union

from app.models import BrochureDraft, ComplianceIssue, ComplianceResult, EmailDraft, IssueSeverity, Topic, WhatsAppDraft
from app.models.brief import Channel

# Absolute/unverifiable outcome language -- generic in the same way the
# real-estate version's "guaranteed/assured returns" pattern was, just
# rescoped from investment returns to training outcomes. "guarantees?" (not
# just "guarantee") so the plural form still matches -- \b requires a
# word/non-word boundary, which "guaranteeS" doesn't have after "guarantee".
UNVERIFIABLE_CLAIM_PATTERN = re.compile(
    r"\b(guarantees?|guaranteed|100%\s*(?:results?|success)|will definitely|assured results?)\b", re.IGNORECASE
)
TOKEN_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
KNOWN_PERSONALIZATION_TOKENS = {"first_name", "topic_name"}
WHATSAPP_CHAR_LIMIT = 320
VOID_TAGS = {"br", "img", "hr", "input", "meta", "link"}


class _TagBalanceChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        # Self-closed form (<tag/>) is inherently balanced -- HTMLParser's
        # default implementation calls handle_starttag + handle_endtag for
        # this, which would wrongly flag e.g. <br/> as an unmatched close.
        pass

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected closing tag </{tag}>")
        else:
            self.stack.pop()


def _extract_text(draft: Union[EmailDraft, WhatsAppDraft, BrochureDraft]) -> str:
    if isinstance(draft, EmailDraft):
        return " ".join(draft.subject_lines) + " " + draft.html_body
    if isinstance(draft, WhatsAppDraft):
        return " ".join(draft.message_variants) + " " + " ".join(draft.cta_variants or [])
    # BrochureDraft -- only the LLM-generated prose is worth scanning here;
    # modules/methodology/outcomes/positioning_tags are copied verbatim from
    # Topic and were never LLM-touched, so there's nothing to flag in them.
    c = draft.content
    return " ".join([c.hero_title, c.hero_tagline, c.hero_description, *c.hook_lines, c.closing_line])


class ComplianceAgent:
    """Takes the same Topic the content agents were given, not just the
    draft -- "flag unverifiable claims" only means something if there's a
    ground truth (Topic.outcomes) to check against.
    """

    def review(
        self,
        *,
        draft: Union[EmailDraft, WhatsAppDraft, BrochureDraft],
        channel: Channel,
        topic: Topic,
        trainer_name: str = "",
        trainer_contact: str = "",
    ) -> ComplianceResult:
        working_draft = draft.model_copy(deep=True)
        issues: list[ComplianceIssue] = []

        text = _extract_text(working_draft)
        issues += self._check_unverifiable_outcome_claims(text, topic)
        issues += self._check_personalization_tokens(text)

        if channel == Channel.EMAIL:
            issues += self._check_html(working_draft)
        elif channel == Channel.WHATSAPP:
            issues += self._check_char_limit(working_draft)
        else:
            issues += self._check_brand_consistency(working_draft, trainer_name, trainer_contact)
            issues += self._check_brochure_overflow(working_draft)

        blocking = [i for i in issues if i.severity == IssueSeverity.BLOCKING]
        return ComplianceResult(
            approved=len(blocking) == 0,
            issues=issues,
            corrected_draft=working_draft if working_draft != draft else None,
        )

    def _check_unverifiable_outcome_claims(self, text: str, topic: Topic):
        matches = UNVERIFIABLE_CLAIM_PATTERN.findall(text)
        if not matches:
            return []
        # Absolute/guarantee-style language is only defensible if the
        # topic's own outcomes make an equally strong claim -- otherwise the
        # content agent is overselling beyond what the Topic record supports.
        outcomes_text = " ".join(topic.outcomes).lower()
        if all(m.lower() in outcomes_text for m in matches):
            return []
        return [
            ComplianceIssue(
                code="unverifiable_outcome_claim",
                message=f"Content uses absolute/unverifiable outcome language not backed by TOPIC outcomes: {sorted(set(matches))}",
                severity=IssueSeverity.BLOCKING,
            )
        ]

    def _check_personalization_tokens(self, text: str):
        issues = []
        for match in TOKEN_PATTERN.finditer(text):
            token = match.group(1)
            if token not in KNOWN_PERSONALIZATION_TOKENS:
                issues.append(
                    ComplianceIssue(
                        code="unresolved_personalization_token",
                        message=f"Unknown personalization token: {{{{{token}}}}}",
                        severity=IssueSeverity.BLOCKING,
                    )
                )
        return issues

    def _check_html(self, draft: EmailDraft):
        checker = _TagBalanceChecker()
        checker.feed(draft.html_body)
        if checker.errors or checker.stack:
            detail = "; ".join(checker.errors + [f"unclosed <{t}>" for t in checker.stack])
            return [
                ComplianceIssue(
                    code="invalid_html", message=f"HTML is not well-formed: {detail}", severity=IssueSeverity.BLOCKING
                )
            ]
        return []

    def _check_char_limit(self, draft: WhatsAppDraft):
        issues = []
        for i, variant in enumerate(draft.message_variants):
            cta_text = draft.cta_variants[i] if draft.cta_variants and i < len(draft.cta_variants) else ""
            length = len(variant) + len(cta_text)
            if length > WHATSAPP_CHAR_LIMIT:
                issues.append(
                    ComplianceIssue(
                        code="char_limit_exceeded",
                        message=f"Variant {i + 1} + CTA is {length} chars, over the {WHATSAPP_CHAR_LIMIT} limit",
                        severity=IssueSeverity.BLOCKING,
                    )
                )
        return issues

    def _check_brand_consistency(self, draft: BrochureDraft, trainer_name: str, trainer_contact: str):
        issues = []
        if not trainer_name:
            issues.append(
                ComplianceIssue(
                    code="trainer_identity_not_configured",
                    message="Settings.trainer_name is not set -- the brochure footer has no trainer identity",
                    severity=IssueSeverity.WARNING,
                )
            )
        elif trainer_name not in draft.html:
            issues.append(
                ComplianceIssue(
                    code="missing_trainer_name",
                    message=f"Trainer name '{trainer_name}' not found in the rendered brochure",
                    severity=IssueSeverity.WARNING,
                )
            )
        if trainer_contact and trainer_contact not in draft.html:
            issues.append(
                ComplianceIssue(
                    code="missing_trainer_contact",
                    message=f"Trainer contact '{trainer_contact}' not found in the rendered brochure",
                    severity=IssueSeverity.WARNING,
                )
            )
        if not draft.content.positioning_tags:
            issues.append(
                ComplianceIssue(
                    code="missing_positioning_tags",
                    message="Brochure has no positioning tags",
                    severity=IssueSeverity.WARNING,
                )
            )
        return issues

    def _check_brochure_overflow(self, draft: BrochureDraft):
        if draft.overflowed:
            return [
                ComplianceIssue(
                    code="content_overflow",
                    message="Brochure content overflows the fixed one-page layout -- shorten the hero/hook/closing copy",
                    severity=IssueSeverity.BLOCKING,
                )
            ]
        return []
