import { useEffect, useRef, useState } from "react";
import { saveGeneratedAsset, suggestOverlayText } from "../api";

const MAX_CANVAS_WIDTH = 560;
const COLOR_OPTIONS = ["#ffffff", "#000000", "#facc15", "#ef4444", "#22c55e", "#4f46e5"];

// `google` is the fonts.googleapis.com family spec for that font; system
// fonts (no `google` key) need no network fetch and render immediately.
const FONT_OPTIONS = [
  { label: "Arial", family: "Arial" },
  { label: "Georgia", family: "Georgia" },
  { label: "Times New Roman", family: "'Times New Roman'" },
  { label: "Verdana", family: "Verdana" },
  { label: "Impact", family: "Impact" },
  { label: "Playfair Display", family: "'Playfair Display'", google: "Playfair+Display:wght@400;700" },
  { label: "Lato", family: "Lato", google: "Lato:wght@400;700" },
  { label: "Montserrat", family: "Montserrat", google: "Montserrat:wght@400;700" },
  { label: "Merriweather", family: "Merriweather", google: "Merriweather:wght@400;700" },
  { label: "Oswald", family: "Oswald", google: "Oswald:wght@400;700" },
  { label: "Open Sans", family: "'Open Sans'", google: "Open+Sans:wght@400;700" },
  { label: "Poppins", family: "Poppins", google: "Poppins:wght@400;700" },
  { label: "Roboto", family: "Roboto", google: "Roboto:wght@400;700" },
  { label: "Bebas Neue", family: "'Bebas Neue'", google: "Bebas+Neue" },
  { label: "Nunito Sans", family: "'Nunito Sans'", google: "Nunito+Sans:wght@400;700" },
  { label: "Cormorant Garamond", family: "'Cormorant Garamond'", google: "Cormorant+Garamond:wght@400;700" },
  { label: "Karla", family: "Karla", google: "Karla:wght@400;700" },
];

// Curated heading+body pairs (the kind of combo a design tool's font-pairing
// picker suggests) -- picking one drops in two ready-made text elements, a
// heading and a body line, each already set to its side of the pair.
const FONT_PAIRINGS = [
  { label: "Playfair Display + Lato", heading: "'Playfair Display'", body: "Lato" },
  { label: "Montserrat + Merriweather", heading: "Montserrat", body: "Merriweather" },
  { label: "Oswald + Open Sans", heading: "Oswald", body: "'Open Sans'" },
  { label: "Poppins + Roboto", heading: "Poppins", body: "Roboto" },
  { label: "Bebas Neue + Nunito Sans", heading: "'Bebas Neue'", body: "'Nunito Sans'" },
  { label: "Cormorant Garamond + Karla", heading: "'Cormorant Garamond'", body: "Karla" },
];

let googleFontsLoaded = false;
function ensureGoogleFontsLoaded() {
  if (googleFontsLoaded) return;
  googleFontsLoaded = true;
  const families = FONT_OPTIONS.filter((f) => f.google)
    .map((f) => f.google)
    .join("&family=");
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = `https://fonts.googleapis.com/css2?family=${families}&display=swap`;
  document.head.appendChild(link);
}
ensureGoogleFontsLoaded();

async function ensureFontsLoaded(elements) {
  const specs = new Set(
    elements
      .filter((el) => el.type !== "shape")
      .map((el) => `${el.type === "button" || el.bold ? "bold " : ""}${el.fontSize}px ${el.fontFamily}`)
  );
  await Promise.all([...specs].map((spec) => document.fonts.load(spec).catch(() => {})));
}

function roundRectPath(ctx, x, y, w, h, r) {
  const radius = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

// Center point + size in canvas px, for hit-testing and drawing -- computed
// the same way regardless of whether the caller is checking a click or
// painting a frame, so the visible box always matches the clickable box.
function elementBox(ctx, canvas, el) {
  const cx = el.xPct * canvas.width;
  const cy = el.yPct * canvas.height;
  if (el.type === "shape") {
    return { cx, cy, w: el.widthPct * canvas.width, h: el.heightPct * canvas.height };
  }
  if (el.type === "button") {
    ctx.font = `bold ${el.fontSize}px ${el.fontFamily}`;
    const textW = ctx.measureText(el.text).width;
    return { cx, cy, w: textW + 48, h: el.fontSize + 28 };
  }
  ctx.font = `${el.bold ? "bold " : ""}${el.fontSize}px ${el.fontFamily}`;
  const textW = ctx.measureText(el.text).width;
  return { cx, cy, w: textW + 16, h: el.fontSize + 16 };
}

// Shared by the live canvas (selectedId set, draws the dashed selection
// outline) and the export path (selectedId omitted) -- keeping one draw
// routine means the exported PNG can't drift from what the editor rendered,
// and never picks up the selection-outline artifact.
function drawScene(ctx, canvas, image, elements, selectedId) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  elements.forEach((el) => {
    const { cx, cy, w, h } = elementBox(ctx, canvas, el);
    if (el.type === "shape") {
      ctx.save();
      ctx.globalAlpha = el.opacity;
      ctx.fillStyle = el.color;
      roundRectPath(ctx, cx - w / 2, cy - h / 2, w, h, el.cornerRadius);
      ctx.fill();
      ctx.restore();
    } else if (el.type === "button") {
      ctx.save();
      ctx.font = `bold ${el.fontSize}px ${el.fontFamily}`;
      roundRectPath(ctx, cx - w / 2, cy - h / 2, w, h, el.style === "pill" ? h / 2 : 10);
      if (el.style === "outline") {
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = el.bgColor;
        ctx.stroke();
        ctx.fillStyle = el.bgColor;
      } else {
        ctx.fillStyle = el.bgColor;
        ctx.fill();
        ctx.fillStyle = el.textColor;
      }
      ctx.fillText(el.text, cx, cy);
      ctx.restore();
    } else {
      ctx.save();
      ctx.font = `${el.bold ? "bold " : ""}${el.fontSize}px ${el.fontFamily}`;
      ctx.fillStyle = el.color;
      ctx.shadowColor = "rgba(0,0,0,0.45)";
      ctx.shadowBlur = 6;
      ctx.fillText(el.text, cx, cy);
      ctx.restore();
    }
    if (el.id === selectedId) {
      ctx.save();
      ctx.strokeStyle = "#4f46e5";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.strokeRect(cx - w / 2, cy - h / 2, w, h);
      ctx.restore();
    }
  });
}

function drawCropMask(ctx, canvas, rect) {
  ctx.save();
  ctx.fillStyle = "rgba(0,0,0,0.55)";
  ctx.fillRect(0, 0, canvas.width, rect.y);
  ctx.fillRect(0, rect.y + rect.h, canvas.width, canvas.height - (rect.y + rect.h));
  ctx.fillRect(0, rect.y, rect.x, rect.h);
  ctx.fillRect(rect.x + rect.w, rect.y, canvas.width - (rect.x + rect.w), rect.h);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
  const hs = 18;
  ctx.fillStyle = "#4f46e5";
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 1.5;
  [
    [rect.x, rect.y],
    [rect.x + rect.w, rect.y + rect.h],
  ].forEach(([hx, hy]) => {
    ctx.beginPath();
    ctx.arc(hx, hy, hs / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  });
  ctx.restore();
}

function presetCropRect(canvas, ratioW, ratioH) {
  const canvasRatio = canvas.width / canvas.height;
  const targetRatio = ratioW / ratioH;
  let w, h;
  if (targetRatio > canvasRatio) {
    w = canvas.width;
    h = w / targetRatio;
  } else {
    h = canvas.height;
    w = h * targetRatio;
  }
  return { x: (canvas.width - w) / 2, y: (canvas.height - h) / 2, w, h };
}

let nextId = 1;
function makeTextElement(text = "Your text here") {
  return { id: nextId++, type: "text", text, xPct: 0.5, yPct: 0.5, fontFamily: "Arial", fontSize: 36, color: "#ffffff", bold: true };
}
function makeButtonElement() {
  return {
    id: nextId++,
    type: "button",
    text: "Book Now",
    xPct: 0.5,
    yPct: 0.82,
    style: "solid",
    bgColor: "#4f46e5",
    textColor: "#ffffff",
    fontFamily: "Arial",
    fontSize: 20,
  };
}
function makeShapeElement() {
  return { id: nextId++, type: "shape", xPct: 0.5, yPct: 0.5, widthPct: 0.7, heightPct: 0.18, color: "#000000", opacity: 0.45, cornerRadius: 12 };
}

// A plain-image editor: pick a base image from the asset bank, crop it,
// drop text/CTA-button/background-panel elements anywhere on it, then
// flatten to a PNG and save it back into the same asset bank so it
// immediately shows up in ImagePicker.
export default function ImageEditor({ topicId, assets, campaignBrief, onClose, onCreated }) {
  const [baseAsset, setBaseAsset] = useState(null);
  const [image, setImage] = useState(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [elements, setElements] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [cropMode, setCropMode] = useState(false);
  const [cropRect, setCropRect] = useState(null);
  const [fontPairingIndex, setFontPairingIndex] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [suggesting, setSuggesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const canvasRef = useRef(null);
  const dragState = useRef(null);

  useEffect(() => {
    if (!baseAsset) {
      setImage(null);
      return;
    }
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const scale = Math.min(1, MAX_CANVAS_WIDTH / img.naturalWidth);
      setCanvasSize({ width: Math.round(img.naturalWidth * scale), height: Math.round(img.naturalHeight * scale) });
      setImage(img);
    };
    img.onerror = () => setError("Couldn't load that image for editing.");
    img.src = baseAsset.url;
  }, [baseAsset]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !image || !canvasSize.width) return;
    canvas.width = canvasSize.width;
    canvas.height = canvasSize.height;
    const ctx = canvas.getContext("2d");
    let cancelled = false;
    ensureFontsLoaded(elements).then(() => {
      if (cancelled) return;
      drawScene(ctx, canvas, image, elements, selectedId);
      if (cropMode && cropRect) drawCropMask(ctx, canvas, cropRect);
    });
    return () => {
      cancelled = true;
    };
  }, [image, elements, canvasSize, selectedId, cropMode, cropRect]);

  const selectedElement = elements.find((el) => el.id === selectedId) || null;

  function updateSelected(patch) {
    setElements((prev) => prev.map((el) => (el.id === selectedId ? { ...el, ...patch } : el)));
  }

  function addTextElement(text) {
    const el = makeTextElement(text);
    setElements((prev) => [...prev, el]);
    setSelectedId(el.id);
  }

  function addButtonElement() {
    const el = makeButtonElement();
    setElements((prev) => [...prev, el]);
    setSelectedId(el.id);
  }

  function addShapeElement() {
    // Inserted at the front of the array (bottom of the stack) so a
    // newly-added background panel lands behind existing and future text.
    const el = makeShapeElement();
    setElements((prev) => [el, ...prev]);
    setSelectedId(el.id);
  }

  function removeSelected() {
    setElements((prev) => prev.filter((el) => el.id !== selectedId));
    setSelectedId(null);
  }

  function bringToFront() {
    setElements((prev) => {
      const el = prev.find((e) => e.id === selectedId);
      return el ? [...prev.filter((e) => e.id !== selectedId), el] : prev;
    });
  }

  function sendToBack() {
    setElements((prev) => {
      const el = prev.find((e) => e.id === selectedId);
      return el ? [el, ...prev.filter((e) => e.id !== selectedId)] : prev;
    });
  }

  function canvasPointFromEvent(e) {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) * canvas.width) / rect.width,
      y: ((e.clientY - rect.top) * canvas.height) / rect.height,
    };
  }

  function hitTestElement(point) {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    for (let i = elements.length - 1; i >= 0; i--) {
      const el = elements[i];
      const { cx, cy, w, h } = elementBox(ctx, canvas, el);
      if (point.x >= cx - w / 2 && point.x <= cx + w / 2 && point.y >= cy - h / 2 && point.y <= cy + h / 2) {
        return el;
      }
    }
    return null;
  }

  function handleCanvasMouseDown(e) {
    const point = canvasPointFromEvent(e);
    if (cropMode) {
      const rect = cropRect;
      // Generous hit radius (in canvas-internal px, which are already ~1.3-1.8x
      // the on-screen CSS px at this component's display size) -- a tight
      // tolerance here makes the handle nearly unhittable in practice.
      const hs = 28;
      if (Math.abs(point.x - (rect.x + rect.w)) < hs && Math.abs(point.y - (rect.y + rect.h)) < hs) {
        dragState.current = { mode: "crop-resize-br" };
      } else if (Math.abs(point.x - rect.x) < hs && Math.abs(point.y - rect.y) < hs) {
        dragState.current = { mode: "crop-resize-tl" };
      } else if (point.x >= rect.x && point.x <= rect.x + rect.w && point.y >= rect.y && point.y <= rect.y + rect.h) {
        dragState.current = { mode: "crop-move", offsetX: point.x - rect.x, offsetY: point.y - rect.y };
      } else {
        dragState.current = null;
      }
      return;
    }
    const el = hitTestElement(point);
    setSelectedId(el ? el.id : null);
    if (el) {
      const canvas = canvasRef.current;
      dragState.current = {
        mode: "element",
        id: el.id,
        offsetX: point.x - el.xPct * canvas.width,
        offsetY: point.y - el.yPct * canvas.height,
      };
    }
  }

  function handleCanvasMouseMove(e) {
    if (!dragState.current) return;
    const point = canvasPointFromEvent(e);
    const canvas = canvasRef.current;
    const { mode } = dragState.current;
    if (mode === "crop-move") {
      const { offsetX, offsetY } = dragState.current;
      setCropRect((prev) => ({
        ...prev,
        x: clamp(point.x - offsetX, 0, canvas.width - prev.w),
        y: clamp(point.y - offsetY, 0, canvas.height - prev.h),
      }));
    } else if (mode === "crop-resize-br") {
      setCropRect((prev) => ({
        ...prev,
        w: clamp(point.x - prev.x, 40, canvas.width - prev.x),
        h: clamp(point.y - prev.y, 40, canvas.height - prev.y),
      }));
    } else if (mode === "crop-resize-tl") {
      setCropRect((prev) => {
        const newX = clamp(point.x, 0, prev.x + prev.w - 40);
        const newY = clamp(point.y, 0, prev.y + prev.h - 40);
        return { x: newX, y: newY, w: prev.x + prev.w - newX, h: prev.y + prev.h - newY };
      });
    } else if (mode === "element") {
      const { id, offsetX, offsetY } = dragState.current;
      const xPct = clamp((point.x - offsetX) / canvas.width, 0, 1);
      const yPct = clamp((point.y - offsetY) / canvas.height, 0, 1);
      setElements((prev) => prev.map((el) => (el.id === id ? { ...el, xPct, yPct } : el)));
    }
  }

  function handleCanvasMouseUp() {
    dragState.current = null;
  }

  function toggleCropMode() {
    if (cropMode) {
      setCropMode(false);
      setCropRect(null);
    } else {
      setSelectedId(null);
      setCropRect({ x: 0, y: 0, w: canvasSize.width, h: canvasSize.height });
      setCropMode(true);
    }
  }

  function applyCrop() {
    if (!cropRect || !image) return;
    const scale = image.naturalWidth / canvasSize.width;
    const sx = cropRect.x * scale;
    const sy = cropRect.y * scale;
    const sw = cropRect.w * scale;
    const sh = cropRect.h * scale;

    const off = document.createElement("canvas");
    off.width = sw;
    off.height = sh;
    off.getContext("2d").drawImage(image, sx, sy, sw, sh, 0, 0, sw, sh);

    const oldCanvasSize = canvasSize;
    const rect = cropRect;
    const newImg = new Image();
    newImg.onload = () => {
      // Remap element positions from the old canvas's fraction-of-full-image
      // space into the new (cropped) canvas's fraction space, so a text
      // element that was anchored to a feature in the photo stays there
      // instead of drifting when the visible frame changes.
      setElements((prev) =>
        prev.map((el) => {
          const oldCx = el.xPct * oldCanvasSize.width;
          const oldCy = el.yPct * oldCanvasSize.height;
          return { ...el, xPct: (oldCx - rect.x) / rect.w, yPct: (oldCy - rect.y) / rect.h };
        })
      );
      const newScale = Math.min(1, MAX_CANVAS_WIDTH / newImg.naturalWidth);
      setCanvasSize({ width: Math.round(newImg.naturalWidth * newScale), height: Math.round(newImg.naturalHeight * newScale) });
      setImage(newImg);
      setCropMode(false);
      setCropRect(null);
    };
    newImg.src = off.toDataURL("image/png");
  }

  function addPairingTextElements() {
    if (fontPairingIndex === "") return;
    const pairing = FONT_PAIRINGS[fontPairingIndex];
    const heading = {
      id: nextId++,
      type: "text",
      text: "Heading text",
      xPct: 0.5,
      yPct: 0.4,
      fontFamily: pairing.heading,
      fontSize: 44,
      color: "#ffffff",
      bold: true,
    };
    const body = {
      id: nextId++,
      type: "text",
      text: "Body text",
      xPct: 0.5,
      yPct: 0.53,
      fontFamily: pairing.body,
      fontSize: 22,
      color: "#ffffff",
      bold: false,
    };
    setElements((prev) => [...prev, heading, body]);
    setSelectedId(heading.id);
  }

  async function handleSuggest() {
    setSuggesting(true);
    setError(null);
    try {
      const result = await suggestOverlayText({ campaign_brief: campaignBrief });
      setSuggestions(result.suggestions || []);
    } catch (e) {
      setError(e.message || "Couldn't get AI suggestions.");
    } finally {
      setSuggesting(false);
    }
  }

  function applySuggestion(text) {
    if (selectedElement && selectedElement.type === "text") {
      updateSelected({ text });
    } else {
      addTextElement(text);
    }
  }

  async function handleSave() {
    if (!image || !canvasSize.width) return;
    setSaving(true);
    setError(null);
    try {
      // Exported from a fresh offscreen canvas (selectedId omitted) rather
      // than the visible one -- otherwise the dashed selection outline gets
      // baked permanently into the saved PNG.
      await ensureFontsLoaded(elements);
      const exportCanvas = document.createElement("canvas");
      exportCanvas.width = canvasSize.width;
      exportCanvas.height = canvasSize.height;
      drawScene(exportCanvas.getContext("2d"), exportCanvas, image, elements, null);
      const dataUrl = exportCanvas.toDataURL("image/png");
      const asset = await saveGeneratedAsset({ topic_id: topicId, image_base64: dataUrl, tags: ["image-template"] });
      onCreated(asset);
    } catch (e) {
      setError(e.message || "Couldn't save the image template.");
    } finally {
      setSaving(false);
    }
  }

  function renderCommonActions() {
    return (
      <div className="image-editor__control-row">
        <button className="btn btn--ghost" type="button" onClick={bringToFront}>
          ↑ Front
        </button>
        <button className="btn btn--ghost" type="button" onClick={sendToBack}>
          ↓ Back
        </button>
        <button className="btn btn--ghost image-editor__remove" type="button" onClick={removeSelected}>
          Remove
        </button>
      </div>
    );
  }

  function renderTextControls() {
    return (
      <>
        <textarea
          className="campaign-form__textarea image-editor__text-input"
          rows={2}
          value={selectedElement.text}
          onChange={(e) => updateSelected({ text: e.target.value })}
        />
        <div className="image-editor__control-row">
          <select
            className="filter-bar__input"
            value={selectedElement.fontFamily}
            onChange={(e) => updateSelected({ fontFamily: e.target.value })}
          >
            {FONT_OPTIONS.map((f) => (
              <option key={f.label} value={f.family} style={{ fontFamily: f.family }}>
                {f.label}
              </option>
            ))}
          </select>
          <input
            type="number"
            className="filter-bar__input image-editor__font-size"
            value={selectedElement.fontSize}
            min={12}
            max={140}
            onChange={(e) => updateSelected({ fontSize: Number(e.target.value) || 12 })}
          />
        </div>
        <div className="image-editor__control-row">
          {COLOR_OPTIONS.map((c) => (
            <button
              key={c}
              type="button"
              className={`image-editor__swatch ${selectedElement.color === c ? "image-editor__swatch--selected" : ""}`}
              style={{ background: c }}
              onClick={() => updateSelected({ color: c })}
              aria-label={`Set color ${c}`}
            />
          ))}
          <label className="image-editor__bold-toggle">
            <input type="checkbox" checked={selectedElement.bold} onChange={(e) => updateSelected({ bold: e.target.checked })} />
            Bold
          </label>
        </div>
        {renderCommonActions()}
      </>
    );
  }

  function renderButtonControls() {
    return (
      <>
        <input
          className="filter-bar__input"
          value={selectedElement.text}
          onChange={(e) => updateSelected({ text: e.target.value })}
        />
        <div className="image-editor__control-row">
          <select className="filter-bar__input" value={selectedElement.style} onChange={(e) => updateSelected({ style: e.target.value })}>
            <option value="solid">Solid</option>
            <option value="outline">Outline</option>
            <option value="pill">Pill</option>
          </select>
          <select
            className="filter-bar__input"
            value={selectedElement.fontFamily}
            onChange={(e) => updateSelected({ fontFamily: e.target.value })}
          >
            {FONT_OPTIONS.map((f) => (
              <option key={f.label} value={f.family} style={{ fontFamily: f.family }}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
        <div className="image-editor__control-row">
          <span className="image-picker__hint">{selectedElement.style === "outline" ? "Border/text color" : "Button color"}</span>
          {COLOR_OPTIONS.map((c) => (
            <button
              key={c}
              type="button"
              className={`image-editor__swatch ${selectedElement.bgColor === c ? "image-editor__swatch--selected" : ""}`}
              style={{ background: c }}
              onClick={() => updateSelected({ bgColor: c })}
              aria-label={`Set button color ${c}`}
            />
          ))}
        </div>
        {selectedElement.style !== "outline" && (
          <div className="image-editor__control-row">
            <span className="image-picker__hint">Text color</span>
            {["#ffffff", "#000000"].map((c) => (
              <button
                key={c}
                type="button"
                className={`image-editor__swatch ${selectedElement.textColor === c ? "image-editor__swatch--selected" : ""}`}
                style={{ background: c }}
                onClick={() => updateSelected({ textColor: c })}
                aria-label={`Set text color ${c}`}
              />
            ))}
          </div>
        )}
        {renderCommonActions()}
      </>
    );
  }

  function renderShapeControls() {
    return (
      <>
        <div className="image-editor__control-row">
          {["#000000", "#ffffff", "#4f46e5", "#facc15"].map((c) => (
            <button
              key={c}
              type="button"
              className={`image-editor__swatch ${selectedElement.color === c ? "image-editor__swatch--selected" : ""}`}
              style={{ background: c }}
              onClick={() => updateSelected({ color: c })}
              aria-label={`Set panel color ${c}`}
            />
          ))}
        </div>
        <div className="image-editor__control-row">
          <label className="image-editor__bold-toggle">
            Opacity
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              value={selectedElement.opacity}
              onChange={(e) => updateSelected({ opacity: Number(e.target.value) })}
            />
          </label>
          <label className="image-editor__bold-toggle">
            Corners
            <input
              type="number"
              className="filter-bar__input image-editor__font-size"
              min={0}
              max={60}
              value={selectedElement.cornerRadius}
              onChange={(e) => updateSelected({ cornerRadius: Number(e.target.value) || 0 })}
            />
          </label>
        </div>
        <div className="image-editor__control-row">
          <label className="image-editor__bold-toggle">
            Width %
            <input
              type="number"
              className="filter-bar__input image-editor__font-size"
              min={10}
              max={100}
              value={Math.round(selectedElement.widthPct * 100)}
              onChange={(e) => updateSelected({ widthPct: clamp(Number(e.target.value) || 10, 10, 100) / 100 })}
            />
          </label>
          <label className="image-editor__bold-toggle">
            Height %
            <input
              type="number"
              className="filter-bar__input image-editor__font-size"
              min={5}
              max={100}
              value={Math.round(selectedElement.heightPct * 100)}
              onChange={(e) => updateSelected({ heightPct: clamp(Number(e.target.value) || 5, 5, 100) / 100 })}
            />
          </label>
        </div>
        {renderCommonActions()}
      </>
    );
  }

  return (
    <div className="channel-picker-overlay" onClick={onClose}>
      <div className="image-editor-modal" onClick={(e) => e.stopPropagation()}>
        <div className="channel-picker-modal__header">
          <h3>Create image template</h3>
          <button className="detail-panel__close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {!baseAsset ? (
          <>
            <p className="channel-picker-modal__hint">Pick a plain image to add text on top of.</p>
            <div className="image-picker__grid">
              {assets.map((asset) => (
                <button
                  key={asset.asset_id}
                  type="button"
                  className="image-picker__thumb"
                  onClick={() => setBaseAsset(asset)}
                  title={asset.tags?.join(", ")}
                >
                  <img src={asset.url} alt="" />
                </button>
              ))}
            </div>
            {assets.length === 0 && <p className="image-picker__hint">No images in this project's asset bank yet.</p>}
          </>
        ) : (
          <div className="image-editor">
            <div className="image-editor__canvas-wrap">
              <canvas
                ref={canvasRef}
                className={cropMode ? "image-editor__canvas--crop" : ""}
                onMouseDown={handleCanvasMouseDown}
                onMouseMove={handleCanvasMouseMove}
                onMouseUp={handleCanvasMouseUp}
                onMouseLeave={handleCanvasMouseUp}
              />
            </div>

            <div className="image-editor__controls">
              {cropMode ? (
                <>
                  <p className="image-picker__hint">Drag the corner handles or move the box, or pick a preset.</p>
                  <div className="image-editor__control-row">
                    <button
                      className="btn btn--ghost"
                      type="button"
                      onClick={() => setCropRect(presetCropRect(canvasRef.current, 1, 1))}
                    >
                      Square
                    </button>
                    <button
                      className="btn btn--ghost"
                      type="button"
                      onClick={() => setCropRect(presetCropRect(canvasRef.current, 9, 16))}
                    >
                      Story 9:16
                    </button>
                    <button
                      className="btn btn--ghost"
                      type="button"
                      onClick={() => setCropRect({ x: 0, y: 0, w: canvasSize.width, h: canvasSize.height })}
                    >
                      Original
                    </button>
                  </div>
                  <div className="channel-picker-modal__actions">
                    <button className="btn btn--ghost" type="button" onClick={toggleCropMode}>
                      Cancel
                    </button>
                    <button className="btn btn--cta" type="button" onClick={applyCrop}>
                      Apply Crop
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="image-editor__toolbar">
                    <button className="btn btn--ghost" type="button" onClick={() => addTextElement()}>
                      + Text
                    </button>
                    <button className="btn btn--ghost" type="button" onClick={addButtonElement}>
                      + CTA Button
                    </button>
                    <button className="btn btn--ghost" type="button" onClick={addShapeElement}>
                      + Background
                    </button>
                    <button className="btn btn--ghost" type="button" onClick={toggleCropMode}>
                      ✂ Crop
                    </button>
                  </div>

                  <div className="image-editor__control-row">
                    <select
                      className="filter-bar__input"
                      value={fontPairingIndex}
                      onChange={(e) => setFontPairingIndex(e.target.value)}
                    >
                      <option value="">Font pairing…</option>
                      {FONT_PAIRINGS.map((p, i) => (
                        <option key={p.label} value={i}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                    <button className="btn btn--ghost" type="button" onClick={addPairingTextElements} disabled={fontPairingIndex === ""}>
                      + Add heading &amp; body text
                    </button>
                  </div>

                  {selectedElement ? (
                    selectedElement.type === "text" ? (
                      renderTextControls()
                    ) : selectedElement.type === "button" ? (
                      renderButtonControls()
                    ) : (
                      renderShapeControls()
                    )
                  ) : (
                    <p className="image-picker__hint">Add a text, CTA button, or background panel, or click any element on the image to edit it.</p>
                  )}

                  <div className="image-editor__suggest">
                    <button className="btn btn--ghost" type="button" onClick={handleSuggest} disabled={suggesting}>
                      {suggesting ? "Thinking…" : "✨ Suggest text with AI"}
                    </button>
                    {suggestions.length > 0 && (
                      <div className="image-editor__suggestions">
                        {suggestions.map((s, i) => (
                          <button key={i} type="button" className="image-editor__suggestion-chip" onClick={() => applySuggestion(s)}>
                            {s}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {error && <div className="state-message state-message--error">{error}</div>}

                  <div className="channel-picker-modal__actions">
                    <button className="btn btn--ghost" type="button" onClick={() => setBaseAsset(null)}>
                      ← Change base image
                    </button>
                    <button className="btn btn--cta" type="button" onClick={handleSave} disabled={saving}>
                      {saving ? "Saving…" : "Save as image template"}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
