import { useEffect, useState } from "react";
import EmailPreview from "./EmailPreview";
import WhatsAppPreview from "./WhatsAppPreview";
import BrochurePreview from "./BrochurePreview";
import SubjectLinePicker from "./SubjectLinePicker";
import CtaPicker from "./CtaPicker";
import KeyMessageField from "./KeyMessageField";
import ImagePicker from "./ImagePicker";
import ImageEditor from "./ImageEditor";
import {
  generateCampaign,
  generateMoreSubjectLines,
  listAssets,
  listTopics,
  reviseBrochure,
  reviseEmail,
  reviseWhatsapp,
  saveBrochure,
  saveEmail,
  saveWhatsapp,
  updateBrochure,
  updateEmail,
  updateWhatsapp,
} from "../api";

const PURPOSE_OPTIONS = [
  { value: "product_announcement", label: "Product Announcement" },
  { value: "newsletter", label: "Newsletter" },
  { value: "promo_sale", label: "Promo / Sale" },
  { value: "event_invite", label: "Event Invite" },
  { value: "welcome_onboarding", label: "Welcome / Onboarding" },
  { value: "transactional_receipt", label: "Transactional Receipt" },
  { value: "follow_up_nudge", label: "Follow-up Nudge" },
  { value: "payment_possession_reminder", label: "Payment / Possession Reminder" },
  { value: "other", label: "Other" },
];

const AUDIENCE_TONE_OPTIONS = [
  { value: "consumers_casual", label: "Consumers - Casual" },
  { value: "consumers_premium", label: "Consumers - Premium" },
  { value: "b2b_professional", label: "B2B - Professional" },
  { value: "internal_team", label: "Internal Team" },
  { value: "community_newsletter", label: "Community Newsletter" },
];

const EMAIL_LENGTH_OPTIONS = [
  { value: "short", label: "Short" },
  { value: "medium", label: "Medium" },
  { value: "long", label: "Long" },
];

const EMAIL_IMAGERY_OPTIONS = [
  { value: "text_only", label: "Text only" },
  { value: "placeholder_blocks", label: "Placeholder image blocks" },
  { value: "use_asset_bank", label: "Hero image + photo gallery" },
];

const HERO_IMAGE_SOURCE_OPTIONS = [
  { value: "selected_photo", label: "Choose from photos" },
  { value: "ai_generated", label: "Generate with AI" },
];

// Mirrors app/models/brief.py's EMAIL_LAYOUT_SPECS -- an optional
// pre-built structure the user can pick before generating (each is a fixed
// HTML template, not something the AI freely designs), so the exact number
// of image slots and their recommended dimensions are known up front.
const EMAIL_LAYOUT_OPTIONS = [
  {
    value: "hero_three_column",
    label: "Hero + 3-Column",
    description: "Full-width hero photo, then 3 captioned photos side by side, each with its own optional button.",
    heroRequired: true,
    itemCount: 3,
    itemsOptional: false,
    heroDims: "wide banner, at least 1200×600px",
    itemDims: "square, at least 800×800px",
  },
  {
    value: "event",
    label: "Event",
    description: "Dark date-bar header, hero photo, then 3 photos -- built for save-the-date and event invites.",
    heroRequired: true,
    itemCount: 3,
    itemsOptional: false,
    heroDims: "wide banner, at least 1200×600px",
    itemDims: "square, at least 800×800px",
  },
  {
    value: "minimal_announcement",
    label: "Minimal Announcement",
    description: "No hero photo -- two large equal-weight photos bookend a short, punchy announcement.",
    heroRequired: false,
    itemCount: 2,
    itemsOptional: false,
    heroDims: "",
    itemDims: "wide, at least 1200×600px",
  },
  {
    value: "welcome_grid",
    label: "Welcome Grid",
    description: "Hero photo up top, then a clean 2×2 grid of 4 captioned photos below.",
    heroRequired: true,
    itemCount: 4,
    itemsOptional: false,
    heroDims: "wide banner, at least 1200×600px",
    itemDims: "square, at least 800×800px",
  },
  {
    value: "workshop_highlights",
    label: "Workshop Highlights",
    description:
      "Hero photo, a stat strip, and your workshop's modules/methodology pulled in automatically, plus an optional photo gallery.",
    heroRequired: true,
    itemCount: 3,
    itemsOptional: true,
    heroDims: "wide banner, at least 1200×600px",
    itemDims: "square, at least 600×600px (optional gallery photos)",
  },
];

const WHATSAPP_LENGTH_OPTIONS = [
  { value: "short", label: "Short (under 150 chars)" },
  { value: "standard", label: "Standard (under 300 chars)" },
];

const CONTENT_TAG_OPTIONS = [
  { value: "service", label: "Service" },
  { value: "promotional_communication", label: "Promotional Communication" },
];

const CHANNEL_LABELS = { email: "Email", whatsapp: "WhatsApp", brochure: "Brochure" };

const BROCHURE_LAYOUT_OPTIONS = [
  { value: "modern_gradient", label: "Modern Gradient" },
  { value: "clean_minimal", label: "Clean Minimal" },
  { value: "bold_geometric", label: "Bold Geometric" },
  { value: "classic_sidebar", label: "Classic Sidebar" },
];

// campaign_id is only used internally to group saved content -- the user
// never needs to see or type it, so generate one instead of asking for it.
function generateCampaignId() {
  return `camp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

// Chip order stays stable while the user is picking -- reordering only
// happens once, right before save, so index 0 (the "primary" subject line
// everywhere else in the app) reflects whichever chip they selected.
function withSelectedFirst(lines, selectedIndex) {
  const copy = [...lines];
  const [chosen] = copy.splice(selectedIndex, 1);
  return [chosen, ...copy];
}

// Entries saved before request_json existed have nothing to prefill the
// form from -- Edit still needs *some* valid CampaignRequest shape to hand
// to Revise/Save, so this fills in sane defaults rather than leaving them
// blank and breaking those calls.
function fallbackRequestContext(entry) {
  return {
    topic_id: entry.topic_id,
    campaign_id: entry.campaign_id,
    campaign_brief: {
      purpose: "promo_sale",
      purpose_other_description: null,
      key_message: "",
      cta_text: "",
      audience_tone: "consumers_premium",
    },
    email_brief: entry.channel === "email" ? {} : undefined,
    whatsapp_brief: entry.channel === "whatsapp" ? {} : undefined,
    brochure_brief: entry.channel === "brochure" ? {} : undefined,
  };
}

export default function GenerateWorkspace({ channel, onChangeChannel, onDone, editingEntry }) {
  // Stable for this component instance's lifetime -- App.jsx remounts
  // GenerateWorkspace fresh for each edit session, so reading editingEntry
  // straight into lazy useState initializers below is safe and avoids the
  // effect-ordering hazards a delayed prefill-on-mount effect would have
  // (e.g. racing the "clear stale picks" effects on topicId/emailLayout).
  const editReq = editingEntry?.request_json || null;
  const editCb = editReq?.campaign_brief || null;
  const editChannelBrief = editReq?.[`${editingEntry?.channel}_brief`] || null;
  const [topics, setTopics] = useState([]);
  const [topicId, setTopicId] = useState(() => editingEntry?.topic_id || "");
  const topicName = topics.find((t) => t.topic_id === topicId)?.topic_name || "";

  const [templateName, setTemplateName] = useState(() => editingEntry?.template_name || "");
  const [contentTag, setContentTag] = useState(() => editingEntry?.content_tag || "promotional_communication");
  const [purpose, setPurpose] = useState(() => editCb?.purpose || "promo_sale");
  const [purposeOtherDescription, setPurposeOtherDescription] = useState(() => editCb?.purpose_other_description || "");
  const [keyMessage, setKeyMessage] = useState(() => editCb?.key_message || "");
  const [ctaText, setCtaText] = useState(() => (editingEntry && editingEntry.channel !== "whatsapp" ? editCb?.cta_text || "" : ""));
  const [whatsappCtas, setWhatsappCtas] = useState(() =>
    editingEntry?.channel === "whatsapp" ? [editCb?.cta_text, editChannelBrief?.secondary_cta_text].filter(Boolean) : []
  );
  const [audienceTone, setAudienceTone] = useState(() => editCb?.audience_tone || "consumers_premium");

  const [brochureLayout, setBrochureLayout] = useState(() =>
    editingEntry?.channel === "brochure" ? editChannelBrief?.layout || "modern_gradient" : "modern_gradient"
  );
  const [designSystemId, setDesignSystemId] = useState(() =>
    editingEntry?.channel === "email" ? editChannelBrief?.design_system_id || "" : ""
  );
  const [emailLength, setEmailLength] = useState(() =>
    editingEntry?.channel === "email" ? editChannelBrief?.length || "medium" : "medium"
  );
  const [emailImagery, setEmailImagery] = useState(() =>
    editingEntry?.channel === "email" ? editChannelBrief?.imagery || "use_asset_bank" : "use_asset_bank"
  );
  // Picking a structure is optional in spirit -- this default (the richest,
  // most-tested layout) means a user who never opens the picker still gets
  // a sensible, working email.
  const [emailLayout, setEmailLayout] = useState(() =>
    editingEntry?.channel === "email" ? editChannelBrief?.layout || "workshop_highlights" : "workshop_highlights"
  );
  const emailLayoutSpec = EMAIL_LAYOUT_OPTIONS.find((opt) => opt.value === emailLayout) || EMAIL_LAYOUT_OPTIONS[4];
  // Defaults to reusing/selecting a photo, not AI generation -- generating
  // costs a real paid API call, so it should be an explicit choice.
  const [heroImageSource, setHeroImageSource] = useState(() =>
    editingEntry?.channel === "email" ? editChannelBrief?.hero_image_source || "selected_photo" : "selected_photo"
  );
  const [selectedAssetIds, setSelectedAssetIds] = useState(() =>
    editingEntry?.channel === "email" || editingEntry?.channel === "brochure"
      ? editChannelBrief?.selected_asset_ids || []
      : []
  );

  const [whatsappCtaRequired, setWhatsappCtaRequired] = useState(() =>
    editingEntry?.channel === "whatsapp" ? (editChannelBrief?.cta_required ?? true) : true
  );
  const [whatsappImageRequired, setWhatsappImageRequired] = useState(() =>
    editingEntry?.channel === "whatsapp" ? (editChannelBrief?.image_required ?? true) : true
  );
  const [whatsappLength, setWhatsappLength] = useState(() =>
    editingEntry?.channel === "whatsapp" ? editChannelBrief?.length || "standard" : "standard"
  );
  const [whatsappSelectedAssetId, setWhatsappSelectedAssetId] = useState(() =>
    editingEntry?.channel === "whatsapp" ? editChannelBrief?.selected_asset_id || "" : ""
  );

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const [requestContext, setRequestContext] = useState(() =>
    editingEntry ? editReq || fallbackRequestContext(editingEntry) : null
  );
  const [draftState, setDraftState] = useState(() =>
    editingEntry
      ? {
          draft: editingEntry.content_json,
          approved: true,
          issues: [],
          instruction: "",
          revising: false,
          savingAs: null,
          error: null,
          creativeId: editingEntry.creative_id,
          savedStatus: editingEntry.status,
          justSaved: false,
        }
      : null
  );
  const [assetsById, setAssetsById] = useState({});
  // AI-generated hero images are saved into the same asset bank as real
  // workshop photos and are deliberately kept pickable here -- reselecting
  // a previous generation (instead of generating a new one) costs nothing.
  // ImagePicker flags them with an "AI" badge so they're easy to tell apart
  // from real photos.
  const pickableAssets = Object.values(assetsById);
  const [selectedSubjectIndex, setSelectedSubjectIndex] = useState(0);
  const [generatingMoreSubjects, setGeneratingMoreSubjects] = useState(false);
  const [showImageEditor, setShowImageEditor] = useState(false);

  // Same shape as the campaign_brief sent to /campaigns/generate -- reused
  // here so the image editor's "Suggest text with AI" has the same context
  // (purpose/key message/tone) the content agents get, without waiting for
  // an actual generation to happen first.
  function currentCampaignBrief() {
    return {
      purpose,
      purpose_other_description: purpose === "other" ? purposeOtherDescription.trim() || "Custom" : null,
      key_message: keyMessage.trim() || "Promote this workshop",
      cta_text: (channel === "whatsapp" ? whatsappCtas[0] : ctaText.trim()) || "Learn more",
      audience_tone: audienceTone,
    };
  }

  function handleImageTemplateCreated(asset) {
    setAssetsById((prev) => ({ ...prev, [asset.asset_id]: asset }));
    if (channel === "whatsapp") {
      setWhatsappSelectedAssetId(asset.asset_id);
    } else {
      const cap =
        channel === "email"
          ? emailLayoutSpec.itemCount + (emailLayoutSpec.heroRequired && heroImageSource === "selected_photo" ? 1 : 0)
          : 4;
      setSelectedAssetIds((prev) => (prev.length < cap ? [...prev, asset.asset_id] : prev));
    }
    setShowImageEditor(false);
  }

  useEffect(() => {
    let cancelled = false;
    listTopics()
      .then((list) => {
        if (cancelled) return;
        setTopics(list);
        if (list.length) setTopicId((prev) => (prev && list.some((t) => t.topic_id === prev) ? prev : list[0].topic_id));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // Fetched by topicId so the image picker has thumbnails to show before
    // the user has generated anything yet.
    if (!topicId) return;
    listAssets(topicId)
      .then((assets) => setAssetsById(Object.fromEntries(assets.map((a) => [a.asset_id, a]))))
      .catch(() => setAssetsById({}));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId]);

  useEffect(() => {
    // Asset picks are topic-specific -- clear them if the user switches
    // topics so a stale asset_id from another topic's bank can't leak in.
    setSelectedAssetIds([]);
    setWhatsappSelectedAssetId("");
  }, [topicId]);

  useEffect(() => {
    // Each email layout wants a different number of image slots -- clear
    // picks on layout change so a selection sized for one layout doesn't
    // silently overflow or under-fill a different one.
    setSelectedAssetIds([]);
  }, [emailLayout]);

  async function handleGenerate(e) {
    e.preventDefault();
    setFormError(null);

    const primaryCta = channel === "whatsapp" ? whatsappCtas[0] || "" : ctaText.trim();
    if (!topicId || !templateName.trim() || !keyMessage.trim() || !primaryCta) {
      setFormError(
        channel === "whatsapp"
          ? "Topic, Template Name, Key Message, and at least one CTA are required."
          : "Topic, Template Name, Key Message, and CTA Text are required."
      );
      return;
    }
    if (purpose === "other" && !purposeOtherDescription.trim()) {
      setFormError("Please describe the purpose when 'Other' is selected.");
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        campaign_id: generateCampaignId(),
        topic_id: topicId,
        campaign_brief: {
          purpose,
          purpose_other_description: purpose === "other" ? purposeOtherDescription.trim() : null,
          key_message: keyMessage.trim(),
          cta_text: primaryCta,
          audience_tone: audienceTone,
        },
        email_brief:
          channel === "email"
            ? {
                design_system_id: designSystemId.trim() || null,
                length: emailLength,
                imagery: emailImagery,
                layout: emailLayout,
                hero_image_source: heroImageSource,
                selected_asset_ids: selectedAssetIds,
              }
            : undefined,
        whatsapp_brief:
          channel === "whatsapp"
            ? {
                cta_required: whatsappCtaRequired,
                image_required: whatsappImageRequired,
                length: whatsappLength,
                secondary_cta_text: whatsappCtas[1] || null,
                selected_asset_id: whatsappSelectedAssetId || null,
              }
            : undefined,
        brochure_brief:
          channel === "brochure" ? { layout: brochureLayout, selected_asset_ids: selectedAssetIds } : undefined,
      };
      const drafts = await generateCampaign(payload);
      const result = drafts[channel];
      await refreshAssetsForHeroImage();
      setRequestContext(payload);
      setSelectedSubjectIndex(0);
      setDraftState({
        draft: result.draft,
        approved: result.approved,
        issues: result.issues,
        instruction: "",
        revising: false,
        savingAs: null,
        error: null,
        creativeId: null,
        savedStatus: null,
      });
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  function updateDraftState(patch) {
    setDraftState((prev) => ({ ...prev, ...patch }));
  }

  // Email generate/revise can create a brand-new AI hero image asset on the
  // server (see HeroImageAgent) -- the draft only carries its asset_id
  // (via the asset://{id} placeholder scheme), so the preview can't resolve
  // it to a real URL until assetsById is refreshed to include it.
  async function refreshAssetsForHeroImage() {
    if (channel !== "email" || !topicId) return;
    try {
      const assets = await listAssets(topicId);
      setAssetsById(Object.fromEntries(assets.map((a) => [a.asset_id, a])));
    } catch {
      // Non-fatal -- the draft itself already generated successfully; a
      // failed asset refresh just means the hero image won't preview until
      // the next natural refetch (e.g. switching topics and back).
    }
  }

  async function handleRevise() {
    if (!draftState.instruction.trim()) return;
    updateDraftState({ revising: true, error: null });
    try {
      const revise = channel === "email" ? reviseEmail : channel === "whatsapp" ? reviseWhatsapp : reviseBrochure;
      const briefKey =
        channel === "email" ? "email_brief" : channel === "whatsapp" ? "whatsapp_brief" : "brochure_brief";
      const payload = {
        topic_id: requestContext.topic_id,
        campaign_brief: requestContext.campaign_brief,
        [briefKey]: requestContext[briefKey],
        current_draft: draftState.draft,
        instruction: draftState.instruction.trim(),
      };
      const result = await revise(payload);
      await refreshAssetsForHeroImage();
      setSelectedSubjectIndex(0);
      updateDraftState({
        draft: result.draft,
        approved: result.approved,
        issues: result.issues,
        instruction: "",
        revising: false,
        justSaved: false,
      });
    } catch (err) {
      updateDraftState({ revising: false, error: err.message });
    }
  }

  async function handleGenerateMoreSubjectLines() {
    setGeneratingMoreSubjects(true);
    try {
      const result = await generateMoreSubjectLines({
        topic_id: requestContext.topic_id,
        campaign_brief: requestContext.campaign_brief,
        existing_subject_lines: draftState.draft.subject_lines,
      });
      updateDraftState({
        draft: { ...draftState.draft, subject_lines: [...draftState.draft.subject_lines, ...result.subject_lines] },
      });
    } catch (err) {
      updateDraftState({ error: err.message });
    } finally {
      setGeneratingMoreSubjects(false);
    }
  }

  async function handleSave(asDraft) {
    updateDraftState({ savingAs: asDraft ? "draft" : "approved", error: null, justSaved: false });
    try {
      const draftToSave =
        channel === "email"
          ? { ...draftState.draft, subject_lines: withSelectedFirst(draftState.draft.subject_lines, selectedSubjectIndex) }
          : draftState.draft;
      const payload = {
        topic_id: requestContext.topic_id,
        campaign_id: requestContext.campaign_id,
        draft: draftToSave,
        template_name: templateName.trim(),
        content_tag: contentTag,
        as_draft: asDraft,
        // Stored alongside the content so a saved draft can be reopened via
        // Edit later and land back on this same form, prefilled.
        request_json: requestContext,
      };
      let result;
      if (editingEntry) {
        const update = channel === "email" ? updateEmail : channel === "whatsapp" ? updateWhatsapp : updateBrochure;
        result = await update(editingEntry.creative_id, payload);
      } else {
        const save = channel === "email" ? saveEmail : channel === "whatsapp" ? saveWhatsapp : saveBrochure;
        result = await save(payload);
      }
      updateDraftState({
        savingAs: null,
        creativeId: result.creative_id,
        savedStatus: asDraft ? "draft" : "approved",
        justSaved: true,
      });
    } catch (err) {
      updateDraftState({ savingAs: null, error: err.message });
    }
  }

  const blockingIssues = draftState?.issues.filter((i) => i.severity === "blocking") || [];
  const warningIssues = draftState?.issues.filter((i) => i.severity === "warning") || [];

  // How many picker slots this layout needs, and what the picker's hint
  // text should say -- both depend on whether the layout has a hero slot
  // at all, and (when it does) whether the hero comes from a pick here or
  // from AI generation instead.
  const emailImageMaxSlots =
    emailLayoutSpec.itemCount + (emailLayoutSpec.heroRequired && heroImageSource === "selected_photo" ? 1 : 0);
  const emailImagePickerHint = !emailLayoutSpec.heroRequired
    ? selectedAssetIds.length === 0
      ? `Optional -- pick up to ${emailLayoutSpec.itemCount} images (${emailLayoutSpec.itemDims}), or leave blank and the AI will choose. This layout has no hero photo -- pick order sets position in the layout. Right-click a photo to move it first.`
      : `${selectedAssetIds.length} selected -- pick order sets position in the layout (no hero photo here). Right-click a photo to move it first.`
    : heroImageSource === "ai_generated"
      ? selectedAssetIds.length === 0
        ? `Optional -- pick up to ${emailLayoutSpec.itemCount} gallery photos (${emailLayoutSpec.itemDims}), or leave blank and the AI will choose. The hero banner is generated separately.`
        : `${selectedAssetIds.length} selected as gallery photos. The hero banner is generated separately.`
      : selectedAssetIds.length === 0
        ? `Optional -- pick up to ${emailImageMaxSlots} images, or leave blank and the AI will choose. The first pick becomes the hero (${emailLayoutSpec.heroDims}), the rest fill this layout's ${emailLayoutSpec.itemCount} photo slot${emailLayoutSpec.itemCount === 1 ? "" : "s"} (${emailLayoutSpec.itemDims}). Right-click any photo to make it the hero instead.`
        : `${selectedAssetIds.length} selected -- "Main" is the hero image, the rest fill this layout's photo slots. Right-click a photo to make it the hero.`;

  return (
    <div className="workspace">
      <div className="workspace__col workspace__col--form">
        <div className="campaign-form__channel-banner">
          {editingEntry ? "Editing" : "Creating"} <strong>{CHANNEL_LABELS[channel]}</strong> content
          {!editingEntry && (
            <button type="button" className="campaign-form__change-channel" onClick={onChangeChannel}>
              Change channel
            </button>
          )}
        </div>

        <form className="campaign-form" onSubmit={handleGenerate}>
          <div className="campaign-form__field">
            <label className="filter-bar__label">
              Topic<span className="required">*</span>
            </label>
            <select className="filter-bar__input" value={topicId} onChange={(e) => setTopicId(e.target.value)}>
              {topics.length === 0 && <option value="">Loading topics&hellip;</option>}
              {topics.map((t) => (
                <option key={t.topic_id} value={t.topic_id}>
                  {t.topic_name}
                </option>
              ))}
            </select>
          </div>

          <div className="campaign-form__field">
            <label className="filter-bar__label">
              Template Name<span className="required">*</span>
            </label>
            <input
              className="filter-bar__input"
              placeholder="Eg: March Cohort Launch"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
            />
          </div>

          <div className="campaign-form__field">
            <label className="filter-bar__label">
              Content Tag<span className="required">*</span>
            </label>
            <select className="filter-bar__input" value={contentTag} onChange={(e) => setContentTag(e.target.value)}>
              {CONTENT_TAG_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <h4 className="campaign-form__section-title">Campaign brief</h4>

          <div className="campaign-form__row">
            <div className="campaign-form__field">
              <label className="filter-bar__label">
                Purpose<span className="required">*</span>
              </label>
              <select className="filter-bar__input" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                {PURPOSE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="campaign-form__field">
              <label className="filter-bar__label">
                Audience / Tone<span className="required">*</span>
              </label>
              <select
                className="filter-bar__input"
                value={audienceTone}
                onChange={(e) => setAudienceTone(e.target.value)}
              >
                {AUDIENCE_TONE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {purpose === "other" && (
            <div className="campaign-form__field">
              <label className="filter-bar__label">
                Describe the purpose<span className="required">*</span>
              </label>
              <input
                className="filter-bar__input"
                placeholder="Eg: post-visit survey follow-up"
                value={purposeOtherDescription}
                onChange={(e) => setPurposeOtherDescription(e.target.value)}
              />
            </div>
          )}

          <div className="campaign-form__field">
            <label className="filter-bar__label">
              Key Message<span className="required">*</span>
            </label>
            <KeyMessageField value={keyMessage} onChange={setKeyMessage} />
          </div>

          <div className="campaign-form__field">
            <label className="filter-bar__label">
              CTA Text<span className="required">*</span>
            </label>
            {channel === "whatsapp" ? (
              <CtaPicker onChange={setWhatsappCtas} initialCtas={whatsappCtas} />
            ) : (
              <input
                className="filter-bar__input"
                placeholder="Eg: Reserve your seat"
                value={ctaText}
                onChange={(e) => setCtaText(e.target.value)}
              />
            )}
          </div>

          <h4 className="campaign-form__section-title">{CHANNEL_LABELS[channel]} settings</h4>

          {channel === "email" && (
            <div className="campaign-form__channel-panel">
              <p className="campaign-form__hint">
                Picking a structure is optional -- it's a fixed HTML template, so the number of image
                slots (and their recommended dimensions) are known up front.
              </p>
              <div className="campaign-form__field">
                <label className="filter-bar__label">Layout</label>
                <div className="layout-picker">
                  {EMAIL_LAYOUT_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      className={
                        "layout-picker__option" + (emailLayout === opt.value ? " layout-picker__option--selected" : "")
                      }
                      onClick={() => setEmailLayout(opt.value)}
                    >
                      <span className="layout-swatch email-layout-swatch">
                        {opt.heroRequired && <span className="email-layout-swatch__hero" />}
                        <span className="email-layout-swatch__items">
                          {Array.from({ length: opt.itemCount }).map((_, i) => (
                            <span key={i} className="email-layout-swatch__item" />
                          ))}
                        </span>
                      </span>
                      <span className="layout-picker__label">{opt.label}</span>
                      <span className="layout-picker__tooltip" role="tooltip">
                        {opt.description}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="campaign-form__row">
                <div className="campaign-form__field">
                  <label className="filter-bar__label">Length</label>
                  <select
                    className="filter-bar__input"
                    value={emailLength}
                    onChange={(e) => setEmailLength(e.target.value)}
                  >
                    {EMAIL_LENGTH_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="campaign-form__field">
                  <label className="filter-bar__label">Imagery</label>
                  <select
                    className="filter-bar__input"
                    value={emailImagery}
                    onChange={(e) => setEmailImagery(e.target.value)}
                  >
                    {EMAIL_IMAGERY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {emailImagery === "use_asset_bank" && (
                <>
                  {emailLayoutSpec.heroRequired && (
                    <div className="campaign-form__field">
                      <label className="filter-bar__label">Hero image</label>
                      <div className="segmented-control">
                        {HERO_IMAGE_SOURCE_OPTIONS.map((opt) => (
                          <button
                            key={opt.value}
                            type="button"
                            className={`segmented-control__option ${heroImageSource === opt.value ? "segmented-control__option--active" : ""}`}
                            onClick={() => setHeroImageSource(opt.value)}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="campaign-form__field">
                    <div className="image-picker__header">
                      <label className="filter-bar__label">
                        {emailLayoutSpec.heroRequired
                          ? heroImageSource === "ai_generated"
                            ? "Choose gallery photos (optional)"
                            : "Choose photos (optional)"
                          : emailLayoutSpec.itemsOptional
                            ? "Choose photos (optional)"
                            : "Choose photos"}
                      </label>
                      <button type="button" className="btn btn--ghost image-picker__create-btn" onClick={() => setShowImageEditor(true)}>
                        🖉 Create image template
                      </button>
                    </div>
                    <ImagePicker
                      assets={pickableAssets}
                      selectedIds={selectedAssetIds}
                      onChange={setSelectedAssetIds}
                      maxImages={emailImageMaxSlots}
                      topicId={topicId}
                      onUploaded={handleImageTemplateCreated}
                      hintOverride={emailImagePickerHint}
                    />
                  </div>
                </>
              )}

              <div className="campaign-form__field">
                <label className="filter-bar__label">Design System ID (optional)</label>
                <input
                  className="filter-bar__input"
                  placeholder="Eg: brand-template-2026"
                  value={designSystemId}
                  onChange={(e) => setDesignSystemId(e.target.value)}
                />
              </div>
            </div>
          )}

          {channel === "whatsapp" && (
            <div className="campaign-form__channel-panel">
              <div className="campaign-form__row">
                <label className="campaign-form__checkbox">
                  <input
                    type="checkbox"
                    checked={whatsappCtaRequired}
                    onChange={(e) => setWhatsappCtaRequired(e.target.checked)}
                  />
                  Include a CTA
                </label>
                <label className="campaign-form__checkbox">
                  <input
                    type="checkbox"
                    checked={whatsappImageRequired}
                    onChange={(e) => setWhatsappImageRequired(e.target.checked)}
                  />
                  Include an image
                </label>
              </div>
              <div className="campaign-form__field">
                <label className="filter-bar__label">Length</label>
                <select
                  className="filter-bar__input"
                  value={whatsappLength}
                  onChange={(e) => setWhatsappLength(e.target.value)}
                >
                  {WHATSAPP_LENGTH_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {whatsappImageRequired && (
                <div className="campaign-form__field">
                  <div className="image-picker__header">
                    <label className="filter-bar__label">Choose image (optional)</label>
                    <button type="button" className="btn btn--ghost image-picker__create-btn" onClick={() => setShowImageEditor(true)}>
                      🖉 Create image template
                    </button>
                  </div>
                  <ImagePicker
                    assets={pickableAssets}
                    selectedIds={whatsappSelectedAssetId ? [whatsappSelectedAssetId] : []}
                    onChange={(ids) => setWhatsappSelectedAssetId(ids[0] || "")}
                    maxImages={1}
                    topicId={topicId}
                    onUploaded={handleImageTemplateCreated}
                  />
                </div>
              )}
            </div>
          )}

          {channel === "brochure" && (
            <div className="campaign-form__channel-panel">
              <p className="campaign-form__hint">
                The brochure uses a fixed one-page template — its Modules, Methodology, and Outcomes sections come
                straight from this topic's content. The layout and photos are yours to pick.
              </p>
              <div className="campaign-form__field">
                <label className="filter-bar__label">Layout</label>
                <div className="layout-picker">
                  {BROCHURE_LAYOUT_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      className={
                        "layout-picker__option" +
                        (brochureLayout === opt.value ? " layout-picker__option--selected" : "")
                      }
                      onClick={() => setBrochureLayout(opt.value)}
                    >
                      <span className={`layout-swatch layout-swatch--${opt.value}`}>
                        <span className="layout-swatch__block layout-swatch__block--a" />
                        <span className="layout-swatch__block layout-swatch__block--b" />
                        <span className="layout-swatch__block layout-swatch__block--c" />
                      </span>
                      <span className="layout-picker__label">{opt.label}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="campaign-form__field">
                <div className="image-picker__header">
                  <label className="filter-bar__label">Choose photos (optional)</label>
                  <button type="button" className="btn btn--ghost image-picker__create-btn" onClick={() => setShowImageEditor(true)}>
                    🖉 Create image template
                  </button>
                </div>
                <ImagePicker
                  assets={pickableAssets}
                  selectedIds={selectedAssetIds}
                  onChange={setSelectedAssetIds}
                  topicId={topicId}
                  onUploaded={handleImageTemplateCreated}
                />
              </div>
            </div>
          )}

          {showImageEditor && (
            <ImageEditor
              topicId={topicId}
              assets={pickableAssets}
              campaignBrief={currentCampaignBrief()}
              onClose={() => setShowImageEditor(false)}
              onCreated={handleImageTemplateCreated}
            />
          )}

          {formError && <div className="state-message state-message--error">{formError}</div>}

          <button className="btn btn--cta campaign-form__submit" type="submit" disabled={submitting}>
            {submitting ? "Generating…" : draftState ? "Regenerate Content" : "Generate Content"}
          </button>
        </form>
      </div>

      <div className="workspace__col workspace__col--preview">
        {submitting && (
          <div className="workspace__loading">
            <span className="workspace__spinner" />
            Generating your {CHANNEL_LABELS[channel]} content&hellip;
          </div>
        )}

        {!submitting && !draftState && (
          <div className="workspace__empty">
            Fill in the form and click <strong>Generate Content</strong> to see the {CHANNEL_LABELS[channel]}{" "}
            preview here.
          </div>
        )}

        {!submitting && draftState && (
          <div className="review-drafts__panel">
            {blockingIssues.length > 0 && (
              <div className="state-message state-message--error">
                Not approved yet — {blockingIssues.map((i) => i.message).join("; ")}
              </div>
            )}
            {warningIssues.length > 0 && (
              <div className="review-drafts__warning">{warningIssues.map((i) => i.message).join("; ")}</div>
            )}

            {channel === "email" && (
              <>
                <SubjectLinePicker
                  subjectLines={draftState.draft.subject_lines}
                  selectedIndex={selectedSubjectIndex}
                  onSelect={setSelectedSubjectIndex}
                  onGenerateMore={handleGenerateMoreSubjectLines}
                  generating={generatingMoreSubjects}
                />
                <EmailPreview
                  subjectLines={draftState.draft.subject_lines}
                  selectedSubjectIndex={selectedSubjectIndex}
                  htmlBody={draftState.draft.html_body}
                  assetsById={assetsById}
                  creativeId={draftState.creativeId}
                  onHtmlChange={(html) =>
                    updateDraftState({ draft: { ...draftState.draft, html_body: html }, justSaved: false })
                  }
                />
              </>
            )}
            {channel === "whatsapp" && (
              <WhatsAppPreview
                draft={draftState.draft}
                imageUrl={draftState.draft.image_asset_id ? assetsById?.[draftState.draft.image_asset_id]?.url : null}
                businessName={topicName}
              />
            )}
            {channel === "brochure" && <BrochurePreview draft={draftState.draft} topicName={topicName} />}

            <div className="review-drafts__refine">
              <label className="filter-bar__label">Refine this content</label>
              <textarea
                className="filter-bar__input campaign-form__textarea"
                placeholder="Eg: make it shorter, add more urgency, mention module 2 first"
                value={draftState.instruction}
                onChange={(e) => updateDraftState({ instruction: e.target.value })}
              />
              <div className="review-drafts__actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={handleRevise}
                  disabled={draftState.revising || !draftState.instruction.trim()}
                >
                  {draftState.revising ? "Revising…" : "Revise"}
                </button>
                {draftState.creativeId && !editingEntry ? (
                  <span className="review-drafts__saved">
                    Saved{draftState.savedStatus === "draft" ? " as draft" : ""}: {draftState.creativeId}
                  </span>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => handleSave(true)}
                      disabled={draftState.savingAs !== null}
                    >
                      {draftState.savingAs === "draft" ? "Saving…" : editingEntry ? "Update Draft" : "Save as Draft"}
                    </button>
                    <button
                      type="button"
                      className="btn btn--cta"
                      onClick={() => handleSave(false)}
                      disabled={draftState.savingAs !== null || blockingIssues.length > 0}
                      title={
                        blockingIssues.length > 0
                          ? "Resolve the blocking issue(s) above, or save as a draft instead"
                          : undefined
                      }
                    >
                      {draftState.savingAs === "approved"
                        ? "Saving…"
                        : editingEntry
                          ? "Update & Approve"
                          : "Save to Library"}
                    </button>
                    {editingEntry && draftState.justSaved && (
                      <span className="review-drafts__saved">✓ Changes saved</span>
                    )}
                  </>
                )}
              </div>
              {draftState.error && <div className="state-message state-message--error">{draftState.error}</div>}
            </div>

            {draftState.creativeId && (
              <button type="button" className="new-content-btn" onClick={onDone}>
                Done
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
