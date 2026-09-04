# Workshop Content Agent

Multi-agent system that generates marketing content (email, WhatsApp, and a one-page PDF/PNG brochure) for a
solo corporate trainer's workshop topics, and saves it to a content library with a short template ID the trainer
can browse, revise, and send/download from.

Stack: FastAPI + LangGraph orchestrator, Gemini (generation only — no embeddings), SQLite (content library),
Jinja2 + Playwright/headless Chromium (brochure rendering).

This started as a real-estate MarTech content agent (RERA compliance, Pinecone brochure-RAG, `project_id`,
campaign-setup-CRM integration) and was transformed into a standalone tool for one trainer's own workshop
content. The domain-specific pieces below were rebuilt or rescoped; the general content-agent plumbing
(structured contracts, protocol-based LLM client, generate/revise/save split, compliance-before-save) carried
over unchanged. Where a design decision only makes sense in contrast to that history, the rationale below says so.

## Status

Rebuilt/retargeted in dependency order — models first, then the agents that read them, then the orchestrator
that wires the agents together, then the API/frontend that expose it:

- [x] 1. Shared Pydantic contracts (`app/models/`): `Topic`/`TopicModule` replace the old `ProjectFacts` +
  retrieved-chunk split; `CampaignRequest` gained a third optional `brochure_brief` alongside
  `email_brief`/`whatsapp_brief`; `ContentLibraryEntry` gained a `BR####` template-ID prefix for the new channel.
- [x] 2. `TopicStore` (`app/storage/topic_store.py`) + `TopicContextAgent` (`app/agents/topic_context_agent.py`):
  one JSON file per topic (`data/topics/{topic_id}/topic.json`), read directly — no embeddings, no vector store,
  no retrieval step at all.
- [x] 3. Topic ingestion CLI (`app/ingest/topic_ingest.py`), replacing the old `brochure_ingest.py` +
  `facts.json` + Pinecone indexing: one structured-extraction LLM call over a zip of {one source doc, past-run
  photos} produces the whole `topic.json` in a single shot.
- [x] 4. `AssetAgent` rescoped from `project_id` to `topic_id`; mechanics (tag-match search, explicit-pick
  override, fallback-to-topic-bank-when-nothing-scores) unchanged.
- [x] 5. `EmailContentAgent` / `WhatsAppContentAgent` rescoped to read `Topic` instead of `ProjectFacts` +
  retrieved brochure chunks; RERA/pricing/possession-date fact-checking dropped since a workshop has none of
  those facts to reproduce.
- [x] 6. New channel: `BrochureContentAgent` (`app/agents/brochure_agent.py`) + `BrochureRenderer`
  (`app/rendering/brochure_renderer.py`). The LLM writes only Hero/Hook/Closing copy; Modules, Methodology,
  Outcomes, and Positioning Tags are copied verbatim from `Topic` and rendered via a fixed Jinja2 template
  (`app/rendering/templates/brochure.html`) through headless Chromium (Playwright) to PDF + PNG.
- [x] 7. `Orchestrator` (`app/agents/orchestrator.py`) extended from a 2-channel to a 3-channel `StateGraph`:
  Topic + Asset agents still fan out from `START` in parallel and join, then fan back into whichever of
  `email_content`/`whatsapp_content`/`brochure_content` the request's briefs actually asked for.
- [x] 8. `ComplianceAgent` rescoped: the old guaranteed-returns / RERA-disclaimer / price-mismatch checks are
  replaced by an unverifiable-outcome-claim check against `Topic.outcomes`, plus channel-specific checks —
  HTML validity for email, character limit for WhatsApp, and (new) brand-consistency + one-page-overflow checks
  for brochure.
- [x] 9. `ContentLibraryAgent` + `ContentLibraryStore` + FastAPI endpoints extended with
  `POST /content-library/brochure` and a `BrochureFileStore` that persists a saved brochure's PDF/PNG as real
  files on disk (draft previews stay ephemeral base64 in the response and are never written to disk).
- [x] 10. Frontend: `TopicGate` replaces the old project picker as the hard gate before anything else renders;
  `ChannelPickerModal` gained a third "Brochure" option; `GenerateWorkspace` gained `BrochurePreview` (PNG page
  preview + Download PDF/PNG); `ArchitectureModal`'s diagram was redrawn node-for-node to match the new pipeline
  shape (Topic Gate → Brief → Orchestrator → Topic Context + Assets → Content → Compliance → Library).
- [x] 11. Fly.io deployment retargeted: `data/topics` replaces `data/projects` as the seeded volume directory,
  `TOPIC_DATA_PATH`/`BROCHURE_FILES_PATH`/`TRAINER_NAME`/`TRAINER_CONTACT` replace the old project-facts env
  vars, no `PINECONE_*` secrets are needed anywhere, and the Docker image now installs headless Chromium
  (`playwright install --with-deps chromium`) with the Fly VM's memory bumped accordingly.
- [ ] Not carried over / not yet done: `InsightsAgent` (`GET /insights`) still only covers Email and WhatsApp —
  Brochure isn't part of the composition-analytics dashboard yet. The `Purpose` enum
  (`app/models/brief.py`) also still has a leftover `payment_possession_reminder` option from the real-estate
  version's picklist; it's harmless (no agent branches on it) but doesn't mean anything for a workshop and
  should eventually be pruned from the form.

## Why it's structured this way

- **No RAG, deliberately.** `TopicContextAgent` reads one JSON file and returns it — full stop. The real-estate
  version needed retrieval because a project's brochure prose was too long to put in every prompt and had to be
  chunked/embedded/searched; a workshop topic's modules, methodology, and outcomes are already short, structured,
  and *complete* — there's nothing to retrieve because there's no larger corpus behind them. `Topic` (`app/models/
  topic.py`) says this directly in its docstring: it's not split into "facts" + "retrieved chunks" the way the
  real-estate version was, because the whole record already is the complete context a content agent needs.
- **Structured facts are still reproduced exactly, just from a smaller source.** `BrochureContentAgent` never
  lets the LLM touch Modules/Methodology/Outcomes/Positioning Tags — those come straight from `Topic` into
  `BrochureContent`, unedited, the same "don't let the model rephrase what must stay exact" principle the
  real-estate version applied to RERA numbers and prices. The LLM's only job on a brochure is the three prose
  spots (hero, hook, closing) that are genuinely meant to vary per campaign.
- **Compliance now checks outcome claims, not price/RERA facts.** `_check_unverifiable_outcome_claims`
  (`compliance_agent.py`) flags absolute language ("guaranteed", "100% results", "will definitely") *unless*
  `Topic.outcomes` itself makes an equally strong claim — same shape as the old guaranteed-returns check, just
  re-pointed at a workshop's outcomes instead of a project's disclosed returns. There's no more RERA-disclaimer
  auto-fix or price/date-mismatch check, because a workshop brochure has no regulatory number or possession date
  to get wrong.
- **The self-closed-tag HTML bug fix is still load-bearing.** `_TagBalanceChecker.handle_startendtag` still
  no-ops instead of using `HTMLParser`'s default behavior, which calls both `handle_starttag` *and*
  `handle_endtag` for a self-closed tag like `<br/>` and would otherwise flag every one as an unmatched close.
  This wasn't touched in the domain transform because the underlying `HTMLParser` behavior it works around has
  nothing to do with real estate vs. workshops — it's a general email-HTML-validation fix that's still correct
  here.
- **Brochure rendering is deterministic, not an LLM step.** `BrochureRenderer.render()` loads the assembled HTML
  into one headless Chromium page and takes *both* the PDF and the PNG from that same loaded page
  (`page.pdf()` then `page.screenshot()`), so the two exports are pixel-identical to each other by construction —
  there's no risk of the PDF and the on-screen preview drifting apart. The page size is a fixed A4-at-96dpi pixel
  box (`794×1123`, not `format: "A4"`) for the same reason: an explicit pixel size is what makes the PDF match
  the PNG screenshot exactly, and overflow detection (`scroll_height > PAGE_HEIGHT + 2`) only makes sense against
  a fixed, known page size.
- **A brochure's binary files are only ever written to disk at save time.** `BrochureDraft.pdf_base64`/
  `png_base64` are the ephemeral preview payload, regenerated on every `generate`/`revise` call and discarded if
  the user never saves. `BrochureFileStore.persist()` only runs from `ContentLibraryAgent.save()`, writing one
  PDF + one PNG per `creative_id` and swapping the base64 blobs in `content_json` for `pdf_url`/`png_url` — same
  reasoning as `LocalAssetStore`: a binary artifact belongs in a file with a URL, not crammed into a SQLite TEXT
  column, and a draft nobody saved shouldn't leave files behind either.
- **The Orchestrator's fan-out/fan-in shape didn't change, it just grew a third branch.** `_route_channels`
  still reads `request.email_brief`/`whatsapp_brief`/`brochure_brief is not None` to decide which content nodes
  run — adding Brochure meant adding `brochure_content → brochure_compliance → brochure_library` as a third
  independent chain off the same `join` node, not restructuring the graph. A rejected brochure still shows up as
  a status note with its issue codes, exactly like a rejected email or WhatsApp draft.
- **Brochure compliance checks things email/WhatsApp compliance never needed to.** `_check_brand_consistency`
  is brochure-only: it warns (not blocks) when `Settings.trainer_name`/`trainer_contact` aren't configured, or
  configured but not actually present in the rendered HTML footer — the one place this app enforces "does this
  actually say whose workshop it is." `_check_brochure_overflow` is also brochure-only, and it's the one
  *blocking* Brochure-specific check: content that doesn't fit the fixed one-page layout has to be shortened
  and regenerated, since there's no scroll/pagination in a one-page brochure export.
- **`BrochureBrief` is an empty marker model on purpose.** Its only job is to exist or not exist on
  `CampaignRequest`, the same convention `EmailBrief`/`WhatsAppBrief` already used for "which channels run."
  It carries zero fields because the brochure template is fixed and everything besides Hero/Hook/Closing comes
  straight from `Topic` — there's nothing left for a user to configure per-brochure the way email has
  length/imagery or WhatsApp has cta/image requirements.
- **The topic ingestion CLI is one LLM call, not a pipeline.** `topic_ingest.py` takes a zip containing one
  source doc (a curriculum outline, a proposal deck exported to text, workshop notes) and any number of past-run
  photos, extracts the doc's text, and asks Gemini for the whole structured `Topic` shape in one
  `generate_json` call — no chunking, no per-section calls, no embeddings. Photos are copied into
  `data/assets/{topic_id}/photos/` and registered in the same `metadata.json` the rest of the asset bank reads,
  keyed off a stable `{topic_id}-photo-{n:02d}` id so re-running ingestion after adding new photos only copies
  what's new rather than re-numbering everything.
- **`get_topic_store()`/`TopicStore.list_topics()` only surface topics that have a real `topic.json`.** A bare
  `data/topics/{id}/` directory scaffolded but never ingested shouldn't show up as pickable in `TopicGate` — the
  same "only fully-formed records are usable" rule the old project picker applied to `facts.json`.
- **The trainer's identity is one global setting, not per-topic.** `trainer_name`/`trainer_contact` live on
  `Settings` (`app/config.py`) and get threaded into both `BrochureRenderer` (footer text) and
  `ComplianceAgent.review()` (the brand-consistency check) — this app is scoped to a single trainer running many
  workshop topics, not a multi-tenant platform, so there's exactly one identity to configure, not one per topic.
- **The Insights dashboard's silence on Brochure is a real gap, not a design choice worth defending.**
  `InsightsAgent.compute()` still only builds `EmailInsights`/`WhatsAppInsights` from the library — a brochure
  entry contributes nothing to the composition analytics on the homepage. Extending it (brochure count, average
  hook-line length, positioning-tag frequency, hero-photo usage rate) would follow the exact same pattern as the
  other two, it just hasn't been done.

### Brief schema (`app/models/brief.py`)

The Orchestrator's entry point is `CampaignRequest { topic_id, campaign_id, campaign_brief, email_brief?,
whatsapp_brief?, brochure_brief? }`. `campaign_brief` (`purpose`, `key_message`, `cta_text`, `audience_tone`) is
shared across every channel; each channel brief holds only what's unique to that channel — `EmailBrief.length`/
`imagery`/`selected_asset_ids`, `WhatsAppBrief.cta_required`/`image_required`/`secondary_cta_text`/
`selected_asset_id`, and `BrochureBrief` (no fields at all). Which channels run is implied by which briefs are
present — there's no separate `channels` list, so "email_brief is set but email shouldn't run" isn't a state
that can exist; `CampaignRequest.channels` is a derived property, not stored input.

### Generate / review / revise / save workflow

Nothing lands in the content library just because content was generated. `POST /campaigns/run` (the original
one-shot endpoint) still generates *and* saves in a single call and is kept for tests/scripts, but the frontend
doesn't use it. Instead:

1. `POST /campaigns/generate` — runs Topic Context + Asset agents in parallel, then the requested content
   agent(s) + Compliance, and returns `{email?, whatsapp?, brochure?: {draft, approved, issues}}`. Nothing is
   persisted.
2. `POST /campaigns/revise/email` / `.../revise/whatsapp` / `.../revise/brochure` — takes the current draft plus
   a plain-language `instruction` ("make it shorter", "lead with module 2"), re-runs that one content agent with
   the current draft and the instruction folded into the prompt, re-checks Compliance, and returns the updated
   draft. Can be called repeatedly. Still nothing is persisted. For Brochure, only the hero/hook/closing fields
   are shown to the model as "current draft" — Modules/Methodology/Outcomes/Positioning Tags are never part of
   what a revision instruction can touch.
3. `POST /content-library/email` / `.../whatsapp` / `.../brochure` — the only endpoints that write to the
   library. Take whatever draft the caller currently has (original or revised) plus a required `template_name`
   and `content_tag`, and save it — for Brochure this is also the point where the PDF/PNG get written to real
   files via `BrochureFileStore`.

On the frontend, `GenerateWorkspace` owns the whole flow on one screen per channel: the brief form on the left
(the `+ New Content` flow starts with `ChannelPickerModal`, since content is generated for exactly one channel
at a time), and the live preview (`EmailPreview` / `WhatsAppPreview` / `BrochurePreview`) on the right with a
"Refine this content" box (revise) and "Save as Draft" / "Save to Library" buttons (save) once a draft exists. A
blocking compliance issue disables "Save to Library" until a revision resolves it — for Brochure, that's
almost always the one-page overflow check. `campaign_id` is generated client-side
(`camp-<timestamp>-<random>`) rather than asked for, since it only exists to group saved content.

### The Brochure channel

Brochure is the one genuinely new channel, not a rescoped copy of Email/WhatsApp — it's the only channel with a
deterministic rendering step after the LLM call, and the only one that produces real binary files.

- **What the LLM writes vs. what's fixed.** `BrochureContentAgent` prompts Gemini for exactly five fields —
  `hero_title`, `hero_tagline`, `hero_description`, `hook_lines` (2-3 lines), `closing_line` — grounded in
  `TOPIC CONTENT` and the campaign brief. Everything else in the rendered page (Modules, Methodology, Outcomes,
  Positioning Tags) is copied verbatim from `Topic` into `BrochureContent` in code, never sent through the model.
- **Rendering.** `BrochureRenderer` fills `app/rendering/templates/brochure.html` (Jinja2, autoescaped) with the
  assembled `BrochureContent` plus `trainer_name`/`trainer_contact` and an optional hero photo (the first
  candidate asset, if any were found), then drives headless Chromium via Playwright's sync API to produce both a
  PDF (`page.pdf()`) and a PNG (`page.screenshot()`) from that one loaded page, at a fixed 794×1123px (A4 @
  96dpi) page size.
- **Overflow is a blocking compliance issue, not a rendering error.** If the rendered content's
  `scrollHeight` exceeds the fixed page height (past a small sub-pixel tolerance), `BrochureDraft.overflowed`
  is set and `ComplianceAgent._check_brochure_overflow` blocks the save — the fix is always "shorten the
  hero/hook/closing copy and regenerate," since Modules/Methodology/Outcomes are fixed-length by definition
  (whatever the topic actually has).
- **Preview vs. saved state.** A live (unsaved) draft carries `pdf_base64`/`png_base64` directly in the API
  response; `BrochurePreview.jsx` renders the PNG as a `data:` URL and downloads either format from that base64
  via a `Blob`. Once saved, `content_json` instead has `pdf_url`/`png_url` pointing at real files served from
  `GET /brochure-files/{topic_id}/{creative_id}.pdf|.png` — the same component renders either shape, branching
  only on whether `png_base64` is present.
- **No per-channel settings.** `BrochureBrief` carries no fields, so the "Brochure settings" section of the New
  Content form doesn't exist — the form just shows a hint that Modules/Methodology/Outcomes come straight from
  the topic and there's nothing else to configure.
- **Template IDs.** Saved brochures get a `BR####`/`BR#####` `template_id` (`ContentLibraryStore
  ._TEMPLATE_ID_PREFIXES`), alongside `E####` for email and `WA####` for WhatsApp, so a card's channel is
  readable at a glance without opening it.
- **Not yet wired into Insights.** `GET /insights` only computes `EmailInsights`/`WhatsAppInsights` — a saved
  brochure doesn't move any number on the homepage dashboard yet.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt   # includes requirements.txt (fastapi, langgraph, playwright, ...) + pytest
playwright install chromium           # one-time: `pip install playwright` only installs the driver, not the
                                       # browser binary itself -- brochure PDF/PNG rendering needs this too
cp .env.example .env                  # fill in GEMINI_API_KEY when ready; TRAINER_NAME/TRAINER_CONTACT for the
                                       # brochure footer; GMAIL_ADDRESS/GMAIL_APP_PASSWORD only if you want
                                       # the "Send Email" feature
```

## Run tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

## Ingest a topic's content (one-time, per topic)

```bash
python -m app.ingest.topic_ingest --topic-id comm-impact --zip-path data/incoming/comm-impact.zip
```

The zip must contain exactly one source document (`.pdf`/`.txt`/`.md` — a curriculum outline, a proposal deck
exported to text, workshop notes) plus any number of photos (`.jpg`/`.jpeg`/`.png`/`.webp`/`.gif`) from past
runs of the workshop. One Gemini call extracts the whole structured shape (`topic_name`, `tagline`,
`hook_description`, numbered `modules`, `methodology`, `outcomes`, `closing_line`, `positioning_tags`) and writes
it to `data/topics/{topic_id}/topic.json`; photos get copied into `data/assets/{topic_id}/photos/` and
registered in that topic's `metadata.json`, ready for the Asset agent to search. Pass `--topic-name` to override
the LLM-extracted name. There's no separate facts file and no indexing step — `topic.json` is the whole source
of truth a content agent reads.

Re-running ingestion (e.g. after adding new photos) is safe: previously-copied photos are skipped by their
stable `{topic_id}-photo-{n}` id, but `topic.json` itself is fully overwritten from the new extraction each time
— don't hand-edit fields in it that you want to survive a re-ingest.

## Run the API

```bash
source venv/bin/activate
uvicorn app.api.main:app --port 8123
```

- `POST /campaigns/run` — one-shot generate + save (used by tests/scripts; the frontend uses the split flow below)
- `POST /campaigns/generate` — generate drafts for the requested channels, does not save
- `POST /campaigns/revise/email`, `.../revise/whatsapp`, `.../revise/brochure` — revise a draft from a
  plain-language instruction, does not save
- `POST /campaigns/generate-more-subject-lines` — append more email subject-line options without touching the
  rest of the draft
- `POST /content-library/email`, `.../whatsapp`, `.../brochure` — save a draft to the library, returns
  `{creative_id}` (brochure also persists the PDF/PNG to disk at this point)
- `GET /content-library/{creative_id}` — fetch one entry
- `PATCH /content-library/{creative_id}` — rename `template_name`
- `DELETE /content-library/{creative_id}` — delete an entry
- `GET /content-library/{creative_id}/sends` — email send history for one entry
- `GET /content-library?topic_id=...&channel=...` — list/filter entries
- `GET /topics` — list ingested topics (only ones with a real `topic.json`)
- `GET /assets?topic_id=...` — resolve `asset_id` -> real URL (content-library entries only store IDs)
- `GET /insights?topic_id=...` — composition analytics (Email + WhatsApp only)
- `GET /usage`, `PUT /usage/cap` — Gemini call tracking / daily cap
- `POST /send-email` — send a rendered email via Gmail SMTP
- `POST /assets/generated`, `POST /assets/suggest-overlay-text` — image editor save + AI overlay-text suggestions

## Run the browse UI

```bash
cd frontend
npm install
npm run dev   # http://localhost:5174, expects the API on :8123
```

Every screen is gated behind picking a topic first (`TopicGate`) — the homepage, browse library, insights, and
usage tabs all scope their data to exactly one `topic_id`. "+ New Content" opens a channel picker (Email /
WhatsApp / Brochure — one channel per generation), then the single-screen generate/preview/revise/save
workspace described above.

## Deploying (Fly.io)

The app is stateful (SQLite files + the asset bank + persisted brochure PDFs/PNGs all live on local disk under
`data/`), so it needs a real persistent disk, not a serverless/stateless host. `Dockerfile` builds one container
that serves both the API and the built React frontend from the same origin, and also installs headless Chromium
at build time (`playwright install --with-deps chromium`) since `BrochureRenderer` needs it at runtime; `fly.toml`
attaches a persistent volume at `/app/data` and sets the VM's memory to `1024mb` (bumped from what the API alone
needed) to give headless Chromium enough headroom. `docker-entrypoint.sh` seeds that volume with the demo
topic content and sample assets (`data/topics`, `data/assets`) from the image the first time the volume is
empty, and never touches it again after that.

```bash
# one-time
curl -L https://fly.io/install.sh | sh
fly auth login

# from the repo root
fly apps create sakshi-dua-content-agent   # pick a different name if taken; update fly.toml's `app =` line to match
fly volumes create data --size 1 --region sin   # match fly.toml's primary_region

fly secrets set \
  GEMINI_API_KEY=... \
  TRAINER_NAME=... \
  TRAINER_CONTACT=... \
  GMAIL_ADDRESS=... \
  GMAIL_APP_PASSWORD=... \
  API_PUBLIC_BASE_URL=https://sakshi-dua-content-agent.fly.dev   # your actual app URL

fly deploy
```

No `PINECONE_*` secrets are needed — there's no vector store anywhere in this version. `fly deploy` builds
remotely (no local Docker install needed). `API_PUBLIC_BASE_URL` matters because `LocalAssetStore` and
`BrochureFileStore` both use it to build the absolute URLs the frontend loads asset/brochure files from — left
at its `http://127.0.0.1:8123` default, images and brochure downloads would be broken in production even though
the API itself works fine. Re-run `fly deploy` for any future code change; the volume (and everything on it) is
untouched by that.

## Note on Python version

This machine only has Python 3.9.6 available (no 3.10+, no pyenv/brew found). Pydantic models here use
`typing.Optional`/`typing.Union` instead of the `X | None` operator syntax for that reason — functionally
identical, just 3.9-compatible. (Built-in generics like `list[str]`/`dict[str, Any]` are fine as-is on 3.9 via
PEP 585 — it's only the `|`-union syntax that needs 3.10+.) If a newer Python becomes available later this isn't
worth changing.
