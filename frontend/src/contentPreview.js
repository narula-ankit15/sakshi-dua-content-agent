function stripHtml(html) {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

const CONTENT_TAG_LABELS = {
  service: "Service",
  promotional_communication: "Promotional Communication",
};

export function contentTagLabel(entry) {
  return CONTENT_TAG_LABELS[entry.content_tag] || null;
}

export function previewTitle(entry) {
  if (entry.channel === "email") {
    return entry.content_json.subject_lines?.[0] || "(no subject)";
  }
  if (entry.channel === "brochure") {
    return entry.content_json.content?.hero_title || "Workshop brochure";
  }
  return entry.content_json.cta_variants?.[0] || entry.content_json.cta || "WhatsApp message";
}

export function previewBody(entry) {
  if (entry.channel === "email") {
    return stripHtml(entry.content_json.html_body || "");
  }
  if (entry.channel === "brochure") {
    return entry.content_json.content?.hero_tagline || "";
  }
  // Backward compatible with older saved entries that only had message_text.
  return entry.content_json.message_variants?.[0] || entry.content_json.message_text || "";
}
