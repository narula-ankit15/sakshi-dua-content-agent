function base64ToBlob(base64, mime) {
  const byteChars = atob(base64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
  return new Blob([new Uint8Array(byteNumbers)], { type: mime });
}

function triggerDownload(href, filename) {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// A live (unsaved) draft carries the PDF/PNG as base64 -- the ephemeral
// preview payload. A saved library entry's content_json has pdf_url/png_url
// instead (see ContentLibraryAgent.save / BrochureFileStore), pointing at
// files actually written to disk. Same component renders either shape.
export default function BrochurePreview({ draft, topicName }) {
  const isLive = !!draft.png_base64;
  const pngSrc = isLive ? `data:image/png;base64,${draft.png_base64}` : draft.png_url;
  const slug =
    (topicName || "brochure")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "brochure";

  function handleDownload(kind) {
    if (isLive) {
      const base64 = kind === "pdf" ? draft.pdf_base64 : draft.png_base64;
      const mime = kind === "pdf" ? "application/pdf" : "image/png";
      const blob = base64ToBlob(base64, mime);
      const url = URL.createObjectURL(blob);
      triggerDownload(url, `${slug}.${kind}`);
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } else {
      const href = kind === "pdf" ? draft.pdf_url : draft.png_url;
      window.open(href, "_blank", "noopener");
    }
  }

  return (
    <div className="brochure-preview">
      {draft.overflowed && (
        <div className="state-message state-message--error">
          Content overflows the fixed one-page layout — shorten the hero/hook/closing copy and regenerate.
        </div>
      )}
      <div className="brochure-preview__page">
        <img src={pngSrc} alt="Brochure preview" />
      </div>
      <div className="brochure-preview__actions">
        <button type="button" className="btn btn--ghost" onClick={() => handleDownload("pdf")}>
          Download PDF ⬇
        </button>
        <button type="button" className="btn btn--ghost" onClick={() => handleDownload("png")}>
          Download PNG ⬇
        </button>
      </div>
    </div>
  );
}
