import { useState } from "react";

// WhatsApp's own bold markdown -- *word* -- isn't real markdown anywhere else
// in this app, so it has to be parsed by hand to actually render bold here.
function formatWhatsAppText(text) {
  return text.split(/(\*[^*\n]+\*)/g).map((part, i) => {
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
      return <strong key={i}>{part.slice(1, -1)}</strong>;
    }
    return part;
  });
}

export default function WhatsAppPreview({ draft, imageUrl, businessName = "Business" }) {
  // Backward compatible with older saved entries that only ever had a
  // single `message_text` field, before message_variants existed.
  const variants = draft.message_variants?.length ? draft.message_variants : [draft.message_text || ""];
  // Backward compatible with older saved entries that had a single shared
  // `cta` string instead of one CTA per variant.
  const ctaVariants = draft.cta_variants?.length ? draft.cta_variants : draft.cta ? [draft.cta] : [];
  const [selected, setSelected] = useState(0);
  const activeIndex = Math.min(selected, variants.length - 1);
  const activeVariant = variants[activeIndex];
  const activeCta = ctaVariants[Math.min(activeIndex, ctaVariants.length - 1)];

  const now = new Date();
  const time = now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

  return (
    <div className="wa-preview">
      {variants.length > 1 && (
        <div className="wa-variant-tabs">
          {variants.map((_, i) => (
            <button
              key={i}
              type="button"
              className={`wa-variant-tab ${selected === i ? "wa-variant-tab--active" : ""}`}
              onClick={() => setSelected(i)}
            >
              Option {i + 1}
            </button>
          ))}
        </div>
      )}

      <div className="wa-phone">
        <div className="wa-phone__header">
          <div className="wa-phone__avatar">{businessName.charAt(0).toUpperCase()}</div>
          <div className="wa-phone__header-text">
            <div className="wa-phone__name">{businessName}</div>
            <div className="wa-phone__status">business account</div>
          </div>
        </div>

        <div className="wa-phone__body">
          <div className="wa-bubble">
            {draft.image_asset_id && imageUrl && <img className="wa-bubble__image" src={imageUrl} alt="" />}
            <div className="wa-bubble__text">{formatWhatsAppText(activeVariant)}</div>
            <div className="wa-bubble__meta">
              {time} <span className="wa-bubble__ticks">✓✓</span>
            </div>
          </div>
          {activeCta && (
            <button className="wa-cta-button" type="button">
              {activeCta}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
