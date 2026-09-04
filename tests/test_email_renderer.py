import pytest

from app.models import EmailContent, EmailContentItem, EmailLayout
from app.rendering.email_renderer import EmailRenderer


def _content(**overrides) -> EmailContent:
    base = dict(
        eyebrow="Workshop",
        headline="Communicate with Impact",
        intro_text="A hands-on session for your team.",
        bullet_line=None,
        items=[],
        closing_text="See you there.",
    )
    base.update(overrides)
    return EmailContent(**base)


def test_render_grounds_footer_in_real_trainer_identity_when_configured():
    renderer = EmailRenderer(trainer_name="Sakshi Dua", trainer_contact="sakshi@example.com")

    html = renderer.render(_content(), EmailLayout.WORKSHOP_HIGHLIGHTS, cta_text="Reserve Your Seat")

    assert "Sakshi Dua" in html
    assert "sakshi@example.com" in html


def test_render_omits_contact_line_when_trainer_contact_not_given():
    renderer = EmailRenderer(trainer_name="Sakshi Dua", trainer_contact="")

    html = renderer.render(_content(), EmailLayout.WORKSHOP_HIGHLIGHTS, cta_text="Reserve Your Seat")

    assert "Sakshi Dua" in html


def test_render_never_invents_trainer_identity_when_not_configured():
    renderer = EmailRenderer(trainer_name="", trainer_contact="")

    html = renderer.render(_content(), EmailLayout.WORKSHOP_HIGHLIGHTS, cta_text="Reserve Your Seat")

    # No fabricated company name/address -- this is purely code-driven now,
    # so there's nothing for an LLM to hallucinate here at all.
    assert "Delivered by" not in html


def test_render_uses_cta_text_verbatim_as_the_button_label():
    renderer = EmailRenderer(trainer_name="Sakshi Dua")

    html = renderer.render(_content(), EmailLayout.WORKSHOP_HIGHLIGHTS, cta_text="Book Your Spot Now")

    assert "Book Your Spot Now" in html


def test_render_caps_positioning_tags_at_five():
    renderer = EmailRenderer(trainer_name="Sakshi Dua")
    tags = [f"Tag{i}" for i in range(8)]

    html = renderer.render(_content(), EmailLayout.WORKSHOP_HIGHLIGHTS, cta_text="Go", positioning_tags=tags)

    for tag in tags[:5]:
        assert tag in html
    for tag in tags[5:]:
        assert tag not in html


@pytest.mark.parametrize("layout", list(EmailLayout))
def test_render_produces_a_full_html_document_for_every_layout(layout):
    renderer = EmailRenderer(trainer_name="Sakshi Dua", trainer_contact="sakshi@example.com")
    content = _content(
        items=[EmailContentItem(title=f"Item {i}", text="Some text", cta_text=None) for i in range(4)]
    )

    html = renderer.render(
        content,
        layout,
        cta_text="Reserve Your Seat",
        positioning_tags=["Experiential"],
        hero_photo_url="https://example.com/hero.jpg",
        item_photo_urls=[f"https://example.com/item{i}.jpg" for i in range(4)],
    )

    assert html.strip().lower().startswith("<!doctype")
    assert "Communicate with Impact" in html


@pytest.mark.parametrize("layout", list(EmailLayout))
def test_render_does_not_crash_with_no_images_and_no_optional_fields(layout):
    renderer = EmailRenderer(trainer_name="", trainer_contact="")
    content = EmailContent(headline="Minimal", intro_text="Just the basics.", closing_text="Bye.")

    html = renderer.render(content, layout, cta_text="Go")

    assert html.strip().lower().startswith("<!doctype")


def test_render_hero_three_column_places_hero_and_item_images():
    renderer = EmailRenderer(trainer_name="Sakshi Dua")
    content = _content(
        items=[
            EmailContentItem(title="One", text="a", cta_text="Learn more"),
            EmailContentItem(title="Two", text="b"),
            EmailContentItem(title="Three", text="c"),
        ]
    )

    html = renderer.render(
        content,
        EmailLayout.HERO_THREE_COLUMN,
        cta_text="Go",
        hero_photo_url="https://example.com/hero.jpg",
        item_photo_urls=["https://example.com/1.jpg", "https://example.com/2.jpg", "https://example.com/3.jpg"],
    )

    assert "https://example.com/hero.jpg" in html
    assert "https://example.com/1.jpg" in html
    assert "https://example.com/2.jpg" in html
    assert "https://example.com/3.jpg" in html
    assert "Learn more" in html


def test_render_workshop_highlights_shows_topic_modules_and_computed_stats():
    from app.models import TopicModule

    renderer = EmailRenderer(trainer_name="Sakshi Dua")
    content = _content(
        modules=[
            TopicModule(module_number=1, title="Structuring Your Message", bullets=["The framework"]),
            TopicModule(module_number=2, title="Reading the Room", bullets=["Spot disengagement"]),
        ],
        methodology=["Role Plays", "Live Feedback"],
        outcomes=["Outcome one"],
    )

    html = renderer.render(content, EmailLayout.WORKSHOP_HIGHLIGHTS, cta_text="Go")

    assert "Structuring Your Message" in html
    assert "Reading the Room" in html
    assert "Role Plays" in html
    # Stat strip counts are computed from the actual lists, not hardcoded
    assert ">2<" in html  # modules count
    assert ">1<" in html  # outcomes count


def test_render_uses_logo_image_instead_of_plain_text_name_when_configured():
    renderer = EmailRenderer(trainer_name="Sakshi Dua", trainer_contact="sakshi@example.com", logo_url="https://example.com/logo.png")

    html = renderer.render(_content(), EmailLayout.WORKSHOP_HIGHLIGHTS, cta_text="Reserve Your Seat")

    assert 'src="https://example.com/logo.png"' in html
    assert 'alt="Sakshi Dua"' in html


def test_render_falls_back_to_plain_text_name_when_logo_not_configured():
    renderer = EmailRenderer(trainer_name="Sakshi Dua", trainer_contact="sakshi@example.com")

    html = renderer.render(_content(), EmailLayout.WORKSHOP_HIGHLIGHTS, cta_text="Reserve Your Seat")

    assert "<img" not in html
    assert "Sakshi Dua" in html


@pytest.mark.parametrize("layout", list(EmailLayout))
def test_render_places_logo_image_somewhere_in_every_layout_when_configured(layout):
    renderer = EmailRenderer(trainer_name="Sakshi Dua", trainer_contact="sakshi@example.com", logo_url="https://example.com/logo.png")

    html = renderer.render(_content(), layout, cta_text="Go")

    assert 'src="https://example.com/logo.png"' in html


def test_render_minimal_announcement_has_no_hero_slot():
    renderer = EmailRenderer(trainer_name="Sakshi Dua")
    content = _content(items=[EmailContentItem(title="A", text="a"), EmailContentItem(title="B", text="b")])

    html = renderer.render(
        content,
        EmailLayout.MINIMAL_ANNOUNCEMENT,
        cta_text="Go",
        # Even if a hero_photo_url is accidentally passed, this layout has
        # no hero <img> slot to place it in.
        hero_photo_url="https://example.com/should-not-appear.jpg",
        item_photo_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
    )

    assert "should-not-appear.jpg" not in html
    assert "https://example.com/1.jpg" in html
    assert "https://example.com/2.jpg" in html
