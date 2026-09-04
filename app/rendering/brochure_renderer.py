import base64
import mimetypes
import re
from pathlib import Path
from typing import Optional, TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import BrochureContent, BrochureLayout

# A4 @ 96dpi -- fixed so every topic's brochure renders to the exact same
# page size; PDF export uses this as an explicit pixel size (not "format:
# A4") so it matches the PNG screenshot pixel-for-pixel.
PAGE_WIDTH = 794
PAGE_HEIGHT = 1123

# One template file per layout -- all four accept the exact same Jinja
# variables and follow the same content-capping conventions (see each
# template's own comments), so BrochureContentAgent's output works
# unmodified against any of them; only the visual treatment differs.
_LAYOUT_TEMPLATES = {
    BrochureLayout.MODERN_GRADIENT: "brochure_modern_gradient.html",
    BrochureLayout.CLEAN_MINIMAL: "brochure_clean_minimal.html",
    BrochureLayout.BOLD_GEOMETRIC: "brochure_bold_geometric.html",
    BrochureLayout.CLASSIC_SIDEBAR: "brochure_classic_sidebar.html",
}

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=select_autoescape(["html"]))


def _shorten_methodology(text: str, max_chars: int = 44) -> str:
    # Real source docs often write methodology as a full descriptive
    # sentence with a parenthetical example list ("Interactive case studies
    # (e.g., Difference in working styles, ...)") -- fine for a fuller
    # channel, but this brochure renders methodology as a compact pill chip,
    # not a sentence. Drop the trailing parenthetical (the module bullets
    # already carry that level of detail) and hard-cap what's left, since a
    # fixed one-page layout can't grow to fit an arbitrarily long label.
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


_env.filters["shorten_methodology"] = _shorten_methodology


class BrochureRenderResult(TypedDict):
    html: str
    pdf_bytes: bytes
    png_bytes: bytes
    overflowed: bool


class BrochureRenderer:
    """Renders one of four styled-once brochure templates (app/rendering/
    templates/brochure_*.html, picked by BrochureLayout) to HTML, then to
    PDF + PNG via headless Chromium (Playwright) -- one rendered DOM, two
    export formats, so the PDF and PNG are always pixel-identical to each
    other. Not an LLM agent: this is a deterministic rendering step, always
    run after BrochureContentAgent produces the copy.
    """

    def __init__(self, trainer_name: str, trainer_contact: str = "", asset_bank_path: str = ""):
        self._trainer_name = trainer_name
        self._trainer_contact = trainer_contact
        self._asset_bank_path = asset_bank_path

    def render(
        self,
        content: BrochureContent,
        layout: BrochureLayout = BrochureLayout.MODERN_GRADIENT,
        hero_photo_url: Optional[str] = None,
        gallery_photo_urls: Optional[list[str]] = None,
    ) -> BrochureRenderResult:
        # Embed local asset-bank photos as data URIs instead of letting
        # Chromium fetch them over HTTP -- the API and this renderer run in
        # the same container/process, so an <img src> pointing at this
        # app's own public URL would otherwise make Chromium round-trip out
        # through the public internet back to itself. Real bug hit in
        # production: that self-referential fetch was slow (a cold Fly
        # machine wake-up) and risks self-blocking a single-machine deploy
        # that's already busy handling the very request doing the
        # rendering. Falls back to the given URL untouched for anything
        # that isn't a locally-resolvable asset-bank file.
        hero_photo_url = self._localize(hero_photo_url)
        gallery_photo_urls = [self._localize(u) for u in (gallery_photo_urls or [])]
        html = self._render_html(content, layout, hero_photo_url, gallery_photo_urls)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": PAGE_WIDTH, "height": PAGE_HEIGHT})
                page.set_content(html, wait_until="load")
                scroll_height = page.evaluate("document.body.scrollHeight")
                # Small tolerance for sub-pixel rounding -- a 1-2px overage
                # from font metrics shouldn't count as real overflow.
                overflowed = scroll_height > PAGE_HEIGHT + 2
                pdf_bytes = page.pdf(width=f"{PAGE_WIDTH}px", height=f"{PAGE_HEIGHT}px", print_background=True)
                png_bytes = page.screenshot(clip={"x": 0, "y": 0, "width": PAGE_WIDTH, "height": PAGE_HEIGHT})
            finally:
                browser.close()

        return {"html": html, "pdf_bytes": pdf_bytes, "png_bytes": png_bytes, "overflowed": overflowed}

    def _localize(self, url: Optional[str]) -> Optional[str]:
        if not url or not self._asset_bank_path or "/asset-files/" not in url:
            return url
        # "/asset-files/" is mounted directly onto asset_bank_path (see
        # app/api/main.py), so the path after that marker is exactly the
        # relative path on disk.
        rel_path = url.split("/asset-files/", 1)[1]
        local_path = Path(self._asset_bank_path) / rel_path
        if not local_path.is_file():
            return url
        mime = mimetypes.guess_type(local_path.name)[0] or "image/jpeg"
        data = base64.b64encode(local_path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"

    def _render_html(
        self,
        content: BrochureContent,
        layout: BrochureLayout,
        hero_photo_url: Optional[str],
        gallery_photo_urls: list[str],
    ) -> str:
        template = _env.get_template(_LAYOUT_TEMPLATES[layout])
        return template.render(
            content=content,
            hero_photo_url=hero_photo_url,
            gallery_photo_urls=gallery_photo_urls,
            trainer_name=self._trainer_name,
            trainer_contact=self._trainer_contact,
            page_width=PAGE_WIDTH,
            page_height=PAGE_HEIGHT,
        )
