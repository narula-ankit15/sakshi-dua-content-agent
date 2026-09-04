from app.models import BrochureContent, TopicModule
from app.rendering.brochure_renderer import PAGE_HEIGHT, PAGE_WIDTH, BrochureRenderer, _shorten_methodology


def _content(sample_topic, modules=None):
    return BrochureContent(
        hero_title=sample_topic.topic_name,
        hero_tagline=sample_topic.tagline,
        hero_description=sample_topic.hook_description,
        hook_lines=["Teams lose deals from how ideas get said, not the ideas themselves."],
        modules=modules if modules is not None else sample_topic.modules,
        methodology=sample_topic.methodology,
        outcomes=sample_topic.outcomes,
        closing_line=sample_topic.closing_line,
        positioning_tags=sample_topic.positioning_tags,
    )


def test_render_produces_pdf_and_png_and_embeds_trainer_identity(sample_topic):
    renderer = BrochureRenderer(trainer_name="Sakshi Dua", trainer_contact="sakshi@example.com")

    result = renderer.render(_content(sample_topic))

    assert result["pdf_bytes"].startswith(b"%PDF")
    assert result["png_bytes"].startswith(b"\x89PNG")
    assert "Sakshi Dua" in result["html"]
    assert "sakshi@example.com" in result["html"]


def test_render_embeds_local_asset_bank_photo_as_data_uri_not_http_url(tmp_path, sample_topic):
    # The API and this renderer run in the same process -- an <img src>
    # pointing back at this app's own public URL would make Chromium fetch
    # over the real network back to itself. Real bug hit in production:
    # that self-referential fetch was slow (a cold machine wake-up) and
    # risks self-blocking a single-machine deploy that's already busy
    # handling the request doing the rendering. Local asset-bank files must
    # be embedded directly instead.
    topic_dir = tmp_path / "comm-impact" / "photos"
    topic_dir.mkdir(parents=True)
    photo_path = topic_dir / "comm-impact-photo-01.png"
    # Minimal valid 1x1 PNG.
    photo_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
            "3df40000000a4944415478da6360000002000155bd8a2b0000000049454e44ae426082"
        )
    )
    renderer = BrochureRenderer(trainer_name="Sakshi Dua", asset_bank_path=str(tmp_path))
    hero_url = "http://127.0.0.1:8123/asset-files/comm-impact/photos/comm-impact-photo-01.png"

    result = renderer.render(_content(sample_topic), hero_photo_url=hero_url)

    assert hero_url not in result["html"]
    assert "data:image/png;base64," in result["html"]


def test_render_falls_back_to_the_given_url_when_no_local_file_matches(sample_topic):
    # No asset_bank_path configured (or the file just isn't found locally)
    # -- e.g. a genuinely external image URL -- must still render using the
    # URL as-is rather than erroring or silently dropping the image.
    renderer = BrochureRenderer(trainer_name="Sakshi Dua")
    hero_url = "https://example.com/some-photo.jpg"

    result = renderer.render(_content(sample_topic), hero_photo_url=hero_url)

    assert hero_url in result["html"]


def test_render_reasonable_content_fits_one_page(sample_topic):
    renderer = BrochureRenderer(trainer_name="Sakshi Dua")

    result = renderer.render(_content(sample_topic))

    assert result["overflowed"] is False


def test_render_flags_overflow_for_excessive_content(sample_topic):
    # Modules/bullets/methodology/outcomes/positioning_tags are all capped at
    # the template level (see brochure_*.html), so no amount of raw list data
    # alone can force overflow anymore -- that's the point. Stress the fields
    # that render at whatever length they're given instead: hero copy,
    # hook_lines, closing_line have no cap on text length.
    renderer = BrochureRenderer(trainer_name="Sakshi Dua")
    content = _content(sample_topic)
    content.hero_description = "Test description " * 20
    content.hook_lines = ["Long hook line " * 30 for _ in range(6)]
    content.closing_line = "Closing " * 60
    content.positioning_tags = [f"Tag number {i} is fairly long" for i in range(1, 30)]

    result = renderer.render(content)

    assert result["overflowed"] is True


def test_page_dimensions_are_fixed_a4_pixel_size():
    assert PAGE_WIDTH == 794
    assert PAGE_HEIGHT == 1123


def test_shorten_methodology_drops_trailing_parenthetical():
    text = "Interactive case studies (e.g., Difference in working styles, Communication styles)"
    assert _shorten_methodology(text) == "Interactive case studies"


def test_shorten_methodology_leaves_short_text_untouched():
    assert _shorten_methodology("Role Plays") == "Role Plays"


def test_shorten_methodology_hard_caps_long_text_with_no_parenthetical():
    text = "A" * 60
    result = _shorten_methodology(text, max_chars=44)
    assert len(result) == 44
    assert result.endswith("…")


def test_render_caps_modules_bullets_and_methodology_shown(sample_topic):
    renderer = BrochureRenderer(trainer_name="Sakshi Dua")
    content = _content(
        sample_topic,
        modules=[
            TopicModule(module_number=i, title=f"Module {i}", bullets=[f"bullet {j}" for j in range(6)])
            for i in range(1, 7)
        ],
    )
    content.methodology = [f"Method {i}" for i in range(1, 10)]

    result = renderer.render(content)

    # 4 of 6 modules, 3 of 6 bullets each, 5 of 9 methodology chips.
    assert result["html"].count('class="module-card"') == 4
    assert result["html"].count("bullet 0") == 4  # one per rendered module
    assert result["html"].count("bullet 3") == 0  # 4th bullet, past the cap
    assert "Method 5" in result["html"]
    assert "Method 6" not in result["html"]
