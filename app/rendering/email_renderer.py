from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import EmailContent, EmailLayout

# One template file per layout -- unlike BrochureRenderer, no PDF/PNG export
# and no data-URI localization: this just renders an HTML string, and real
# email clients need to fetch images from a real hosted URL anyway (a
# data: URI would bloat the message and many clients strip it outright).
_LAYOUT_TEMPLATES = {
    EmailLayout.HERO_THREE_COLUMN: "email_hero_three_column.html",
    EmailLayout.EVENT: "email_event.html",
    EmailLayout.MINIMAL_ANNOUNCEMENT: "email_minimal_announcement.html",
    EmailLayout.WELCOME_GRID: "email_welcome_grid.html",
    EmailLayout.WORKSHOP_HIGHLIGHTS: "email_workshop_highlights.html",
}

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=select_autoescape(["html"]))

PAGE_WIDTH = 600


class EmailRenderer:
    """Renders one of the five fixed EmailLayout templates
    (app/rendering/templates/email_*.html) to an HTML string. Deterministic,
    not an LLM agent -- always run after EmailContentAgent produces the copy,
    the same division of labor BrochureRenderer already uses.
    """

    def __init__(self, trainer_name: str, trainer_contact: str = "", logo_url: str = ""):
        self._trainer_name = trainer_name
        self._trainer_contact = trainer_contact
        # Real trainer branding (the "Sakshi Dua" wordmark), not a topic
        # photo -- code-controlled like trainer_name/contact, so the LLM
        # never has a say in whether/how it appears. Empty means "not
        # configured," and every template falls back to the plain text name
        # exactly like it did before this existed.
        self._logo_url = logo_url

    def render(
        self,
        content: EmailContent,
        layout: EmailLayout,
        cta_text: str,
        positioning_tags: Optional[list[str]] = None,
        hero_photo_url: Optional[str] = None,
        item_photo_urls: Optional[list[str]] = None,
    ) -> str:
        item_photo_urls = item_photo_urls or []
        # Pair each item's copy with its resolved photo URL (None if fewer
        # photos were supplied than items -- the template renders a plain
        # tinted placeholder block in that case rather than a broken <img>).
        items = [
            {"content": item, "photo_url": item_photo_urls[i] if i < len(item_photo_urls) else None}
            for i, item in enumerate(content.items)
        ]
        template = _env.get_template(_LAYOUT_TEMPLATES[layout])
        return template.render(
            content=content,
            items=items,
            # Raw (unpaired-with-caption) URLs too -- WORKSHOP_HIGHLIGHTS uses
            # these directly as a bare photo gallery, since that layout's
            # items aren't captioned cells the way the other four are.
            item_photo_urls=item_photo_urls,
            hero_photo_url=hero_photo_url,
            cta_text=cta_text,
            positioning_tags=positioning_tags or [],
            trainer_name=self._trainer_name,
            trainer_contact=self._trainer_contact,
            logo_url=self._logo_url,
            page_width=PAGE_WIDTH,
        )
