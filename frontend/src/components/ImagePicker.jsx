import { useEffect, useRef, useState } from "react";
import { uploadAsset } from "../api";

// maxImages=1 (WhatsApp's single image_asset_id) swaps the selection on
// click instead of filling up slots -- disabling every other thumbnail
// once one is picked would be a worse single-select UX than letting a
// new click just replace the old pick.
//
// topicId/onUploaded are optional -- pass both to let the user add their
// own photo straight from this picker; the new asset is handed back via
// onUploaded so the caller can merge it into its asset list and, if it
// wants, auto-select it.
//
// hintOverride replaces the default "first pick becomes the main image"
// copy -- needed wherever that framing doesn't fit (e.g. an email layout
// with no hero slot at all, where every pick is an equal-weight item).
export default function ImagePicker({ assets, selectedIds, onChange, maxImages = 4, topicId, onUploaded, hintOverride }) {
  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  // { assetId, x, y } while a right-click menu is open, else null.
  const [contextMenu, setContextMenu] = useState(null);

  function toggle(assetId) {
    if (selectedIds.includes(assetId)) {
      onChange(selectedIds.filter((id) => id !== assetId));
      return;
    }
    if (maxImages === 1) {
      onChange([assetId]);
      return;
    }
    if (selectedIds.length < maxImages) {
      onChange([...selectedIds, assetId]);
    }
  }

  // Reordering to the front (not just toggling in/out) is the whole point --
  // without this, swapping which photo is the hero meant unselecting
  // everything and re-picking in the right order.
  function setAsMain(assetId) {
    setContextMenu(null);
    if (maxImages === 1) {
      onChange([assetId]);
      return;
    }
    const rest = selectedIds.filter((id) => id !== assetId);
    // Already at the cap and adding a new (previously unselected) image --
    // bump the current last pick to make room rather than silently no-op.
    const capped = rest.length >= maxImages ? rest.slice(0, maxImages - 1) : rest;
    onChange([assetId, ...capped]);
  }

  function handleContextMenu(e, assetId) {
    if (maxImages === 1) return; // only one slot -- nothing to "make main"
    e.preventDefault();
    setContextMenu({ assetId, x: e.clientX, y: e.clientY });
  }

  useEffect(() => {
    if (!contextMenu) return;
    function close(e) {
      // A click *inside* the menu (i.e. the "Set as main image" button
      // itself) must be left alone -- closing here first would race with
      // that button's own onClick reading stale (already-nulled) state.
      if (e.target.closest && e.target.closest(".image-picker__context-menu")) return;
      setContextMenu(null);
    }
    function closeOnEscape(e) {
      if (e.key === "Escape") setContextMenu(null);
    }
    // Capture phase so this fires before the click that opened a *different*
    // thumbnail's menu, and so a click anywhere (including other thumbs)
    // closes the currently-open one first.
    document.addEventListener("click", close, true);
    document.addEventListener("contextmenu", close, true);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("click", close, true);
      document.removeEventListener("contextmenu", close, true);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [contextMenu]);

  async function handleFileSelected(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // lets the same file be picked again later if needed
    if (!file || !topicId) return;
    setUploading(true);
    setUploadError(null);
    try {
      const asset = await uploadAsset(topicId, file, ["uploaded"]);
      onUploaded?.(asset);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  }

  const hint =
    assets.length === 0
      ? null
      : hintOverride !== undefined
        ? hintOverride
        : maxImages === 1
          ? selectedIds.length === 0
            ? "Optional -- pick one image, or leave blank and the AI will choose."
            : "1 selected -- clear it to let the AI choose instead."
          : selectedIds.length === 0
            ? `Optional -- pick up to ${maxImages} images, or leave blank and the AI will choose. The first pick becomes the main image, the rest appear smaller below it. Right-click any photo to make it the main one instead.`
            : `${selectedIds.length} selected -- "Main" is the hero image, the rest appear smaller below it. Right-click a photo to make it the main one.`;

  return (
    <div className="image-picker">
      {topicId && (
        <div className="image-picker__upload">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="image-picker__upload-input"
            onChange={handleFileSelected}
            disabled={uploading}
          />
          <button
            type="button"
            className="btn btn--ghost image-picker__upload-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? "Uploading…" : "⬆ Upload a photo"}
          </button>
          <span className="image-picker__upload-hint">
            Landscape or square photos at least 800×800px work best.
          </span>
        </div>
      )}
      {uploadError && <p className="state-message state-message--error">{uploadError}</p>}

      {assets.length > 0 && (
        <>
          <div className="image-picker__grid">
            {assets.map((asset) => {
              const order = selectedIds.indexOf(asset.asset_id);
              const selected = order !== -1;
              return (
                <button
                  key={asset.asset_id}
                  type="button"
                  className={`image-picker__thumb ${selected ? "image-picker__thumb--selected" : ""}`}
                  onClick={() => toggle(asset.asset_id)}
                  onContextMenu={(e) => handleContextMenu(e, asset.asset_id)}
                  disabled={!selected && maxImages > 1 && selectedIds.length >= maxImages}
                  title={asset.tags?.join(", ")}
                >
                  <img src={asset.url} alt="" />
                  {asset.width && asset.height && (
                    <span className="image-picker__dims-badge">
                      {asset.width}×{asset.height}
                    </span>
                  )}
                  {asset.tags?.includes("ai_generated_hero") && (
                    <span className="image-picker__ai-badge" title="Previously AI-generated -- free to reuse">
                      AI
                    </span>
                  )}
                  {selected && (
                    <span className="image-picker__badge">
                      {maxImages === 1 ? "Selected" : order === 0 ? "Main" : order + 1}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          {hint && <p className="image-picker__hint">{hint}</p>}
        </>
      )}

      {contextMenu && (
        <div
          className="image-picker__context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button type="button" onClick={() => setAsMain(contextMenu.assetId)}>
            ★ Set as main image
          </button>
        </div>
      )}
    </div>
  );
}
